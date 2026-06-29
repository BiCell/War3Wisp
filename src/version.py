"""从 build/version.txt 读取应用版本号（开发与打包后共用）。"""
from __future__ import annotations

from pathlib import Path

from .paths import is_frozen, project_root, resource_root


def _parse_version_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("v", "V")):
            return f"v{line[1:]}"
        return f"v{line}"
    return None


def get_app_version() -> str:
    """读取 build/version.txt；打包后从内置的 version.txt 读取。"""
    candidates = [resource_root() / "version.txt"]
    if not is_frozen():
        candidates.insert(0, project_root() / "build" / "version.txt")
    for path in candidates:
        version = _parse_version_file(path)
        if version:
            return version
    return "v4.75"
