from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont
from pathlib import Path
from typing import Callable, Dict, List, Optional

APP_VERSION = "v4.75"

from ..models import (
    COMBO2_ROW_COUNT,
    COMBO3_ROW_COUNT,
    INVENTORY_SLOTS,
    SKILL_ROW_COUNT,
    AppState,
    Combo2Row,
    Combo3Row,
    KeyMappingRow,
    PROFILE_COUNT,
)
from .key_entry import KeyCaptureEntry


def _bind_tooltip(widget: tk.Widget, text: str) -> None:
    """给控件绑定简单的悬浮提示（进入显示，离开隐藏）。"""
    tip: List[Optional[tk.Toplevel]] = [None]

    def _show(_event=None) -> None:
        if tip[0] is not None:
            return
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        t = tk.Toplevel(widget)
        t.wm_overrideredirect(True)
        t.wm_geometry(f"+{x}+{y}")
        tk.Label(
            t,
            text=text,
            background="#ffffe0",
            foreground="#000000",
            relief="solid",
            borderwidth=1,
            padx=4,
            pady=2,
            font=("Microsoft YaHei UI", 9),
        ).pack()
        tip[0] = t

    def _hide(_event=None) -> None:
        t = tip[0]
        tip[0] = None
        if t is not None:
            try:
                t.destroy()
            except Exception:
                pass

    widget.bind("<Enter>", _show)
    widget.bind("<Leave>", _hide)


