from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional

from .key_codes import send_vk

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x10
COMBO_KEY_INTERVAL_SEC = 0.015

# 正确设置 64 位下的返回类型和参数类型
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = (
    ctypes.c_void_p,   # hhk - 忽略，传 NULL
    ctypes.c_int,      # nCode
    wintypes.WPARAM,   # wParam
    wintypes.LPARAM,   # lParam
)
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
)

LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KeyboardRemapperService:
    """
    使用全局低级键盘钩子 (WH_KEYBOARD_LL) 实现按键映射。
    钩子在主线程安装，利用 Tk 的消息循环保持活跃。
    所有判断（是否改键、是否本程序前台等）都在回调里做，简单可靠。
    """

    def __init__(self) -> None:
        self._hook_id: Optional[int] = None
        self._proc = LowLevelKeyboardProc(self._callback)
        self._enabled = False
        self._reverse_map: dict[int, int] = {}
        self._combo_map: dict[int, list[int]] = {}
        self._swallow_keys: set[int] = set()
        self._disable_win_key: bool = False
        self._should_intercept: Callable[[], bool] = lambda: False
        self._on_toggle: Optional[Callable[[], None]] = None
        self._on_profile_switch: Optional[Callable[[int], None]] = None
        self._lock = threading.Lock()

    def set_reverse_map(self, mapping: dict[int, int]) -> None:
        with self._lock:
            self._reverse_map = dict(mapping)

    def set_combo_map(self, mapping: dict[int, list[int]]) -> None:
        with self._lock:
            self._combo_map = dict(mapping)

    def set_swallow_keys(self, keys: set[int]) -> None:
        with self._lock:
            self._swallow_keys = set(keys)

    def set_disable_win_key(self, enabled: bool) -> None:
        with self._lock:
            self._disable_win_key = enabled

    def set_should_intercept(self, fn: Callable[[], bool]) -> None:
        self._should_intercept = fn

    def set_on_toggle(self, fn: Callable[[], None]) -> None:
        self._on_toggle = fn

    def set_on_profile_switch(self, fn: Callable[[int], None]) -> None:
        self._on_profile_switch = fn

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def hook_installed(self) -> bool:
        return self._hook_id is not None

    def install_hook(self) -> None:
        """在当前线程安装低级键盘钩子。当前线程必须有消息循环（主线程的 Tk mainloop 即可）。"""
        if self._hook_id:
            return
        # hMod = NULL (0), 线程 ID = 0 表示当前线程
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not hook:
            err = kernel32.GetLastError()
            raise OSError(f"无法安装键盘钩子，错误码 {err}")
        self._hook_id = hook

    def uninstall_hook(self) -> None:
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

    @staticmethod
    def _is_down(vk: int) -> bool:
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    @staticmethod
    def _ctrl_down() -> bool:
        return (
            KeyboardRemapperService._is_down(0x11)
            or KeyboardRemapperService._is_down(0xA2)
            or KeyboardRemapperService._is_down(0xA3)
        )

    @staticmethod
    def _shift_down() -> bool:
        return (
            KeyboardRemapperService._is_down(0x10)
            or KeyboardRemapperService._is_down(0xA0)
            or KeyboardRemapperService._is_down(0xA1)
        )

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        NULL = ctypes.c_void_p(0)

        # 任何情况下，如果 nCode < 0 或事件是 injected，都必须直接放行
        if n_code < 0:
            return user32.CallNextHookEx(NULL, n_code, w_param, l_param)

        try:
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents

            if kb.flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(NULL, n_code, w_param, l_param)

            vk = kb.vkCode
            is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
            is_up = w_param in (WM_KEYUP, WM_SYSKEYUP)

            # 决定当前是否要接管这个按键
            if not self._should_intercept():
                return user32.CallNextHookEx(NULL, n_code, w_param, l_param)

            # 全局热键（Scroll/Pause 总开关、Ctrl+Shift+字母 切方案）
            if is_down and self._handle_hotkeys(vk):
                return 1

            # 禁用 Win 键（防止游戏中误按弹出桌面）；只要在前台拦截范围就生效
            with self._lock:
                disable_win = self._disable_win_key
            if disable_win and vk in (0x5B, 0x5C):  # VK_LWIN, VK_RWIN
                return 1

            if not self._enabled:
                return user32.CallNextHookEx(NULL, n_code, w_param, l_param)

            # 吞掉被重新映射走的“原技能按键”（只有功能开启时才吞）
            # 例如把 C 技能映射走后，按 C 就应该没反应
            with self._lock:
                swallow = self._swallow_keys
            if vk in swallow:
                return 1

            # 一键必杀
            if is_down and self._handle_combo(vk):
                return 1

            # 普通映射改键
            if (is_down or is_up) and self._handle_remap(vk, is_up):
                return 1

            # 默认：放行给下一个钩子 / 系统
            return user32.CallNextHookEx(NULL, n_code, w_param, l_param)

        except Exception:
            # 防御性：回调里任何异常都不能导致按键丢失
            # 出错时尽量放行
            return user32.CallNextHookEx(NULL, n_code, w_param, l_param)

    def _handle_hotkeys(self, vk: int) -> bool:
        if vk in (0x91, 0x13) and self._on_toggle:
            self._on_toggle()
            return True
        if self._ctrl_down() and self._shift_down() and 0x41 <= vk <= 0x5A and self._on_profile_switch:
            self._on_profile_switch(vk - 0x41)
            return True
        return False

    def _handle_combo(self, vk: int) -> bool:
        with self._lock:
            sequence = self._combo_map.get(vk)
        if not sequence:
            return False
        for target_vk in sequence:
            send_vk(target_vk, key_up=False)
            send_vk(target_vk, key_up=True)
            time.sleep(COMBO_KEY_INTERVAL_SEC)
        return True

    def _handle_remap(self, vk: int, is_up: bool) -> bool:
        with self._lock:
            if vk in self._combo_map:
                return False
            target_vk = self._reverse_map.get(vk)
        if target_vk is None:
            return False

        # 语义：用户按下 vk（实际按的键），我们要让游戏收到 target_vk
        # 对于物品栏位置（小键盘数字键），在物理键按下时立即用 tap 发送一个短促完整的按压，
        # 能更可靠地让游戏识别为“使用该位置道具”。
        # 技能映射等保持 down/up 跟随物理键的时长。
        if 0x60 <= target_vk <= 0x69:
            if not is_up:
                from .key_codes import tap_key
                tap_key(target_vk)
            # up 时不再额外发送（tap 已经完成一次完整按压）
        else:
            send_vk(target_vk, key_up=is_up)
        return True
