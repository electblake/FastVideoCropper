"""Native widgets composed around Qt Multimedia and PyQtGraph's ROI."""

import json
import os
import subprocess
import sys
from pathlib import Path

import psutil
import pyqtgraph as pg
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
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QPen, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsRectItem,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_VERSION, integrations
from .encoding import Export, rotate_rect
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


class Application(QObject):
    """Application controller; all visual components are stock or third-party."""

    def __init__(
        self,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        folder=None,
        launcher_module=integrations.APP_MODULE,
    ):
        super().__init__()
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.launcher_module = launcher_module
        self.settings = QSettings("FastVideoCropper", "FastVideoCropper")
        if folder is not None:
            self.settings.setValue("folder_path", folder)
        self.paths = []
        self.index = 0
        self.done = set()
        self.turns = self.settings.value("turns", 0, int)
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
        self.output = None
        self.progress_buffer = ""
        self.progress_values = {}
        self.seek_pending = False
        self.segments = []
        self.source_segments = {}
        self.active_segment = -1
        self.restoring_segment = False
        self.detecting = False
        self.segment_regions = []
        self.export_jobs = []
        self.export_index = 0
        self.window = QMainWindow()
        self.window.pending_installer = None
        self.update_dialog = UpdateDialog(self.window)
        self.update_dialog.busy_changed.connect(self.update_busy)
        self.update_dialog.install_requested.connect(self.install_update)
        self.window.setWindowTitle("FastVideoCropper")
        self.window.resize(1200, 800)
        self.window.setAcceptDrops(True)
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
        self.build_ui()
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
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(500)
        self.resize_timer.timeout.connect(self.fit)
        self.window.installEventFilter(self)
        self.viewport = self.graphics.viewport()
        self.viewport.installEventFilter(self)
        self.update_enabled()

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
        self.detect_action = segment_menu.addAction(
            "&Detect segments…", self.show_scene_detection
        )
        self.clear_segments_action = segment_menu.addAction(
            "&Clear segments", self.clear_segments
        )
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
            "for folders, folder backgrounds, and drives."
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
        folder_form = QFormLayout()
        self.folder = QLineEdit(self.settings.value("folder_path", ""))
        self.folder.textChanged.connect(
            lambda value: self.settings.setValue("folder_path", value)
        )
        folder_form.addRow("&Folder", self.folder)
        layout.addLayout(folder_form)
        header = QHBoxLayout()
        self.open_button = self.button("Open videos…", self.open_files, header)
        self.open_action = action
        self.previous = self.button(
            "Previous", lambda: self.load(self.index - 1), header
        )
        self.next = self.button("Next", lambda: self.load(self.index + 1), header)
        self.title = QLabel("Open or drop videos to begin")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(self.title, 1)
        layout.addLayout(header)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.crop_summary = QLabel("No segment selected")
        self.crop_summary.setWordWrap(True)
        left_layout.addWidget(self.crop_summary)
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
        self.roi.sigRegionChanged.connect(self.geometry_changed)
        self.roi.sigRegionChangeFinished.connect(self.geometry_finished)
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
        self.seek.valueChanged.connect(self.player.setPosition)
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
        self.play = self.button("Play", self.toggle_play, buttons)
        self.mute = QCheckBox("Mute")
        self.mute.toggled.connect(self.audio.setMuted)
        buttons.addWidget(self.mute)
        self.time = QLabel("0.000 / 0.000 s")
        buttons.addWidget(self.time)
        buttons.addStretch()
        playback.addLayout(buttons)
        left_layout.addWidget(self.transport)
        self.progress = QProgressBar()
        left_layout.addWidget(self.progress)
        self.progress_text = QLabel("Ready")
        left_layout.addWidget(self.progress_text)
        process_buttons = QHBoxLayout()
        self.pause = self.button("Pause", self.pause_export, process_buttons)
        self.stop = self.button("Stop and keep", self.stop_export, process_buttons)
        self.cancel = self.button(
            "Cancel and delete", self.cancel_export, process_buttons
        )
        self.locate = self.button("Locate output", self.locate_output, process_buttons)
        left_layout.addLayout(process_buttons)
        splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Segments"))
        self.segment_list = QListWidget()
        self.segment_list.setAccessibleName("Video segments")
        self.segment_list.currentRowChanged.connect(self.select_segment)
        right_layout.addWidget(self.segment_list, 1)
        self.segment_summary = QLabel("No segments — detect scenes to begin")
        self.segment_summary.setWordWrap(True)
        right_layout.addWidget(self.segment_summary)
        segment_buttons = QHBoxLayout()
        self.detect_button = self.button(
            "Detect segments…", self.show_scene_detection, segment_buttons
        )
        self.clear_segments_button = self.button(
            "Clear segments", self.clear_segments, segment_buttons
        )
        right_layout.addLayout(segment_buttons)
        tabs = QTabWidget()
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
        rotation = QVBoxLayout()
        self.button("Rotate left", lambda: self.rotate(3), rotation)
        self.button("Rotate right", lambda: self.rotate(1), rotation)
        self.button("Reset rotation", lambda: self.rotate((-self.turns) % 4), rotation)
        form.addRow(rotation)
        self.lock = self.preference("&Lock aspect ratio", "lock", False, form)
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
        self.preset_status = QLabel("Aspect ratio: Custom")
        form.addRow(self.preset_status)
        center_row = QHBoxLayout()
        self.button("Center frame", self.center, center_row)
        self.button("Full frame", self.full_frame, center_row)
        form.addRow(center_row)
        self.zoom = self.preference("Zoom into frame", "zoom", False, form)
        self.zoom.toggled.connect(self.fit)
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
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        tabs.addTab(self.log, "Process log")
        self.export_button = self.button("Export segments", self.export, right_layout)
        self.advance = QCheckBox("Load next after completion")
        self.auto = QCheckBox("Auto-run next")
        self.quit_done = QCheckBox("Quit when done")
        for control, key in [
            (self.advance, "advance"),
            (self.auto, "auto"),
            (self.quit_done, "quit"),
        ]:
            control.setChecked(self.settings.value(key, False, bool))
            control.toggled.connect(
                lambda value, k=key: self.settings.setValue(k, value)
            )
            right_layout.addWidget(control)
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
        self.window.statusBar().showMessage(
            "Source preview • exports replace matching numbered segment files"
        )

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
        threshold.setSingleStep(0.05)
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
            self.detect_segments(threshold.value(), minimum.value())
        dialog.deleteLater()

    def detect_segments(self, threshold, minimum):
        self.count_cancelled()
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
        self.progress_text.setText(
            f"Detecting scenes • {self.progress.value()}% • "
            f"{seconds:.1f} / {duration:.1f} s scanned • {cuts} cuts found"
        )

    def replace_segments(self, ranges):
        x, y, w, h = self.rect()
        rect = x / self.width, y / self.height, w / self.width, h / self.height
        self.active_segment = -1
        self.segments[:] = [
            Segment(
                start,
                end,
                rect,
                self.turns,
                self.selected_preset,
                self.lock.isChecked(),
            )
            for start, end in ranges
        ]
        self.refresh_segments()
        self.segment_list.setCurrentRow(0)
        self.progress.setValue(100)
        self.progress_text.setText(
            f"Scene detection complete — {len(self.segments)} segments"
        )
        self.update_enabled()

    def clear_segments(self):
        self.count_cancelled()
        self.active_segment = -1
        self.segments.clear()
        self.refresh_segments()
        self.progress.setValue(0)
        self.progress_text.setText("Ready")
        self.update_enabled()

    def segment_text(self, index):
        segment = self.segments[index]
        width, height = self.source_width, self.source_height
        if (self.source_rotation + segment.turns) % 2:
            width, height = height, width
        x, y, w, h = segment.rect
        return (
            f"{index + 1:02d}   {segment.start:.3f} – {segment.end:.3f} s\n"
            f"Duration {segment.end - segment.start:.3f} s\n"
            f"Crop {w * width:.0f} × {h * height:.0f} at {x * width:.0f}, {y * height:.0f}\n"
            f"{segment.preset} • Rotation {segment.turns * 90}°"
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
        if self.segments:
            total = sum(segment.end - segment.start for segment in self.segments)
            self.segment_summary.setText(
                f"{len(self.segments)} segments • {total:.3f} s total"
            )
            self.export_button.setText(f"Export {len(self.segments)} segments")
        else:
            self.segment_summary.setText("No segments — detect scenes to begin")
            self.export_button.setText("Export segments")

    def save_segment(self):
        if self.active_segment < 0 or self.restoring_segment:
            return
        segment = self.segments[self.active_segment]
        x, y, w, h = self.rect()
        segment.rect = x / self.width, y / self.height, w / self.width, h / self.height
        segment.turns = self.turns
        segment.preset = self.selected_preset
        segment.locked = self.lock.isChecked()
        self.segment_list.item(self.active_segment).setText(
            self.segment_text(self.active_segment)
        )
        self.segment_regions[self.active_segment].setRegion(
            (segment.start, segment.end)
        )
        self.update_segment_summary()
        self.update_crop_summary()

    def select_segment(self, index):
        if index < 0:
            return
        self.save_segment()
        self.restoring_segment = True
        segment = self.segments[index]
        self.rotate((segment.turns - self.turns) % 4)
        x, y, w, h = segment.rect
        self.set_rect(
            (x * self.width, y * self.height, w * self.width, h * self.height)
        )
        self.set_preset(segment.preset)
        self.lock.setChecked(segment.locked)
        self.active_segment = index
        for row, region in enumerate(self.segment_regions):
            brush = self.window.palette().highlight().color()
            brush.setAlpha(130 if row == index else 60)
            region.setBrush(brush)
        self.restoring_segment = False
        self.update_crop_summary()
        self.fit()
        self.player.setPosition(round(segment.start * 1000))

    def update_crop_summary(self):
        if self.active_segment < 0:
            self.crop_summary.setText("No segment selected")
            return
        state = "Processing" if self.running and not self.detecting else "Selected"
        segment = self.segments[self.active_segment]
        x, y, w, h = segment.rect
        self.crop_summary.setText(
            f"{state} segment {self.active_segment + 1} of {len(self.segments)} • "
            f"{segment.start:.3f} – {segment.end:.3f} s\n"
            f"Crop {w * self.pixel_width:.0f} × {h * self.pixel_height:.0f} at "
            f"{x * self.pixel_width:.0f}, {y * self.pixel_height:.0f} • "
            f"{segment.preset} • Rotation {segment.turns * 90}° • "
            f"Aspect {'locked' if segment.locked else 'unlocked'}"
        )

    def select_timeline_segment(self, event):
        if (
            self.running
            or self.detecting
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return
        position = self.range_view.mapSceneToView(event.scenePos()).x()
        for index, segment in enumerate(self.segments):
            if segment.start <= position < segment.end:
                self.segment_list.setCurrentRow(index)
                break

    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.window,
            "Open videos",
            self.folder.text(),
            "Videos (*.mp4 *.mkv *.mov *.avi *.webm);;All files (*)",
        )
        if paths:
            self.paths = [Path(p) for p in paths]
            self.load(0)

    def load(self, index):
        self.count_cancelled()
        self.save_segment()
        self.active_segment = -1
        self.segments = self.source_segments.setdefault(self.paths[index], [])
        self.refresh_segments()
        self.ready = False
        self.loading = True
        self.index = index
        self.player.stop()
        self.player.setSource(QUrl())
        self.output = None
        self.progress.setValue(0)
        self.progress_text.setText("Loading video…")
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
        self.player.setSource(QUrl.fromLocalFile(str(self.paths[self.index])))
        self.title.setText(
            f"{self.index + 1}/{len(self.paths)} • {self.paths[self.index].name}"
            + (" • Done" if self.paths[self.index] in self.done else " • Pending")
        )
        self.output = None
        self.update_enabled()
        self.player.pause()

    def media_size(self, size):
        if size.isEmpty():
            return
        self.video.setSize(size)
        self.width, self.height = size.width(), size.height()
        if self.turns % 2:
            self.width, self.height = self.height, self.width
        self.apply_rotation()
        self.roi.maxBounds = QRectF(0, 0, self.width, self.height)
        saved = self.settings.value("geometry", [0.0, 0.0, 1.0, 1.0])
        preset = self.settings.value("preset", "Custom")
        centered = self.settings.value("centered", False, bool)
        x, y, w, h = [float(v) for v in saved]
        self.set_rect(
            (x * self.width, y * self.height, w * self.width, h * self.height)
        )
        self.ready = True
        self.loading = False
        self.progress_text.setText("Ready")
        self.set_preset(preset)
        self.apply_preset()
        if centered:
            self.center()
        self.geometry_changed()
        self.set_aspect_lock()
        self.fit()
        self.update_enabled()

        if self.segments:
            self.segment_list.setCurrentRow(0)

    def frame_changed(self, frame):
        self.seek_pending = False
        if (
            not self.ready
            and frame.isValid()
            and self.probe.state() == QProcess.ProcessState.NotRunning
            and self.player.duration() > 0
            and not self.player.source().isEmpty()
        ):
            self.pixel_width, self.pixel_height = self.source_width, self.source_height
            if (self.source_rotation + self.turns) % 2:
                self.pixel_width, self.pixel_height = (
                    self.pixel_height,
                    self.pixel_width,
                )
            display_size = self.video.nativeSize()
            if self.source_rotation % 2:
                display_size.transpose()
            self.media_size(display_size)

    def duration_changed(self, duration):
        self.seek.setRange(0, duration)
        self.position_changed(self.player.position())
        self.range_view.setXRange(0, duration / 1000, padding=0)

    def position_changed(self, position):
        self.seek.blockSignals(True)
        self.seek.setValue(position)
        self.seek.blockSignals(False)
        self.time.setText(
            f"{position / 1000:.3f} / {self.player.duration() / 1000:.3f} s"
        )

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
            self.settings.setValue(
                "geometry",
                [x / self.width, y / self.height, w / self.width, h / self.height],
            )
            self.settings.setValue(
                "centered",
                abs(x - (self.width - w) / 2) < 0.5
                and abs(y - (self.height - h) / 2) < 0.5,
            )
            selected = self.selected_preset
            if selected != "Custom":
                ratio = (
                    self.width / self.height
                    if selected == "Original"
                    else RATIOS[selected]
                )
                if h and abs(w / h - ratio) > 0.001:
                    self.set_preset("Custom")
            self.settings.setValue("preset", self.selected_preset)
            self.save_segment()

    def geometry_finished(self):
        if self.zoom.isChecked():
            self.fit()

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
            center = [1 - pos[0], 1 - pos[1]]
            if self.lock.isChecked():
                center = [0 if v == 0.5 else v for v in center]
            self.roi.addScaleHandle(pos, center, lockAspect=self.lock.isChecked())
        self.save_segment()

    def set_preset(self, name):
        self.selected_preset = name
        self.preset_group.setExclusive(False)
        for label, button in self.preset_buttons.items():
            button.setChecked(label == name)
        self.preset_group.setExclusive(True)
        self.preset_status.setText(f"Aspect ratio: {name}")

    def choose_preset(self, button):
        self.set_preset(button.text())
        self.apply_preset()

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
        self.settings.setValue("preset", name)
        self.geometry_finished()

    def center(self):
        _, _, w, h = self.rect()
        self.set_rect(((self.width - w) / 2, (self.height - h) / 2, w, h))
        self.geometry_finished()

    def full_frame(self):
        self.set_rect((0, 0, self.width, self.height))
        self.fit()

    def rotate(self, steps):
        preset = self.selected_preset
        for _ in range(steps):
            rect = rotate_rect(self.rect(), self.width, self.height)
            self.width, self.height = self.height, self.width
            self.pixel_width, self.pixel_height = self.pixel_height, self.pixel_width
            self.turns = (self.turns + 1) % 4
            self.roi.maxBounds = QRectF(0, 0, self.width, self.height)
            self.set_rect(rect)
        self.apply_rotation()
        if steps % 2 and ":" in preset:
            preset = ":".join(reversed(preset.split(":")))
        self.set_preset(preset)
        self.settings.setValue("preset", preset)
        self.settings.setValue("turns", self.turns)
        self.save_segment()
        self.fit()

    def apply_rotation(self):
        transform = QTransform()
        w, h = self.video.size().width(), self.video.size().height()
        if self.turns == 1:
            transform.translate(h, 0)
        elif self.turns == 2:
            transform.translate(w, h)
        elif self.turns == 3:
            transform.translate(0, w)
        transform.rotate(90 * self.turns)
        self.video.setTransform(transform)

    def fit(self):
        rect = QRectF(0, 0, self.width, self.height)
        if self.zoom.isChecked():
            rect = QRectF(*self.rect()).adjusted(-50, -50, 50, 50).intersected(rect)
        self.view.setRange(rect, padding=0)

    def export(self):
        self.count_cancelled()
        self.save_segment()
        encoder = self.encoder.currentData()
        if encoder == "auto":
            self.resolving_encoder = True
            self.progress_text.setText("Detecting GPU encoder…")
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
            if (self.source_rotation + segment.turns) % 2:
                width, height = height, width
            x, y, w, h = segment.rect
            self.export_jobs.append(
                Export(
                    self.paths[self.index],
                    (x * width, y * height, w * width, h * height),
                    segment.turns,
                    segment.start,
                    segment.end,
                    self.square.isChecked(),
                    encoder,
                    self.device.value(),
                    index + 1,
                )
            )
        self.export_index = 0
        self.log.clear()
        self.start_export_job()

    def start_export_job(self):
        self.job = self.export_jobs[self.export_index]
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
        self.seek_pending = False
        self.progress.setValue(0)
        self.progress_text.setText(
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
        self.progress_text.setText("Installing in File Explorer…")
        self.update_enabled()
        arguments = ["-I", "-m", self.launcher_module, "--install-explorer"]
        self.process.start(str(Path(sys.executable).resolve()), arguments)

    def read_log(self):
        text = bytes(self.process.readAllStandardError()).decode("utf-8")
        self.log.appendPlainText(text)
        if self.detecting:
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
                self.progress_text.setText(
                    f"Processing segment {self.export_index + 1}/{len(self.export_jobs)} • "
                    f"{self.progress.value()}% • {self.progress_values['fps']} fps • {speed}{eta}"
                )
                self.processing_position = self.job.start + max(0, elapsed)

    def follow_progress(self):
        position = round(min(self.processing_position, self.job.end - 0.001) * 1000)
        if not self.seek_pending and abs(self.player.position() - position) >= 100:
            self.seek_pending = True
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
            self.progress_text.setText("Ready")
            if code == 0 and status == QProcess.ExitStatus.NormalExit:
                self.install_status.setText("Installed in File Explorer")
                self.progress_text.setText("Installed in File Explorer")
            self.update_enabled()
            return
        self.read_log()
        self.read_progress()
        detecting = self.detecting
        self.detecting = False
        self.running = False
        self.follow_timer.stop()
        self.pause.setText("Pause")
        if self.outcome == "cancel":
            if detecting:
                self.progress_text.setText("Scene detection canceled")
            else:
                self.output.unlink()
                self.output = None
                self.progress_text.setText("Canceled — output deleted")
        elif code != 0:
            self.progress_text.setText(
                f"FFmpeg exited with code {code} — see Process log"
            )
        elif self.outcome == "stop":
            self.progress_text.setText("Stopped — output saved")
        elif detecting:
            self.replace_segments(self.scene_scan.ranges())
        else:
            if self.export_index + 1 < len(self.export_jobs):
                self.export_index += 1
                self.start_export_job()
                return
            self.progress.setValue(100)
            self.progress_text.setText(
                f"Complete — {len(self.export_jobs)} segments saved"
            )
            self.done.add(self.job.source)
            self.title.setText(
                f"{self.index + 1}/{len(self.paths)} • {self.job.source.name} • Done"
            )
            if self.notify.isChecked():
                QApplication.beep()
                QApplication.alert(self.window)
            if self.advance.isChecked() and self.index + 1 < len(self.paths):
                self.load(self.index + 1)
                if self.auto.isChecked() and self.segments:
                    self.countdown("export", self.auto_delay.value())
            elif self.quit_done.isChecked():
                self.countdown("quit", self.quit_delay.value())
        self.update_enabled()

    def countdown(self, action, seconds):
        self.count_action = action
        self.count_remaining = seconds
        self.count_label.setText(f"{action.capitalize()} in {seconds} s")
        self.count_now.show()
        self.count_cancel.show()
        self.count_timer.start()
        self.count_now.setEnabled(action == "quit" or self.ready)

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
        self.count_timer.stop()
        self.count_label.clear()
        self.count_now.hide()
        self.count_cancel.hide()

    def update_enabled(self):
        self.update_crop_summary()
        busy = self.running or self.loading or self.resolving_encoder
        self.detect_action.setEnabled(self.ready and not busy)
        self.detect_button.setEnabled(self.ready and not busy)
        self.clear_segments_action.setEnabled(bool(self.segments) and not busy)
        self.clear_segments_button.setEnabled(bool(self.segments) and not busy)
        self.segment_list.setEnabled(self.ready and not busy)
        self.check_update_action.setEnabled(not busy)
        self.check_update_button.setEnabled(not busy)
        self.install_button.setEnabled(not busy)
        self.folder.setEnabled(not busy)
        self.count_now.setEnabled(self.count_action == "quit" or self.ready)
        self.open_button.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.previous.setEnabled(not busy and self.index > 0)
        self.next.setEnabled(not busy and self.index + 1 < len(self.paths))
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
        self.window.menuBar().setEnabled(not busy)
        self.window.setAcceptDrops(not busy)

    def install_update(self, path):
        self.window.pending_installer = path
        self.window.close()

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
        if watched is self.window:
            if (
                event.type() == QEvent.Type.DragEnter
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
                self.paths = [
                    Path(url.toLocalFile()) for url in event.mimeData().urls()
                ]
                self.load(0)
                event.acceptProposedAction()
                return True
            if event.type() == QEvent.Type.Close:
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
                self.viewport.removeEventFilter(self)
                self.resize_timer.stop()
                self.follow_timer.stop()
                self.count_timer.stop()
                self.player.stop()
                self.player.setSource(QUrl())
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
    controller = Application(folder=sys.argv[1] if len(sys.argv) > 1 else None)
    controller.window.show()
    result = app.exec()
    if controller.window.pending_installer is not None:
        os.startfile(controller.window.pending_installer)
    return result
