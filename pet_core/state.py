"""
Pure domain logic for virtual pet state. No framework dependencies.
All functions return NEW state objects — never mutate in place.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Optional
import time


class PetBehavior(Enum):
    """What the pet is currently doing — NOT a Live2D motion name."""
    IDLE = auto()
    WALK = auto()
    LOOK_AT_USER = auto()
    STRETCH = auto()
    SICK = auto()
    BEG_FOOD = auto()
    DIRTY = auto()
    SLEEPY = auto()
    SAD = auto()
    HAPPY = auto()
    EAT = auto()
    BATH = auto()
    SLEEP = auto()
    PETTED = auto()
    SHOW_LOVE = auto()


# Behavior → display message (for speech bubble)
BEHAVIOR_MESSAGE: dict[PetBehavior, str] = {
    PetBehavior.BEG_FOOD: "好饿呀... 有吃的吗？🥺",
    PetBehavior.DIRTY: "身上好脏，想洗澡了 🛁",
    PetBehavior.SICK: "有点不舒服... 😷",
    PetBehavior.SLEEPY: "好困呀，想睡觉了 😴",
    PetBehavior.SAD: "心情不太好呢 😢",
    PetBehavior.HAPPY: "今天真开心！😸",
    PetBehavior.EAT: "好吃好吃！谢谢款待 🍖",
    PetBehavior.BATH: "洗干净了好舒服~ 🛁",
    PetBehavior.SLEEP: "zzZ... 睡着了 💤",
    PetBehavior.PETTED: "嘿嘿，好舒服~ 🥰",
    PetBehavior.SHOW_LOVE: "最喜欢你了！💕",
}

# Max offline time to simulate (hours) — prevents death-after-vacation
MAX_OFFLINE_HOURS = 8


@dataclass
class PetState:
    """Complete state of a virtual pet. All values 0-100 unless noted."""

    # ── status bars ──
    hunger: float = 20        # 0=full, 100=starving
    cleanliness: float = 80   # 0=filthy, 100=clean
    mood: float = 70          # 0=depressed, 100=ecstatic
    health: float = 90        # 0=dead, 100=perfect
    fatigue: float = 30       # 0=energetic, 100=exhausted
    affection: float = 50     # 0=dislikes you, 100=loves you

    # ── progression ──
    level: int = 1
    exp: float = 0
    coins: int = 0

    # ── current behavior ──
    current_behavior: PetBehavior = PetBehavior.IDLE

    # ── timestamps ──
    last_tick_at: float = field(default_factory=time.time)
    last_fed_at: Optional[float] = None
    last_cleaned_at: Optional[float] = None
    last_slept_at: Optional[float] = None
    last_petted_at: Optional[float] = None
    last_interaction_at: Optional[float] = None

    # ── schema version for persistence migration ──
    version: int = 2

    def to_dict(self) -> dict:
        d = asdict(self)
        d["current_behavior"] = self.current_behavior.name
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PetState":
        d = dict(d)  # shallow copy
        behavior_name = d.pop("current_behavior", "IDLE")
        d["current_behavior"] = PetBehavior[behavior_name]
        return cls(**d)

    @property
    def exp_to_next_level(self) -> float:
        return 100 + (self.level - 1) * 50


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def compute_health(state: PetState) -> float:
    """Health is derived from other stats — NOT set directly."""
    penalty = 0.0
    if state.hunger > 70:
        penalty += (state.hunger - 70) * 0.5
    if state.cleanliness < 30:
        penalty += (30 - state.cleanliness) * 0.4
    if state.fatigue > 80:
        penalty += (state.fatigue - 80) * 0.3
    return clamp(state.health - penalty * 0.1, 0, 100)


# ═══════════════════════════════════════════════════════════════
# State tick — time-based decay
# ═══════════════════════════════════════════════════════════════

def tick_pet(state: PetState, now: Optional[float] = None) -> PetState:
    """Advance pet state based on elapsed time. Pure function."""
    if now is None:
        now = time.time()

    elapsed_hours = (now - state.last_tick_at) / 3600.0
    # Cap offline decay to avoid punishment
    effective = min(elapsed_hours, MAX_OFFLINE_HOURS)

    hunger = clamp(state.hunger + effective * 4.0, 0, 100)
    cleanliness = clamp(state.cleanliness - effective * 3.0, 0, 100)
    mood = clamp(state.mood - effective * 2.0, 0, 100)
    fatigue = clamp(state.fatigue + effective * 2.0, 0, 100)

    new_state = PetState(
        hunger=hunger,
        cleanliness=cleanliness,
        mood=mood,
        health=state.health,  # computed separately
        fatigue=fatigue,
        affection=state.affection,
        level=state.level,
        exp=state.exp,
        coins=state.coins,
        current_behavior=state.current_behavior,
        last_tick_at=now,
        last_fed_at=state.last_fed_at,
        last_cleaned_at=state.last_cleaned_at,
        last_slept_at=state.last_slept_at,
        last_petted_at=state.last_petted_at,
    )
    return PetState(
        **{**new_state.__dict__,
           "health": compute_health(new_state)}
    )


# ═══════════════════════════════════════════════════════════════
# Actions — user-initiated interactions. Pure functions.
# ═══════════════════════════════════════════════════════════════

def feed(state: PetState, now: Optional[float] = None) -> PetState:
    """Feed the pet — reduces hunger, improves mood and affection."""
    if now is None:
        now = time.time()

    # Apply tick first to get up-to-date state
    s = tick_pet(state, now)

    return PetState(
        hunger=clamp(s.hunger - 30, 0, 100),
        cleanliness=s.cleanliness,
        mood=clamp(s.mood + 10, 0, 100),
        health=s.health,
        fatigue=s.fatigue,
        affection=clamp(s.affection + 3, 0, 100),
        level=s.level,
        exp=clamp(s.exp + 5, 0, float("inf")),
        coins=s.coins + 1,
        current_behavior=PetBehavior.EAT,
        last_tick_at=now,
        last_fed_at=now,
        last_cleaned_at=s.last_cleaned_at,
        last_slept_at=s.last_slept_at,
        last_petted_at=s.last_petted_at,
    )


def clean(state: PetState, now: Optional[float] = None) -> PetState:
    """Bathe the pet — restores cleanliness."""
    if now is None:
        now = time.time()

    s = tick_pet(state, now)

    return PetState(
        hunger=s.hunger,
        cleanliness=100,
        mood=clamp(s.mood + 8, 0, 100),
        health=s.health,
        fatigue=s.fatigue,
        affection=clamp(s.affection + 2, 0, 100),
        level=s.level,
        exp=clamp(s.exp + 5, 0, float("inf")),
        coins=s.coins + 1,
        current_behavior=PetBehavior.BATH,
        last_tick_at=now,
        last_fed_at=s.last_fed_at,
        last_cleaned_at=now,
        last_slept_at=s.last_slept_at,
        last_petted_at=s.last_petted_at,
    )


def pet_action(state: PetState, now: Optional[float] = None) -> PetState:
    """Pet the pet — improves mood and affection."""
    if now is None:
        now = time.time()

    s = tick_pet(state, now)

    return PetState(
        hunger=s.hunger,
        cleanliness=s.cleanliness,
        mood=clamp(s.mood + 15, 0, 100),
        health=s.health,
        fatigue=s.fatigue,
        affection=clamp(s.affection + 5, 0, 100),
        level=s.level,
        exp=clamp(s.exp + 3, 0, float("inf")),
        coins=s.coins,
        current_behavior=PetBehavior.PETTED,
        last_tick_at=now,
        last_fed_at=s.last_fed_at,
        last_cleaned_at=s.last_cleaned_at,
        last_slept_at=s.last_slept_at,
        last_petted_at=now,
    )


def sleep_action(state: PetState, now: Optional[float] = None) -> PetState:
    """Put pet to sleep — reduces fatigue, improves health."""
    if now is None:
        now = time.time()

    s = tick_pet(state, now)

    return PetState(
        hunger=clamp(s.hunger + 5, 0, 100),  # sleeping burns some energy
        cleanliness=s.cleanliness,
        mood=clamp(s.mood + 5, 0, 100),
        health=clamp(s.health + 10, 0, 100),
        fatigue=clamp(s.fatigue - 50, 0, 100),
        affection=clamp(s.affection + 1, 0, 100),
        level=s.level,
        exp=clamp(s.exp + 2, 0, float("inf")),
        coins=s.coins,
        current_behavior=PetBehavior.SLEEP,
        last_tick_at=now,
        last_fed_at=s.last_fed_at,
        last_cleaned_at=s.last_cleaned_at,
        last_slept_at=now,
        last_petted_at=s.last_petted_at,
    )


# ── Level-up ────────────────────────────────────────────────

def exp_to_next_level(level: int) -> float:
    """EXP required to reach the next level. Scales with level."""
    return 100 + (level - 1) * 50


def check_level_up(state: PetState) -> tuple[PetState, bool]:
    """Check if exp exceeds threshold and level up. Returns (new_state, did_level_up)."""
    required = exp_to_next_level(state.level)
    if state.exp < required:
        return state, False
    new_level = state.level + 1
    remaining = state.exp - required
    bonus_coins = new_level * 5
    return PetState(
        hunger=state.hunger,
        cleanliness=state.cleanliness,
        mood=clamp(state.mood + 20, 0, 100),
        health=state.health,
        fatigue=state.fatigue,
        affection=clamp(state.affection + 10, 0, 100),
        level=new_level,
        exp=remaining,
        coins=state.coins + bonus_coins,
        current_behavior=PetBehavior.HAPPY,
        last_tick_at=state.last_tick_at,
        last_fed_at=state.last_fed_at,
        last_cleaned_at=state.last_cleaned_at,
        last_slept_at=state.last_slept_at,
        last_petted_at=state.last_petted_at,
    ), True


# ── Time-of-day awareness ───────────────────────────────────

def time_of_day_context(now: Optional[float] = None) -> dict:
    """Return time-of-day context for behavior adjustments."""
    from datetime import datetime
    if now is None:
        now = time.time()
    hour = datetime.fromtimestamp(now).hour
    if 6 <= hour < 12:
        return {"period": "morning", "energy_mod": 1.1, "greeting": "早上好呀~"}
    elif 12 <= hour < 18:
        return {"period": "afternoon", "energy_mod": 1.0, "greeting": "下午好~"}
    elif 18 <= hour < 22:
        return {"period": "evening", "energy_mod": 0.9, "greeting": "晚上好~"}
    else:
        return {"period": "night", "energy_mod": 0.7, "greeting": "该睡觉了...~"}


# ── Absence greeting ────────────────────────────────────────

def absence_greeting(last_interaction: Optional[float], now: Optional[float] = None) -> Optional[str]:
    """Return a greeting based on how long the user was away."""
    if last_interaction is None:
        return None
    if now is None:
        now = time.time()
    hours = (now - last_interaction) / 3600
    if hours < 0.5:
        return None
    elif hours < 2:
        return "你回来啦~"
    elif hours < 8:
        return "好久不见！想你了~"
    elif hours < 24:
        return "终于回来了！我等了好久呢~"
    else:
        return "你终于出现了！我以为你不要我了..."
