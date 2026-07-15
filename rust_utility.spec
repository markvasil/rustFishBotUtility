# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
icon_path = Path(SPECPATH) / "assets" / "app_icon.ico"

hiddenimports = collect_submodules("customtkinter")
hiddenimports += [
    "PIL",
    "PIL._tkinter_finder",
    "keyboard",
    "win32api",
    "win32con",
    "winsound",
    "numpy",
    "mss",
    "scipy",
    "scipy.special.cython_special",
    "websockets",
    "rustplus",
    "rustplus.remote.camera.camera_constants",
    "rustplus.structs",
    "rustplus.structs.rust_marker",
    "rustplus.structs.rust_team_info",
    "rustplus.structs.util",
    "rustplus.utils.grab_items",
    "rustplus.utils.utils",
]

datas = collect_data_files("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "matplotlib",
        "sympy",
        "pytest",
        "IPython",
        "notebook",
        "tkinter.test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="RustUtilityOverlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
