import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QSettings

from fastvideocropper import integrations


@pytest.mark.parametrize("module", ["fastvideocropper", "fastvideocropper.installed"])
@pytest.mark.parametrize("icon_name", [None, "blue", "charcoal", "gray", "violet"])
def test_install_commands_and_reinstall(monkeypatch, tmp_path, module, icon_name):
    monkeypatch.setattr(integrations, "user_config_path", lambda *a, **kw: tmp_path)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    if icon_name is not None:
        settings.setValue("appearance/icon", icon_name)
        settings.sync()
    registry = MagicMock()
    values = {}
    registry.CreateKeyEx.side_effect = lambda hive, path, reserved, access: MagicMock(
        __enter__=lambda self: path
    )
    registry.SetValueEx.side_effect = lambda key, name, reserved, kind, value: (
        values.update({(key, name): value})
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    executable = tmp_path / "Program Files" / "FastVideoCropper.exe"
    monkeypatch.setattr(sys, "executable", str(executable))
    for _ in range(2):
        assert integrations.install(module) == 0
        assert len(values) == 29
        for root, target in integrations.CONTEXTS:
            key = rf"{root}\FastVideoCropper"
            launcher = f'"{executable.resolve()}"'
            launcher += f' "-I" "-m" "{module}"'
            assert values[key, ""] == "Open in FastVideoCropper"
            assert values[key + r"\command", ""] == f'{launcher} "{target}"'
            icon_root = Path(integrations.__file__).parent
            selected_icon = icon_root / "icons" / ((icon_name or "blue") + ".ico")
            assert selected_icon.is_file()
            assert values[key, "Icon"] == f'"{selected_icon}"'
        for extension in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
            key = rf"Software\Classes\SystemFileAssociations\{extension}\shell\FastVideoCropper"
            assert values[key, "MultiSelectModel"] == "Player"
            assert values[key + r"\command", ""] == f'{launcher} "%1"'
    assert all(
        call.args[0] == registry.HKEY_CURRENT_USER
        for call in registry.CreateKeyEx.call_args_list
    )


def test_source_icon_exists():
    assert (Path(integrations.__file__).parent / integrations.ICON_NAME).is_file()
