"""
Maps semantic action names to Live2D motion (group, index) pairs.

mao_pro has 7 motions across 2 groups:
  - "Idle" group: mtn_01 (index 0) — looping idle
  - "" (unnamed) group: mtn_02-04 + special_01-03 (indices 0-5) — one-shot actions

Configuration can be loaded from config/pet_actions.json:
    cat = MotionCatalog.from_config("config/pet_actions.json")
"""

import json
from pathlib import Path
from typing import Optional, Union


# ── Defaults (embedded — overwritten when loaded from config) ──
DEFAULT_MOTION_GROUPS: dict[str, list[str]] = {
    "Idle": ["idle"],
    "": ["wave", "dance", "nod", "shake_head", "spin", "jump"],
}

DEFAULT_ALIASES: dict[str, str] = {
    "still": "idle", "stand": "idle",
    "greet": "wave", "hello": "wave", "bye": "wave", "goodbye": "wave",
    "boogie": "dance", "groove": "dance",
    "agree": "nod", "yes": "nod",
    "disagree": "shake_head", "no": "shake_head", "deny": "shake_head",
    "twirl": "spin",
    "hop": "jump", "leap": "jump",
    "yawn": "stretch", "stretch": "stretch",
    "bow": "bow", "clap": "clap",
    "挥手": "wave", "打招呼": "wave",
    "跳舞": "dance",
    "点头": "nod", "同意": "nod",
    "摇头": "shake_head", "不同意": "shake_head",
    "转圈": "spin",
    "跳": "jump", "跳跃": "jump",
    "伸懒腰": "stretch",
    "鞠躬": "bow",
    "拍手": "clap",
}

DEFAULT_RANDOM_ACTIONS: frozenset[str] = {"stretch", "bow", "clap"}


def _build_index_to_action(
    motion_groups: dict[str, list[str]],
) -> dict[tuple[str, int], str]:
    result: dict[tuple[str, int], str] = {}
    for group, actions in motion_groups.items():
        for idx, action in enumerate(actions):
            result[(group, idx)] = action
    return result


def _build_action_to_motion(
    index_to_action: dict[tuple[str, int], str],
) -> dict[str, tuple[str, int]]:
    return {action: key for key, action in index_to_action.items()}


class MotionCatalog:
    """Resolves action names to Live2D (group, index) motion pairs.

    Args:
        index_to_action: Override for (group, index) → action name mapping.
        aliases: Override for alias → canonical action name mapping.
        random_actions: Action names that fall back to random unnamed-group motion.
    """

    def __init__(
        self,
        index_to_action: Optional[dict[tuple[str, int], str]] = None,
        aliases: Optional[dict[str, str]] = None,
        random_actions: Optional[frozenset[str]] = None,
    ):
        self._index_to_action = (
            dict(index_to_action) if index_to_action
            else _build_index_to_action(DEFAULT_MOTION_GROUPS)
        )
        self._action_to_motion = _build_action_to_motion(self._index_to_action)
        self._aliases = dict(aliases) if aliases else dict(DEFAULT_ALIASES)
        self._random = frozenset(random_actions) if random_actions is not None else DEFAULT_RANDOM_ACTIONS

    @classmethod
    def from_config(cls, path: Union[str, Path]) -> "MotionCatalog":
        """Load motion catalog from a JSON config file."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        mot = raw.get("motions", {})
        motion_groups = mot.get("motion_groups", {})
        index_to_action = _build_index_to_action(motion_groups)
        aliases = mot.get("aliases", {})
        random_set = frozenset(mot.get("random_actions", []))
        return cls(
            index_to_action=index_to_action,
            aliases=aliases,
            random_actions=random_set,
        )

    def resolve(self, name: str) -> Optional[tuple[str, int]]:
        """Return (group, index) for an action name/alias, or None (random)."""
        if not isinstance(name, str):
            return None
        key = name.strip().lower()
        if key in self._action_to_motion:
            return self._action_to_motion[key]
        canonical = self._aliases.get(key)
        if canonical and canonical in self._action_to_motion:
            return self._action_to_motion[canonical]
        if key in self._random or canonical in self._random:
            return None  # None means "pick a random unnamed motion"
        return None

    def name_of(self, group: str, index: int) -> Optional[str]:
        """Return the semantic name for a (group, index), or None."""
        return self._index_to_action.get((group, index))

    @property
    def count(self) -> int:
        return len(self._index_to_action)

    @property
    def all_actions(self) -> list[str]:
        return list(self._action_to_motion.keys())

    @property
    def all_random_actions(self) -> list[str]:
        return sorted(self._random)
