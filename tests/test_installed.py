import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastvideocropper import installed


def test_installed_launcher_uses_private_tools_and_forwards_folder(
    monkeypatch, tmp_path
):
    root = tmp_path / "Installed App"
    prefix = root / "application/.venv"
    folder = str(tmp_path / "Video Folder")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "argv", ["pythonw", folder])
    qt = Mock()
    qt.exec.return_value = 0
    monkeypatch.setattr(installed, "QApplication", lambda args: qt)
    controller = Mock(
        return_value=SimpleNamespace(
            window=SimpleNamespace(show=lambda: None, pending_installer=None)
        )
    )
    monkeypatch.setattr(installed, "Application", controller)
    assert installed.main() == 0
    tools = root / "tools/ffmpeg/ffmpeg-8.1.2-essentials_build/bin"
    controller.assert_called_once_with(
        str(tools / "ffmpeg.exe"),
        str(tools / "ffprobe.exe"),
        folder=folder,
        launcher_module="fastvideocropper.installed",
    )


def test_installed_explorer_registration_keeps_installed_entry_point(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["python", "--install-explorer"])
    register = Mock(return_value=0)
    monkeypatch.setattr(installed.integrations, "install", register)
    assert installed.main() == 0
    register.assert_called_once_with("fastvideocropper.installed")
