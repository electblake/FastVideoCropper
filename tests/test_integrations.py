import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fastvideocropper import integrations


@pytest.mark.parametrize("frozen", [False, True])
def test_install_commands_and_reinstall(monkeypatch, tmp_path, frozen):
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
    bundle = tmp_path / "Bundle Files"
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    for _ in range(2):
        assert integrations.install() == 0
        assert len(values) == 9
        for root, target in integrations.CONTEXTS:
            key = rf"{root}\FastVideoCropper"
            launcher = f'"{executable.resolve()}"'
            if not frozen:
                launcher += ' "-I" "-m" "fastvideocropper"'
            assert values[key, ""] == "Open in FastVideoCropper"
            assert values[key + r"\command", ""] == f'{launcher} "{target}"'
            icon_root = bundle if frozen else Path(integrations.__file__).parent
            assert values[key, "Icon"] == f'"{icon_root / integrations.ICON_NAME}"'
    assert all(
        call.args[0] == registry.HKEY_CURRENT_USER
        for call in registry.CreateKeyEx.call_args_list
    )


def test_source_icon_exists():
    assert (Path(integrations.__file__).parent / integrations.ICON_NAME).is_file()