class MainWindow(tk.Tk):
    """仿市场版四宫格布局。"""

    def __init__(
        self,
        state: AppState,
        on_save: Callable[[AppState], None],
        on_profile_change: Callable[[int], None],
        on_toggle_enabled: Callable[[], None],
        on_only_warcraft_change: Callable[[bool], None],
        on_import: Optional[Callable[[str], None]] = None,
        on_show_friendly_health: Optional[Callable[[bool], None]] = None,
        on_show_enemy_health: Optional[Callable[[bool], None]] = None,
        on_disable_win_key: Optional[Callable[[bool], None]] = None,
        on_query_run_status: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__()
        # 构建期间隐藏窗口，避免控件逐个 pack 时从左上角“撑开”的视觉效果
        self.withdraw()
        self.state = state
        self.on_save = on_save
        self.on_profile_change = on_profile_change
        self.on_toggle_enabled = on_toggle_enabled
        self.on_only_warcraft_change = on_only_warcraft_change
        self.on_import = on_import
        self.on_show_friendly_health = on_show_friendly_health
        self.on_show_enemy_health = on_show_enemy_health
        self.on_disable_win_key = on_disable_win_key
        self.on_query_run_status = on_query_run_status

        self.title("魔兽改键精灵")
        self.resizable(False, False)
        self.configure(bg="#ece9d8")

        try:
            base = Path(__file__).resolve().parent.parent.parent / "assets"
            ico_path = base / "logo.ico"
            if ico_path.exists():
                self.iconbitmap(str(ico_path))
            png_path = base / "logo.png"
            if png_path.exists():
                self._app_icon = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self._inventory_entries: Dict[str, KeyCaptureEntry] = {}
        self._skill_rows: List[tuple[KeyCaptureEntry, KeyCaptureEntry]] = []
        self._combo2_rows: List[tuple[KeyCaptureEntry, KeyCaptureEntry, KeyCaptureEntry]] = []
        self._combo3_rows: List[tuple[KeyCaptureEntry, KeyCaptureEntry, KeyCaptureEntry, KeyCaptureEntry]] = []

        self._build_style()
        self._build_ui()
        self._load_profile_to_ui()
        self._update_status()

        # 启动运行状态轮询（每 500ms 真实判断一次）
        self._run_status_poll_id: Optional[str] = None
        self._poll_run_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._on_close_callback: Optional[Callable[[], None]] = None
        self._is_minimized = False
        self.bind("<Unmap>", self._on_unmap)
        self.bind("<Map>", self._on_map)

        self._show_when_ready()

    def _show_when_ready(self) -> None:
        """布局全部算完后再一次性显示，避免启动时窗口从角上逐步展开。"""
        if getattr(self, "_status_box", None) is not None:
            self._align_status_heights(self._status_box)
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.update_idletasks()
        self.deiconify()

    def _on_unmap(self, event: tk.Event) -> None:
        if event.widget is self and self.state() == "iconic":
            self._is_minimized = True

    def _on_map(self, event: tk.Event) -> None:
        if event.widget is self:
            self._is_minimized = False

    @property
    def is_minimized(self) -> bool:
        return self._is_minimized or self.state() == "iconic"

    def set_close_callback(self, fn: Callable[[], None]) -> None:
        self._on_close_callback = fn

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#ece9d8")
        style.configure("TLabelframe", background="#ece9d8")
        style.configure("TLabelframe.Label", background="#ece9d8", font=("Microsoft YaHei UI", 9))
        style.configure("TLabel", background="#ece9d8", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=4)
        # 紧凑按钮：纵向 padding 减小，整体高度约缩减 10%
        style.configure("Compact.TButton", font=("Microsoft YaHei UI", 9), padding=(6, 2))
        # 状态栏按钮：字体降一号 + 横向 padding 收到 0，宽度较默认缩减约 20%；
        # 纵向 padding 按字体度量初估（运行时 _align_status_heights 会实测微调到精确等高）
        _stat_fnt = tkfont.Font(self, font=("Microsoft YaHei UI", 10, "bold"))
        _btn_fnt = tkfont.Font(self, font=("Microsoft YaHei UI", 8))
        _target_h = _stat_fnt.metrics("linespace") + 6  # 状态框 padding 2*2 + 边框 1*2
        _btn_pady = max(0, (_target_h - _btn_fnt.metrics("linespace") - 2) // 2)
        style.configure("Status.TButton", font=("Microsoft YaHei UI", 8), padding=(0, _btn_pady))
        style.configure("TCheckbutton", background="#ece9d8", font=("Microsoft YaHei UI", 9))
        # 下拉框：readonly 状态下字段背景与主题色一致，避免出现灰色块
        style.configure("TCombobox", fieldbackground="#ece9d8", background="#ece9d8",
                        foreground="black", arrowcolor="#333333")
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#ece9d8")],
                  background=[("readonly", "#ece9d8")],
                  foreground=[("readonly", "black")])

    @staticmethod
    def _green_label(parent: ttk.Frame, text: str) -> ttk.Label:
        return ttk.Label(parent, text=text, foreground="#008800", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=2)
        outer.pack(fill="both", expand=True)

        # 点击空白区域时，把焦点移到主窗口，让所有 KeyCaptureEntry 失去焦点并恢复原始外观
        def _clear_focus_on_background(_event=None):
            try:
                self.focus_set()
            except Exception:
                pass
        outer.bind("<Button-1>", _clear_focus_on_background, add="+")

        header = ttk.Frame(outer, relief="groove", borderwidth=1, padding=4)
        header.pack(fill="x", pady=(0, 4))

        # ---- 左侧：logo + 标题 + 版本号 ----
        base = Path(__file__).resolve().parent.parent.parent / "assets"
        # 巫妖王 logo
        try:
            war3_path = base / "war3_logo_32.png"
            if war3_path.exists():
                self._title_icon = tk.PhotoImage(file=str(war3_path))
                ttk.Label(header, image=self._title_icon, background="#ece9d8").pack(side="left", padx=(0, 6))
        except Exception:
            pass
        ttk.Label(header, text="魔兽改键精灵", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text=APP_VERSION,
            foreground="#666666",
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(6, 0))

        # ---- 右侧：4 个操作图标按钮 ----
        self._action_icons: Dict[str, tk.PhotoImage] = {}
        icons_dir = base / "icons"
        icon_specs = [
            ("icon_settings.png", "设置", self._open_settings),
            ("icon_save.png", "保存方案", self._save),
            ("icon_import.png", "导入配置", self._import_config),
            ("icon_about.png", "关于", self._open_about),
        ]
        for fname, tooltip, cmd in icon_specs:
            try:
                p = icons_dir / fname
                if p.exists():
                    img = tk.PhotoImage(file=str(p))
                    self._action_icons[fname] = img
                    btn = tk.Button(
                        header,
                        image=img,
                        command=cmd,
                        relief="flat",
                        bd=0,
                        cursor="hand2",
                        background="#ece9d8",
                        activebackground="#ece9d8",
                        highlightthickness=0,
                        takefocus=False,
                    )
                    btn.pack(side="right", padx=(3, 0))
                    btn.bind("<FocusIn>", lambda e: header.focus_set())
                    # 简易 tooltip
                    _bind_tooltip(btn, tooltip)
            except Exception:
                pass

        # ---- 第二栏：左两个上下叠加的框 + 右一个等高框 ----
        # 左上：欢迎语；左下：3 个等宽复选框；右：方案选择 + 保存按钮（跨两行等高）
        section = ttk.Frame(outer)
        section.pack(fill="x", pady=(0, 6))
        section.columnconfigure(0, weight=1)
        section.columnconfigure(1, weight=0)

        # 左上：欢迎语（细边框，无标题缺口，最紧凑）
        welcome_box = ttk.Frame(section, relief="groove", borderwidth=1, padding=2)
        welcome_box.grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=(0, 1))
        ttk.Label(
            welcome_box,
            text="欢迎使用魔兽改键精灵",
            foreground="#ff8800",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left", anchor="w")

        # 左下：3 个等宽复选框（细边框）
        func_box = ttk.Frame(section, relief="groove", borderwidth=1, padding=2)
        func_box.grid(row=1, column=0, sticky="ew", padx=(0, 3))
        func_box.columnconfigure((0, 1, 2), weight=1, uniform="func")

        self.friendly_health_var = tk.BooleanVar(value=self.state.show_friendly_health)
        tk.Checkbutton(
            func_box,
            text="显示友方血条",
            variable=self.friendly_health_var,
            command=self._on_friendly_health_toggle,
            background="#ece9d8",
            selectcolor="#ece9d8",
            activebackground="#ece9d8",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=0, sticky="w")

        self.enemy_health_var = tk.BooleanVar(value=self.state.show_enemy_health)
        tk.Checkbutton(
            func_box,
            text="显示敌方血条",
            variable=self.enemy_health_var,
            command=self._on_enemy_health_toggle,
            background="#ece9d8",
            selectcolor="#ece9d8",
            activebackground="#ece9d8",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=1, sticky="w")

        self.disable_win_var = tk.BooleanVar(value=self.state.disable_win_key)
        tk.Checkbutton(
            func_box,
            text="禁止用WIN键",
            variable=self.disable_win_var,
            command=self._on_disable_win_toggle,
            background="#ece9d8",
            selectcolor="#ece9d8",
            activebackground="#ece9d8",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=2, sticky="w")

        # 右：方案选择 + 保存按钮（细边框，跨两行纵向撑满与左侧总高一致）
        right_box = ttk.Frame(section, relief="groove", borderwidth=1, padding=2)
        right_box.grid(row=0, column=1, rowspan=2, sticky="ns")

        self.profile_var = tk.StringVar()
        values = [f"方案 {i + 1}" for i in range(PROFILE_COUNT)]
        self.profile_combo = ttk.Combobox(
            right_box, textvariable=self.profile_var, values=values, width=14, state="readonly"
        )
        self.profile_combo.pack(fill="x", pady=(0, 4))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        # 保存方案按钮：宽度收窄（8 字符 ≈ 缩减 30%）、高度缩减 10%、在框内居中
        save_btn = ttk.Button(
            right_box, text="保存方案", style="Compact.TButton", width=8, command=self._save,
            takefocus=False,
        )
        save_btn.pack(anchor="center")
        save_btn.bind("<FocusIn>", lambda e: right_box.focus_set())

        grid = ttk.Frame(outer)
        grid.pack(fill="both", expand=True, pady=1)
        grid.bind("<Button-1>", _clear_focus_on_background, add="+")

        self._build_inventory_panel(grid)
        self._build_skill_panel(grid)
        self._build_combo2_panel(grid)
        self._build_combo3_panel(grid)

        # 第五栏：状态框（放大字体，带边框）与两个按钮同一行水平居中对齐
        self._run_status_text = "运行中"
        status_row = ttk.Frame(outer)
        status_row.pack(fill="x", pady=2)
        # 状态框：groove 外边框，内部 3 个格子按内容宽度（不等宽、不扩展）+ 2 条竖向分隔线
        # 状态框本身 fill+expand 填满到第 4 栏宽度，但格子只占内容所需，多出空间为背景色
        status_box = ttk.Frame(status_row, relief="groove", borderwidth=1, padding=(8, 2))
        status_box.pack(side="left", fill="x", expand=True)
        _stat_font = ("Microsoft YaHei UI", 10, "bold")
        self._state_label = tk.Label(
            status_box, text="状态：", foreground="#008800",
            background="#ece9d8", font=_stat_font, anchor="w",
        )
        self._profile_label = tk.Label(
            status_box, text="启用：方案1", foreground="#008800",
            background="#ece9d8", font=_stat_font, anchor="w",
        )
        self._count_label = tk.Label(
            status_box, text="映射：0", foreground="#008800",
            background="#ece9d8", font=_stat_font, anchor="w",
        )
        sep1 = ttk.Separator(status_box, orient="vertical")
        sep2 = ttk.Separator(status_box, orient="vertical")
        # 格子按内容宽度排列，不设 weight/uniform，避免撑宽
        self._state_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        sep1.grid(row=0, column=1, sticky="ns", padx=2)
        self._profile_label.grid(row=0, column=2, sticky="w", padx=(6, 6))
        sep2.grid(row=0, column=3, sticky="ns", padx=2)
        self._count_label.grid(row=0, column=4, sticky="w", padx=(6, 0))
        # 两个按钮靠右；保存引用，便于实测高度后精准对齐状态框
        self._status_btn1 = self._make_button(status_row, "启用/停用", self._toggle, style="Status.TButton")
        self._status_btn1.pack(side="right", padx=2)
        self._status_btn2 = self._make_button(status_row, "方案重置", self._clear_current, style="Status.TButton")
        self._status_btn2.pack(side="right", padx=2)
        self._status_box = status_box

        # 仅魔兽前台改键：框外末尾，靠左
        opt_row = ttk.Frame(outer)
        opt_row.pack(fill="x", pady=1)
        self.only_warcraft_var = tk.BooleanVar(value=self.state.only_when_warcraft_focused)
        tk.Checkbutton(
            opt_row,
            text="仅在魔兽争霸窗口前台时改键（推荐）",
            variable=self.only_warcraft_var,
            command=self._on_only_warcraft_toggle,
            background="#ece9d8",
            selectcolor="#ece9d8",
            activebackground="#ece9d8",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w")

        self._dirty = False

    def _build_inventory_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="自定义包裹快捷键", padding=2)
        frame.grid(row=0, column=0, padx=1, pady=1, sticky="nsew")

        # 3行2列紧凑布局
        cols_container = ttk.Frame(frame)
        cols_container.pack()
        left_col = ttk.Frame(cols_container)
        left_col.pack(side="left", padx=1)
        right_col = ttk.Frame(cols_container)
        right_col.pack(side="left", padx=1)

        left_indices = [0, 2, 4]
        right_indices = [1, 3, 5]
        for col, indices in ((left_col, left_indices), (right_col, right_indices)):
            for idx in indices:
                fixed_id, display_name = INVENTORY_SLOTS[idx]
                row = ttk.Frame(col)
                row.pack(fill="x", pady=(2, 2))

                # 只显示 "小键盘X:"，使用固定宽度+右对齐，让冒号紧贴后面的箭头（与其他面板风格一致）
                ttk.Label(row, text=display_name + ":", width=6, anchor="e").pack(side="left", padx=(0, 0))
                self._green_label(row, "→").pack(side="left", padx=0)

                entry = KeyCaptureEntry(row, on_change=self._mark_dirty)
                entry.pack(side="left", padx=0)
                entry.set_readonly()
                self._inventory_entries[fixed_id] = entry
                # 物品栏填的是“实际按的键” → 触发源角色
                # partner 是该槽位的固定游戏键（如 NUMPAD7），按 NUMPAD7 映射 NUMPAD7 即自映射
                self._attach_validator(entry, "src", partners=(lambda _fid=fixed_id: _fid,))

    def _build_skill_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="自定义技能快捷键", padding=2)
        frame.grid(row=0, column=1, padx=1, pady=1, sticky="nsew")

        # 两列紧凑展示（每列4个），列间留少量间隔以区分
        cols_container = ttk.Frame(frame)
        cols_container.pack()

        left_col = ttk.Frame(cols_container)
        left_col.pack(side="left", padx=(0, 4))
        right_col = ttk.Frame(cols_container)
        right_col.pack(side="left", padx=(4, 0))

        for i, col in enumerate((left_col, right_col)):
            start = i * 4
            for j in range(4):
                row = ttk.Frame(col)
                row.pack(fill="x", pady=(2, 2))
                ttk.Label(row, text="默认:", width=4, anchor="e").pack(side="left")
                # 左边：原技能按键（游戏里这个技能默认绑定的键，如 C）
                original = KeyCaptureEntry(row, on_change=self._mark_dirty)
                original.pack(side="left", padx=0)
                original.set_readonly()
                self._green_label(row, "→").pack(side="left", padx=0)
                # 右边：用户实际要按的物理键（如 E），按这个键就触发原技能
                physical = KeyCaptureEntry(row, on_change=self._mark_dirty)
                physical.pack(side="left", padx=0)
                physical.set_readonly()
                self._skill_rows.append((original, physical))
                # original=游戏原键(目标键) → dst 角色；physical=实际按的键(触发源) → src 角色
                # partners 指向同一行另一端，用于拦截自映射（如 H→H）
                self._attach_validator(original, "dst", partners=(physical.get_key,))
                self._attach_validator(physical, "src", partners=(original.get_key,))

    def _build_combo2_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="一键必杀 (2键合一)", padding=2)
        frame.grid(row=1, column=0, padx=1, pady=1, sticky="nsew")

        for _ in range(COMBO2_ROW_COUNT):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=(2, 2))
            ttk.Label(row, text="默认键:", width=5, anchor="e").pack(side="left")
            out1 = KeyCaptureEntry(row, on_change=self._mark_dirty)
            out1.pack(side="left", padx=0)
            out1.set_readonly()
            self._green_label(row, "+").pack(side="left", padx=0)
            out2 = KeyCaptureEntry(row, on_change=self._mark_dirty)
            out2.pack(side="left", padx=0)
            out2.set_readonly()
            self._green_label(row, "→").pack(side="left", padx=0)
            trigger = KeyCaptureEntry(row, on_change=self._mark_dirty)
            trigger.pack(side="left", padx=0)
            trigger.set_readonly()
            self._combo2_rows.append((out1, out2, trigger))
            # out1/out2=游戏原键(目标键) → dst；trigger=实际按的键(触发源) → src
            # 自映射检查：trigger 不能等于任一 output（反之亦然）
            self._attach_validator(out1, "dst", partners=(trigger.get_key,))
            self._attach_validator(out2, "dst", partners=(trigger.get_key,))
            self._attach_validator(trigger, "src", partners=(out1.get_key, out2.get_key))

    def _build_combo3_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="一键必杀 (3键合一)", padding=2)
        frame.grid(row=1, column=1, padx=1, pady=1, sticky="nsew")

        for _ in range(COMBO3_ROW_COUNT):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=(2, 2))
            ttk.Label(row, text="默认键:", width=5, anchor="e").pack(side="left")
            out1 = KeyCaptureEntry(row, on_change=self._mark_dirty)
            out1.pack(side="left", padx=0)
            out1.set_readonly()
            self._green_label(row, "+").pack(side="left", padx=0)
            out2 = KeyCaptureEntry(row, on_change=self._mark_dirty)
            out2.pack(side="left", padx=0)
            out2.set_readonly()
            self._green_label(row, "+").pack(side="left", padx=0)
            out3 = KeyCaptureEntry(row, on_change=self._mark_dirty)
            out3.pack(side="left", padx=0)
            out3.set_readonly()
            self._green_label(row, "→").pack(side="left", padx=0)
            trigger = KeyCaptureEntry(row, on_change=self._mark_dirty)
            trigger.pack(side="left", padx=0)
            trigger.set_readonly()
            self._combo3_rows.append((out1, out2, out3, trigger))
            # out1/out2/out3=游戏原键(目标键) → dst；trigger=实际按的键(触发源) → src
            # 自映射检查：trigger 不能等于任一 output（反之亦然）
            self._attach_validator(out1, "dst", partners=(trigger.get_key,))
            self._attach_validator(out2, "dst", partners=(trigger.get_key,))
            self._attach_validator(out3, "dst", partners=(trigger.get_key,))
            self._attach_validator(trigger, "src", partners=(out1.get_key, out2.get_key, out3.get_key))

    def _mark_dirty(self) -> None:
        self._dirty = True
        # 实时把 UI 同步到 state，让状态栏的「映射」数量反映当前编辑（含未保存的改动）
        self._sync_ui_to_state()
        self._update_status()

    # ---------- 按键冲突校验 ----------

    def _attach_validator(
        self,
        entry: KeyCaptureEntry,
        role: str,
        partners: tuple = (),
    ) -> None:
        """
        给一个 KeyCaptureEntry 挂上指定角色的冲突校验器。
        partners: 同一映射单元里“另一端”的取值回调元组，用于自映射检查（src == dst）。
                  每个回调返回 str（可为空）。
        """
        def validator(key_name: str) -> bool:
            return self._check_key_conflict(entry, role, key_name, partners)
        entry.set_validator(validator)

    def _check_key_conflict(
        self,
        entry: KeyCaptureEntry,
        role: str,
        new_key: str,
        partners: tuple = (),
    ) -> bool:
        """
        返回 True 表示无冲突可接受，False 表示有冲突已拒绝（并已弹框提示）。
        role == "src"：触发源（实际按的键）—— 技能 physical / 物品栏值 / combo trigger
        role == "dst"：目标键（游戏原键）—— 技能 game_key / combo 各 output
        partners：同一映射单元的另一端键，用于拦截自映射（如 H→H、NUMPAD7→NUMPAD7）。
        """
        if not new_key:
            return True
        # 1) 自映射检查：新键 == 同一映射单元的另一端
        for getter in partners:
            try:
                p = getter() or ""
            except Exception:
                p = ""
            if p and p == new_key:
                messagebox.showwarning(
                    "映射冲突",
                    f"按键 “{new_key}” 与该映射的目标键相同，自映射没有意义。\n本次输入已被取消。",
                )
                return False
        # 2) 跨映射重复检查
        if role == "src":
            existing = self._collect_src_keys(exclude=entry)
            role_label = "触发键（实际按的键）"
        else:
            existing = self._collect_dst_keys(exclude=entry)
            role_label = "目标键（游戏原键）"
        if new_key in existing:
            messagebox.showwarning(
                "映射冲突",
                f"按键 “{new_key}” 已经被其他映射作为{role_label}使用，不能重复。\n本次输入已被取消。",
            )
            return False
        return True

    def _collect_src_keys(self, exclude: KeyCaptureEntry) -> set:
        """收集所有“触发源”角色的当前键（排除正在编辑的 entry 自己）。"""
        keys: set = set()
        # 技能 physical（右框）
        for _original, physical in self._skill_rows:
            if physical is exclude:
                continue
            v = physical.get_key()
            if v:
                keys.add(v)
        # 物品栏填的值（用户实际按的键）
        for _fixed_id, entry in self._inventory_entries.items():
            if entry is exclude:
                continue
            v = entry.get_key()
            if v:
                keys.add(v)
        # combo2 / combo3 触发键
        for _out1, _out2, trigger in self._combo2_rows:
            if trigger is exclude:
                continue
            v = trigger.get_key()
            if v:
                keys.add(v)
        for _out1, _out2, _out3, trigger in self._combo3_rows:
            if trigger is exclude:
                continue
            v = trigger.get_key()
            if v:
                keys.add(v)
        return keys

    def _collect_dst_keys(self, exclude: KeyCaptureEntry) -> set:
        """收集所有“目标键”角色的当前键（排除正在编辑的 entry 自己）。"""
        keys: set = set()
        # 技能 game_key（左框 = 原技能按键）
        for original, _physical in self._skill_rows:
            if original is exclude:
                continue
            v = original.get_key()
            if v:
                keys.add(v)
        # combo 输出键
        for out1, out2, _trigger in self._combo2_rows:
            for e in (out1, out2):
                if e is exclude:
                    continue
                v = e.get_key()
                if v:
                    keys.add(v)
        for out1, out2, out3, _trigger in self._combo3_rows:
            for e in (out1, out2, out3):
                if e is exclude:
                    continue
                v = e.get_key()
                if v:
                    keys.add(v)
        return keys

    def _on_profile_selected(self, _event=None) -> None:
        idx = self.profile_combo.current()
        if idx >= 0:
            self._sync_ui_to_state()
            self.on_profile_change(idx)
            self._load_profile_to_ui()

    def _load_profile_to_ui(self) -> None:
        profile = self.state.active_profile()
        self.profile_var.set(profile.name or f"方案 {profile.index + 1}")
        self.profile_combo.current(profile.index)

        for fixed_id, entry in self._inventory_entries.items():
            val = profile.inventory.get(fixed_id, "")
            entry.set_value(val)
            entry.set_readonly()

        for index, (original, physical) in enumerate(self._skill_rows):
            row = profile.skills[index]
            # 左边显示“原技能按键”（游戏里这个技能原本绑定的键，如 C）
            original.set_value(row.game_key)
            # 右边显示“实际按的键”（用户要按哪个物理键来触发它，如 E）
            physical.set_value(row.physical_key)
            original.set_readonly()
            physical.set_readonly()

        for index, (out1, out2, trigger) in enumerate(self._combo2_rows):
            row = profile.combo2[index]
            out1.set_value(row.output_key1)
            out2.set_value(row.output_key2)
            trigger.set_value(row.trigger_key)
            out1.set_readonly()
            out2.set_readonly()
            trigger.set_readonly()

        for index, (out1, out2, out3, trigger) in enumerate(self._combo3_rows):
            row = profile.combo3[index]
            out1.set_value(row.output_key1)
            out2.set_value(row.output_key2)
            out3.set_value(row.output_key3)
            trigger.set_value(row.trigger_key)
            out1.set_readonly()
            out2.set_readonly()
            out3.set_readonly()
            trigger.set_readonly()

        self._dirty = False

    def _sync_ui_to_state(self) -> None:
        profile = self.state.active_profile()

        # 物品栏：fixed_id -> 用户填的实际按键
        inventory: Dict[str, str] = {}
        for fixed_id, entry in self._inventory_entries.items():
            val = entry.get_key()
            if val:
                inventory[fixed_id] = val
        profile.inventory = inventory

        skills: List[KeyMappingRow] = []
        for original, physical in self._skill_rows:
            skills.append(
                KeyMappingRow(
                    # 左边 original = 原技能按键 → 存为 game_key（游戏收到的）
                    game_key=original.get_key(),
                    # 右边 physical = 实际按的键 → 存为 physical_key（触发源）
                    physical_key=physical.get_key(),
                )
            )
        profile.skills = skills

        combo2: List[Combo2Row] = []
        for out1, out2, trigger in self._combo2_rows:
            combo2.append(
                Combo2Row(
                    output_key1=out1.get_key(),
                    output_key2=out2.get_key(),
                    trigger_key=trigger.get_key(),
                )
            )
        profile.combo2 = combo2

        combo3: List[Combo3Row] = []
        for out1, out2, out3, trigger in self._combo3_rows:
            combo3.append(
                Combo3Row(
                    output_key1=out1.get_key(),
                    output_key2=out2.get_key(),
                    output_key3=out3.get_key(),
                    trigger_key=trigger.get_key(),
                )
            )
        profile.combo3 = combo3
        profile.normalize_rows()

    def _save(self) -> None:
        self._sync_ui_to_state()
        self.on_save(self.state)
        self._dirty = False
        count = self.state.valid_mapping_count()
        messagebox.showinfo("保存成功", f"方案 {self.state.active_profile_index + 1} 已保存，有效映射 {count} 条。")

    def _clear_current(self) -> None:
        if not messagebox.askyesno("确认", "确定清空当前方案的所有映射？"):
            return
        profile = self.state.active_profile()
        profile.inventory = {}
        profile.skills = [KeyMappingRow() for _ in range(SKILL_ROW_COUNT)]
        profile.combo2 = [Combo2Row() for _ in range(COMBO2_ROW_COUNT)]
        profile.combo3 = [Combo3Row() for _ in range(COMBO3_ROW_COUNT)]
        profile.normalize_rows()
        self._load_profile_to_ui()
        self._mark_dirty()

    def _toggle(self) -> None:
        self.on_toggle_enabled()
        self._update_status()

    def _on_only_warcraft_toggle(self) -> None:
        self.on_only_warcraft_change(self.only_warcraft_var.get())

    def _on_friendly_health_toggle(self) -> None:
        if self.on_show_friendly_health:
            self.on_show_friendly_health(self.friendly_health_var.get())

    def _on_enemy_health_toggle(self) -> None:
        if self.on_show_enemy_health:
            self.on_show_enemy_health(self.enemy_health_var.get())

    def _on_disable_win_toggle(self) -> None:
        if self.on_disable_win_key:
            self.on_disable_win_key(self.disable_win_var.get())

    def _make_button(self, parent, text, command, style="TButton"):
        """创建一个不带焦点虚线框的按钮：点击后立即把焦点转移走，避免残留虚线框。"""
        btn = ttk.Button(parent, text=text, command=command, takefocus=False, style=style)
        # 即便鼠标点击强行给了焦点，也立刻转给父容器
        btn.bind("<FocusIn>", lambda e: parent.focus_set())
        return btn

    def _align_status_heights(self, status_box) -> None:
        """迭代实测：反复微调 Status.TButton 纵向 padding，直到按钮自然高度与状态框高度差 ≤1px。"""
        try:
            style = ttk.Style(self)
            for _ in range(8):
                self.update_idletasks()
                box_h = status_box.winfo_reqheight()
                btn_h = self._status_btn1.winfo_reqheight()
                diff = box_h - btn_h
                if abs(diff) <= 1:
                    break
                cur = style.lookup("Status.TButton", "padding")
                px, py = (cur[0], cur[1]) if cur and len(cur) >= 2 else (0, 0)
                new_py = max(0, py + diff // 2)
                if new_py == py:
                    break
                style.configure("Status.TButton", padding=(px, new_py))
        except Exception:
            pass

    def _update_status(self) -> None:
        idx = self.state.active_profile_index + 1
        count = self.state.valid_mapping_count()
        # 三列各自独立更新：任一指标长度变化只影响自己那一格，不会挤压其他列
        self._state_label.configure(text=f"状态：{self._run_status_text}")
        self._profile_label.configure(text=f"启用：方案{idx}")
        self._count_label.configure(text=f"映射：{count}")

    def _poll_run_status(self) -> None:
        """每 500ms 向 AppController 查询真实运行状态，刷新状态列文本与颜色。"""
        if self.on_query_run_status is not None:
            text = self.on_query_run_status()
        else:
            text = "运行中" if self.state.remapping_enabled else "已停用"
        if text != self._run_status_text:
            self._run_status_text = text
            self._state_label.configure(text=f"状态：{text}")
        color = "#008800" if text == "运行中" else ("#aa6600" if text == "待机" else "#888888")
        try:
            self._state_label.configure(foreground=color)
        except Exception:
            pass
        self._run_status_poll_id = self.after(500, self._poll_run_status)

    def refresh(self) -> None:
        self._load_profile_to_ui()
        self._update_status()

    # ---- 标题栏右侧图标按钮的功能 ----

    def _open_settings(self) -> None:
        """打开设置对话框（目前仅含「仅魔兽前台改键」选项）。"""
        win = tk.Toplevel(self)
        win.title("设置")
        win.configure(bg="#ece9d8")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        var = tk.BooleanVar(value=self.state.only_when_warcraft_focused)
        tk.Checkbutton(
            win,
            text="仅在魔兽争霸窗口前台时改键（推荐）",
            variable=var,
            command=lambda: self.on_only_warcraft_change(var.get()),
            background="#ece9d8",
            selectcolor="#ece9d8",
            activebackground="#ece9d8",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=12, pady=10)

        ttk.Label(
            win,
            text=f"当前版本：{APP_VERSION}",
            foreground="#666666",
        ).pack(anchor="w", padx=12, pady=(0, 10))
        # 居中显示在主窗口上方
        win.update_idletasks()
        x = self.winfo_rootx() + 40
        y = self.winfo_rooty() + 60
        win.wm_geometry(f"+{x}+{y}")

    def _import_config(self) -> None:
        """从外部 JSON 文件导入配置。"""
        if self._dirty:
            if not messagebox.askyesno(
                "未保存",
                "当前方案有未保存的修改，导入会覆盖当前配置，是否继续？",
            ):
                return
        path = filedialog.askopenfilename(
            title="选择要导入的配置文件",
            filetypes=[("JSON 配置文件", "*.json"), ("所有文件", "*.*")],
            defaultextension="*.json",
        )
        if not path:
            return
        if self.on_import is None:
            messagebox.showwarning("暂不支持", "当前未接入导入功能。")
            return
        try:
            self.on_import(path)
            self._load_profile_to_ui()
            self._update_status()
            messagebox.showinfo("导入成功", f"已从以下文件导入配置：\n{path}")
        except Exception as e:
            messagebox.showerror("导入失败", f"导入配置时出错：\n{e}")

    def _open_about(self) -> None:
        """显示关于对话框。"""
        messagebox.showinfo(
            "关于",
            f"魔兽改键精灵 {APP_VERSION}\n\n"
            "仿市面经典版改键工具，支持：\n"
            "  • 技能/物品快捷键自定义\n"
            "  • 2 键合一 / 3 键合一（一键必杀）\n"
            "  • 26 套方案 + 游戏内 Ctrl+Shift+(A-Z) 切换\n"
            "  • Scroll / Pause 开关改键\n"
            "  • 仅魔兽前台时改键\n\n"
            "配置存储于：%APPDATA%\\WarcraftKeyRemapper\\config.json",
        )

    def _on_close(self) -> None:
        if self._run_status_poll_id is not None:
            try:
                self.after_cancel(self._run_status_poll_id)
            except Exception:
                pass
        if self._dirty:
            if messagebox.askyesno("未保存", "当前方案有未保存的修改，是否保存？"):
                self._save()
        if self._on_close_callback:
            self._on_close_callback()
        self.destroy()
