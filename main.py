from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
import threading
import tkinter as tk
from pathlib import Path

# 开发模式：先把项目根加入 sys.path；打包后由 PyInstaller 处理导入
_bootstrap_root = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False) and str(_bootstrap_root) not in sys.path:
    sys.path.insert(0, str(_bootstrap_root))

from src.paths import is_frozen, project_root

ROOT = project_root()

from src.keyboard_remapper import KeyboardRemapperService
from src.models import AppState
from src.profile_service import ProfileService
from src.ui.main_window import MainWindow
from src.warcraft_detector import WarcraftDetector, is_own_process_foreground
from src.win_foreground import APP_WINDOW_TITLE, activate_existing_instance

SW_HIDE = 0
SW_SHOW = 5
MB_ICONERROR = 0x10

ERROR_LOG = Path(os.environ.get("APPDATA", ".")) / "WarcraftKeyRemapper" / "last_error.txt"

_SHELL_EXECUTE_ERRORS: dict[int, str] = {
    0: "系统内存不足",
    2: "找不到 Python 可执行文件",
    3: "找不到 Python 路径",
    5: "拒绝访问（未通过 UAC 管理员授权）",
    8: "内存不足，无法完成操作",
    11: "可执行文件格式无效",
    26: "无法打开文件共享",
    27: "文件名关联不完整或无效",
    28: "DDE 事务超时",
    29: "DDE 事务失败",
    30: "正在处理其他 DDE 事务",
    31: "没有关联的应用程序",
    32: "找不到指定的 DLL",
}


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _python_executable() -> str:
    if is_frozen():
        return str(Path(sys.executable))
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        py = exe.with_name("python.exe")
        if py.exists():
            return str(py)
    return str(exe)


def _build_launch_params() -> str:
    extra = [arg for arg in sys.argv[1:] if arg != "--no-admin"]
    if is_frozen():
        parts = [f'"{Path(sys.executable).resolve()}"'] + [f'"{arg}"' for arg in extra]
    else:
        script = str(Path(sys.argv[0]).resolve())
        parts = [f'"{script}"'] + [f'"{arg}"' for arg in extra]
    return " ".join(parts)


def _attach_stdio() -> None:
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")


def show_console() -> None:
    kernel32 = ctypes.windll.kernel32
    if kernel32.GetConsoleWindow() == 0:
        kernel32.AllocConsole()
        _attach_stdio()
    elif sys.stdout is None or not hasattr(sys.stdout, "write"):
        _attach_stdio()
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
        ctypes.windll.user32.SetForegroundWindow(hwnd)


def hide_console() -> None:
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)


def _message_box(message: str, title: str = "魔兽改键精灵") -> None:
    ctypes.windll.user32.MessageBoxW(None, message, title, MB_ICONERROR)


def report_fatal_error(message: str) -> None:
    text = message.strip()
    if not text.startswith("错误"):
        text = f"错误：{text}"

    try:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        ERROR_LOG.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass

    show_console()
    print(text, flush=True)
    print(f"（错误日志：{ERROR_LOG}）", flush=True)
    _message_box(text)

    try:
        input("\n按 Enter 键退出...")
    except EOFError:
        pass
    sys.exit(1)


def request_admin() -> None:
    """请求管理员权限，以便 SendInput 能注入到游戏窗口。"""
    if is_admin():
        return

    params = _build_launch_params()
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", _python_executable(), params, str(ROOT), SW_HIDE
    )
    # 用户在 UAC 提示中选择“否”（取消），或权限请求失败时，静默退出。
    # 不再调用 report_fatal_error（它会弹出控制台和错误框），直接结束进程。
    # 常见取消返回值：5 (ERROR_ACCESS_DENIED), 1223 (ERROR_CANCELLED)
    sys.exit(0)


def ensure_admin() -> None:
    if "--no-admin" in sys.argv:
        return
    request_admin()


# ---- 单实例控制 ----
_MUTEX_NAME = "Local\\WarcraftKeyRemapper_SingleInstance"
ERROR_ALREADY_EXISTS = 183


def ensure_single_instance() -> None:
    """通过命名互斥量保证单实例；若已有实例则弹原生提示框并退出当前进程。"""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        return  # 创建失败不阻断，继续启动
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32 = ctypes.windll.user32
        user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
        existing_hwnd = activate_existing_instance()
        # MB_OK | MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND
        user32.MessageBoxW(
            existing_hwnd or 0,
            "魔兽改键精灵已在运行中。",
            "提示",
            0x40 | 0x40000 | 0x10000,
        )
        sys.exit(0)


