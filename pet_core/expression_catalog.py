"""
Maps Live2D expression indices to semantic names and aliases.

mao_pro has 8 expressions (exp_01 through exp_08). Each gets a primary
semantic name and optional aliases for flexible LLM matching.

Usage:
    cat = ExpressionCatalog()
    idx = cat.resolve("happy")   # → 3
    idx = cat.resolve("开心")     # → 3 (alias)
    name = cat.name_of(3)        # → "happy"

Configuration can be loaded from config/pet_actions.json:
    cat = ExpressionCatalog.from_config("config/pet_actions.json")
"""

import json
from pathlib import Path
from typing import Optional, Union


# ── Defaults (embedded — overwritten when loaded from config) ──
DEFAULT_INDEX_TO_NAME: dict[int, str] = {
    0: "neutral",
    1: "sad",
    2: "angry",
    3: "happy",
    4: "shy",
    5: "surprised",
    6: "sleepy",
    7: "love",
}

DEFAULT_ALIASES: dict[str, int] = {
    "default": 0, "normal": 0,
    "glad": 3, "joy": 3, "delighted": 3,
    "blush": 4, "embarrassed": 4,
    "shocked": 5, "amazed": 5,
    "mad": 2,
    "unhappy": 1, "cry": 1,
    "tired": 6, "drowsy": 6,
    "affection": 7, "heart": 7,
    "开心": 3, "快乐": 3, "高兴": 3,
    "害羞": 4,
    "惊讶": 5, "吃惊": 5,
    "生气": 2, "愤怒": 2,
    "难过": 1, "悲伤": 1, "伤心": 1,
    "困": 6, "困倦": 6,
    "喜欢": 7, "爱": 7,
    "眨眼": 3,
    "平静": 0,
}

DEFAULT_INDEX = 0


class ExpressionCatalog:
    """Resolves expression names/aliases to Live2D expression indices.

    Args:
        index_to_name: Override for the index→name mapping.
        aliases: Override for the alias→index mapping.
    """

    def __init__(
        self,
        index_to_name: Optional[dict[int, str]] = None,
        aliases: Optional[dict[str, int]] = None,
    ):
        self._index_to_name = dict(index_to_name) if index_to_name else dict(DEFAULT_INDEX_TO_NAME)
        self._name_to_index: dict[str, int] = {
            name: idx for idx, name in self._index_to_name.items()
        }
        self._aliases = dict(aliases) if aliases else dict(DEFAULT_ALIASES)

    @classmethod
    def from_config(cls, path: Union[str, Path]) -> "ExpressionCatalog":
        """Load expression catalog from a JSON config file."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        expr = raw.get("expressions", {})
        idx_raw = expr.get("index_to_name", {})
        index_to_name = {int(k): v for k, v in idx_raw.items()}
        aliases = expr.get("aliases", {})
        return cls(index_to_name=index_to_name, aliases=aliases)

    def resolve(self, name: str) -> int:
        """Return the expression index for a name or alias, or default (0)."""
        if not isinstance(name, str):
            return DEFAULT_INDEX
        key = name.strip().lower()
        if key in self._name_to_index:
            return self._name_to_index[key]
        if key in self._aliases:
            return self._aliases[key]
        return DEFAULT_INDEX

    def name_of(self, index: int) -> Optional[str]:
        """Return the primary semantic name for an index, or None."""
        return self._index_to_name.get(index)

    @property
    def count(self) -> int:
        return len(self._index_to_name)

    @property
    def all_names(self) -> list[str]:
        return list(self._name_to_index.keys())

    def as_mapping(self) -> dict[str, int]:
        """Full merged mapping (names + aliases → index) for JS bridge."""
        mapping = dict(self._name_to_index)
        mapping.update(self._aliases)
        return mapping
