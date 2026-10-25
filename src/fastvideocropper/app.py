"""Native widgets composed around Qt Multimedia and PyQtGraph's ROI."""

import ctypes
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from string import Template

import psutil
import pyqtgraph as pg
import PySide6
import qt_themes
from platformdirs import user_config_path
from PySide6.QtCore import (
    QEvent,
    QObject,
    QProcess,
    QRectF,
    QSettings,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPen,
    QTransform,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsRectItem,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyleOptionSlider,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_VERSION, integrations
from .crops import CropScan
from .encoding import Export, padded_rect, rotate_rect
from .segments import SceneScan, Segment
from .updates import RELEASES_URL, UpdateDialog

RATIOS = {
    "Original": None,
    "Square": 1.0,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "5:4": 5 / 4,
    "4:5": 4 / 5,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
    "2:1": 2.0,
    "1:2": 0.5,
}


class VideoFileDialog(QFileDialog):
    def accept(self):
        # Accept highlighted folders as inputs; double-click still navigates.
        QDialog.accept(self)


class SessionSettings:
    """Preferences kept only in memory for a no-profile session."""

    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value

    def contains(self, key):
        return key in self.values

    def allKeys(self):
        return sorted(self.values)

    def fileName(self):
        return "Session only (-NoProfile; nothing is saved)"

    def sync(self):
        pass


class Application(QObject):
    """Application controller; all visual components are stock or third-party."""

    def __init__(
        self,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        paths=(),
        launcher_module=integrations.APP_MODULE,
        no_profile=False,
    ):
        super().__init__()
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.launcher_module = launcher_module
        if no_profile:
            self.settings = SessionSettings()
        else:
            self.settings = QSettings(
                str(user_config_path(APP_NAME, appauthor=False) / "settings.ini"),
                QSettings.Format.IniFormat,
            )
        self.restart_requested = False
        self.themes = qt_themes.get_themes()
        self.applied_theme = self.settings.value("appearance/theme", "")
        self.applied_icon = self.settings.value("appearance/icon", "blue")
        self.icons = {
            path.stem: QIcon(str(path))
            for path in sorted(Path(__file__).with_name("icons").glob("*.ico"))
        }
        styles = Path(__file__).with_name("styles")
        QApplication.instance().setStyleSheet("")
        if self.applied_theme:
            qt_themes.set_theme(self.themes[self.applied_theme])
        normal_button = QPushButton()
        normal_height = normal_button.sizeHint().height()
        frame_height = 2 * normal_button.style().pixelMetric(
            QStyle.PixelMetric.PM_DefaultFrameWidth, None, normal_button
        )
        base_font_size = QApplication.font().pointSizeF()
        normal_button.deleteLater()
        QApplication.instance().setStyleSheet(
            Template(
                (styles / "components.qss").read_text(encoding="utf-8")
            ).substitute(
                medium_font_size=base_font_size * 1.25,
                medium_height=round(normal_height * 1.5) - frame_height,
                large_font_size=base_font_size * 1.5,
                xlarge_font_size=base_font_size * 2.5,
                large_height=normal_height * 2 - frame_height,
                xlarge_height=normal_height * 3 - frame_height,
            )
        )
        if paths:
            path = Path(paths[0]).resolve()
            self.settings.setValue(
                "folder_path", str(path if path.is_dir() else path.parent)
            )
        self.paths = []
        self.index = -1
        self.done = set()
        self.rotation = 0
        self.width = self.height = 1.0
        self.pixel_width = self.pixel_height = 1.0
        self.ready = False
        self.loading = False
        self.resolving_encoder = False
        self.closing = False
        self.running = False
        self.installing = False
        self.paused = False
        self.outcome = ""
        self.count_action = ""
        self.auto_export_pending = False
        self.output = None
        self.progress_buffer = ""
        self.progress_values = {}
        self.export_log = ""
        self.container_rejected = False
        self.segments = []
        self.source_segments = {}
        self.active_segment = -1
        self.restoring_segment = False
        self.detecting = False
        self.detecting_crop = False
        self.segment_regions = []
        self.export_jobs = []
        self.export_index = 0
        self.window = QMainWindow()
        self.setParent(self.window)
        QApplication.setWindowIcon(self.icons[self.applied_icon])
        self.window.pending_installer = None
        self.update_dialog = UpdateDialog(self.window)
        self.update_dialog.busy_changed.connect(self.update_busy)
        self.update_dialog.install_requested.connect(self.install_update)
        self.window.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.window.resize(1200, 800)
        self.window.setAcceptDrops(True)
        # Auto frame threading can exhaust Qt's audio buffer before a low-FPS
        # video yields its first frame. Keep preview decoding single-threaded.
        [avutil_path] = Path(PySide6.__file__).parent.glob("avutil-*.dll")
        self.avutil = ctypes.CDLL(str(avutil_path))
        self.avutil.av_cpu_force_count.argtypes = [ctypes.c_int]
        self.avutil.av_cpu_force_count.restype = None
        self.avutil.av_cpu_force_count(1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QGraphicsVideoItem()
        # The scene supplies the display aspect, including metadata rotation.
        self.video.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self.player.setVideoOutput(self.video)
        self.process = QProcess(self)
        self.probe = QProcess(self)
        self.probe.finished.connect(self.media_probed)
        self.probe.readyReadStandardError.connect(
            lambda: self.log.appendPlainText(
                bytes(self.probe.readAllStandardError()).decode("utf-8")
            )
        )
        self.probe.errorOccurred.connect(
            lambda _: self.log.appendPlainText(self.probe.errorString())
        )
        self.gpu_probe = QProcess(self)
        self.gpu_probe.finished.connect(self.encoder_probed)
        self.process.readyReadStandardOutput.connect(self.read_progress)
        self.process.readyReadStandardError.connect(self.read_log)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(
            lambda _: self.log.appendPlainText(self.process.errorString())
        )
        self.player.errorOccurred.connect(
            lambda _, text: self.log.appendPlainText(text)
        )
        self.player.errorOccurred.connect(
            lambda _, text: self.window.statusBar().showMessage(text)
        )
        self.player.mediaStatusChanged.connect(
            lambda status: self.log.appendPlainText(f"Playback: {status.name}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self.build_ui()
        if self.settings.contains("mainWindow/geometry"):
            self.window.restoreGeometry(self.settings.value("mainWindow/geometry"))
        if self.settings.contains("mainWindow/state"):
            self.window.restoreState(self.settings.value("mainWindow/state"), 1)
        if self.settings.contains("mainWindow/splitterState"):
            self.splitter.restoreState(self.settings.value("mainWindow/splitterState"))
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.video.videoSink().videoFrameChanged.connect(self.frame_changed)
        self.follow_timer = QTimer(self)
        self.follow_timer.setInterval(500)
        self.follow_timer.timeout.connect(self.follow_progress)
        self.count_timer = QTimer(self)
        self.count_timer.setInterval(1000)
        self.count_timer.timeout.connect(self.count_tick)
        self.load_timer = QTimer(self)
        self.load_timer.setSingleShot(True)
        self.load_timer.timeout.connect(self.complete_load)
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(500)
        self.resize_timer.timeout.connect(self.fit)
        self.window.installEventFilter(self)
        self.seek.installEventFilter(self)
        self.viewport = self.graphics.viewport()
        self.viewport.installEventFilter(self)
        self.files_dock.widget().installEventFilter(self)
        self.file_list.viewport().installEventFilter(self)
        self.update_enabled()
        self.add_paths(paths)

    def button(self, text, slot, layout):
        button = QPushButton(text)
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    def preference(self, text, key, default, form):
        control = QCheckBox(text)
        control.setChecked(self.settings.value(key, default, bool))
        control.toggled.connect(lambda value: self.settings.setValue(key, value))
        form.addRow(control)
        return control

    def build_ui(self):
        menu = self.window.menuBar().addMenu("&File")
        action = QAction("&Open videos…", self)
        action.setShortcut(QKeySequence.StandardKey.Open)
        action.triggered.connect(self.open_files)
        menu.addAction(action)
        quit_action = menu.addAction("&Quit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.window.close)
        segment_menu = self.window.menuBar().addMenu("&Segment")
        self.add_segment_action = segment_menu.addAction(
            "&Add segment", self.add_segment
        )
        self.detect_action = segment_menu.addAction(
            "&Detect segments…", self.show_scene_detection
        )
        self.split_segment_action = segment_menu.addAction(
            "&Split segment", self.split_segment
        )
        self.clear_segments_action = segment_menu.addAction(
            "&Clear segments", self.clear_segments
        )
        self.merge_segments_action = segment_menu.addAction(
            "&Merge similar segments", self.merge_segments
        )
        crop_menu = self.window.menuBar().addMenu("&Crop")
        self.detect_crop_action = crop_menu.addAction(
            "&Detect crop borders…", self.show_crop_detection
        )
        view_menu = self.window.menuBar().addMenu("&View")
        help_menu = self.window.menuBar().addMenu("&Help")
        self.check_update_action = help_menu.addAction(
            "Check for Updates", self.check_updates
        )
        help_menu.addAction("View Releases", self.view_releases)
        self.explorer_dialog = QDialog(self.window)
        self.explorer_dialog.setWindowTitle("Install in File Explorer")
        extras = QVBoxLayout(self.explorer_dialog)
        explorer = QGroupBox("File Explorer")
        explorer_layout = QVBoxLayout(explorer)
        hint = QLabel(
            f"Add Open in {integrations.APP_NAME} to right-click menus "
            "for video files (including multiple selections), folders, "
            "folder backgrounds, and drives."
        )
        hint.setWordWrap(True)
        explorer_layout.addWidget(hint)
        self.install_button = QPushButton("Install in File Explorer")
        self.install_button.clicked.connect(self.install_explorer)
        explorer_layout.addWidget(
            self.install_button, alignment=Qt.AlignmentFlag.AlignLeft
        )
        self.install_status = QLabel()
        explorer_layout.addWidget(self.install_status)
        extras.addWidget(explorer)
        help_menu.addAction("Install in File Explorer", self.explorer_dialog.show)
        help_menu.addAction(
            "Original application releases…",
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/electblake/VideoCropper/releases")
            ),
        )
        help_menu.addAction("Show settings", self.show_settings)
        help_menu.addAction("Save diagnostic report…", self.save_report)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.window.setCentralWidget(root)
        self.files_dock = QDockWidget("Files", self.window)
        self.files_dock.setObjectName("filesDock")
        files = QWidget()
        files_layout = QVBoxLayout(files)
        self.files_dock.setWidget(files)
        self.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.files_dock)
        view_menu.addAction(self.files_dock.toggleViewAction())
        self.open_button = self.button("Open videos…", self.open_files, files_layout)
        self.file_list = QListWidget()
        files.setAcceptDrops(True)
        self.file_list.setAcceptDrops(True)
        self.file_list.setAccessibleName("Input videos")
        self.file_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.file_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.file_list.currentRowChanged.connect(self.select_file)
        files_layout.addWidget(self.file_list, 1)
        header = QHBoxLayout()
        self.open_action = action
        self.previous = self.button(
            "Previous", lambda: self.load(self.index - 1), header
        )
        self.next = self.button("Next", lambda: self.load(self.index + 1), header)
        files_layout.addLayout(header)
        self.locate = self.button(
            "Open Output Folder", self.locate_output, files_layout
        )
        self.select_none_button = self.button("Select none", self.unload, files_layout)
        self.clear_files_button = self.button(
            "Clear files", self.clear_files, files_layout
        )
        splitter = self.splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.graphics = pg.GraphicsLayoutWidget()
        self.graphics.setBackground(self.window.palette().window().color())
        self.view = self.graphics.addViewBox(
            lockAspect=True, invertY=True, enableMenu=False
        )
        self.view.setMouseEnabled(x=False, y=False)
        self.view.addItem(self.video)
        self.video.setZValue(0)
        self.roi = pg.RectROI((0, 0), (1, 1), maxBounds=QRectF(0, 0, 1, 1))
        for handle in list(self.roi.getHandles()):
            self.roi.removeHandle(handle)
        for pos in [
            (0, 0),
            (0.5, 0),
            (1, 0),
            (1, 0.5),
            (1, 1),
            (0.5, 1),
            (0, 1),
            (0, 0.5),
        ]:
            self.roi.addScaleHandle(pos, (1 - pos[0], 1 - pos[1]))
        self.roi.setZValue(2)
        self.roi.setPen(pg.mkPen("#ffd166", width=2))
        self.view.addItem(self.roi)
        self.padding_outline = QGraphicsRectItem()
        pen = QPen(self.window.palette().text().color(), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.padding_outline.setPen(pen)
        self.padding_outline.setZValue(3)
        self.padding_outline.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.padding_outline.hide()
        self.view.addItem(self.padding_outline)
        self.roi.sigRegionChanged.connect(self.geometry_changed)
        self.masks = []
        for _ in range(4):
            mask = QGraphicsRectItem()
            mask.setPen(QPen(Qt.PenStyle.NoPen))
            mask.setBrush(Qt.GlobalColor.black)
            mask.setOpacity(0.55)
            mask.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            mask.setZValue(1)
            self.view.addItem(mask)
            self.masks.append(mask)
        left_layout.addWidget(self.graphics, 1)
        self.transport = QWidget()
        playback = QVBoxLayout(self.transport)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("Playback position")
        self.seek.setSingleStep(250)
        self.seek.valueChanged.connect(self.seek_segment)
        playback.addWidget(self.seek)
        self.range_graph = pg.GraphicsLayoutWidget()
        self.range_graph.setBackground(self.window.palette().window().color())
        self.range_graph.setFixedHeight(self.window.fontMetrics().height() * 4)
        self.range_view = self.range_graph.addViewBox(
            enableMouse=False, enableMenu=False
        )
        self.range_graph.scene().sigMouseClicked.connect(self.select_timeline_segment)
        playback.addWidget(self.range_graph)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.play = self.button("Play", self.toggle_play, buttons)
        self.navigation_buttons = {}
        for name, text, icon, slot in [
            (
                "start",
                "Jump to start",
                QStyle.StandardPixmap.SP_MediaSkipBackward,
                lambda: self.seek_segment(0),
            ),
            (
                "previous",
                "Previous segment",
                QStyle.StandardPixmap.SP_MediaSeekBackward,
                lambda: self.jump_segment(-1),
            ),
            (
                "back_two",
                "−2 s",
                None,
                lambda: self.seek_segment(max(0, self.player.position() - 2000)),
            ),
            (
                "back",
                "−1 s",
                None,
                lambda: self.seek_segment(max(0, self.player.position() - 1000)),
            ),
            (
                "back_half",
                "−0.5 s",
                None,
                lambda: self.seek_segment(max(0, self.player.position() - 500)),
            ),
            (
                "forward_half",
                "+0.5 s",
                None,
                lambda: self.seek_segment(
                    min(self.player.duration(), self.player.position() + 500)
                ),
            ),
            (
                "forward",
                "+1 s",
                None,
                lambda: self.seek_segment(
                    min(self.player.duration(), self.player.position() + 1000)
                ),
            ),
            (
                "forward_two",
                "+2 s",
                None,
                lambda: self.seek_segment(
                    min(self.player.duration(), self.player.position() + 2000)
                ),
            ),
            (
                "next",
                "Next segment",
                QStyle.StandardPixmap.SP_MediaSeekForward,
                lambda: self.jump_segment(1),
            ),
            (
                "end",
                "Jump to end",
                QStyle.StandardPixmap.SP_MediaSkipForward,
                lambda: self.seek_segment(self.player.duration()),
            ),
        ]:
            button = QToolButton()
            button.setText(text)
            button.setAccessibleName(text)
            button.setToolTip(text)
            button.setAutoRepeat(icon is None)
            if icon is not None:
                button.setIcon(self.window.style().standardIcon(icon))
            button.clicked.connect(slot)
            buttons.addWidget(button)
            self.navigation_buttons[name] = button
        self.mute = QCheckBox("Mute")
        self.mute.setChecked(self.settings.value("mute", False, bool))
        self.audio.setMuted(self.mute.isChecked())
        self.mute.toggled.connect(self.audio.setMuted)
        self.mute.toggled.connect(lambda value: self.settings.setValue("mute", value))
        buttons.addWidget(self.mute)
        self.time = QLabel("00:00:00")
        self.time.setAccessibleName("Current position")
        self.time.setToolTip("Current position (hours:minutes:seconds)")
        buttons.addWidget(self.time)
        buttons.addStretch()
        self.total_time = QLabel("00:00:00")
        self.total_time.setAccessibleName("Video duration")
        self.total_time.setToolTip("Video duration (hours:minutes:seconds)")
        buttons.addWidget(self.total_time)
        playback.addLayout(buttons)
        left_layout.addWidget(self.transport)
        self.progress = QProgressBar()
        left_layout.addWidget(self.progress)
        self.window.statusBar().showMessage("Ready")
        process_buttons = QGridLayout()
        process_buttons.setDefaultPositioning(3, Qt.Orientation.Horizontal)
        for column in range(3):
            process_buttons.setColumnStretch(column, 1)
        self.add_segment_button = self.button(
            "Add segment", self.add_segment, process_buttons
        )
        self.split_segment_button = self.button(
            "Split segment", self.split_segment, process_buttons
        )
        self.merge_segments_button = self.button(
            "Merge similar segments", self.merge_segments, process_buttons
        )
        self.detect_button = self.button(
            "Detect segments…", self.show_scene_detection, process_buttons
        )
        self.clear_segments_button = self.button(
            "Clear segments", self.clear_segments, process_buttons
        )
        left_layout.addLayout(process_buttons)
        self.export_button = self.button("Export segments", self.export, left_layout)
        self.export_button.setProperty("variant", "primary")
        self.export_button.setProperty("buttonSize", "large")
        export_controls = QGridLayout()
        export_controls.setDefaultPositioning(3, Qt.Orientation.Horizontal)
        for column in range(3):
            export_controls.setColumnStretch(column, 1)
        self.stop = self.button("Stop and keep", self.stop_export, export_controls)
        self.stop.setProperty("buttonSize", "medium")
        self.cancel = self.button(
            "Cancel and delete", self.cancel_export, export_controls
        )
        self.cancel.setProperty("buttonSize", "medium")
        self.pause = self.button("Pause", self.pause_export, export_controls)
        self.pause.setProperty("buttonSize", "medium")
        left_layout.addLayout(export_controls)
        self.remember_crop = QCheckBox("Remember crop settings")
        self.remember_crop.setToolTip(
            "Restore the last crop, rotation, aspect preset, aspect lock, and padding "
            "for new videos. Crop position and size scale with the video dimensions."
        )
        self.auto_segment = QCheckBox("Automatically create first segment")
        self.advance = QCheckBox("Load next after completion")
        self.auto = QCheckBox("Auto-run next")
        self.quit_done = QCheckBox("Quit when done")
        process_options = QGridLayout()
        process_options.setColumnStretch(0, 1)
        process_options.setColumnStretch(1, 1)
        for index, (control, key) in enumerate(
            [
                (self.remember_crop, "remember_crop"),
                (self.auto_segment, "auto_segment"),
                (self.advance, "advance"),
                (self.auto, "auto"),
                (self.quit_done, "quit"),
            ]
        ):
            control.setChecked(self.settings.value(key, False, bool))
            control.toggled.connect(
                lambda value, k=key: self.settings.setValue(k, value)
            )
            process_options.addWidget(control, index // 2, index % 2)
        left_layout.addLayout(process_options)
        splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.segments_dock = QDockWidget("Segments", self.window)
        self.segments_dock.setObjectName("segmentsDock")
        segments = QWidget()
        segments_layout = QVBoxLayout(segments)
        self.segments_dock.setWidget(segments)
        self.window.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.segments_dock
        )
        view_menu.addAction(self.segments_dock.toggleViewAction())
        view_menu.addSeparator()
        self.reset_layout_action = view_menu.addAction(
            "&Reset Layout", self.reset_layout
        )
        self.segment_list = QListWidget()
        self.segment_list.setAccessibleName("Video segments")
        self.segment_list.currentRowChanged.connect(self.select_segment)
        segments_layout.addWidget(self.segment_list, 1)
        tabs = self.tabs = QTabWidget()
        right_layout.addWidget(tabs, 1)
        self.crop_page = QWidget()
        form = QFormLayout(self.crop_page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.fields = []
        for label in ["&X (%)", "&Y (%)", "&Width (pixels)", "&Height (pixels)"]:
            field = QDoubleSpinBox()
            field.setDecimals(2)
            field.setRange(0, 100000)
            field.setKeyboardTracking(False)
            form.addRow(label, field)
            self.fields.append(field)
            field.valueChanged.connect(self.numeric_geometry)
        self.padding_fields = []
        for axis in ("X", "Y"):
            field = QSpinBox()
            field.setRange(-100000, 100000)
            field.setSuffix(" px")
            field.setKeyboardTracking(False)
            field.setAccessibleName(f"{axis} padding in source pixels")
            field.setToolTip(
                "Positive expands both sides; negative insets both sides. "
                "Expansion stops at the source edges."
            )
            row = QHBoxLayout()
            row.addWidget(field, 1)
            reset = self.button(
                "Zero", lambda checked=False, field=field: field.setValue(0), row
            )
            reset.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            reset.setAccessibleName(f"Reset padding {axis} to zero")
            reset.setToolTip(f"Set padding {axis} to 0 px")
            form.addRow(f"Padding {axis}", row)
            self.padding_fields.append(field)
            field.valueChanged.connect(self.geometry_changed)
        padding_reset_row = QHBoxLayout()
        self.button(
            "Zero both",
            lambda: (
                self.padding_fields[0].setValue(0),
                self.padding_fields[1].setValue(0),
            ),
            padding_reset_row,
        ).setToolTip("Set padding X and Y to 0 px")
        padding_reset_row.addStretch()
        form.addRow("", padding_reset_row)
        rotation = QVBoxLayout()
        self.button("Rotate left", lambda: self.rotate(3), rotation)
        self.button("Rotate right", lambda: self.rotate(1), rotation)
        self.button(
            "Reset rotation", lambda: self.rotate((-self.rotation) % 4), rotation
        )
        form.addRow(rotation)
        self.lock = QCheckBox("&Lock aspect ratio")
        form.addRow(self.lock)
        self.lock.toggled.connect(self.set_aspect_lock)
        self.selected_preset = "Custom"
        self.preset_group = QButtonGroup(self)
        self.preset_buttons = {}
        presets = QGridLayout()
        for index, name in enumerate(RATIOS):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setAccessibleName(f"{name} aspect ratio")
            self.preset_group.addButton(button)
            self.preset_buttons[name] = button
            presets.addWidget(button, index // 4, index % 4)
        self.preset_group.buttonClicked.connect(self.choose_preset)
        form.addRow(presets)
        for divisions, positions in [
            (3, ["Left", "Center", "Right"]),
            (2, ["Left", "Center", "Right"]),
        ]:
            row = QHBoxLayout()
            for index, position in enumerate(positions):
                self.button(
                    f"1/{divisions} {position}",
                    lambda checked=False, divisions=divisions, index=index: (
                        self.crop_slice(divisions, index * (divisions - 1) / 2)
                    ),
                    row,
                )
            form.addRow(row)
        center_row = QHBoxLayout()
        self.button("Center frame", self.center, center_row)
        self.button("Full frame", self.full_frame, center_row)
        form.addRow(center_row)
        self.detect_crop_button = QPushButton("Detect crop borders…")
        self.detect_crop_button.clicked.connect(self.show_crop_detection)
        form.addRow(self.detect_crop_button)
        fit_row = QHBoxLayout()
        self.button("Fit view", self.fit, fit_row)
        form.addRow(fit_row)
        crop_scroll = QScrollArea()
        crop_scroll.setWidgetResizable(True)
        crop_scroll.setWidget(self.crop_page)
        tabs.addTab(crop_scroll, "Crop")
        options = QWidget()
        options_form = QFormLayout(options)
        options_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        appearance = QGroupBox("Appearance")
        appearance_layout = QGridLayout(appearance)
        self.theme = QComboBox()
        self.theme.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.theme.setMinimumContentsLength(8)
        self.theme.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.theme.addItem("System", "")
        for name in sorted(self.themes):
            self.theme.addItem(name.replace("_", " ").title(), name)
        self.theme.setCurrentIndex(self.theme.findData(self.applied_theme))
        theme_label = QLabel("&Theme")
        theme_label.setBuddy(self.theme)
        appearance_layout.addWidget(theme_label, 0, 0)
        appearance_layout.addWidget(self.theme, 1, 0)
        self.icon = QComboBox()
        for name, icon in self.icons.items():
            self.icon.addItem(icon, name.title(), name)
        self.icon.setCurrentIndex(self.icon.findData(self.applied_icon))
        icon_label = QLabel("&Icon")
        icon_label.setBuddy(self.icon)
        appearance_layout.addWidget(icon_label, 2, 0)
        appearance_layout.addWidget(self.icon, 3, 0)
        appearance_layout.setColumnStretch(0, 1)
        self.apply_appearance_button = QPushButton("Apply")
        self.apply_appearance_button.setProperty("variant", "primary")
        self.apply_appearance_button.clicked.connect(self.apply_appearance)
        appearance_layout.addWidget(self.apply_appearance_button, 3, 1)
        self.theme.currentIndexChanged.connect(self.update_enabled)
        self.icon.currentIndexChanged.connect(self.update_enabled)
        options_form.addRow(appearance)
        self.notify = self.preference(
            "Notify on completion", "notify", False, options_form
        )
        self.preview = self.preference(
            "Preview while processing", "preview", True, options_form
        )
        self.preview.toggled.connect(self.preview_changed)
        self.wheel = self.preference("Mouse-wheel zoom", "wheel", False, options_form)
        self.square = self.preference(
            "Square-pixel output", "square", False, options_form
        )
        self.encoder = QComboBox()
        self.encoder.addItem("CPU — HEVC", "libx265")
        self.encoder.addItem("Auto GPU — HEVC", "auto")
        encoders = subprocess.check_output(
            [self.ffmpeg, "-hide_banner", "-encoders"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode()
        self.compiled_encoders = encoders
        for name, key in [
            ("NVIDIA — HEVC", "hevc_nvenc"),
            ("Intel — HEVC", "hevc_qsv"),
            ("AMD — HEVC", "hevc_amf"),
        ]:
            if key in encoders:
                self.encoder.addItem(name, key)
        self.encoder.setCurrentIndex(
            self.encoder.findData(self.settings.value("encoder", "libx265"))
        )
        self.encoder.currentIndexChanged.connect(
            lambda: self.settings.setValue("encoder", self.encoder.currentData())
        )
        options_form.addRow("&Encoder", self.encoder)
        self.device = QSpinBox()
        self.device.setRange(0, 32)
        self.device.setValue(self.settings.value("device", 0, int))
        self.device.valueChanged.connect(
            lambda value: self.settings.setValue("device", value)
        )
        options_form.addRow("NVIDIA device index", self.device)
        updates = QGroupBox("Updates")
        updates_layout = QVBoxLayout(updates)
        updates_layout.addWidget(QLabel(f"Installed version: {APP_VERSION}"))
        self.check_update_button = self.button(
            "Check for Updates", self.check_updates, updates_layout
        )
        self.button("View Releases", self.view_releases, updates_layout)
        options_form.addRow(updates)
        note = QLabel(
            "GPU entries reflect FFmpeg build support. The selected GPU and driver must be installed."
        )
        note.setWordWrap(True)
        options_form.addRow(note)
        self.auto_delay = QSpinBox()
        self.quit_delay = QSpinBox()
        for label, control, key, default in [
            ("Auto-run delay", self.auto_delay, "auto_delay", 6),
            ("Quit countdown", self.quit_delay, "quit_delay", 30),
        ]:
            control.setRange(1, 3600)
            control.setSuffix(" s")
            control.setValue(self.settings.value(key, default, int))
            control.valueChanged.connect(
                lambda value, k=key: self.settings.setValue(k, value)
            )
            options_form.addRow(label, control)
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_scroll.setWidget(options)
        tabs.addTab(options_scroll, "Settings")
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log, 1)
        log_buttons = QHBoxLayout()
        self.copy_logs_button = self.button(
            "Copy Logs to Clipboard", self.copy_logs, log_buttons
        )
        self.clear_logs_button = self.button("Clear Logs", self.clear_logs, log_buttons)
        log_layout.addLayout(log_buttons)
        tabs.addTab(log_page, "Process log")
        self.count_label = QLabel()
        right_layout.addWidget(self.count_label)
        count_buttons = QHBoxLayout()
        self.count_now = self.button("Continue now", self.count_execute, count_buttons)
        self.count_cancel = self.button(
            "Cancel countdown", self.count_cancelled, count_buttons
        )
        right_layout.addLayout(count_buttons)
        self.count_now.hide()
        self.count_cancel.hide()
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([750, 420])
        self.window.resizeDocks(
            [self.files_dock, self.segments_dock], [260, 320], Qt.Orientation.Horizontal
        )
        self.default_window_state = self.window.saveState(1)
        self.default_splitter_state = splitter.saveState()
        tabs.setCurrentIndex(self.settings.value("active_tab", 0, int))
        tabs.currentChanged.connect(
            lambda value: self.settings.setValue("active_tab", value)
        )
        self.window.statusBar().showMessage(
            "Source preview • exports replace matching numbered segment files"
        )

    def reset_layout(self):
        self.window.restoreState(self.default_window_state, 1)
        self.splitter.restoreState(self.default_splitter_state)

    def show_scene_detection(self):
        self.count_cancelled()
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Detect segments")
        layout = QVBoxLayout(dialog)
        description = QLabel(
            "Find scene changes across the whole video. This replaces the current "
            "segments; new segments inherit the current crop settings."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        threshold = QDoubleSpinBox()
        threshold.setRange(0, 1)
        threshold.setDecimals(2)
        threshold.setSingleStep(0.01)
        threshold.setValue(self.settings.value("scene_threshold", 0.3, float))
        threshold.valueChanged.connect(
            lambda value: self.settings.setValue("scene_threshold", value)
        )
        threshold.setToolTip(
            "Lower values detect smaller changes and usually create more segments."
        )
        form.addRow("Scene &threshold", threshold)
        minimum = QDoubleSpinBox()
        minimum.setRange(0, self.player.duration() / 1000)
        minimum.setDecimals(3)
        minimum.setSuffix(" s")
        minimum.setValue(self.settings.value("scene_minimum_length", 1.0, float))
        minimum.valueChanged.connect(
            lambda value: self.settings.setValue("scene_minimum_length", value)
        )
        minimum.setToolTip("Ignore cuts that would create a shorter segment.")
        form.addRow("&Minimum segment length", minimum)
        framestep = QSpinBox()
        framestep.setRange(1, 2147483647)
        framestep.setValue(self.settings.value("scene_framestep", 1, int))
        framestep.valueChanged.connect(
            lambda value: self.settings.setValue("scene_framestep", value)
        )
        framestep.setToolTip(
            "Analyze every Nth frame. 1 checks every frame; larger steps can miss short scenes."
        )
        form.addRow("&Frame step", framestep)
        threads = QSpinBox()
        threads.setRange(0, 2147483647)
        threads.setSpecialValueText("Auto")
        threads.setValue(self.settings.value("scene_decoder_threads", 0, int))
        threads.valueChanged.connect(
            lambda value: self.settings.setValue("scene_decoder_threads", value)
        )
        threads.setToolTip("Decoder thread count. Auto lets FFmpeg choose.")
        form.addRow("&Decoder threads", threads)
        layout.addLayout(form)
        hint = QLabel(
            "Lower threshold = more cuts. Increase minimum length to skip short scenes."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Detect segments")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.detect_segments(
                threshold.value(), minimum.value(), framestep.value(), threads.value()
            )
        dialog.deleteLater()

    def show_crop_detection(self):
        self.count_cancelled()
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Detect crop borders")
        layout = QVBoxLayout(dialog)
        description = QLabel(
            "Scan the selected segment and apply the detected crop frame. "
            "With reset count 0, detection keeps the largest video area found. "
            "Otherwise, the final detection window is used."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        mode = QComboBox()
        mode.addItem("Black borders", "black")
        mode.addItem("Motion and edges", "mvedges")
        mode.setCurrentIndex(
            mode.findData(self.settings.value("cropdetect_mode", "black"))
        )
        mode.currentIndexChanged.connect(
            lambda _: self.settings.setValue("cropdetect_mode", mode.currentData())
        )
        form.addRow("&Mode", mode)
        fields = {}
        for name, label, maximum, default, hint in [
            (
                "limit",
                "Black &threshold",
                65535,
                24 / 255,
                "Pixels below this level are black. Values 0–1 scale with bit depth; higher values are absolute.",
            ),
            (
                "round",
                "Dimension &multiple",
                2147483647,
                16,
                "Round width and height to this multiple. Use 2 for even dimensions.",
            ),
            (
                "skip",
                "&Skip initial frames",
                2147483647,
                2,
                "Number of frames to ignore at the start of the segment.",
            ),
            (
                "reset_count",
                "&Reset count (frames)",
                2147483647,
                0,
                "0 keeps the largest area across the segment. Otherwise restart after this many frames.",
            ),
            (
                "max_outliers",
                "Maximum &outliers",
                2147483647,
                0,
                "Number of non-black pixels tolerated when scanning a border line.",
            ),
            (
                "mv_threshold",
                "Motion threshold (&pixels)",
                100,
                8,
                "Minimum motion used to locate the video area.",
            ),
            (
                "low",
                "&Low edge threshold",
                1,
                15 / 255,
                "Weak-edge threshold, from 0 to 1. Use a value no higher than the high threshold.",
            ),
            (
                "high",
                "&High edge threshold",
                1,
                25 / 255,
                "Strong-edge threshold, from 0 to 1.",
            ),
        ]:
            field = QDoubleSpinBox() if isinstance(default, float) else QSpinBox()
            field.setObjectName(name)
            field.setRange(0, maximum)
            if isinstance(default, float):
                field.setDecimals(6)
                field.setSingleStep(0.01)
            field.setValue(
                self.settings.value(f"cropdetect_{name}", default, type(default))
            )
            field.setToolTip(hint)
            field.valueChanged.connect(
                lambda value, key=name: self.settings.setValue(
                    f"cropdetect_{key}", value
                )
            )
            form.addRow(label, field)
            fields[name] = field
        for name in ("limit", "max_outliers", "mv_threshold", "low", "high"):
            black = name in ("limit", "max_outliers")
            fields[name].setEnabled((mode.currentData() == "black") == black)
            mode.currentIndexChanged.connect(
                lambda _, field=fields[name], black=black: field.setEnabled(
                    (mode.currentData() == "black") == black
                )
            )
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Detect and apply crop"
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.detect_crop(
                {
                    "mode": mode.currentData(),
                    **{name: field.value() for name, field in fields.items()},
                }
            )
        dialog.deleteLater()

    def detect_crop(self, options):
        self.count_cancelled()
        self.player.pause()
        self.crop_scan = CropScan(
            self.paths[self.index], self.segments[self.active_segment], options
        )
        self.detecting = True
        self.detecting_crop = True
        self.running = True
        self.outcome = ""
        self.progress_buffer = ""
        self.progress_values = {}
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.window.statusBar().showMessage("Detecting crop borders…")
        self.log.clear()
        self.log.appendPlainText(
            subprocess.list2cmdline([self.ffmpeg, *self.crop_scan.arguments()])
        )
        self.update_enabled()
        self.process.start(self.ffmpeg, self.crop_scan.arguments())

    def detect_segments(self, threshold, minimum, framestep=1, threads=0):
        self.count_cancelled()
        if self.segments:
            answer = QMessageBox.warning(
                self.window,
                "Replace existing segments?",
                "Starting scene detection will clear all existing segments and their "
                "individual crop settings. New detected segments will be created on "
                "an empty timeline. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.clear_segments()
        self.player.pause()
        self.detecting = True
        self.running = True
        self.outcome = ""
        self.progress_buffer = ""
        self.progress_values = {}
        self.progress.setRange(0, 100)
        self.detection_progress(0, 0)
        self.scene_scan = SceneScan(
            self.paths[self.index],
            self.player.duration() / 1000,
            threshold,
            minimum,
            framestep,
            threads,
        )
        self.log.clear()
        self.log.appendPlainText(
            subprocess.list2cmdline([self.ffmpeg, *self.scene_scan.arguments()])
        )
        self.update_enabled()
        self.process.start(self.ffmpeg, self.scene_scan.arguments())

    def detection_progress(self, seconds, cuts):
        duration = self.player.duration() / 1000
        self.progress.setValue(min(99, int(seconds / duration * 100)))
        self.window.statusBar().showMessage(
            f"Detecting scenes • {self.progress.value()}% • "
            f"{seconds:.1f} / {duration:.1f} s scanned • {cuts} cuts found"
        )
        if self.preview.isChecked():
            self.player.setPosition(round(seconds * 1000))

    def replace_segments(self, ranges):
        x, y, w, h = self.rect()
        rect = x / self.width, y / self.height, w / self.width, h / self.height
        self.active_segment = -1
        self.segments[:] = [
            Segment(
                start,
                end,
                rect,
                self.rotation,
                self.selected_preset,
                self.lock.isChecked(),
                *(field.value() for field in self.padding_fields),
            )
            for start, end in ranges
        ]
        self.refresh_segments()
        self.segment_list.setCurrentRow(0)
        self.progress.setValue(100)
        self.window.statusBar().showMessage(
            f"Scene detection complete — {len(self.segments)} segments"
        )
        self.update_enabled()

    def add_segment(self):
        if self.segments:
            self.window.statusBar().showMessage(
                "No segment added — segments already exist"
            )
            return
        self.count_cancelled()
        self.player.pause()
        x, y, w, h = self.rect()
        self.segments.append(
            Segment(
                0.0,
                self.player.duration() / 1000,
                (x / self.width, y / self.height, w / self.width, h / self.height),
                self.rotation,
                self.selected_preset,
                self.lock.isChecked(),
                *(field.value() for field in self.padding_fields),
            )
        )
        self.refresh_segments()
        self.segment_list.setCurrentRow(0)
        self.update_enabled()
        self.window.statusBar().showMessage("Added segment covering the full timeline")

    def split_segment(self):
        self.count_cancelled()
        self.player.pause()
        self.save_segment()
        position = self.player.position() / 1000
        index = next(
            i
            for i, segment in enumerate(self.segments)
            if segment.start < position < segment.end
        )
        segment = self.segments[index]
        self.segments[index : index + 1] = [
            replace(segment, end=position),
            replace(segment, start=position),
        ]
        self.active_segment = -1
        self.refresh_segments()
        self.segment_list.setCurrentRow(index + 1)
        self.segment_list.scrollToItem(self.segment_list.currentItem())
        self.update_enabled()

    def merge_segments(self):
        self.count_cancelled()
        self.player.pause()
        self.save_segment()
        original_count = len(self.segments)
        merged = []
        selected = -1
        for index, segment in enumerate(self.segments):
            if merged and merged[-1].can_merge(segment):
                merged[-1].end = segment.end
            else:
                merged.append(segment)
            if index == self.active_segment:
                selected = len(merged) - 1
        self.segments[:] = merged
        self.active_segment = -1
        self.refresh_segments()
        self.segment_list.blockSignals(True)
        self.segment_list.setCurrentRow(selected)
        self.segment_list.blockSignals(False)
        self.select_segment(selected, seek_start=False)
        self.update_enabled()
        self.window.statusBar().showMessage(
            f"Merged {original_count} segments into {len(self.segments)}"
        )

    def update_merge_enabled(self):
        enabled = (
            self.ready
            and not (self.running or self.loading or self.resolving_encoder)
            and any(
                left.can_merge(right)
                for left, right in zip(self.segments, self.segments[1:])
            )
        )
        self.merge_segments_action.setEnabled(enabled)
        self.merge_segments_button.setEnabled(enabled)

    def update_split_enabled(self):
        position = self.player.position()
        enabled = (
            self.ready
            and not (self.running or self.loading or self.resolving_encoder)
            and any(
                round(segment.start * 1000) < position < round(segment.end * 1000)
                for segment in self.segments
            )
        )
        self.split_segment_action.setEnabled(enabled)
        self.split_segment_button.setEnabled(enabled)

    def clear_segments(self):
        self.count_cancelled()
        self.active_segment = -1
        self.segments.clear()
        self.refresh_segments()
        self.progress.setValue(0)
        self.window.statusBar().showMessage("Ready")
        self.update_enabled()

    def segment_text(self, index):
        segment = self.segments[index]
        width, height = self.source_width, self.source_height
        if (self.source_rotation + segment.rotation) % 2:
            width, height = height, width
        x, y, w, h = segment.rect
        return (
            f"{index + 1:02d}   {segment.start:.3f} – {segment.end:.3f} s\n"
            f"Duration {segment.end - segment.start:.3f} s\n"
            f"Crop {w * width:.0f} × {h * height:.0f} at {x * width:.0f}, {y * height:.0f}\n"
            f"{segment.preset} • Rotation {segment.rotation * 90}°\n"
            f"Padding X {segment.padding_x:+d} px / Y {segment.padding_y:+d} px per side"
        )

    def refresh_segments(self):
        self.segment_list.blockSignals(True)
        self.segment_list.clear()
        self.segment_list.addItems(
            [self.segment_text(i) for i in range(len(self.segments))]
        )
        self.segment_list.blockSignals(False)
        for region in self.segment_regions:
            self.range_view.removeItem(region)
        self.segment_regions.clear()
        palette = self.window.palette()
        brush = palette.highlight().color()
        brush.setAlpha(60)
        for index, segment in enumerate(self.segments):
            region = pg.LinearRegionItem(
                (segment.start, segment.end),
                movable=False,
                brush=brush,
                pen=palette.text().color(),
            )
            region.setZValue(-1)
            self.range_view.addItem(region)
            self.segment_regions.append(region)
            pg.InfLineLabel(
                region.lines[0],
                str(index + 1),
                position=0.85,
                anchors=[(0, 0.5), (0, 0.5)],
                color=palette.text().color(),
            )
        self.update_segment_summary()

    def update_segment_summary(self):
        self.update_merge_enabled()
        if self.segments:
            self.export_button.setText(f"Export {len(self.segments)} segments")
        else:
            self.export_button.setText("Export segments")

    def save_segment(self):
        if self.active_segment < 0 or self.restoring_segment:
            return
        segment = self.segments[self.active_segment]
        x, y, w, h = self.rect()
        segment.rect = x / self.width, y / self.height, w / self.width, h / self.height
        segment.rotation = self.rotation
        segment.preset = self.selected_preset
        segment.locked = self.lock.isChecked()
        segment.padding_x, segment.padding_y = (
            field.value() for field in self.padding_fields
        )
        self.segment_list.item(self.active_segment).setText(
            self.segment_text(self.active_segment)
        )
        self.segment_regions[self.active_segment].setRegion(
            (segment.start, segment.end)
        )
        self.update_segment_summary()

    def select_segment(self, index, seek_start=True):
        if index < 0:
            return
        self.save_segment()
        self.restoring_segment = True
        segment = self.segments[index]
        self.rotate((segment.rotation - self.rotation) % 4)
        for field, value in zip(
            self.padding_fields, (segment.padding_x, segment.padding_y)
        ):
            field.blockSignals(True)
            field.setValue(value)
            field.blockSignals(False)
        x, y, w, h = segment.rect
        self.set_rect(
            (x * self.width, y * self.height, w * self.width, h * self.height)
        )
        self.set_preset(segment.preset)
        self.lock.setChecked(segment.locked)
        self.active_segment = index
        for row, region in enumerate(self.segment_regions):
            item = self.segment_list.item(row)
            font = item.font()
            font.setBold(row == index)
            item.setFont(font)
            brush = self.window.palette().highlight().color()
            brush.setAlpha(130 if row == index else 60)
            region.setBrush(brush)
            region.setHoverBrush(brush)
            region.update()
        self.restoring_segment = False
        self.fit()
        if seek_start:
            self.player.setPosition(round(segment.start * 1000))

    def select_timeline_segment(self, event):
        if (
            self.running
            or self.detecting
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return
        position = self.range_view.mapSceneToView(event.scenePos()).x()
        self.seek_segment(max(0, min(self.player.duration(), round(position * 1000))))

    def open_files(self):
        dialog = VideoFileDialog(
            self.window,
            "Open videos",
            self.settings.value("folder_path", ""),
            "Videos (*.mp4 *.mkv *.mov *.avi *.webm);;All files (*)",
        )
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.setValue("folder_path", dialog.directory().absolutePath())
            self.add_paths(dialog.selectedFiles())
        dialog.deleteLater()

    def add_paths(self, paths):
        videos = []
        for value in paths:
            path = Path(value).resolve()
            if path.is_dir():
                videos.extend(
                    child.resolve()
                    for child in sorted(path.iterdir())
                    if child.is_file()
                    and child.suffix.lower()
                    in (".mp4", ".mkv", ".mov", ".avi", ".webm")
                )
            else:
                videos.append(path)
        for video in videos:
            if video not in self.paths:
                self.paths.append(video)
        if videos:
            self.load(self.paths.index(videos[0]))

    def refresh_files(self):
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for path in self.paths:
            status = "Done" if path in self.done else "Pending"
            item = QListWidgetItem(f"{path.name}\n{status}", self.file_list)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
        if self.index >= 0:
            self.file_list.setCurrentRow(self.index)
            self.file_list.scrollToItem(self.file_list.currentItem())
        self.file_list.blockSignals(False)

    def select_file(self, index):
        if index == -1:
            self.unload()
        elif index != self.index:
            self.load(index)

    def unload(self):
        self.load_timer.stop()
        self.follow_timer.stop()
        self.count_cancelled()
        self.auto_export_pending = False
        self.save_segment()
        if self.ready:
            self.save_crop_settings()
        self.ready = False
        self.loading = False
        self.index = -1
        self.active_segment = -1
        self.segments = []
        self.refresh_segments()
        self.player.stop()
        self.player.setSource(QUrl())
        self.video.videoSink().setVideoFrame(QVideoFrame())
        # Hiding the ViewBox collapses its graphics-layout geometry on later loads.
        self.view.setOpacity(0)
        self.refresh_files()
        self.window.statusBar().showMessage("No video selected")
        self.update_enabled()

    def clear_files(self):
        self.unload()
        self.paths.clear()
        self.source_segments.clear()
        self.done.clear()
        self.output = None
        self.refresh_files()
        self.window.statusBar().showMessage("File list cleared")
        self.update_enabled()

    def save_crop_settings(self):
        x, y, w, h = self.rect()
        self.settings.setValue(
            "crop/rect",
            QRectF(x / self.width, y / self.height, w / self.width, h / self.height),
        )
        self.settings.setValue("crop/turns", self.rotation)
        self.settings.setValue("crop/preset", self.selected_preset)
        self.settings.setValue("crop/locked", self.lock.isChecked())
        self.settings.setValue("crop/padding_x", self.padding_fields[0].value())
        self.settings.setValue("crop/padding_y", self.padding_fields[1].value())

    def load(self, index):
        self.unload()
        self.segments = self.source_segments.setdefault(self.paths[index], [])
        self.refresh_segments()
        self.ready = False
        self.loading = True
        self.index = index
        self.refresh_files()
        self.rotation = 0
        self.lock.setChecked(False)
        for field in self.padding_fields:
            field.blockSignals(True)
            field.setValue(0)
            field.blockSignals(False)
        self.set_preset("Custom")
        self.output = None
        self.progress.setValue(0)
        self.window.statusBar().showMessage("Loading video…")
        self.log.appendPlainText(f"Loading video: {self.paths[index]}")
        self.log.appendPlainText(f"Probing metadata: {self.ffprobe}")
        self.update_enabled()
        self.probe.start(
            self.ffprobe,
            [
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:stream_side_data=rotation",
                "-of",
                "json",
                str(self.paths[index]),
            ],
        )

    def media_probed(self):
        stream = json.loads(bytes(self.probe.readAllStandardOutput()))["streams"][0]
        self.source_width, self.source_height = stream["width"], stream["height"]
        self.source_rotation = 0
        if "side_data_list" in stream:
            for data in stream["side_data_list"]:
                if "rotation" in data:
                    self.source_rotation = data["rotation"] // 90
        self.refresh_segments()
        self.log.appendPlainText(
            f"Metadata ready: {self.source_width} × {self.source_height}; "
            "decoding first video frame"
        )
        self.window.statusBar().showMessage("Decoding first video frame…")
        self.player.setSource(QUrl.fromLocalFile(str(self.paths[self.index])))
        self.output = None
        self.update_enabled()
        self.player.pause()

    def media_size(self, size):
        if size.isEmpty():
            return
        self.video.setSize(size)
        self.width, self.height = size.width(), size.height()
        if self.rotation % 2:
            self.width, self.height = self.height, self.width
        self.apply_rotation()
        self.roi.maxBounds = QRectF(0, 0, self.width, self.height)
        self.set_rect((0, 0, self.width, self.height))
        if (
            self.remember_crop.isChecked()
            and not self.segments
            and self.settings.contains("crop/rect")
        ):
            self.rotate(self.settings.value("crop/turns", type=int))
            for field, key in zip(self.padding_fields, ("padding_x", "padding_y")):
                field.setValue(self.settings.value(f"crop/{key}", type=int))
            rect = self.settings.value("crop/rect", type=QRectF)
            self.set_rect(
                (
                    rect.x() * self.width,
                    rect.y() * self.height,
                    rect.width() * self.width,
                    rect.height() * self.height,
                )
            )
            self.set_preset(self.settings.value("crop/preset", type=str))
            self.apply_preset()
            self.lock.setChecked(self.settings.value("crop/locked", type=bool))
        self.ready = True
        self.loading = False
        self.view.setOpacity(1)
        self.window.statusBar().showMessage("Ready")
        self.log.appendPlainText("Video ready: first preview frame decoded")
        self.geometry_changed()
        self.set_aspect_lock()
        self.fit()

        if self.segments:
            self.segment_list.setCurrentRow(0)
        self.load_timer.start(0)
        self.update_enabled()

    def complete_load(self):
        auto_export = self.auto_export_pending
        self.auto_export_pending = False
        if self.auto_segment.isChecked():
            self.add_segment()
        if auto_export and self.segments:
            self.countdown("export", self.auto_delay.value())

    def frame_changed(self, frame):
        if (
            self.loading
            and frame.isValid()
            and self.probe.state() == QProcess.ProcessState.NotRunning
            and self.player.duration() > 0
            and not self.player.source().isEmpty()
        ):
            self.pixel_width, self.pixel_height = self.source_width, self.source_height
            if (self.source_rotation + self.rotation) % 2:
                self.pixel_width, self.pixel_height = (
                    self.pixel_height,
                    self.pixel_width,
                )
            display_size = self.video.nativeSize()
            if self.source_rotation % 2:
                display_size.transpose()
            self.media_size(display_size)

    def duration_changed(self, duration):
        seconds = duration // 1000
        self.total_time.setText(
            f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
        )
        self.seek.setRange(0, duration)
        self.position_changed(self.player.position())
        self.range_view.setXRange(0, duration / 1000, padding=0)

    def position_changed(self, position):
        self.seek.blockSignals(True)
        self.seek.setValue(position)
        self.seek.blockSignals(False)
        seconds = position // 1000
        self.time.setText(
            f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
        )
        self.update_split_enabled()

        self.update_navigation()

    def update_navigation(self):
        position = self.player.position()
        index = (
            sum(round(segment.start * 1000) <= position for segment in self.segments)
            - 1
        )
        self.navigation_buttons["previous"].setEnabled(index > 0)
        self.navigation_buttons["next"].setEnabled(index + 1 < len(self.segments))

    def jump_segment(self, direction):
        position = self.player.position()
        index = (
            sum(round(segment.start * 1000) <= position for segment in self.segments)
            - 1
        )
        self.seek_segment(round(self.segments[index + direction].start * 1000))

    def seek_segment(self, position):
        for index, segment in enumerate(self.segments):
            if round(segment.start * 1000) <= position < round(segment.end * 1000) or (
                position == self.player.duration() == round(segment.end * 1000)
            ):
                if index != self.active_segment:
                    self.segment_list.blockSignals(True)
                    self.segment_list.setCurrentRow(index)
                    self.segment_list.blockSignals(False)
                    self.select_segment(index, seek_start=False)
                    self.segment_list.scrollToItem(self.segment_list.currentItem())
                break
        self.player.setPosition(position)

    def playback_changed(self, state):
        self.play.setText(
            "Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play"
        )

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def rect(self):
        return (*self.roi.pos(), *self.roi.size())

    def set_rect(self, rect):
        x, y, w, h = rect
        self.roi.blockSignals(True)
        self.roi.setPos((x, y))
        self.roi.setSize((w, h))
        self.roi.blockSignals(False)
        self.geometry_changed()

    def geometry_changed(self):
        x, y, w, h = self.rect()
        for field, value in zip(
            self.fields,
            (
                x / self.width * 100,
                y / self.height * 100,
                w / self.width * self.pixel_width,
                h / self.height * self.pixel_height,
            ),
        ):
            field.blockSignals(True)
            field.setValue(value)
            field.blockSignals(False)
        px, py = (field.value() for field in self.padding_fields)
        x, y, w, h = padded_rect(
            (x, y, w, h),
            px * self.width / self.pixel_width,
            py * self.height / self.pixel_height,
            self.width,
            self.height,
        )
        self.padding_outline.setRect(x, y, w, h)
        self.padding_outline.setVisible(bool(px or py))
        for mask, rect in zip(
            self.masks,
            [
                (0, 0, self.width, y),
                (0, y + h, self.width, self.height - y - h),
                (0, y, x, h),
                (x + w, y, self.width - x - w, h),
            ],
        ):
            mask.setRect(*rect)
        if self.ready:
            x, y, w, h = self.rect()
            selected = self.selected_preset
            if selected != "Custom":
                ratio = (
                    self.width / self.height
                    if selected == "Original"
                    else RATIOS[selected]
                )
                if h and abs(w / h - ratio) > 0.001:
                    self.set_preset("Custom")
            self.save_segment()

    def numeric_geometry(self):
        x, y, old_w, old_h = self.rect()
        w, h = old_w, old_h
        index = self.fields.index(self.sender())
        value = self.fields[index].value()
        if index == 0:
            x = value / 100 * self.width
        elif index == 1:
            y = value / 100 * self.height
        elif index == 2:
            w = value / self.pixel_width * self.width
        else:
            h = value / self.pixel_height * self.height
        if self.lock.isChecked() and index in (2, 3):
            if index == 2:
                h = w * old_h / old_w
            else:
                w = h * old_w / old_h
            scale = min(1, self.width / w, self.height / h)
            w, h = w * scale, h * scale
        else:
            w, h = min(w, self.width), min(h, self.height)
        self.set_rect(
            (
                min(x, self.width - w),
                min(y, self.height - h),
                w,
                h,
            )
        )

    def set_aspect_lock(self):
        for handle in self.roi.handles:
            pos = handle["pos"]
            center = [1 - pos[0], 1 - pos[1]]
            if self.lock.isChecked():
                center = [0 if v == 0.5 else v for v in center]
            handle["center"] = pg.Point(center)
            handle["lockAspect"] = self.lock.isChecked()
        self.save_segment()

    def set_preset(self, name):
        self.selected_preset = name
        self.preset_group.setExclusive(False)
        for label, button in self.preset_buttons.items():
            button.setChecked(label == name)
        self.preset_group.setExclusive(True)

    def choose_preset(self, button):
        name = button.text()
        self.set_preset(name)
        ratio = self.width / self.height if name == "Original" else RATIOS[name]
        w = min(self.width, self.height * ratio)
        h = w / ratio
        self.set_rect(((self.width - w) / 2, (self.height - h) / 2, w, h))

    def apply_preset(self):
        name = self.selected_preset
        if name == "Custom":
            return
        ratio = self.width / self.height if name == "Original" else RATIOS[name]
        x, y, w, h = self.rect()
        if w / h > ratio:
            w = h * ratio
        else:
            h = w / ratio
        self.set_rect((x, y, w, h))

    def center(self):
        _, _, w, h = self.rect()
        self.set_rect(((self.width - w) / 2, (self.height - h) / 2, w, h))

    def full_frame(self):
        self.set_rect((0, 0, self.width, self.height))
        self.fit()

    def crop_slice(self, divisions, index):
        width = self.width / divisions
        self.set_preset("Custom")
        self.set_rect((index * width, 0, width, self.height))
        self.fit()

    def rotate(self, steps):
        preset = self.selected_preset
        for _ in range(steps):
            rect = rotate_rect(self.rect(), self.width, self.height)
            self.width, self.height = self.height, self.width
            self.pixel_width, self.pixel_height = self.pixel_height, self.pixel_width
            px, py = (field.value() for field in self.padding_fields)
            for field, value in zip(self.padding_fields, (py, px)):
                field.blockSignals(True)
                field.setValue(value)
                field.blockSignals(False)
            self.rotation = (self.rotation + 1) % 4
            self.roi.maxBounds = QRectF(0, 0, self.width, self.height)
            self.set_rect(rect)
        self.apply_rotation()
        if steps % 2 and ":" in preset:
            preset = ":".join(reversed(preset.split(":")))
        self.set_preset(preset)
        self.save_segment()
        self.fit()

    def apply_rotation(self):
        transform = QTransform()
        w, h = self.video.size().width(), self.video.size().height()
        if self.rotation == 1:
            transform.translate(h, 0)
        elif self.rotation == 2:
            transform.translate(w, h)
        elif self.rotation == 3:
            transform.translate(0, w)
        transform.rotate(90 * self.rotation)
        self.video.setTransform(transform)

    def fit(self):
        rect = QRectF(0, 0, self.width, self.height)
        self.view.setRange(rect, padding=0)

    def export(self):
        self.count_cancelled()
        self.save_segment()
        encoder = self.encoder.currentData()
        if encoder == "auto":
            self.resolving_encoder = True
            self.window.statusBar().showMessage("Detecting GPU encoder…")
            self.update_enabled()
            self.gpu_probe.start(
                "powershell.exe",
                [
                    "-NoProfile",
                    "-Command",
                    "ConvertTo-Json -InputObject @(Get-CimInstance Win32_VideoController | Select-Object Name) -Compress",
                ],
            )
        else:
            self.export_with_encoder(encoder)

    def encoder_probed(self):
        devices = json.loads(bytes(self.gpu_probe.readAllStandardOutput()))
        encoder = next(
            key
            for names, key in [
                (("nvidia",), "hevc_nvenc"),
                (("intel",), "hevc_qsv"),
                (("amd", "radeon"), "hevc_amf"),
            ]
            if key in self.compiled_encoders
            and any(
                name in device["Name"].lower() for name in names for device in devices
            )
        )
        self.resolving_encoder = False
        self.export_with_encoder(encoder)

    def export_with_encoder(self, encoder):
        self.export_jobs = []
        for index, segment in enumerate(self.segments):
            width, height = self.source_width, self.source_height
            if (self.source_rotation + segment.rotation) % 2:
                width, height = height, width
            x, y, w, h = segment.rect
            self.export_jobs.append(
                Export(
                    self.paths[self.index],
                    padded_rect(
                        (x * width, y * height, w * width, h * height),
                        segment.padding_x,
                        segment.padding_y,
                        width,
                        height,
                    ),
                    segment.rotation,
                    segment.start,
                    segment.end,
                    self.square.isChecked(),
                    encoder,
                    self.device.value(),
                    index + 1,
                    exact_crop=bool(segment.padding_x or segment.padding_y),
                )
            )
        self.export_index = 0
        self.log.clear()
        self.start_export_job()

    def start_export_job(self):
        self.job = self.export_jobs[self.export_index]
        self.export_log = ""
        self.container_rejected = False
        self.player.pause()
        self.segment_list.blockSignals(True)
        self.segment_list.setCurrentRow(self.export_index)
        self.segment_list.blockSignals(False)
        self.select_segment(self.export_index)
        self.segment_list.scrollToItem(self.segment_list.currentItem())
        self.output = self.job.output
        self.done.discard(self.job.source)
        self.running = True
        self.paused = False
        self.outcome = ""
        self.progress_buffer = ""
        self.progress_values = {}
        self.processing_position = self.job.start
        self.progress.setValue(0)
        self.window.statusBar().showMessage(
            f"Starting segment {self.export_index + 1}/{len(self.export_jobs)} • "
            f"{self.job.start:.3f} – {self.job.end:.3f} s"
        )
        self.log.appendPlainText(
            subprocess.list2cmdline([self.ffmpeg, *self.job.arguments()])
        )
        self.preview_changed()
        self.update_enabled()
        self.process.start(self.ffmpeg, self.job.arguments())

    def install_explorer(self):
        self.count_cancelled()
        self.running = True
        self.installing = True
        self.install_status.setText("Installing…")
        self.window.statusBar().showMessage("Installing in File Explorer…")
        self.update_enabled()
        arguments = ["-I", "-m", self.launcher_module, "--install-explorer"]
        self.process.start(str(Path(sys.executable).resolve()), arguments)

    def copy_logs(self):
        self.log.selectAll()
        self.log.copy()
        self.window.statusBar().showMessage("Logs copied to clipboard")

    def clear_logs(self):
        self.log.clear()
        self.window.statusBar().showMessage("Logs cleared")

    def read_log(self):
        text = bytes(self.process.readAllStandardError()).decode("utf-8")
        self.log.appendPlainText(text)
        if self.running and not self.installing and not self.detecting:
            self.export_log += text
            self.container_rejected |= (
                "Could not find tag for codec hevc" in self.export_log
                or "Only VP8 or VP9 or AV1 video" in self.export_log
            )
            self.export_log = self.export_log[-128:]
        if self.detecting_crop:
            self.crop_scan.read_log(text)
        elif self.detecting:
            self.scene_scan.read_log(text)

    def read_progress(self):
        if self.installing:
            self.log.appendPlainText(
                bytes(self.process.readAllStandardOutput()).decode("utf-8")
            )
            return
        self.progress_buffer += bytes(self.process.readAllStandardOutput()).decode(
            "utf-8"
        )
        lines = self.progress_buffer.split("\n")
        self.progress_buffer = lines.pop()
        for line in lines:
            key, _, value = line.strip().partition("=")
            self.progress_values[key] = value
            if key == "progress" and self.progress_values["out_time_us"] != "N/A":
                if self.detecting_crop:
                    duration = self.crop_scan.segment.end - self.crop_scan.segment.start
                    seconds = float(self.progress_values["out_time_us"]) / 1000000
                    self.progress.setValue(min(99, int(seconds / duration * 100)))
                    self.window.statusBar().showMessage(
                        f"Detecting crop borders • {self.progress.value()}%"
                    )
                    continue
                if self.detecting:
                    self.read_log()
                    self.detection_progress(
                        float(self.progress_values["out_time_us"]) / 1000000,
                        len(self.scene_scan.boundaries) - 1,
                    )
                    continue
                elapsed = min(
                    float(self.progress_values["out_time_us"]) / 1000000,
                    self.job.end - self.job.start,
                )
                self.progress.setValue(
                    round(elapsed / (self.job.end - self.job.start) * 100)
                )
                speed = self.progress_values["speed"]
                eta = ""
                if speed != "N/A" and float(speed.rstrip("x")) > 0:
                    eta = f" • ETA {(self.job.end - self.job.start - elapsed) / float(speed.rstrip('x')):.0f} s"
                self.window.statusBar().showMessage(
                    f"Processing segment {self.export_index + 1}/{len(self.export_jobs)} • "
                    f"{self.progress.value()}% • {self.progress_values['fps']} fps • {speed}{eta}"
                )
                self.processing_position = self.job.start + max(0, elapsed)

    def follow_progress(self):
        position = round(min(self.processing_position, self.job.end - 0.001) * 1000)
        if abs(self.player.position() - position) >= 100:
            self.player.setPosition(position)

    def preview_changed(self):
        follow = (
            self.running
            and not self.installing
            and not self.detecting
            and self.preview.isChecked()
        )
        if follow:
            self.player.pause()
            self.follow_timer.start()
        else:
            self.follow_timer.stop()
        self.transport.setEnabled(
            self.ready and not self.running and not self.detecting
        )

    def pause_export(self):
        process = psutil.Process(self.process.processId())
        if self.paused:
            for child in self.suspended_children:
                child.resume()
            process.resume()
        else:
            self.suspended_children = process.children(recursive=True)
            for child in self.suspended_children:
                child.suspend()
            process.suspend()
        self.paused = not self.paused
        self.pause.setText("Resume" if self.paused else "Pause")

    def stop_export(self):
        self.outcome = "stop"
        if self.paused:
            self.pause_export()
        self.process.write(b"q\n")

    def cancel_export(self):
        self.outcome = "cancel"
        if self.process.state() == QProcess.ProcessState.Starting:
            self.process.started.connect(
                self.cancel_export, Qt.ConnectionType.SingleShotConnection
            )
            return
        # Tool-manager launchers can own the actual FFmpeg child process.
        children = psutil.Process(self.process.processId()).children(recursive=True)
        for child in children:
            child.kill()
        psutil.wait_procs(children)
        self.process.kill()

    def finished(self, code, status):
        if self.installing:
            self.read_progress()
            self.read_log()
            self.running = False
            self.installing = False
            self.install_status.clear()
            self.window.statusBar().showMessage("Ready")
            if code == 0 and status == QProcess.ExitStatus.NormalExit:
                self.install_status.setText("Installed in File Explorer")
                self.window.statusBar().showMessage("Installed in File Explorer")
            self.update_enabled()
            return
        self.read_log()
        self.read_progress()
        detecting = self.detecting
        detecting_crop = self.detecting_crop
        self.detecting_crop = False
        self.detecting = False
        self.running = False
        self.follow_timer.stop()
        self.pause.setText("Pause")
        if self.outcome == "cancel":
            if detecting:
                self.window.statusBar().showMessage(
                    "Crop detection canceled"
                    if detecting_crop
                    else "Scene detection canceled"
                )
            else:
                for job in self.export_jobs[: self.export_index + 1]:
                    job.output.unlink()
                self.output = None
                self.window.statusBar().showMessage("Canceled — output deleted")
        elif code != 0 or status != QProcess.ExitStatus.NormalExit:
            if (
                code != 0
                and status == QProcess.ExitStatus.NormalExit
                and not self.outcome
                and not detecting
                and self.job.container != "mkv"
                and self.container_rejected
            ):
                failed_output = self.output
                failed_output.unlink()
                for index in range(self.export_index, len(self.export_jobs)):
                    self.export_jobs[index] = replace(
                        self.export_jobs[index], container="mkv"
                    )
                self.log.appendPlainText(
                    f"Container fallback: {failed_output.suffix} rejected HEVC. "
                    "Retrying this segment and exporting remaining segments as MKV "
                    "with the same video encoder and copied audio. "
                    f"Removed failed output: {failed_output}\n"
                    f"New output: {self.export_jobs[self.export_index].output}"
                )
                self.start_export_job()
                return
            self.window.statusBar().showMessage(
                f"FFmpeg exited with code {code} — see Process log"
            )
        elif self.outcome == "stop":
            self.window.statusBar().showMessage("Stopped — output saved")
        elif detecting_crop:
            x, y, w, h = self.crop_scan.rect()
            self.set_preset("Custom")
            self.set_rect(
                (
                    x / self.pixel_width * self.width,
                    y / self.pixel_height * self.height,
                    w / self.pixel_width * self.width,
                    h / self.pixel_height * self.height,
                )
            )
            self.fit()
            self.progress.setValue(100)
            self.window.statusBar().showMessage(
                "Crop detection complete — selected segment updated"
            )
        elif detecting:
            self.replace_segments(self.scene_scan.ranges())
        else:
            if self.export_index + 1 < len(self.export_jobs):
                self.export_index += 1
                self.start_export_job()
                return
            self.progress.setValue(100)
            self.window.statusBar().showMessage(
                f"Complete — {len(self.export_jobs)} segments saved"
            )
            self.done.add(self.job.source)
            self.refresh_files()
            if self.notify.isChecked():
                QApplication.beep()
                QApplication.alert(self.window)
            if self.advance.isChecked() and self.index + 1 < len(self.paths):
                self.load(self.index + 1)
                self.auto_export_pending = self.auto.isChecked()
            else:
                if self.advance.isChecked():
                    self.unload()
                    self.window.statusBar().showMessage(
                        f"Complete — {len(self.export_jobs)} segments saved"
                    )
                if self.quit_done.isChecked():
                    self.countdown("quit", self.quit_delay.value())
        if (
            detecting
            and not detecting_crop
            and not self.segments
            and self.auto_segment.isChecked()
        ):
            message = self.window.statusBar().currentMessage()
            self.add_segment()
            self.window.statusBar().showMessage(message)
        self.update_enabled()

    def countdown(self, action, seconds):
        self.count_action = action
        self.count_remaining = seconds
        self.count_label.setText(f"{action.capitalize()} in {seconds} s")
        self.count_now.show()
        self.count_cancel.show()
        self.count_timer.start()
        self.count_now.setEnabled(action == "quit" or self.ready)
        self.update_enabled()

    def count_tick(self):
        if self.count_action == "export" and not self.ready:
            self.count_label.setText("Waiting for video to load")
            return
        self.count_remaining -= 1
        self.count_label.setText(
            f"{self.count_action.capitalize()} in {self.count_remaining} s"
        )
        if self.count_remaining == 0:
            self.count_execute()

    def count_execute(self):
        action = self.count_action
        self.count_cancelled()
        if action == "quit":
            self.window.close()
        elif self.ready:
            self.export()

    def count_cancelled(self):
        self.auto_export_pending = False
        self.count_timer.stop()
        self.count_label.clear()
        self.count_now.hide()
        self.count_cancel.hide()
        self.update_enabled()

    def update_enabled(self):
        self.apply_appearance_button.setEnabled(
            (
                self.theme.currentData() != self.applied_theme
                or self.icon.currentData() != self.applied_icon
            )
            and not (
                self.running
                or self.loading
                or self.resolving_encoder
                or self.detecting
                or self.count_timer.isActive()
            )
        )
        self.update_merge_enabled()
        self.update_split_enabled()
        self.update_navigation()
        busy = self.running or self.loading or self.resolving_encoder
        self.add_segment_action.setEnabled(self.ready and not busy)
        self.add_segment_button.setEnabled(self.ready and not busy)
        self.detect_action.setEnabled(self.ready and not busy)
        self.detect_button.setEnabled(self.ready and not busy)
        self.detect_crop_action.setEnabled(
            self.ready and self.active_segment >= 0 and not busy
        )
        self.detect_crop_button.setEnabled(
            self.ready and self.active_segment >= 0 and not busy
        )
        self.clear_segments_action.setEnabled(bool(self.segments) and not busy)
        self.clear_segments_button.setEnabled(bool(self.segments) and not busy)
        self.segment_list.setEnabled(self.ready and not busy)
        self.check_update_action.setEnabled(not busy)
        self.check_update_button.setEnabled(not busy)
        self.install_button.setEnabled(not busy)
        self.file_list.setEnabled(bool(self.paths) and not busy)
        self.select_none_button.setEnabled(self.index >= 0 and not busy)
        self.clear_files_button.setEnabled(bool(self.paths) and not busy)
        self.count_now.setEnabled(self.count_action == "quit" or self.ready)
        self.open_button.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.previous.setEnabled(not busy and self.index > 0)
        self.next.setEnabled(not busy and 0 <= self.index < len(self.paths) - 1)
        self.export_button.setEnabled(self.ready and bool(self.segments) and not busy)
        self.crop_page.setEnabled(self.ready and bool(self.segments) and not busy)
        self.roi.setEnabled(self.ready and bool(self.segments) and not busy)
        self.encoder.setEnabled(not busy)
        self.device.setEnabled(not busy)
        self.transport.setEnabled(self.ready and not busy)
        self.cancel.setEnabled(self.running and not self.installing)
        self.pause.setEnabled(
            self.running and not self.installing and not self.detecting
        )
        self.stop.setEnabled(
            self.running and not self.installing and not self.detecting
        )
        self.cancel.setText(
            "Cancel detection" if self.detecting else "Cancel and delete"
        )
        self.locate.setEnabled(self.output is not None and not self.running)

    def locate_output(self):
        QProcess.startDetached("explorer.exe", ["/select,", str(self.output)])

    def view_releases(self):
        QDesktopServices.openUrl(QUrl(RELEASES_URL))

    def check_updates(self):
        self.count_cancelled()
        self.player.pause()
        self.update_dialog.check()

    def update_busy(self, busy):
        self.explorer_dialog.setEnabled(not busy)
        self.window.centralWidget().setEnabled(not busy)
        self.files_dock.setEnabled(not busy)
        self.segments_dock.setEnabled(not busy)
        self.window.menuBar().setEnabled(not busy)
        self.window.setAcceptDrops(not busy)

    def install_update(self, path):
        self.window.pending_installer = path
        self.window.close()

    def apply_appearance(self):
        theme_changed = self.theme.currentData() != self.applied_theme
        if theme_changed:
            answer = QMessageBox.question(
                self.window,
                "Restart to apply appearance?",
                "The app will restart to apply the selected appearance. "
                "Unsaved segment edits will be lost. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.settings.setValue("appearance/theme", self.theme.currentData())
        self.settings.setValue("appearance/icon", self.icon.currentData())
        self.settings.sync()
        self.applied_icon = self.icon.currentData()
        QApplication.setWindowIcon(self.icons[self.applied_icon])
        self.window.setWindowIcon(self.icons[self.applied_icon])
        if theme_changed:
            self.restart_requested = True
            self.window.close()
        else:
            self.update_enabled()

    def show_settings(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Saved settings")
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            self.settings.fileName()
            + "\n\n"
            + "\n".join(
                f"{key} = {self.settings.value(key)}" for key in self.settings.allKeys()
            )
        )
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(600, 400)
        dialog.exec()
        dialog.deleteLater()

    def save_report(self):
        filename, _ = QFileDialog.getSaveFileName(
            self.window, "Save diagnostic report", "crop-report.txt"
        )
        if filename:
            Path(filename).write_text(self.log.toPlainText(), encoding="utf-8")

    def eventFilter(self, watched, event):
        if (
            watched is self.seek
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            option = QStyleOptionSlider()
            self.seek.initStyleOption(option)
            handle = self.seek.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                option,
                QStyle.SubControl.SC_SliderHandle,
                self.seek,
            )
            if not handle.contains(event.position().toPoint()):
                groove = self.seek.style().subControlRect(
                    QStyle.ComplexControl.CC_Slider,
                    option,
                    QStyle.SubControl.SC_SliderGroove,
                    self.seek,
                )
                self.seek.setValue(
                    QStyle.sliderValueFromPosition(
                        self.seek.minimum(),
                        self.seek.maximum(),
                        round(event.position().x() - groove.x() - handle.width() / 2),
                        groove.width() - handle.width(),
                        option.upsideDown,
                    )
                )
                return True
        if watched in (
            self.window,
            self.files_dock.widget(),
            self.file_list.viewport(),
        ):
            if (
                event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove)
                and not self.running
                and not self.detecting
                and not self.loading
                and not self.resolving_encoder
                and event.mimeData().hasUrls()
            ):
                event.acceptProposedAction()
                return True
            if (
                event.type() == QEvent.Type.Drop
                and not self.running
                and not self.detecting
                and not self.loading
                and not self.resolving_encoder
            ):
                self.add_paths([url.toLocalFile() for url in event.mimeData().urls()])
                event.acceptProposedAction()
                return True
            if watched is self.window and event.type() == QEvent.Type.Close:
                if self.update_dialog.busy:
                    event.ignore()
                    return True
                if self.running:
                    event.ignore()
                    if not self.closing:
                        self.closing = True
                        self.process.finished.connect(self.window.close)
                        if not self.installing:
                            self.cancel_export()
                    return True
                for worker in self.update_dialog.workers:
                    worker.wait()
                if self.probe.state() != QProcess.ProcessState.NotRunning:
                    self.probe.finished.disconnect(self.media_probed)
                    self.probe.kill()
                    self.probe.waitForFinished()
                if self.gpu_probe.state() != QProcess.ProcessState.NotRunning:
                    self.gpu_probe.finished.disconnect(self.encoder_probed)
                    self.gpu_probe.kill()
                    self.gpu_probe.waitForFinished()
                self.window.removeEventFilter(self)
                self.seek.removeEventFilter(self)
                self.viewport.removeEventFilter(self)
                self.files_dock.widget().removeEventFilter(self)
                self.file_list.viewport().removeEventFilter(self)
                self.resize_timer.stop()
                self.follow_timer.stop()
                self.count_timer.stop()
                self.load_timer.stop()
                if self.ready:
                    self.save_crop_settings()
                self.player.stop()
                self.player.setSource(QUrl())
                self.video.videoSink().setVideoFrame(QVideoFrame())
                self.settings.setValue(
                    "mainWindow/geometry", self.window.saveGeometry()
                )
                self.settings.setValue("mainWindow/state", self.window.saveState(1))
                self.settings.setValue(
                    "mainWindow/splitterState", self.splitter.saveState()
                )
                self.settings.sync()
        if watched is self.viewport:
            if event.type() == QEvent.Type.Resize:
                self.resize_timer.start()
            if event.type() == QEvent.Type.Wheel:
                if self.wheel.isChecked():
                    point = self.view.mapSceneToView(
                        self.graphics.mapToScene(event.position().toPoint())
                    )
                    self.view.scaleBy(
                        x=1 / 1.1 if event.angleDelta().y() > 0 else 1.1, center=point
                    )
                return True
        return super().eventFilter(watched, event)


def main():
    if sys.argv[1:] == ["--install-explorer"]:
        sys.exit(integrations.install())
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("FastVideoCropper")
    controller = Application(
        paths=[arg for arg in sys.argv[1:] if arg not in ("-NoProfile", "-Minimize")],
        no_profile="-NoProfile" in sys.argv[1:],
    )
    if "-Minimize" in sys.argv[1:]:
        controller.window.showMinimized()
    else:
        controller.window.show()
    result = app.exec()
    if controller.restart_requested:
        subprocess.Popen(
            [sys.executable, "-m", controller.launcher_module, *sys.argv[1:]],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    if controller.window.pending_installer is not None:
        os.startfile(controller.window.pending_installer)
    return result