class AppController:
    def __init__(self) -> None:
        self.profile_service = ProfileService()
        self.state = self.profile_service.load()
        self.detector = WarcraftDetector(self.state.only_when_warcraft_focused)
        self.remapper = KeyboardRemapperService()
        self.window: MainWindow | None = None
        self._is_shutdown = False
        # 跟踪游戏内血条当前状态。假设新开游戏血条默认为“开”（与该游戏实测一致），
        # 这样取消勾选(期望关)时 True!=False 会按一次键关闭；勾选(期望开)时一致不按键。
        self._game_friendly_on = True
        self._game_enemy_on = True
        # 跟踪上次已知的前台魔兽窗口句柄，用于识别“新一局游戏”并重置血条跟踪
        self._last_wc3_hwnd = 0
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None

    def run(self) -> None:
        self._apply_mappings()
        self.remapper.set_should_intercept(self._should_intercept)
        self.remapper.set_on_toggle(self._toggle_remapping)
        self.remapper.set_on_profile_switch(self._switch_profile_hotkey)
        self.remapper.set_enabled(self.state.remapping_enabled)
        self.remapper.set_disable_win_key(self.state.disable_win_key)
        hide_console()

        self.window = MainWindow(
            self.state,
            on_save=self._save,
            on_profile_change=self._change_profile,
            on_toggle_enabled=self._toggle_remapping,
            on_only_warcraft_change=self._set_only_warcraft,
            on_import=self._import_config,
            on_show_friendly_health=self._set_show_friendly_health,
            on_show_enemy_health=self._set_show_enemy_health,
            on_disable_win_key=self._set_disable_win_key,
            on_query_run_status=self._get_run_status,
        )
        self.window.set_close_callback(self._shutdown)

        # 关键架构调整：
        # 钩子直接在主线程安装（主线程有 Tk mainloop 作为消息泵）。
        # 不再使用独立的 GetMessage 线程 + 按需 install/uninstall 轮询。
        # 所有“是否应该改键”的判断都放在钩子回调内部。
        # 这样可以避免钩子线程导致的按键事件丢失问题。
        try:
            self.remapper.install_hook()
        except Exception as e:
            # 如果安装失败（比如权限问题），给出明确错误
            report_fatal_error(f"无法安装键盘钩子：{e}")

        # 启动血条同步线程：检测魔兽进入前台时，把游戏血条状态同步到复选框期望值
        self._hb_thread = threading.Thread(target=self._hb_loop, daemon=True)
        self._hb_thread.start()

        self.window.mainloop()
        self._shutdown()
        sys.exit(0)

    def _apply_mappings(self) -> None:
        self.remapper.set_reverse_map(self.state.build_reverse_map())
        self.remapper.set_combo_map(self.state.build_combo_map())
        self.remapper.set_swallow_keys(self.state.build_swallow_keys())

    def _import_config(self, path: str) -> None:
        """从指定 JSON 文件导入配置，覆盖当前状态并持久化。"""
        import_service = ProfileService()
        # 复用 ProfileService 的解析逻辑，但读取指定文件而非默认 config.json
        from pathlib import Path
        import json
        from src.models import PROFILE_COUNT
        from src.profile_service import ProfileService as _PS

        target = Path(path)
        with open(target, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # 借用 ProfileService 解析单文件
        tmp_service = _PS()
        # 临时把 config_path 指向目标文件来复用 load
        tmp_service.config_path = target
        new_state = tmp_service.load()

        # 用新状态替换当前状态
        self.state = new_state
        self.detector = WarcraftDetector(self.state.only_when_warcraft_focused)
        self.profile_service.save(self.state)
        self._apply_mappings()

    def _should_intercept(self) -> bool:
        """
        回调里用来快速判断“当前这个按键事件我们是否要管”。
        - 本程序界面在前台 → 绝对不管（保证配置时能正常输入）
        - 功能关闭 → 直接放行
        - “仅魔兽前台”模式下，只有魔兽在前台才管
        - 全局模式下只要不是本程序就管
        """
        if self._is_shutdown:
            return False
        if is_own_process_foreground():
            return False
        if not self.state.remapping_enabled:
            return False
        if not self.state.only_when_warcraft_focused:
            return True
        return self.detector.is_warcraft_foreground()

    def _save(self, state: AppState) -> None:
        self.state = state
        self.profile_service.save(state)
        self._apply_mappings()

    def _change_profile(self, index: int) -> None:
        self.state.active_profile_index = index
        self._apply_mappings()
        if self.window:
            self.window.refresh()

    def _switch_profile_hotkey(self, letter_index: int) -> None:
        if letter_index >= 26:
            return

        def ui_update() -> None:
            self._change_profile(letter_index)
            self.profile_service.save(self.state)

        if self.window and not self._is_shutdown:
            try:
                self.window.after(0, ui_update)
            except tk.TclError:
                pass

    def _toggle_remapping(self) -> None:
        if self._is_shutdown:
            return
        self.state.remapping_enabled = not self.state.remapping_enabled
        self.remapper.set_enabled(self.state.remapping_enabled)
        self.profile_service.save(self.state)

        if self.window and not self._is_shutdown:
            try:
                self.window.after(0, self.window.refresh)
            except tk.TclError:
                pass

    def _set_only_warcraft(self, value: bool) -> None:
        self.state.only_when_warcraft_focused = value
        self.detector.set_only_warcraft(value)
        self.profile_service.save(self.state)

    def _set_show_friendly_health(self, value: bool) -> None:
        """友方血条：勾选=开启，取消=关闭。更新期望值后立即尝试同步（若魔兽在前台）。"""
        self.state.show_friendly_health = value
        self.profile_service.save(self.state)
        self._apply_health_bars()

    def _set_show_enemy_health(self, value: bool) -> None:
        """敌方血条：勾选=开启，取消=关闭。更新期望值后立即尝试同步（若魔兽在前台）。"""
        self.state.show_enemy_health = value
        self.profile_service.save(self.state)
        self._apply_health_bars()

    def _apply_health_bars(self) -> None:
        """
        仅当魔兽在前台时，把游戏血条状态同步到复选框期望值。
        HOME/END 是切换键，所以只在“游戏当前状态 != 期望值”时按一下，确保方向正确。
        注入事件带 LLKHF_INJECTED 标记，键盘钩子会直接放行，不会被改键逻辑拦截。
        """
        if self._is_shutdown:
            return
        hwnd = self.detector.warcraft_foreground_hwnd()
        if not hwnd:
            return
        from src.key_codes import tap_key
        if self._game_friendly_on != self.state.show_friendly_health:
            tap_key(0x24)  # VK_HOME 翻转友方血条
            self._game_friendly_on = self.state.show_friendly_health
        if self._game_enemy_on != self.state.show_enemy_health:
            tap_key(0x23)  # VK_END 翻转敌方血条
            self._game_enemy_on = self.state.show_enemy_health

    def _hb_loop(self) -> None:
        """后台轮询：
        - 魔兽从非前台切到前台时同步一次血条；
        - 若前台魔兽窗口句柄变化（新一局游戏/重启游戏），重置血条跟踪后重新同步。"""
        while not self._hb_stop.is_set():
            try:
                hwnd = self.detector.warcraft_foreground_hwnd()
                if hwnd:
                    if hwnd != self._last_wc3_hwnd:
                        # 新窗口：游戏血条回到默认“开”，重置跟踪再同步
                        self._game_friendly_on = True
                        self._game_enemy_on = True
                        self._apply_health_bars()
                    self._last_wc3_hwnd = hwnd
                else:
                    # 不在前台时清空记录，下次进前台即视为“切入”
                    self._last_wc3_hwnd = 0
            except Exception:
                pass
            self._hb_stop.wait(0.5)

    def _set_disable_win_key(self, value: bool) -> None:
        self.state.disable_win_key = value
        self.remapper.set_disable_win_key(value)
        self.profile_service.save(self.state)

    def _get_run_status(self) -> str:
        """真实判断当前改键运行状态，供 UI 轮询显示。"""
        if self._is_shutdown or not self.remapper.hook_installed:
            return "未运行"
        if not self.state.remapping_enabled:
            return "已停用"
        # 仅魔兽前台模式下，魔兽不在前台 → 待机
        if self.state.only_when_warcraft_focused and not self.detector.is_warcraft_foreground():
            return "待机"
        return "运行中"

    def _shutdown(self) -> None:
        if self._is_shutdown:
            return
        self._is_shutdown = True

        # 停止血条同步线程
        self._hb_stop.set()
        if self._hb_thread is not None:
            try:
                self._hb_thread.join(timeout=1.0)
            except Exception:
                pass

        self.remapper.set_on_toggle(None)
        self.remapper.set_on_profile_switch(None)
        self.remapper.set_enabled(False)
        self.remapper.set_reverse_map({})
        self.remapper.set_combo_map({})
        self.remapper.uninstall_hook()

        self.window = None


def main() -> None:
    try:
        ensure_admin()
        ensure_single_instance()
        app = AppController()
        app.run()
    except Exception as exc:
        report_fatal_error(f"程序异常退出 — {exc}")


if __name__ == "__main__":
    main()
