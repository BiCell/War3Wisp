from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Dict, Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 虚拟键码
VK_MAP: Dict[str, int] = {
    "Escape": 0x1B,
    "Space": 0x20,
    "Prior": 0x21,
    "Next": 0x22,
    "End": 0x23,
    "Home": 0x24,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45,
    "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A,
    "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F,
    "P": 0x50, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
    "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59,
    "Z": 0x5A,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "NUMPAD0": 0x60, "NUMPAD1": 0x61, "NUMPAD2": 0x62, "NUMPAD3": 0x63,
    "NUMPAD4": 0x64, "NUMPAD5": 0x65, "NUMPAD6": 0x66, "NUMPAD7": 0x67,
    "NUMPAD8": 0x68, "NUMPAD9": 0x69,
    "Scroll": 0x91,
    "Pause": 0x13,
    "Oem3": 0xC0,
    "OemMinus": 0xBD,
    "OemPlus": 0xBB,
    "OemComma": 0xBC,
    "OemPeriod": 0xBE,
    "Tab": 0x09,
    "Shift": 0x10,
    "Control": 0x11,
    "Alt": 0x12,
}

DISPLAY_MAP: Dict[str, str] = {v: k for k, v in VK_MAP.items()}
DISPLAY_MAP[0x20] = "空"
for vk, label in {
    0x60: "小键盘0", 0x61: "小键盘1", 0x62: "小键盘2", 0x63: "小键盘3",
    0x64: "小键盘4", 0x65: "小键盘5", 0x66: "小键盘6",
    0x67: "小键盘7", 0x68: "小键盘8", 0x69: "小键盘9",
}.items():
    DISPLAY_MAP[vk] = label

VK_TO_NAME: Dict[int, str] = {code: name for name, code in VK_MAP.items()}

VK_PROCESSKEY = 0xE5

KEYSYM_TO_NAME: Dict[str, str] = {
    "space": "Space",
    "Escape": "Escape",
    "Tab": "Tab",
    "Prior": "Prior",
    "Next": "Next",
    "Home": "Home",
    "End": "End",
    "Insert": "Insert",
    "Delete": "Delete",
    "Up": "Up",
    "Down": "Down",
    "Left": "Left",
    "Right": "Right",
    "Scroll_Lock": "Scroll",
    "Pause": "Pause",
    "grave": "Oem3",
    "minus": "OemMinus",
    "equal": "OemPlus",
    "comma": "OemComma",
    "period": "OemPeriod",
}
for i in range(10):
    KEYSYM_TO_NAME[str(i)] = str(i)
for ch in "abcdefghijklmnopqrstuvwxyz":
    KEYSYM_TO_NAME[ch] = ch.upper()
for i in range(1, 13):
    KEYSYM_TO_NAME[f"F{i}"] = f"F{i}"
for i in range(10):
    KEYSYM_TO_NAME[f"KP_{i}"] = f"NUMPAD{i}"


def vk_to_display(vk: int) -> str:
    return DISPLAY_MAP.get(vk, f"VK{vk:02X}")


def key_name_to_display(name: str) -> str:
    if not name:
        return ""
    vk = parse_key(name)
    if vk is not None:
        return vk_to_display(vk)
    return name


def capture_key_from_event(keycode: int, keysym: str) -> Optional[str]:
    if keycode in (VK_PROCESSKEY, 0xFF):
        return None
    name = VK_TO_NAME.get(keycode)
    if name:
        return name
    if keysym in KEYSYM_TO_NAME:
        return KEYSYM_TO_NAME[keysym]
    if len(keysym) == 1 and keysym.isalnum():
        upper = keysym.upper()
        if upper in VK_MAP:
            return upper
    return None


def parse_key(text: str) -> Optional[int]:
    if not text:
        return None
    text = text.strip()
    if text in ("空", "空格"):
        return VK_MAP["Space"]
    numpad_labels = {
        "小键盘0": "NUMPAD0", "小键盘1": "NUMPAD1", "小键盘2": "NUMPAD2",
        "小键盘3": "NUMPAD3", "小键盘4": "NUMPAD4", "小键盘5": "NUMPAD5",
        "小键盘6": "NUMPAD6", "小键盘7": "NUMPAD7", "小键盘8": "NUMPAD8",
        "小键盘9": "NUMPAD9",
    }
    if text in numpad_labels:
        return VK_MAP[numpad_labels[text]]
    upper = text.upper()
    if upper in VK_MAP:
        return VK_MAP[upper]
    if text in VK_MAP:
        return VK_MAP[text]
    return None


def format_key(vk: int) -> str:
    return vk_to_display(vk)


# 扩展键标志（影响扫描码解释）。小键盘数字键（NumLock 开启时的 0-9）通常不需要 extended 标志。
# 只有方向键、Insert/Delete、Home/End/Page、Numpad 的 / * - + Enter 等才需要。
_EXTENDED_KEYS = frozenset({
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,  # 方向、翻页、Insert/Delete
    0x6F,  # Numpad /
    0x6A,  # Numpad *
    0x6D,  # Numpad -
    0x6B,  # Numpad +
    # Numpad Enter 通常用 VK_RETURN + extended，这里不列 VK_RETURN 以免误伤主键盘 Enter
})


