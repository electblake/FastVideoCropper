import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import qt_themes
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from fastvideocropper import app, installed


@pytest.fixture
def controller(qtbot, tmp_path, monkeypatch, request):
    monkeypatch.setattr(app, "user_config_path", lambda *args, **kwargs: tmp_path)
    palette = QApplication.palette()
    icon = QApplication.windowIcon()
    stylesheet = QApplication.instance().styleSheet()
    controller = app.Application(
        no_profile=request.node.get_closest_marker("profile") is None
    )
    qtbot.addWidget(controller.window)
    if request.node.get_closest_marker("visible"):
        controller.window.show()
    else:
        controller.window.showMinimized()
    yield controller
    controller.window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.instance().setStyleSheet(stylesheet)
    QApplication.setPalette(palette)
    QApplication.setWindowIcon(icon)


def test_system_button_size_tiers(controller, qtbot):
    normal = QPushButton("Normal")
    large = QPushButton("Large")
    qtbot.addWidget(normal)
    qtbot.addWidget(large)
    large.setProperty("buttonSize", "large")
    large.ensurePolished()
    assert (
        large.minimumHeight() == large.maximumHeight() == normal.sizeHint().height() * 2
    )
    assert controller.export_button.height() == normal.sizeHint().height() * 2
    assert large.font().pointSizeF() == pytest.approx(normal.font().pointSizeF() * 1.5)
    assert controller.export_button.font().pointSizeF() == pytest.approx(
        normal.font().pointSizeF() * 1.5
    )
    for button in (controller.stop, controller.cancel, controller.pause):
        assert button.height() == round(normal.sizeHint().height() * 1.5)
        assert button.font().pointSizeF() == pytest.approx(
            normal.font().pointSizeF() * 1.25
        )


def test_theme_apply_cancel_leaves_settings_and_window(controller, monkeypatch):
    controller.theme.setCurrentIndex(controller.theme.findData("nord"))
    controller.icon.setCurrentIndex(controller.icon.findData("violet"))
    assert controller.apply_appearance_button.isEnabled()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel
    )
    controller.apply_appearance_button.click()
    assert not controller.settings.contains("appearance/theme")
    assert not controller.settings.contains("appearance/icon")
    assert QApplication.windowIcon().cacheKey() == controller.icons["blue"].cacheKey()
    assert not controller.restart_requested
    assert controller.window.isVisible()


def test_theme_apply_confirms_persists_and_closes(controller, monkeypatch):
    controller.theme.setCurrentIndex(controller.theme.findData("nord"))
    controller.icon.setCurrentIndex(controller.icon.findData("violet"))
    question = Mock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "question", question)
    controller.apply_appearance_button.click()
    assert controller.settings.value("appearance/theme") == "nord"
    assert controller.settings.value("appearance/icon") == "violet"
    assert controller.restart_requested
    assert not controller.window.isVisible()
    assert "Unsaved segment" in question.call_args.args[2]
    assert question.call_args.args[-1] == QMessageBox.StandardButton.Cancel


@pytest.mark.parametrize(
    "busy", ["running", "loading", "resolving_encoder", "detecting"]
)
def test_theme_apply_disabled_when_busy(controller, busy):
    controller.theme.setCurrentIndex(controller.theme.findData("nord"))
    setattr(controller, busy, True)
    controller.update_enabled()
    assert not controller.apply_appearance_button.isEnabled()
    setattr(controller, busy, False)
    controller.update_enabled()
    assert controller.apply_appearance_button.isEnabled()
    controller.theme.setCurrentIndex(0)
    assert not controller.apply_appearance_button.isEnabled()


def test_restart_disabled_during_automatic_countdown(controller):
    controller.theme.setCurrentIndex(controller.theme.findData("nord"))
    controller.countdown("quit", 30)
    assert not controller.apply_appearance_button.isEnabled()
    controller.count_cancelled()
    assert controller.apply_appearance_button.isEnabled()


@pytest.mark.parametrize("name", sorted(qt_themes.get_themes()))
@pytest.mark.profile
def test_saved_theme_applied_before_graphics(controller, qtbot, name):
    controller.settings.setValue("appearance/theme", name)
    controller.window.close()
    restored = app.Application()
    qtbot.addWidget(restored.window)
    expected = qt_themes.get_themes()[name].base
    assert restored.theme.currentData() == name
    assert restored.window.palette().color(QPalette.ColorRole.Window) == expected
    assert restored.graphics.backgroundBrush().color() == expected
    assert restored.range_graph.backgroundBrush().color() == expected
    assert not restored.apply_appearance_button.isEnabled()
    restored.export_button.ensurePolished()
    normal = QPushButton("Normal")
    large = QPushButton("Large")
    qtbot.addWidget(normal)
    qtbot.addWidget(large)
    large.setProperty("buttonSize", "large")
    large.ensurePolished()
    assert large.minimumHeight() == normal.sizeHint().height() * 2
    assert restored.export_button.minimumHeight() == normal.sizeHint().height() * 2
    assert large.font().pointSizeF() == pytest.approx(
        QApplication.font().pointSizeF() * 1.5
    )
    assert restored.export_button.font().pointSizeF() == pytest.approx(
        QApplication.font().pointSizeF() * 1.5
    )
    for button in (restored.stop, restored.cancel, restored.pause):
        button.ensurePolished()
        assert button.minimumHeight() == round(normal.sizeHint().height() * 1.5)
        assert button.font().pointSizeF() == pytest.approx(
            QApplication.font().pointSizeF() * 1.25
        )
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Disabled):
        for role in (QPalette.ColorRole.Button, QPalette.ColorRole.ButtonText):
            assert restored.export_button.palette().color(
                group, role
            ) == QApplication.palette().color(group, role)
    restored.window.close()


