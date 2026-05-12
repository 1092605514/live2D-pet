"""
Maps PetBehavior (domain logic) to Live2D motion/expression names.
The ONLY place where Live2D-specific names live.

If a model doesn't support a motion, it falls back to Idle.
"""

import time
from typing import Optional

from .state import PetBehavior

# ── Default motion mapping (mao_pro model) ──
# mao_pro only ships two motion groups: "Idle" (mtn_01) and "" (mtn_02-04 +
# special_01-03). The previous "Happy" group did not exist in the model file —
# routing to it silently fell through to no-op. Map upbeat behaviors to the
# unnamed group so startRandomMotion("") picks one of the six available motions.
MOTION_GROUP_IDLE = "Idle"
MOTION_GROUP_ACTIVE = ""

DEFAULT_BEHAVIOR_TO_MOTION: dict[PetBehavior, str] = {
    PetBehavior.IDLE: MOTION_GROUP_IDLE,
    PetBehavior.WALK: MOTION_GROUP_IDLE,
    PetBehavior.LOOK_AT_USER: MOTION_GROUP_IDLE,
    PetBehavior.STRETCH: MOTION_GROUP_ACTIVE,
    PetBehavior.SICK: MOTION_GROUP_IDLE,
    PetBehavior.BEG_FOOD: MOTION_GROUP_IDLE,
    PetBehavior.DIRTY: MOTION_GROUP_IDLE,
    PetBehavior.SLEEPY: MOTION_GROUP_IDLE,
    PetBehavior.SAD: MOTION_GROUP_IDLE,
    PetBehavior.HAPPY: MOTION_GROUP_ACTIVE,
    PetBehavior.EAT: MOTION_GROUP_ACTIVE,
    PetBehavior.BATH: MOTION_GROUP_ACTIVE,
    PetBehavior.SLEEP: MOTION_GROUP_IDLE,
    PetBehavior.PETTED: MOTION_GROUP_ACTIVE,
    PetBehavior.SHOW_LOVE: MOTION_GROUP_ACTIVE,
}

# ── Expression (emotion) mapping ──
# These map to Live2D expression parameters.
DEFAULT_BEHAVIOR_TO_EXPRESSION: dict[PetBehavior, str] = {
    PetBehavior.SICK: "sad",
    PetBehavior.BEG_FOOD: "sad",
    PetBehavior.DIRTY: "sad",
    PetBehavior.SLEEPY: "sleepy",
    PetBehavior.SAD: "sad",
    PetBehavior.HAPPY: "happy",
    PetBehavior.SHOW_LOVE: "happy",
    PetBehavior.PETTED: "happy",
    PetBehavior.EAT: "happy",
    PetBehavior.BATH: "happy",
}

# ── Cooldown: don't replay the same motion within N seconds ──
DEFAULT_MOTION_COOLDOWN = 3.0


class MotionAdapter:
    """Translates pet behaviors into Live2D commands.

    Usage:
        adapter = MotionAdapter()
        motion = adapter.get_motion(behavior)
        expression = adapter.get_expression(behavior)
        # Send motion/expression to Live2D model via JS bridge
    """

    def __init__(
        self,
        motion_map: Optional[dict] = None,
        expression_map: Optional[dict] = None,
        cooldown: float = DEFAULT_MOTION_COOLDOWN,
    ):
        self._motion_map = motion_map or dict(DEFAULT_BEHAVIOR_TO_MOTION)
        self._expression_map = expression_map or dict(DEFAULT_BEHAVIOR_TO_EXPRESSION)
        self._cooldown = cooldown
        self._last_motion: Optional[str] = None
        self._last_motion_time: float = 0.0

    def get_motion(self, behavior: PetBehavior) -> str:
        """Get the Live2D motion name for a behavior."""
        return self._motion_map.get(behavior, "Idle")

    def get_expression(self, behavior: PetBehavior) -> Optional[str]:
        """Get the Live2D expression name for a behavior, or None."""
        return self._expression_map.get(behavior)

    def should_play_motion(self, motion: str, now: Optional[float] = None) -> bool:
        """Check if enough time has passed since the last motion."""
        if now is None:
            now = time.time()
        if motion != self._last_motion:
            return True
        return (now - self._last_motion_time) >= self._cooldown

    def record_motion(self, motion: str, now: Optional[float] = None):
        """Record that a motion was played."""
        if now is None:
            now = time.time()
        self._last_motion = motion
        self._last_motion_time = now

    def get_message(self, behavior: PetBehavior) -> str:
        """Get the display message for a behavior (for speech bubble)."""
        from .state import BEHAVIOR_MESSAGE
        return BEHAVIOR_MESSAGE.get(behavior, "")
