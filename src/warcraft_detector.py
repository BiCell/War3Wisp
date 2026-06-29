from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WAR3_PROCESS_NAMES = frozenset(
    {
        "war3.exe",
        "war3x.exe",
        "warcraft iii.exe",
        "frozen throne.exe",
    }
)

WAR3_TITLE_KEYWORDS = (
    "warcraft",
    "魔兽争霸",
    "冰封王座",
    "混乱之治",
    "war3",
    "frozen throne",
    "reforged",
    "重生",
)


def is_own_process_foreground() -> bool:
    """本程序窗口在前台时，不应拦截按键（否则无法配置）。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    # 1. 窗口标题包含程序名（最可靠）
    buf = ctypes.create_unicode_buffer(256)
    if user32.GetWindowTextW(hwnd, buf, 256) > 0:
        if "魔兽改键精灵" in buf.value:
            return True
    # 2. 窗口类名是 Tkinter 的
    class_buf = ctypes.create_unicode_buffer(64)
    if user32.GetClassNameW(hwnd, class_buf, 64) > 0:
        if class_buf.value.lower().startswith("tk"):
            return True
    # 3. PID 兜底
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


class WarcraftDetector:
    """仅在魔兽窗口前台时改键。"""

    def __init__(self, only_warcraft: bool = True) -> None:
        self.only_warcraft = only_warcraft
        self._cached_pid: int = -1
        self._cached_is_war3: bool = False

    def set_only_warcraft(self, value: bool) -> None:
        self.only_warcraft = value
        self._cached_pid = -1

    def is_warcraft_foreground(self) -> bool:
        if not self.only_warcraft:
            return True

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        if self._match_window_title(hwnd):
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value

        if pid_val == self._cached_pid:
            return self._cached_is_war3

        self._cached_pid = pid_val
        self._cached_is_war3 = self._pid_is_warcraft(pid_val)
        return self._cached_is_war3

    def warcraft_foreground_hwnd(self) -> int:
        """若前台窗口是魔兽争霸则返回其窗口句柄，否则返回 0。

        不受 only_warcraft 影响——血条同步只应作用于魔兽本身，所以这里始终做身份判定。
        用于识别“新一局游戏”（句柄变化）并重置血条跟踪状态。
        """
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        if self._match_window_title(hwnd):
            return hwnd
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value
        if pid_val == self._cached_pid:
            return hwnd if self._cached_is_war3 else 0
        self._cached_pid = pid_val
        self._cached_is_war3 = self._pid_is_warcraft(pid_val)
        return hwnd if self._cached_is_war3 else 0

    @staticmethod
    def _match_window_title(hwnd: int) -> bool:
        buf = ctypes.create_unicode_buffer(512)
        length = user32.GetWindowTextW(hwnd, buf, 512)
        if length <= 0:
            return False
        title = buf.value.lower()
        return any(keyword in title for keyword in WAR3_TITLE_KEYWORDS)

    def _pid_is_warcraft(self, pid: int) -> bool:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                name = buf.value.rsplit("\\", 1)[-1].lower()
                return name in WAR3_PROCESS_NAMES
        finally:
            kernel32.CloseHandle(handle)
        return False
