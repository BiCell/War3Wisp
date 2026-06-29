"""应用路径：开发模式与 PyInstaller 打包后共用。"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """项目根目录（开发）或 exe 所在目录（打包后）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """内置资源根目录（assets 等）。打包后指向 _MEIPASS。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", project_root()))
    return project_root()


def assets_dir() -> Path:
    return resource_root() / "assets"
