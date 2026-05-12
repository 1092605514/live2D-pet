"""Tests for pet state machine and actions."""

import pytest
import time
from pet_core.state import (
    PetState,
    PetBehavior,
    tick_pet,
    feed,
    clean,
    pet_action,
    sleep_action,
    clamp,
    compute_health,
    MAX_OFFLINE_HOURS,
    check_level_up,
    exp_to_next_level,
    time_of_day_context,
    absence_greeting,
)


class TestClamp:
    def test_in_range(self):
        assert clamp(50, 0, 100) == 50

    def test_below(self):
        assert clamp(-10, 0, 100) == 0

    def test_above(self):
        assert clamp(150, 0, 100) == 100

    def test_float(self):
        assert clamp(50.5, 0.0, 100.0) == 50.5


class TestComputeHealth:
    def test_default_is_healthy(self):
        state = PetState()
        h = compute_health(state)
        assert h > 80  # Default state should be healthy

    def test_hunger_hurts_health(self):
        state = PetState(hunger=90, cleanliness=80, fatigue=30)
        h = compute_health(state)
        assert h < 90  # High hunger should reduce health

    def test_dirty_hurts_health(self):
        state = PetState(hunger=20, cleanliness=10, fatigue=30)
        h = compute_health(state)
        assert h < 90

    def test_fatigue_hurts_health(self):
        state = PetState(hunger=20, cleanliness=80, fatigue=95)
        h = compute_health(state)
        assert h < 90


class TestTickPet:
    def test_short_elapsed_small_changes(self):
        state = PetState()
        now = state.last_tick_at + 3600  # 1 hour
        new_state = tick_pet(state, now)
        assert new_state.hunger > state.hunger
        assert new_state.cleanliness < state.cleanliness
        assert new_state.fatigue > state.fatigue

    def test_caps_offline_hours(self):
        state = PetState()
        # Simulate 1 week offline
        now = state.last_tick_at + 3600 * 24 * 7
        new_state = tick_pet(state, now)

        # Calculate expected decay with 8-hour cap
        expected_hunger = clamp(state.hunger + MAX_OFFLINE_HOURS * 4.0, 0, 100)
        assert new_state.hunger == pytest.approx(expected_hunger, abs=1)

    def test_does_not_mutate_original(self):
        state = PetState()
        original_hunger = state.hunger
        tick_pet(state, state.last_tick_at + 3600)
        assert state.hunger == original_hunger  # Unchanged

    def test_values_clamped(self):
        state = PetState(hunger=99, cleanliness=1, fatigue=99)
        now = state.last_tick_at + 3600 * 10
        new_state = tick_pet(state, now)
        assert 0 <= new_state.hunger <= 100
        assert 0 <= new_state.cleanliness <= 100
        assert 0 <= new_state.fatigue <= 100

    def test_last_tick_at_updated(self):
        state = PetState()
        now = state.last_tick_at + 3600
        new_state = tick_pet(state, now)
        assert new_state.last_tick_at == now

    def test_timestamp_updated_even_zero_elapsed(self):
        state = PetState()
        now = state.last_tick_at  # zero elapsed
        new_state = tick_pet(state, now)
        assert new_state.last_tick_at == now
        # Values should be unchanged when zero time elapsed
        assert new_state.hunger == state.hunger


class TestFeed:
    def test_reduces_hunger(self):
        state = PetState(hunger=70)
        new_state = feed(state)
        assert new_state.hunger < state.hunger
        assert new_state.hunger == pytest.approx(40, abs=5)

    def test_improves_mood(self):
        state = PetState(mood=50)
        new_state = feed(state)
        assert new_state.mood > state.mood

    def test_increases_affection(self):
        state = PetState(affection=50)
        new_state = feed(state)
        assert new_state.affection > 50

    def test_sets_eat_behavior(self):
        state = PetState()
        new_state = feed(state)
        assert new_state.current_behavior == PetBehavior.EAT

    def test_gives_exp_and_coins(self):
        state = PetState()
        new_state = feed(state)
        assert new_state.exp > 0
        assert new_state.coins >= 1

    def test_does_not_mutate_original(self):
        original = PetState(hunger=70)
        feed(original)
        assert original.hunger == 70


class TestClean:
    def test_restores_cleanliness(self):
        state = PetState(cleanliness=30)
        new_state = clean(state)
        assert new_state.cleanliness == 100

    def test_sets_bath_behavior(self):
        state = PetState()
        new_state = clean(state)
        assert new_state.current_behavior == PetBehavior.BATH


class TestPetAction:
    def test_improves_mood(self):
        state = PetState(mood=40)
        new_state = pet_action(state)
        assert new_state.mood > state.mood

    def test_increases_affection(self):
        state = PetState(affection=50)
        new_state = pet_action(state)
        assert new_state.affection > 50

    def test_sets_petted_behavior(self):
        state = PetState()
        new_state = pet_action(state)
        assert new_state.current_behavior == PetBehavior.PETTED


class TestSleepAction:
    def test_reduces_fatigue(self):
        state = PetState(fatigue=80)
        new_state = sleep_action(state)
        assert new_state.fatigue < state.fatigue
        assert new_state.fatigue == pytest.approx(30, abs=5)

    def test_improves_health(self):
        state = PetState(health=60)
        new_state = sleep_action(state)
        assert new_state.health > 60

    def test_sets_sleep_behavior(self):
        state = PetState()
        new_state = sleep_action(state)
        assert new_state.current_behavior == PetBehavior.SLEEP


