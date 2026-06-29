"""Windows 前台窗口激活工具（用于单实例重复启动时唤醒已有窗口）。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

APP_WINDOW_TITLE = "魔兽改键精灵"

SW_SHOW = 5
SW_RESTORE = 9

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 设置常用函数的类型，避免 64 位下句柄截断
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND

user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
user32.ShowWindow.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL

user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def find_app_window(title: str = APP_WINDOW_TITLE) -> int:
    """按窗口标题查找主窗口句柄，找不到返回 0。"""
    hwnd = user32.FindWindowW(None, title)
    return int(hwnd or 0)


def force_foreground(hwnd: int) -> bool:
    """尽量把指定窗口恢复/显示并设为前台（简化版，避免干扰 Tk 消息循环）。"""
    if not hwnd:
        return False
    try:
        # 无论是否最小化，都先用 RESTORE 确保可见并激活（对 Tk 窗口更安全）
        user32.ShowWindow(hwnd, SW_RESTORE)

        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return True
    except Exception:
        return False


def bring_tk_window_to_front(window) -> None:
    """首次启动时把 Tk 主窗口抬到最前（使用类方法绕过 state 属性覆盖）。"""
    import tkinter as tk

    try:
        if tk.Tk.state(window) == "iconic":
            window.deiconify()
    except tk.TclError:
        pass

    window.lift()
    window.attributes("-topmost", True)
    window.update_idletasks()

    force_foreground(int(window.winfo_id()))
    try:
        window.focus_force()
    except tk.TclError:
        pass

    def _drop_topmost() -> None:
        try:
            window.attributes("-topmost", False)
        except tk.TclError:
            pass

    window.after(300, _drop_topmost)


def activate_existing_instance(title: str = APP_WINDOW_TITLE) -> int:
    """找到已在运行的实例主窗口并激活，返回 hwnd（找不到返回 0）。"""
    hwnd = find_app_window(title)
    if hwnd:
        force_foreground(hwnd)
    return hwnd
