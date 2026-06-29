# -*- mode: python ; coding: utf-8 -*-
# 在项目根目录执行：
# python -m PyInstaller --clean --noconfirm --workpath build\work --distpath build\dist build\warcraft_key_remapper.spec

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # spec 在 build/ 下，上一级即项目根
BUILD = ROOT / "build"
assets = ROOT / "assets"
icon = assets / "logo.ico"
version_file = BUILD / "version.txt"


def _read_app_version() -> str:
    if not version_file.is_file():
        return "4.75"
    for line in version_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line.lstrip("vV")
    return "4.75"


APP_VERSION = _read_app_version()

block_cipher = None

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(assets), "assets"),
        (str(version_file), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name=f"魔兽改键精灵-{APP_VERSION}",
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
    icon=str(icon) if icon.exists() else None,
)
