# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT, BUNDLE
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(os.environ.get("WHISPER_SPEC_DIR", os.getcwd()))
ROOT = Path(os.environ.get("WHISPER_PROJECT_ROOT", '') or SPEC_DIR.parent).resolve()
SRC_DIR = (SPEC_DIR / "src").resolve()

hiddenimports = []
for pkg in [
    "backend",
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "pydantic_settings",
    "requests",
    "anyio",
]:
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

resources = [
    (str(ROOT / "backend"), "backend"),
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "scripts"), "scripts"),
    (str(ROOT / "vendor" / "whisper.cpp" / "build"), "vendor/whisper.cpp/build"),
    (str(ROOT / "vendor" / "whisper.cpp" / "models"), "vendor/whisper.cpp/models"),
    (str(ROOT / "README.md"), "docs"),
]

analysis = Analysis(
    [str(SRC_DIR / "launcher.py")],
    pathex=[str(SRC_DIR), str(ROOT)],
    binaries=[],
    datas=resources,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=None)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    [],
    [],
    [],
    name="Whisper Metal Control Center",
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    exclude_binaries=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Whisper Metal Control Center",
)

app = BUNDLE(
    coll,
    name="Whisper Metal Control Center.app",
    icon=str(SPEC_DIR / "assets" / "app.icns"),
    bundle_identifier="ai.whisper.metal.control-center",
    info_plist={
        "CFBundleName": "Whisper Metal Control Center",
        "CFBundleShortVersionString": "1.0.0",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    },
)