class TestPetStateSerialization:
    def test_roundtrip(self):
        original = PetState(hunger=50, cleanliness=60, mood=70,
                           current_behavior=PetBehavior.HAPPY)
        d = original.to_dict()
        restored = PetState.from_dict(d)
        assert restored.hunger == original.hunger
        assert restored.cleanliness == original.cleanliness
        assert restored.mood == original.mood
        assert restored.current_behavior == original.current_behavior

    def test_exp_to_next_level(self):
        state = PetState(level=1)
        assert state.exp_to_next_level == 100
        state2 = PetState(level=5)
        assert state2.exp_to_next_level == 100 + 4 * 50  # 300


class TestExpToNextLevelFunction:
    def test_level_1(self):
        assert exp_to_next_level(1) == 100

    def test_level_5(self):
        assert exp_to_next_level(5) == 100 + 4 * 50

    def test_scales_linearly(self):
        assert exp_to_next_level(2) - exp_to_next_level(1) == 50
        assert exp_to_next_level(3) - exp_to_next_level(2) == 50


class TestCheckLevelUp:
    def test_no_level_up_below_threshold(self):
        state = PetState(level=1, exp=50)
        new_state, did_level = check_level_up(state)
        assert did_level is False
        assert new_state.level == 1
        assert new_state.exp == 50

    def test_level_up_at_threshold(self):
        state = PetState(level=1, exp=100)
        new_state, did_level = check_level_up(state)
        assert did_level is True
        assert new_state.level == 2
        assert new_state.exp == 0  # 100 - 100 = 0

    def test_level_up_preserves_remaining_exp(self):
        state = PetState(level=1, exp=130)
        new_state, did_level = check_level_up(state)
        assert did_level is True
        assert new_state.level == 2
        assert new_state.exp == 30  # 130 - 100 = 30

    def test_level_up_gives_bonus_coins(self):
        state = PetState(level=1, exp=100, coins=10)
        new_state, _ = check_level_up(state)
        assert new_state.coins == 10 + 2 * 5  # level 2 * 5 = 10

    def test_level_up_improves_mood(self):
        state = PetState(level=1, exp=100, mood=50)
        new_state, _ = check_level_up(state)
        assert new_state.mood > 50

    def test_level_up_improves_affection(self):
        state = PetState(level=1, exp=100, affection=50)
        new_state, _ = check_level_up(state)
        assert new_state.affection > 50

    def test_level_up_sets_happy_behavior(self):
        state = PetState(level=1, exp=100)
        new_state, _ = check_level_up(state)
        assert new_state.current_behavior == PetBehavior.HAPPY

    def test_no_level_up_high_level(self):
        state = PetState(level=10, exp=50)
        new_state, did_level = check_level_up(state)
        assert did_level is False
        assert new_state.level == 10


class TestTimeOfDayContext:
    def test_morning(self):
        # 8 AM
        import datetime
        now = datetime.datetime(2026, 5, 5, 8, 0).timestamp()
        ctx = time_of_day_context(now)
        assert ctx["period"] == "morning"
        assert "早上好" in ctx["greeting"]

    def test_afternoon(self):
        import datetime
        now = datetime.datetime(2026, 5, 5, 14, 0).timestamp()
        ctx = time_of_day_context(now)
        assert ctx["period"] == "afternoon"
        assert "下午好" in ctx["greeting"]

    def test_evening(self):
        import datetime
        now = datetime.datetime(2026, 5, 5, 19, 0).timestamp()
        ctx = time_of_day_context(now)
        assert ctx["period"] == "evening"
        assert "晚上好" in ctx["greeting"]

    def test_night(self):
        import datetime
        now = datetime.datetime(2026, 5, 5, 23, 0).timestamp()
        ctx = time_of_day_context(now)
        assert ctx["period"] == "night"
        assert "睡觉" in ctx["greeting"]

    def test_returns_dict_with_expected_keys(self):
        ctx = time_of_day_context()
        assert "period" in ctx
        assert "energy_mod" in ctx
        assert "greeting" in ctx


class TestAbsenceGreeting:
    def test_no_greeting_when_no_last_interaction(self):
        assert absence_greeting(None) is None

    def test_no_greeting_when_recent(self):
        now = time.time()
        # 10 minutes ago
        assert absence_greeting(now - 600, now) is None

    def test_short_absence(self):
        now = time.time()
        # 1 hour ago
        greeting = absence_greeting(now - 3600, now)
        assert greeting is not None
        assert "回来" in greeting

    def test_medium_absence(self):
        now = time.time()
        # 5 hours ago
        greeting = absence_greeting(now - 5 * 3600, now)
        assert greeting is not None
        assert "想你" in greeting or "好久" in greeting

    def test_long_absence(self):
        now = time.time()
        # 12 hours ago
        greeting = absence_greeting(now - 12 * 3600, now)
        assert greeting is not None
        assert "等了" in greeting or "终于" in greeting

    def test_very_long_absence(self):
        now = time.time()
        # 25 hours ago
        greeting = absence_greeting(now - 25 * 3600, now)
        assert greeting is not None
        assert "出现" in greeting or "不要" in greeting

    def test_uses_current_time_when_now_none(self):
        # Just verify it doesn't crash
        result = absence_greeting(time.time() - 3600)
        assert result is not None
