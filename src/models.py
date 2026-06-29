from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

PROFILE_COUNT = 26
SKILL_ROW_COUNT = 8
COMBO2_ROW_COUNT = 3
COMBO3_ROW_COUNT = 3

# 物品栏 3行2列 排列（对应游戏下方6个固定物品位置）。
# 每个位置在游戏中有固定的快捷键来触发使用该格子的道具。
#
# 用户只需为每个“物品X”位置填写自己想按的字母键（实际按的键）。
# 程序会在按下时模拟发送该位置对应的游戏快捷键，从而使用对应位置的道具（无论里面放什么）。
#
# 以下是用户确认的对应关系（视觉位置 → 游戏中实际触发的按键）：
#   物品1 → 小键盘7
#   物品2 → 小键盘8
#   物品3 → 小键盘4
#   物品4 → 小键盘5
#   物品5 → 小键盘1
#   物品6 → 小键盘2
#
# 布局在界面上显示为：
#   左列：物品1、物品3、物品5
#   右列：物品2、物品4、物品6
INVENTORY_SLOTS: List[tuple[str, str]] = [
    ("NUMPAD7", "小键盘7"),
    ("NUMPAD8", "小键盘8"),
    ("NUMPAD4", "小键盘4"),
    ("NUMPAD5", "小键盘5"),
    ("NUMPAD1", "小键盘1"),
    ("NUMPAD2", "小键盘2"),
]


@dataclass
class KeyMappingRow:
    physical_key: str = ""
    game_key: str = ""


@dataclass
class Combo2Row:
    output_key1: str = ""
    output_key2: str = ""
    trigger_key: str = ""


@dataclass
class Combo3Row:
    output_key1: str = ""
    output_key2: str = ""
    output_key3: str = ""
    trigger_key: str = ""


@dataclass
class KeyMappingProfile:
    index: int
    name: str = ""
    inventory: Dict[str, str] = field(default_factory=dict)  # fixed_slot_id (如"NUMPAD7") -> user_physical_key (如"S")
    skills: List[KeyMappingRow] = field(default_factory=list)
    combo2: List[Combo2Row] = field(default_factory=list)
    combo3: List[Combo3Row] = field(default_factory=list)

    def normalize_rows(self) -> None:
        # inventory 用 dict，不需要行数填充
        while len(self.skills) < SKILL_ROW_COUNT:
            self.skills.append(KeyMappingRow())
        self.skills = self.skills[:SKILL_ROW_COUNT]

        while len(self.combo2) < COMBO2_ROW_COUNT:
            self.combo2.append(Combo2Row())
        self.combo2 = self.combo2[:COMBO2_ROW_COUNT]

        while len(self.combo3) < COMBO3_ROW_COUNT:
            self.combo3.append(Combo3Row())
        self.combo3 = self.combo3[:COMBO3_ROW_COUNT]


