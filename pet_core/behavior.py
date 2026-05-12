"""
Behavior planner — priority-based scheduler for pet actions.

Priority hierarchy:
  1. User-initiated action (already set in state) — don't override
  2. Emergency: health < 30 → SICK
  3. High need: hunger > 75 → BEG_FOOD
  4. High need: cleanliness < 25 → DIRTY
  5. High need: fatigue > 80 → SLEEPY
  6. Emotional: mood < 30 → SAD
  7. High affection (>80): 6% chance → SHOW_LOVE
  8. Night + tired: 30% chance → SLEEPY
  9. Idle pool: weighted random (affection-adjusted)

Pure function — no side effects, no random in tests (seedable).
"""

import random
from typing import Optional
from .state import PetState, PetBehavior, time_of_day_context

# ── Idle behavior weights ──
IDLE_WEIGHTS: list[tuple[PetBehavior, float]] = [
    (PetBehavior.IDLE, 50),
    (PetBehavior.WALK, 20),
    (PetBehavior.LOOK_AT_USER, 15),
    (PetBehavior.STRETCH, 10),
    (PetBehavior.SHOW_LOVE, 5),
]

# ── Behaviors that should not be interrupted ──
UNINTERRUPTIBLE: set[PetBehavior] = {
    PetBehavior.EAT,
    PetBehavior.BATH,
    PetBehavior.SLEEP,
    PetBehavior.PETTED,
    PetBehavior.HAPPY,
}

# ── Minimum duration (seconds) for a behavior before re-planning ──
BEHAVIOR_MIN_DURATION: dict[PetBehavior, float] = {
    PetBehavior.EAT: 5.0,
    PetBehavior.BATH: 5.0,
    PetBehavior.SLEEP: 300.0,      # 5 min sleep minimum
    PetBehavior.PETTED: 3.0,
    PetBehavior.HAPPY: 4.0,
    PetBehavior.SICK: 8.0,
    PetBehavior.BEG_FOOD: 6.0,
    PetBehavior.DIRTY: 5.0,
    PetBehavior.SLEEPY: 4.0,
    PetBehavior.SAD: 4.0,
    # Idle behaviors can re-plan quickly
    PetBehavior.IDLE: 3.0,
    PetBehavior.WALK: 4.0,
    PetBehavior.LOOK_AT_USER: 3.0,
    PetBehavior.STRETCH: 4.0,
    PetBehavior.SHOW_LOVE: 4.0,
}


class BehaviorPlanner:
    """Selects what the pet should do based on its current state."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._behavior_start: float = 0.0
        self._last_behavior: Optional[PetBehavior] = None

    def choose(self, state: PetState, now: Optional[float] = None) -> PetBehavior:
        """
        Choose the best behavior for the current state.

        Returns the new PetBehavior — does NOT modify state.
        The caller decides whether to apply it.
        """
        import time
        if now is None:
            now = time.time()

        current = state.current_behavior

        # ── Guard: don't interrupt uninterruptible behaviors ──
        if current in UNINTERRUPTIBLE:
            elapsed = now - self._behavior_start
            min_dur = BEHAVIOR_MIN_DURATION.get(current, 3.0)
            if elapsed < min_dur:
                return current  # let it finish

        # ── Priority 1: health emergency ──
        if state.health < 30:
            return self._pick(PetBehavior.SICK, now)

        # ── Priority 2: hunger ──
        if state.hunger > 75:
            return self._pick(PetBehavior.BEG_FOOD, now)

        # ── Priority 3: cleanliness ──
        if state.cleanliness < 25:
            return self._pick(PetBehavior.DIRTY, now)

        # ── Priority 4: fatigue ──
        if state.fatigue > 80:
            return self._pick(PetBehavior.SLEEPY, now)

        # ── Priority 5: mood ──
        if state.mood < 30:
            return self._pick(PetBehavior.SAD, now)

        # Very high stats → happy
        if (state.hunger < 20 and state.cleanliness > 80 and
                state.mood > 70 and state.fatigue < 30):
            if self._rng.random() < 0.08:  # 8% chance
                return self._pick(PetBehavior.HAPPY, now)

        # ── Priority 6: high affection → SHOW_LOVE ──
        if state.affection > 80 and self._rng.random() < 0.06:
            return self._pick(PetBehavior.SHOW_LOVE, now)

        # ── Priority 7: night + tired → SLEEPY ──
        ctx = time_of_day_context(now)
        if ctx["period"] == "night" and state.fatigue > 50:
            if self._rng.random() < 0.3:
                return self._pick(PetBehavior.SLEEPY, now)

        # ── Priority 8: idle pool (affection-adjusted) ──
        return self._pick(self._weighted_idle(state), now)

    def _weighted_idle(self, state: Optional[PetState] = None) -> PetBehavior:
        """Weighted random selection from idle behaviors, adjusted by affection."""
        weights = list(IDLE_WEIGHTS)
        if state is not None:
            aff = state.affection
            if aff > 70:
                weights = [(b, w * 1.5 if b == PetBehavior.SHOW_LOVE else w) for b, w in weights]
            elif aff < 30:
                weights = [(b, w * 0.3 if b == PetBehavior.SHOW_LOVE else w) for b, w in weights]
        total = sum(w for _, w in weights)
        r = self._rng.uniform(0, total)
        cumulative = 0.0
        for behavior, weight in weights:
            cumulative += weight
            if r <= cumulative:
                return behavior
        return PetBehavior.IDLE

    def _pick(self, behavior: PetBehavior, now: Optional[float] = None) -> PetBehavior:
        """Record the chosen behavior and avoid spam."""
        if now is None:
            import time
            now = time.time()
        # Don't repeat the same behavior back-to-back unless it's urgent
        urgent = {PetBehavior.SICK, PetBehavior.BEG_FOOD, PetBehavior.DIRTY,
                  PetBehavior.SLEEPY}
        if behavior == self._last_behavior and behavior not in urgent:
            return self._weighted_idle()
        self._last_behavior = behavior
        self._behavior_start = now
        return behavior

    def reset(self):
        """Clear internal state (useful when pet wakes up or resets)."""
        self._last_behavior = None
        self._behavior_start = 0.0
