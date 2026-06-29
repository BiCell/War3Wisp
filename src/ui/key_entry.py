from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..key_codes import VK_TO_NAME, key_name_to_display

user32 = ctypes.windll.user32

# 用于在捕获时临时禁用输入法（IME），防止中文拼音界面弹出。
# 只针对本工具的按键捕获框生效，捕获结束后立即恢复。
try:
    imm32 = ctypes.windll.imm32
except Exception:
    imm32 = None

_MODIFIER_KEYSYMS = frozenset(
    {
        "Shift_L", "Shift_R", "Control_L", "Control_R",
        "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Win_L", "Win_R",
    }
)

# 不作为映射目标的修饰键 VK
_MODIFIER_VKS = frozenset(
    {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C, 0x91, 0x13}
)

VK_PROCESSKEY = 0xE5


def _poll_pressed_vk() -> Optional[int]:
    """IME 拦截了按键事件时，用 GetAsyncKeyState 找出实际按下的键。"""
    for vk in range(0x08, 0x100):
        if vk in _MODIFIER_VKS:
            continue
        if user32.GetAsyncKeyState(vk) & 0x8000:
            return vk
    return None


class KeyCaptureEntry(ttk.Entry):
    """
    仅用于捕获按键的输入框（不作为普通文本输入）。
    - 点击后框获得焦点并加粗边框（作为选中状态）。
    - 不显示光标。
    - 按任意字母键（无论中英文输入法）直接记录并显示大写字母。
    - Delete/Backspace 清空。
    - 框内只显示捕获到的键名或空白，不显示任何占位提示。

    针对中文输入法的特别处理：
    - 捕获期间通过 ImmDisableIME 临时禁用当前线程的输入法，彻底阻止拼音候选界面弹出。
    - 捕获结束后立即恢复，不影响程序其他地方或其他软件的输入法行为。
    """

    def __init__(
        self,
        master,
        on_change: Optional[Callable[[], None]] = None,
        validator: Optional[Callable[[str], bool]] = None,
        **kwargs,
    ):
        super().__init__(master, width=4, justify="center", **kwargs)
        self._capturing = False
        self._capture_dirty = False
        self._capture_backup = ""
        self._on_change = on_change
        # 按键冲突校验器：传入新键名，返回 True 接受、False 拒绝（由调用方负责提示）。
        self._validator = validator
        self._stored_key = ""
        self._prev_ime_ctx = None
        self._ime_disabled_for_thread = False   # 标记我们是否对线程禁用了 IME

        # 默认就使用 readonly，避免任何时候出现编辑光标
        try:
            self.config(state="readonly")
        except Exception:
            pass

        # 强力隐藏插入光标：宽度为0 + 背景色 + 不闪烁
        # 这在 readonly + 获得焦点时通常完全不显示光标，只靠边框高亮表示选中
        self._hide_insert_cursor()

        # 默认就是原始模样（细边框，非选中）
        self._apply_normal_style()

        self.bind("<Button-1>", self._on_click, add="+")
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<FocusIn>", self._on_focus_in, add="+")

    def _notify_change(self) -> None:
        if self._on_change:
            self._on_change()

    def set_validator(self, validator: Callable[[str], bool]) -> None:
        """设置按键冲突校验器：返回 True 接受该键，False 拒绝（调用方负责提示用户）。"""
        self._validator = validator

    def _hide_insert_cursor(self) -> None:
        """强制让插入光标不可见（即使短暂进入 normal 状态）。"""
        try:
            bg = self.cget("background") or self.cget("bg") or "#ffffff"
            self.configure(insertwidth=0, insertbackground=bg, insertontime=0, insertofftime=0)
        except Exception:
            pass

    def _apply_selected_style(self) -> None:
        """捕获/选中状态：边框加粗作为选中提示（用户喜欢点击后加粗的效果）。"""
        try:
            self.configure(highlightthickness=2, highlightcolor="#4a90d9", highlightbackground="#a0a0a0")
        except Exception:
            pass

    def _apply_normal_style(self) -> None:
        """原始模样：恢复正常细边框外观。点击空白区后应该回到这个状态。"""
        try:
            self.configure(highlightthickness=1, highlightcolor="#c0c0c0", highlightbackground="#c0c0c0")
        except Exception:
            pass

    def _close_ime_candidate_windows(self, hwnd: int) -> None:
        """显式关闭输入法候选窗口和状态窗口，防止中文拼音小界面残留。"""
        if not imm32 or not hwnd:
            return
        try:
            WM_IME_CONTROL = 0x0283
            IMC_CLOSESTATUSWINDOW = 0x0001
            IMC_CLOSECANDIDATEWINDOW = 0x0004

            # 关闭状态窗口
            user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_CLOSESTATUSWINDOW, 0)

            # 关闭候选窗口（有些输入法需要指定索引，保险起见多试几次）
            for i in range(10):
                user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_CLOSECANDIDATEWINDOW, i)

            # 也尝试通过 IMC 取消当前合成
            hIMC = imm32.ImmGetContext(hwnd)
            if hIMC:
                try:
                    # NI_COMPOSITIONSTR + CPS_CANCEL
                    imm32.ImmNotifyIME(hIMC, 0x0015, 0x0004, 0)
                finally:
                    imm32.ImmReleaseContext(hwnd, hIMC)
        except Exception:
            pass

    def _on_focus_in(self, _event=None) -> None:
        # 无论何时获得焦点，都再次确保光标不可见（只靠边框表示选中）
        self._hide_insert_cursor()

    def _safe_set_display(self, text: str) -> None:
        """安全地设置显示文本，最大程度避免光标闪烁或出现。"""
        self._hide_insert_cursor()
        self.config(state="normal")
        self.delete(0, tk.END)
        if text:
            self.insert(0, text)
        self.config(state="readonly")
        # 清除可能残留的文本选区，避免切换方案后文字带高亮背景
        try:
            self.selection_clear()
        except Exception:
            pass
        self._hide_insert_cursor()

        # 如果不是正在捕获状态，显示更新后也要恢复原始非选中外观
        if not getattr(self, '_capturing', False):
            self._apply_normal_style()

    def _on_click(self, _event=None) -> None:
        # 尽早尝试禁用线程 IME，减少拼音候选界面闪现的窗口
        if imm32:
            try:
                if not self._ime_disabled_for_thread:
                    imm32.ImmDisableIME(0)
                    self._ime_disabled_for_thread = True
            except Exception:
                pass

        # 先让框获得焦点，触发边框加粗（作为选中状态提示），再进入捕获准备
        self.focus_force()
        self.after_idle(self._begin_capture)

    def _begin_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._capture_dirty = False
        self._capture_backup = self._stored_key

        hwnd = 0
        try:
            hwnd = self.winfo_id()
        except Exception:
            pass

        if imm32 and hwnd:
            try:
                # 1. 先把这个控件的 IME 上下文置空（老办法，保留作为防御）
                self._prev_ime_ctx = imm32.ImmAssociateContext(hwnd, 0)

                # 2. 更强力的措施：临时禁用“当前线程”的输入法。
                #    这能彻底阻止微软拼音/搜狗等在捕获期间弹出候选文字小界面。
                #    因为捕获是单次按键（极短时间），对用户其他输入影响极小。
                if not self._ime_disabled_for_thread:
                    # ImmDisableIME(0) 表示禁用当前线程
                    imm32.ImmDisableIME(0)
                    self._ime_disabled_for_thread = True

                # 3. 显式关闭可能已经弹出的状态窗口和候选窗口
                self._close_ime_candidate_windows(hwnd)
            except Exception:
                pass

        # 保持 readonly + 强制隐藏光标，只靠边框表示选中
        self.set_readonly()
        self.focus_force()
        self._hide_insert_cursor()

    def _end_capture(self) -> None:
        hwnd = 0
        try:
            hwnd = self.winfo_id()
        except Exception:
            pass

        # 恢复该控件的 IME 上下文
        if imm32 and self._prev_ime_ctx and hwnd:
            try:
                imm32.ImmAssociateContext(hwnd, self._prev_ime_ctx)
            except Exception:
                pass
            self._prev_ime_ctx = None

        # 恢复线程级 IME（非常重要）
        if imm32 and self._ime_disabled_for_thread:
            try:
                # ImmDisableIME(-1) 重新启用当前线程的输入法
                imm32.ImmDisableIME(-1)
            except Exception:
                pass
            self._ime_disabled_for_thread = False

        # 额外保险：捕获结束时也尝试关闭可能残留的候选窗口
        if imm32 and hwnd:
            try:
                self._close_ime_candidate_windows(hwnd)
            except Exception:
                pass

        self._capturing = False
        # 捕获结束时，立即恢复正常（非加粗）外观
        self._apply_normal_style()

    def _on_focus_out(self, _event=None) -> None:
        if not self._capturing:
            self.set_readonly()
            # 点击空白区或其他地方导致失去焦点时，强制恢复原始非选中外观
            self._apply_normal_style()
            return
        self._end_capture()
        if self._capture_dirty:
            self.set_value(self._stored_key)
        else:
            self.set_value(self._capture_backup)
            self._stored_key = self._capture_backup

    def _clear_key(self) -> None:
        self._stored_key = ""
        self._capture_dirty = True
        # 使用安全方式更新显示内容，避免出现光标
        self._safe_set_display("")
        self._notify_change()

    def _accept_key(self, key_name: str) -> None:
        # 强制字母大写显示
        if key_name and len(key_name) == 1 and key_name.isalpha():
            key_name = key_name.upper()
        # 冲突校验：validator 返回 False 表示该键不被接受（已由调用方提示用户）
        if self._validator is not None:
            try:
                ok = self._validator(key_name)
            except Exception:
                ok = True
            if not ok:
                # 恢复捕获前的值，结束捕获，不通知 change（本次输入作废）
                self._stored_key = self._capture_backup
                self._capture_dirty = False
                self._end_capture()
                self.set_value(self._capture_backup)
                self._apply_normal_style()
                try:
                    self.master.focus_set()
                except Exception:
                    pass
                return
        self._stored_key = key_name
        self._capture_dirty = True
        self._end_capture()
        self.set_value(key_name)
        self._notify_change()

        # 成功输入映射字母后，立即恢复原始（非加粗）外观
        self._apply_normal_style()

        # 把焦点移开（相当于点击空白区），让框彻底回到原始模样
        try:
            self.master.focus_set()
        except Exception:
            pass

    def _on_key_press(self, event: tk.Event) -> Optional[str]:
        if not self._capturing:
            return None

        if event.keysym in ("BackSpace", "Delete"):
            self._clear_key()
            return "break"

        if event.keysym == "Escape":
            self._stored_key = self._capture_backup
            self._capture_dirty = False
            self._end_capture()
            self.set_value(self._capture_backup)

            # 取消后也立即恢复原始外观，并把焦点移开
            self._apply_normal_style()
            try:
                self.master.focus_set()
            except Exception:
                pass
            return "break"

        if event.keysym in _MODIFIER_KEYSYMS:
            return "break"

        # 核心优化：无论当前是中文输入法还是英文模式，
        # 捕获时优先使用 GetAsyncKeyState 读取物理按键，直接得到大写字母名。
        # 这避免了光标输入 + 输入法干扰的问题。
        vk = _poll_pressed_vk()
        if vk is not None and vk not in _MODIFIER_VKS:
            name = VK_TO_NAME.get(vk)
            if name is not None:
                # 尽早尝试关闭候选窗口，防止拼音小界面在按键瞬间闪现
                hwnd = 0
                try:
                    hwnd = self.winfo_id()
                except Exception:
                    pass
                if imm32 and hwnd:
                    try:
                        self._close_ime_candidate_windows(hwnd)
                    except Exception:
                        pass

                self._accept_key(name)
                return "break"

        # 兜底1：如果轮询没抓到，用 Tk 报告的 keycode
        name = VK_TO_NAME.get(event.keycode)
        if name is not None:
            hwnd = 0
            try:
                hwnd = self.winfo_id()
            except Exception:
                pass
            if imm32 and hwnd:
                try:
                    self._close_ime_candidate_windows(hwnd)
                except Exception:
                    pass
            self._accept_key(name)
            return "break"

        # 兜底2：keysym（单字母时强制大写）
        ks = event.keysym
        if len(ks) == 1 and ks.isalpha():
            self._accept_key(ks.upper())
            return "break"

        from ..key_codes import KEYSYM_TO_NAME
        if ks in KEYSYM_TO_NAME:
            self._accept_key(KEYSYM_TO_NAME[ks])
            return "break"

        # 其他任何情况都吃掉事件，防止 Tk 往框里插入字符
        return "break"

    def set_value(self, key_name: str) -> None:
        self._stored_key = key_name or ""
        disp = ""
        if self._stored_key:
            disp = key_name_to_display(self._stored_key)
            if disp and len(disp) == 1 and disp.isalpha():
                disp = disp.upper()
        self._safe_set_display(disp)

    def get_key(self) -> str:
        return self._stored_key

    def set_readonly(self) -> None:
        # 捕获期间也保持 readonly（我们通过 KeyPress 绑定捕获，不需要编辑状态）
        self.config(state="readonly")
        self._hide_insert_cursor()

        # 非捕获状态下调用 set_readonly 时，恢复原始非加粗外观
        if not getattr(self, '_capturing', False):
            self._apply_normal_style()
