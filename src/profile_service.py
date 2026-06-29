from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from .models import (
    AppState,
    Combo2Row,
    Combo3Row,
    KeyMappingProfile,
    KeyMappingRow,
    PROFILE_COUNT,
    SKILL_ROW_COUNT,
    COMBO2_ROW_COUNT,
    COMBO3_ROW_COUNT,
)


class ProfileService:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_dir = Path(os.environ.get("APPDATA", ".")) / "WarcraftKeyRemapper"
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / "config.json"
        self._listeners: list[Callable[[AppState], None]] = []

    def add_listener(self, fn: Callable[[AppState], None]) -> None:
        self._listeners.append(fn)

    def _notify(self, state: AppState) -> None:
        for fn in self._listeners:
            fn(state)

    @staticmethod
    def _parse_skill_rows(raw: Union[dict, list, None]) -> List[KeyMappingRow]:
        if not raw:
            return []
        if isinstance(raw, dict):
            return [
                KeyMappingRow(physical_key=physical, game_key=game)
                for game, physical in raw.items()
                if game and physical
            ]
        rows: List[KeyMappingRow] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rows.append(
                KeyMappingRow(
                    physical_key=item.get("physical", item.get("physical_key", "")),
                    game_key=item.get("game", item.get("game_key", "")),
                )
            )
        return rows

    @staticmethod
    def _parse_combo2(raw: list | None) -> List[Combo2Row]:
        if not raw:
            return []
        rows: List[Combo2Row] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rows.append(
                Combo2Row(
                    output_key1=item.get("out1", item.get("output_key1", "")),
                    output_key2=item.get("out2", item.get("output_key2", "")),
                    trigger_key=item.get("trigger", item.get("trigger_key", "")),
                )
            )
        return rows

    @staticmethod
    def _parse_combo3(raw: list | None) -> List[Combo3Row]:
        if not raw:
            return []
        rows: List[Combo3Row] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rows.append(
                Combo3Row(
                    output_key1=item.get("out1", item.get("output_key1", "")),
                    output_key2=item.get("out2", item.get("output_key2", "")),
                    output_key3=item.get("out3", item.get("output_key3", "")),
                    trigger_key=item.get("trigger", item.get("trigger_key", "")),
                )
            )
        return rows

    def _parse_profile(self, item: dict) -> KeyMappingProfile:
        if "inventory" in item or "skills" in item or "combo2" in item or "combo3" in item:
            inv_raw = item.get("inventory")
            if isinstance(inv_raw, dict):
                # 推荐存储： { "NUMPAD7": "S", ... }
                inventory = {k: v for k, v in inv_raw.items() if v}
            elif isinstance(inv_raw, list):
                # 兼容之前错误的 list 格式，尽量转成 dict（丢弃不完整行）
                inventory = {}
                for r in inv_raw:
                    if isinstance(r, dict):
                        g = r.get("game") or r.get("game_key") or ""
                        p = r.get("physical") or r.get("physical_key") or ""
                        if g and p:
                            inventory[g] = p
            else:
                inventory = {}
            profile = KeyMappingProfile(
                index=item.get("index", 0),
                name=item.get("name", ""),
                inventory=inventory,
                skills=self._parse_skill_rows(item.get("skills")),
                combo2=self._parse_combo2(item.get("combo2")),
                combo3=self._parse_combo3(item.get("combo3")),
            )
        else:
            profile = KeyMappingProfile(
                index=item.get("index", 0),
                name=item.get("name", ""),
                skills=self._parse_skill_rows(item.get("mappings")),
            )
        profile.normalize_rows()
        return profile

    def load(self) -> AppState:
        if not self.config_path.exists():
            state = AppState()
            state.ensure_profiles()
            return state

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        profiles = [self._parse_profile(item) for item in raw.get("profiles", [])]

        state = AppState(
            active_profile_index=min(raw.get("active_profile_index", 0), PROFILE_COUNT - 1),
            remapping_enabled=raw.get("remapping_enabled", True),
            only_when_warcraft_focused=raw.get("only_when_warcraft_focused", True),
            show_friendly_health=raw.get("show_friendly_health", True),
            show_enemy_health=raw.get("show_enemy_health", True),
            disable_win_key=raw.get("disable_win_key", True),
            profiles=profiles,
        )
        state.ensure_profiles()
        return state

    @staticmethod
    def _serialize_profile(profile: KeyMappingProfile) -> dict:
        profile.normalize_rows()
        # inventory 存为简单 dict： fixed_slot -> physical_key
        inv_clean = {k: v for k, v in profile.inventory.items() if k and v}
        return {
            "index": profile.index,
            "name": profile.name,
            "inventory": inv_clean,
            "skills": [
                {"physical": row.physical_key, "game": row.game_key}
                for row in profile.skills
                if row.physical_key or row.game_key
            ],
            "combo2": [
                {"out1": row.output_key1, "out2": row.output_key2, "trigger": row.trigger_key}
                for row in profile.combo2
                if row.output_key1 or row.output_key2 or row.trigger_key
            ],
            "combo3": [
                {
                    "out1": row.output_key1,
                    "out2": row.output_key2,
                    "out3": row.output_key3,
                    "trigger": row.trigger_key,
                }
                for row in profile.combo3
                if row.output_key1 or row.output_key2 or row.output_key3 or row.trigger_key
            ],
        }

    def save(self, state: AppState) -> None:
        state.ensure_profiles()
        payload = {
            "active_profile_index": state.active_profile_index,
            "remapping_enabled": state.remapping_enabled,
            "only_when_warcraft_focused": state.only_when_warcraft_focused,
            "show_friendly_health": state.show_friendly_health,
            "show_enemy_health": state.show_enemy_health,
            "disable_win_key": state.disable_win_key,
            "profiles": [self._serialize_profile(p) for p in state.profiles],
        }
        tmp = self.config_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self.config_path)
        self._notify(state)

    def switch_profile(self, state: AppState, index: int) -> None:
        if 0 <= index < PROFILE_COUNT:
            state.active_profile_index = index
            self.save(state)
