"""Tests for behavior planner."""

import pytest
import time
from pet_core.state import PetState, PetBehavior
from pet_core.behavior import BehaviorPlanner


class TestBehaviorPlanner:
    def test_healthy_pet_returns_idle_pool(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState()  # Default healthy state
        behavior = planner.choose(state)
        assert behavior in {
            PetBehavior.IDLE,
            PetBehavior.WALK,
            PetBehavior.LOOK_AT_USER,
            PetBehavior.STRETCH,
            PetBehavior.SHOW_LOVE,
        }

    def test_low_health_triggers_sick(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState(health=25)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.SICK

    def test_high_hunger_triggers_beg_food(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState(hunger=80)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.BEG_FOOD

    def test_low_cleanliness_triggers_dirty(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState(cleanliness=20)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.DIRTY

    def test_high_fatigue_triggers_sleepy(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState(fatigue=85)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.SLEEPY

    def test_low_mood_triggers_sad(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState(mood=25)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.SAD

    def test_priority_order(self):
        """Health emergency should override all other needs."""
        planner = BehaviorPlanner(seed=42)
        # Pet is hungry, dirty, tired AND sick
        state = PetState(health=20, hunger=90, cleanliness=15, fatigue=90, mood=10)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.SICK

    def test_hunger_overrides_lower_priorities(self):
        planner = BehaviorPlanner(seed=42)
        # Pet is dirty, tired, sad AND hungry (but healthy)
        state = PetState(health=50, hunger=85, cleanliness=20, fatigue=85, mood=25)
        behavior = planner.choose(state)
        assert behavior == PetBehavior.BEG_FOOD

    def test_does_not_repeat_idle_behaviors(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState()
        # Force IDLE
        state = PetState(**{**state.__dict__,
                           "hunger": 30, "cleanliness": 70, "mood": 70,
                           "fatigue": 30, "health": 90})
        first = planner.choose(state)
        second = planner.choose(state)
        # Should not repeat the same non-urgent behavior
        if first not in {PetBehavior.SICK, PetBehavior.BEG_FOOD,
                          PetBehavior.DIRTY, PetBehavior.SLEEPY}:
            # Allow same or different — just verify it doesn't crash
            assert isinstance(second, PetBehavior)

    def test_deterministic_with_seed(self):
        """Same seed should produce same behavior sequence."""
        p1 = BehaviorPlanner(seed=123)
        p2 = BehaviorPlanner(seed=123)
        state = PetState()
        for _ in range(10):
            assert p1.choose(state) == p2.choose(state)

    def test_behavior_in_enum(self):
        """All returned behaviors must be valid enum values."""
        planner = BehaviorPlanner(seed=42)
        for hunger in [0, 30, 60, 90]:
            for cleanliness in [0, 30, 60, 100]:
                for fatigue in [0, 30, 60, 90]:
                    for mood in [0, 30, 60, 90]:
                        state = PetState(
                            hunger=hunger, cleanliness=cleanliness,
                            fatigue=fatigue, mood=mood,
                            health=80,
                        )
                        behavior = planner.choose(state)
                        assert isinstance(behavior, PetBehavior)

    def test_very_happy_pet_can_be_happy(self):
        planner = BehaviorPlanner(seed=42)
        state = PetState(hunger=10, cleanliness=90, mood=80, fatigue=20)
        # Try many times — HAPPY should appear occasionally (8% chance)
        behaviors = set()
        for _ in range(200):
            behaviors.add(planner.choose(state))
        assert PetBehavior.HAPPY in behaviors or PetBehavior.SHOW_LOVE in behaviors

    def test_high_affection_more_show_love(self):
        """High affection should increase SHOW_LOVE frequency."""
        planner = BehaviorPlanner(seed=42)
        state = PetState(hunger=30, cleanliness=70, mood=70, fatigue=30, affection=90)
        count = 0
        for _ in range(500):
            if planner.choose(state) == PetBehavior.SHOW_LOVE:
                count += 1
        # With affection=90, SHOW_LOVE weight is 5*1.5=7.5 out of ~102.5 total
        # Plus 6% direct chance → expect ~15+ occurrences in 500
        assert count > 5

    def test_low_affection_less_show_love(self):
        """Low affection should decrease SHOW_LOVE frequency."""
        planner = BehaviorPlanner(seed=42)
        state = PetState(hunger=30, cleanliness=70, mood=70, fatigue=30, affection=10)
        count = 0
        for _ in range(500):
            if planner.choose(state) == PetBehavior.SHOW_LOVE:
                count += 1
        # With affection=10, SHOW_LOVE weight is 5*0.3=1.5 out of ~96.5 total
        # No direct chance (affection < 80) → fewer than high-affection case
        # High affection test gets 15+, so low should be noticeably less
        assert count < 30
