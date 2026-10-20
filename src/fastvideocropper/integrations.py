"""Per-user Windows File Explorer integration."""

import sys
from pathlib import Path

from . import APP_NAME

APP_MODULE = "fastvideocropper"
ICON_NAME = f"{APP_NAME}.ico"

CONTEXTS = (
    (r"Software\Classes\Directory\shell", "%1"),
    (r"Software\Classes\Directory\Background\shell", "%V"),
    (r"Software\Classes\Drive\shell", "%1"),
)


def install(module=APP_MODULE):
    import winreg

    executable = str(Path(sys.executable).resolve())
    launcher = [executable, "-I", "-m", module]
    icon_root = Path(__file__).resolve().parent

    icon = f'"{icon_root / ICON_NAME}"'
    for root, target in CONTEXTS:
        menu_key = rf"{root}\{APP_NAME}"
        command = " ".join(f'"{part}"' for part in [*launcher, target])
        print(f"File Explorer command ({root}): {command}")
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, menu_key, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"Open in {APP_NAME}")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, menu_key + r"\command", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    print(f"[OK] Installed {len(CONTEXTS)} File Explorer context menu entries.")
    return 0
