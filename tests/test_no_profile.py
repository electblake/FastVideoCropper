import os
import subprocess
import sys
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from fastvideocropper import app, installed


@pytest.mark.parametrize("existing_profile", [False, True])
def test_no_profile_never_reads_or_writes_profile(
    qtbot, tmp_path, monkeypatch, source, existing_profile
):
    profile = tmp_path / "profile"
    settings_path = profile / "settings.ini"
    if existing_profile:
        saved = QSettings(str(settings_path), QSettings.Format.IniFormat)
        saved.setValue("appearance/theme", "invalid theme must never be read")
        saved.setValue("appearance/icon", "invalid icon must never be read")
        saved.setValue("mute", True)
        saved.setValue("device", 7)
        saved.sync()
        original = settings_path.read_bytes()
    config_path = Mock(return_value=profile)
    settings_factory = Mock(side_effect=AssertionError("Persistent settings accessed"))
    monkeypatch.setattr(app, "user_config_path", config_path)
    monkeypatch.setattr(app, "QSettings", settings_factory)

    c = app.Application(paths=[source], no_profile=True)
    qtbot.addWidget(c.window)
    c.window.showMinimized()
    qtbot.waitUntil(lambda: c.ready, timeout=15000)
    assert c.applied_theme == ""
    assert c.applied_icon == "blue"
    assert not c.mute.isChecked()
    assert c.device.value() == 0
    c.mute.setChecked(True)
    c.device.setValue(2)
    c.icon.setCurrentIndex(c.icon.findData("violet"))
    c.apply_appearance()
    c.replace_segments([(0, 1)])
    c.rotate(1)
    c.set_rect((10, 20, 100, 200))
    c.save_crop_settings()
    assert c.settings.value("crop/turns", type=int) == 1
    assert c.settings.value("mute", type=bool)

    def inspect_settings():
        dialog = QApplication.activeModalWidget()
        text = dialog.findChild(QPlainTextEdit).toPlainText()
        assert "Session only" in text
        assert "appearance/icon = violet" in text
        dialog.reject()

    QTimer.singleShot(0, inspect_settings)
    c.show_settings()
    c.window.close()
    c.settings.sync()
    with qtbot.waitSignal(c.destroyed):
        c.window.deleteLater()
    fresh = app.Application(no_profile=True)
    qtbot.addWidget(fresh.window)
    assert not fresh.mute.isChecked()
    assert fresh.device.value() == 0
    assert fresh.applied_icon == "blue"
    assert not fresh.settings.contains("mainWindow/geometry")
    assert not fresh.settings.contains("crop/rect")
    fresh.window.close()
    with qtbot.waitSignal(fresh.destroyed):
        fresh.window.deleteLater()
    config_path.assert_not_called()
    settings_factory.assert_not_called()
    if existing_profile:
        assert settings_path.read_bytes() == original
        assert list(profile.iterdir()) == [settings_path]
    else:
        assert not profile.exists()


@pytest.mark.parametrize("launcher", [app, installed])
@pytest.mark.parametrize("paths", [[], ["video folder", "clip.mp4"]])
@pytest.mark.parametrize("flag_first", [False, True])
def test_no_profile_launch_and_restart(monkeypatch, launcher, paths, flag_first):
    flags = ["-NoProfile", "-Minimize"]
    arguments = [*flags, *paths] if flag_first else [*paths, *reversed(flags)]
    monkeypatch.setattr(sys, "argv", ["fastvideocropper", *arguments])
    qt = Mock()
    qt.exec.return_value = 0
    monkeypatch.setattr(launcher, "QApplication", Mock(return_value=qt))
    controller = Mock()
    module = (
        "fastvideocropper.installed" if launcher is installed else "fastvideocropper"
    )
    controller.return_value.launcher_module = module
    controller.return_value.restart_requested = True
    controller.return_value.window.pending_installer = None
    monkeypatch.setattr(launcher, "Application", controller)
    restart = Mock()
    monkeypatch.setattr(launcher.subprocess, "Popen", restart)
    assert launcher.main() == 0
    assert controller.call_args.kwargs["paths"] == paths
    assert controller.call_args.kwargs["no_profile"] is True
    controller.return_value.window.showMinimized.assert_called_once_with()
    controller.return_value.window.show.assert_not_called()
    assert restart.call_args.args[0] == [sys.executable, "-m", module, *arguments]


def test_no_profile_headless_process():
    script = """
from unittest.mock import Mock
from PySide6.QtCore import QTimer
from fastvideocropper import app

original = app.Application
app.user_config_path = Mock(side_effect=AssertionError('Profile path accessed'))
app.QSettings = Mock(side_effect=AssertionError('Persistent settings accessed'))

def create(*args, **kwargs):
    controller = original(*args, **kwargs)
    assert isinstance(controller.settings, app.SessionSettings)
    def check():
        assert controller.window.isMinimized()
        controller.window.close()
    QTimer.singleShot(0, check)
    return controller

app.Application = create
assert app.main() == 0
app.user_config_path.assert_not_called()
app.QSettings.assert_not_called()
"""
    subprocess.run(
        [sys.executable, "-c", script, "-NoProfile", "-Minimize"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@pytest.mark.parametrize("launcher", [app, installed])
@pytest.mark.parametrize("flags", [[], ["-NoProfile"], ["-Minimize"]])
def test_launch_flags_are_independent(monkeypatch, launcher, flags):
    """Explicit option checks; mocked windows cannot interrupt the desktop."""
    monkeypatch.setattr(sys, "argv", ["fastvideocropper", *flags])
    qt = Mock()
    qt.exec.return_value = 0
    monkeypatch.setattr(launcher, "QApplication", Mock(return_value=qt))
    controller = Mock()
    controller.return_value.restart_requested = False
    controller.return_value.window.pending_installer = None
    monkeypatch.setattr(launcher, "Application", controller)
    assert launcher.main() == 0
    assert controller.call_args.kwargs["no_profile"] == ("-NoProfile" in flags)
    assert controller.call_args.kwargs["paths"] == []
    if "-Minimize" in flags:
        controller.return_value.window.showMinimized.assert_called_once_with()
        controller.return_value.window.show.assert_not_called()
    else:
        controller.return_value.window.show.assert_called_once_with()
        controller.return_value.window.showMinimized.assert_not_called()