@dataclass
class AppState:
    active_profile_index: int = 0
    remapping_enabled: bool = True
    only_when_warcraft_focused: bool = True
    # 游戏功能开关（仿市面经典版，默认全部开启）
    show_friendly_health: bool = True
    show_enemy_health: bool = True
    disable_win_key: bool = True
    profiles: List[KeyMappingProfile] = field(default_factory=list)

    def ensure_profiles(self) -> None:
        if len(self.profiles) >= PROFILE_COUNT:
            return
        existing = {p.index: p for p in self.profiles}
        self.profiles = []
        for i in range(PROFILE_COUNT):
            if i in existing:
                profile = existing[i]
            else:
                profile = KeyMappingProfile(index=i, name=f"方案 {i + 1}")
            profile.normalize_rows()
            self.profiles.append(profile)

    def active_profile(self) -> KeyMappingProfile:
        self.ensure_profiles()
        profile = self.profiles[self.active_profile_index]
        profile.normalize_rows()
        return profile

    def build_reverse_map(self) -> Dict[int, int]:
        """
        实际按下的物理键(VK) -> 要让游戏收到的键(VK)。

        技能： physical_key(用户实际按) -> game_key(原技能按键)
        物品栏：用户为某个固定位置指定的 physical -> 该位置的固定游戏键 (INVENTORY_SLOTS 中的键)
                例如：为“物品1(小键盘7)”设置 S  →  按S时发送小键盘7给游戏，触发该位置的道具。
        """
        from .key_codes import parse_key

        combo_triggers = set(self.build_combo_map().keys())
        result: Dict[int, int] = {}
        profile = self.active_profile()

        # 物品栏：inventory dict 是 fixed_slot_id -> user_physical
        # 我们要的是：user_physical -> fixed_slot_id
        for fixed_id, phys in profile.inventory.items():
            if not phys:
                continue
            src_vk = parse_key(phys)      # 用户实际按的键
            dst_vk = parse_key(fixed_id)  # 游戏该物品位置对应的固定键
            if src_vk is None or dst_vk is None or src_vk == dst_vk:
                continue
            if src_vk in combo_triggers:
                continue
            result[src_vk] = dst_vk

        for row in profile.skills:
            if not row.physical_key or not row.game_key:
                continue
            # physical_key = 用户实际按的键
            # game_key     = 原技能按键（游戏里这个技能默认的键）
            src_vk = parse_key(row.physical_key)
            dst_vk = parse_key(row.game_key)
            if src_vk is None or dst_vk is None or src_vk == dst_vk:
                continue
            if src_vk in combo_triggers:
                continue
            result[src_vk] = dst_vk

        return result

    def build_swallow_keys(self) -> set[int]:
        """
        需要完全吞掉的按键（防止原按键同时触发游戏原有绑定）。

        - 技能：如果原技能按键(game_key) 被映射走，则吞掉，除非它被用作其他映射的实际按键。
        - 物品栏：如果某个固定物品位置的键 (如小键盘7) 被分配了物理键，则吞掉该固定键，
          除非该键被用作其他地方的“实际按的键”。

        这支持“被替换键可复用”（如 E→R, R→T）。
        """
        from .key_codes import parse_key

        profile = self.active_profile()

        used_physical: set[int] = set()
        mapped_game_keys: set[int] = set()

        # 技能
        for row in profile.skills:
            if row.physical_key:
                pv = parse_key(row.physical_key)
                if pv is not None:
                    used_physical.add(pv)
            if row.physical_key and row.game_key:
                gv = parse_key(row.game_key)
                if gv is not None:
                    mapped_game_keys.add(gv)

        # 物品栏：inventory 的 key 就是固定原键 (NUMPAD7 等)
        for fixed_id, phys in profile.inventory.items():
            if phys:
                pv = parse_key(phys)
                if pv is not None:
                    used_physical.add(pv)
            if fixed_id:
                gv = parse_key(fixed_id)
                if gv is not None:
                    mapped_game_keys.add(gv)

        to_swallow = mapped_game_keys - used_physical
        return to_swallow

    def build_combo_map(self) -> Dict[int, List[int]]:
        """触发键(VK) -> 依次注入的游戏键列表。"""
        from .key_codes import parse_key

        result: Dict[int, List[int]] = {}
        profile = self.active_profile()

        for row in profile.combo2:
            if not row.trigger_key or not row.output_key1 or not row.output_key2:
                continue
            trigger = parse_key(row.trigger_key)
            keys = [parse_key(row.output_key1), parse_key(row.output_key2)]
            if trigger is None or any(k is None for k in keys):
                continue
            result[trigger] = keys

        for row in profile.combo3:
            if not row.trigger_key or not row.output_key1 or not row.output_key2 or not row.output_key3:
                continue
            trigger = parse_key(row.trigger_key)
            keys = [
                parse_key(row.output_key1),
                parse_key(row.output_key2),
                parse_key(row.output_key3),
            ]
            if trigger is None or any(k is None for k in keys):
                continue
            result[trigger] = keys

        return result

    def valid_mapping_count(self) -> int:
        return len(self.build_reverse_map()) + len(self.build_combo_map())