def test_theme_keyboard_cancel(controller, qtbot):
    controller.theme.setCurrentIndex(controller.theme.findData("nord"))
    assert controller.apply_appearance_button.isEnabled()

    def cancel():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        assert dialog.defaultButton() == dialog.button(
            QMessageBox.StandardButton.Cancel
        )
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    QTimer.singleShot(0, cancel)
    controller.apply_appearance_button.click()
    assert controller.window.isVisible()
    assert not controller.restart_requested
    controller.theme.setCurrentIndex(0)
    assert not controller.apply_appearance_button.isEnabled()


@pytest.mark.parametrize("scale", [1.0, 1.5])
@pytest.mark.visible
def test_appearance_controls_fit_settings_and_keyboard_order(controller, qtbot, scale):
    controller.tabs.setCurrentIndex(1)
    group = controller.theme.parentWidget()
    font = group.font()
    font.setPointSizeF(font.pointSizeF() * scale)
    group.setFont(font)
    controller.window.resize(1200, 800)
    qtbot.wait(50)
    scroll = group.parentWidget().parentWidget().parentWidget()
    assert scroll.horizontalScrollBar().maximum() == 0
    assert (
        controller.theme.geometry().right()
        < controller.apply_appearance_button.geometry().left()
    )
    assert controller.apply_appearance_button.geometry().right() < group.width()
    controller.theme.setCurrentIndex(controller.theme.findData("nord"))
    controller.theme.setFocus()
    qtbot.keyClick(controller.theme, Qt.Key.Key_Tab)
    assert controller.icon.hasFocus()
    assert controller.icon.geometry().top() > controller.theme.geometry().bottom()
    qtbot.keyClick(controller.icon, Qt.Key.Key_Tab)
    assert controller.apply_appearance_button.hasFocus()


@pytest.mark.parametrize("name", ["blue", "charcoal", "gray", "violet"])
@pytest.mark.profile
def test_icon_applies_live_and_restores(controller, qtbot, monkeypatch, name):
    question = Mock()
    monkeypatch.setattr(QMessageBox, "question", question)
    controller.icon.setCurrentIndex(
        controller.icon.findData("violet" if name == "blue" else "blue")
    )
    controller.apply_appearance_button.click()
    controller.icon.setCurrentIndex(controller.icon.findData(name))
    assert controller.apply_appearance_button.isEnabled()
    with qtbot.waitSignal(controller.window.windowIconChanged):
        controller.apply_appearance_button.click()
    question.assert_not_called()
    assert not controller.restart_requested
    assert controller.window.isVisible()
    assert controller.settings.value("appearance/icon") == name
    assert (
        controller.window.windowIcon().cacheKey() == controller.icons[name].cacheKey()
    )
    assert not controller.apply_appearance_button.isEnabled()
    controller.window.close()
    restored = app.Application()
    qtbot.addWidget(restored.window)
    assert restored.icon.currentData() == name
    assert not restored.icons[name].isNull()
    assert restored.window.windowIcon().cacheKey() == restored.icons[name].cacheKey()
    assert not restored.apply_appearance_button.isEnabled()
    restored.window.close()


def test_packaged_icons_match_asset_groups(controller):
    root = Path(__file__).resolve().parents[1]
    groups = sorted(p.name for p in (root / "assets").iterdir() if p.is_dir())
    assert [
        controller.icon.itemData(i) for i in range(controller.icon.count())
    ] == groups
    for name in groups:
        assert (root / f"src/fastvideocropper/icons/{name}.ico").read_bytes() == (
            root / f"assets/{name}/icon.ico"
        ).read_bytes()


@pytest.mark.parametrize("launcher", [app, installed])
def test_restart_after_event_loop_preserves_launcher_and_arguments(
    monkeypatch, launcher
):
    events = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["fastvideocropper", "-NoProfile", "-Minimize", "video folder", "clip.mp4"],
    )
    application = Mock()
    application.exec.side_effect = lambda: events.append("exit") or 0
    monkeypatch.setattr(launcher, "QApplication", lambda args: application)
    module = (
        "fastvideocropper.installed" if launcher is installed else "fastvideocropper"
    )
    controller = SimpleNamespace(
        restart_requested=True,
        launcher_module=module,
        window=SimpleNamespace(showMinimized=Mock(), pending_installer=None),
    )
    monkeypatch.setattr(launcher, "Application", lambda *a, **kw: controller)
    launch = Mock(side_effect=lambda *a, **kw: events.append("launch"))
    monkeypatch.setattr(launcher.subprocess, "Popen", launch)
    assert launcher.main() == 0
    assert events == ["exit", "launch"]
    assert launch.call_args.args[0] == [
        sys.executable,
        "-m",
        module,
        "-NoProfile",
        "-Minimize",
        "video folder",
        "clip.mp4",
    ]