def vk_to_scan(vk: int) -> int:
    scan = user32.MapVirtualKeyW(vk, 0)
    return scan & 0xFF


def send_vk(vk: int, key_up: bool = False) -> bool:
    """
    向魔兽1.24注入按键的核心函数。
    优先使用 SendInput + AttachThreadInput，对老版本魔兽最可靠。
    对小键盘数字键做了专门处理（不带 extended），并尝试多种方式。
    """
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]

    scan = vk_to_scan(vk)
    is_extended = vk in _EXTENDED_KEYS

    # 小键盘数字键（NUMPAD0~9）强制不带 extended，否则 1.24 经常不认。
    if 0x60 <= vk <= 0x69:
        is_extended = False

    keyup_flag = 0x0002 if key_up else 0
    ext_flag = 0x0001 if is_extended else 0

    extra = ctypes.c_ulong(0)
    extra_ptr = ctypes.pointer(extra)

    hwnd = user32.GetForegroundWindow()

    # 先尝试直接 PostMessage 到前台窗口（对菜单界面和某些输入栈有帮助）
    if hwnd:
        msg = 0x0101 if key_up else 0x0100
        # 构造一个基本的 lParam：重复计数1 + 扫描码
        lparam = (scan << 16) | 1
        user32.PostMessageW(hwnd, msg, vk, lparam)

    # 尝试把当前线程的输入状态附加到前台窗口线程（对1.24全屏特别重要）
    fg_thread = 0
    cur_thread = kernel32.GetCurrentThreadId()
    attached = False
    if hwnd:
        fg_thread = user32.GetWindowThreadProcessId(hwnd, None)
        if fg_thread and fg_thread != cur_thread:
            attached = bool(user32.AttachThreadInput(fg_thread, cur_thread, True))

    try:
        # 对物品栏对应的小键盘数字键，优先使用最简单直接的 keybd_event（bScan=0）
        # 这是很多1.24物品栏改键能稳定工作的关键路径。
        if 0x60 <= vk <= 0x69:
            user32.keybd_event(vk, 0, keyup_flag, 0)
            return True

        # 模式1：带扫描码 + extended 控制
        flags1 = 0x0008 | keyup_flag | ext_flag
        inp1 = INPUT()
        inp1.type = 1
        inp1.ki.wVk = vk
        inp1.ki.wScan = scan
        inp1.ki.dwFlags = flags1
        inp1.ki.time = 0
        inp1.ki.dwExtraInfo = extra_ptr
        if user32.SendInput(1, ctypes.byref(inp1), ctypes.sizeof(INPUT)) == 1:
            return True

        # 模式2：纯虚拟键
        flags2 = keyup_flag | ext_flag
        inp2 = INPUT()
        inp2.type = 1
        inp2.ki.wVk = vk
        inp2.ki.wScan = 0
        inp2.ki.dwFlags = flags2
        inp2.ki.time = 0
        inp2.ki.dwExtraInfo = extra_ptr
        if user32.SendInput(1, ctypes.byref(inp2), ctypes.sizeof(INPUT)) == 1:
            return True

        # 针对小键盘数字的额外无 extended 尝试
        if 0x60 <= vk <= 0x69:
            flags3 = keyup_flag
            inp3 = INPUT()
            inp3.type = 1
            inp3.ki.wVk = vk
            inp3.ki.wScan = scan
            inp3.ki.dwFlags = flags3
            inp3.ki.time = 0
            inp3.ki.dwExtraInfo = extra_ptr
            if user32.SendInput(1, ctypes.byref(inp3), ctypes.sizeof(INPUT)) == 1:
                return True

        # 最后回退
        user32.keybd_event(vk, scan, keyup_flag | ext_flag, 0)
        return True
    finally:
        if attached and fg_thread:
            user32.AttachThreadInput(fg_thread, cur_thread, False)


def tap_key(vk: int) -> bool:
    """
    对物品栏位置触发特别有效：发送一个短促的完整按压（down + 短延时 + up）。
    使用最简单的 keybd_event 路径（bScan=0），并尽量附加输入线程，对1.24兼容性更好。
    """
    import time

    hwnd = user32.GetForegroundWindow()
    fg_thread = 0
    cur_thread = kernel32.GetCurrentThreadId()
    attached = False
    if hwnd:
        fg_thread = user32.GetWindowThreadProcessId(hwnd, None)
        if fg_thread and fg_thread != cur_thread:
            attached = bool(user32.AttachThreadInput(fg_thread, cur_thread, True))

    try:
        # 针对小键盘数字键，强制无 extended
        ext = 0
        if vk in _EXTENDED_KEYS and not (0x60 <= vk <= 0x69):
            ext = 0x0001

        # 简单直接的 keybd_event（很多老游戏对这个最敏感）
        user32.keybd_event(vk, 0, ext, 0)           # down
        time.sleep(0.015)
        user32.keybd_event(vk, 0, 0x0002 | ext, 0)  # up
        return True
    finally:
        if attached and fg_thread:
            user32.AttachThreadInput(fg_thread, cur_thread, False)
