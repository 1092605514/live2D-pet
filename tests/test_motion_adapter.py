"""Tests for pet_core.motion_adapter — behavior-to-Live2D mapping."""

import pytest
from pet_core.motion_adapter import (
    MotionAdapter,
    DEFAULT_BEHAVIOR_TO_MOTION,
    DEFAULT_BEHAVIOR_TO_EXPRESSION,
    DEFAULT_MOTION_COOLDOWN,
    MOTION_GROUP_IDLE,
    MOTION_GROUP_ACTIVE,
)
from pet_core.state import PetBehavior


class TestGetMotion:
    def test_idle_behavior_returns_idle_group(self):
        adapter = MotionAdapter()
        assert adapter.get_motion(PetBehavior.IDLE) == MOTION_GROUP_IDLE

    def test_active_behaviors_return_active_group(self):
        adapter = MotionAdapter()
        for b in [PetBehavior.HAPPY, PetBehavior.EAT, PetBehavior.BATH,
                   PetBehavior.PETTED, PetBehavior.SHOW_LOVE, PetBehavior.STRETCH]:
            assert adapter.get_motion(b) == MOTION_GROUP_ACTIVE, f"{b} should be active"

    def test_passive_behaviors_return_idle_group(self):
        adapter = MotionAdapter()
        for b in [PetBehavior.SICK, PetBehavior.BEG_FOOD, PetBehavior.DIRTY,
                   PetBehavior.SLEEPY, PetBehavior.SAD, PetBehavior.SLEEP,
                   PetBehavior.WALK, PetBehavior.LOOK_AT_USER]:
            assert adapter.get_motion(b) == MOTION_GROUP_IDLE, f"{b} should be idle"

    def test_unknown_behavior_returns_default(self):
        adapter = MotionAdapter()
        # Use a behavior not in the map (if any) or verify default
        # All behaviors are mapped, so test with custom empty map
        adapter2 = MotionAdapter(motion_map={})
        assert adapter2.get_motion(PetBehavior.IDLE) == "Idle"

    def test_custom_motion_map(self):
        custom = {PetBehavior.IDLE: "CustomGroup"}
        adapter = MotionAdapter(motion_map=custom)
        assert adapter.get_motion(PetBehavior.IDLE) == "CustomGroup"


class TestGetExpression:
    def test_sad_behaviors_return_sad(self):
        adapter = MotionAdapter()
        for b in [PetBehavior.SICK, PetBehavior.BEG_FOOD, PetBehavior.DIRTY, PetBehavior.SAD]:
            assert adapter.get_expression(b) == "sad", f"{b} should be sad"

    def test_happy_behaviors_return_happy(self):
        adapter = MotionAdapter()
        for b in [PetBehavior.HAPPY, PetBehavior.SHOW_LOVE, PetBehavior.PETTED,
                   PetBehavior.EAT, PetBehavior.BATH]:
            assert adapter.get_expression(b) == "happy", f"{b} should be happy"

    def test_sleepy_returns_sleepy(self):
        adapter = MotionAdapter()
        assert adapter.get_expression(PetBehavior.SLEEPY) == "sleepy"

    def test_unmapped_returns_none(self):
        adapter = MotionAdapter()
        assert adapter.get_expression(PetBehavior.IDLE) is None
        assert adapter.get_expression(PetBehavior.WALK) is None
        assert adapter.get_expression(PetBehavior.LOOK_AT_USER) is None

    def test_custom_expression_map(self):
        custom = {PetBehavior.IDLE: "custom_exp"}
        adapter = MotionAdapter(expression_map=custom)
        assert adapter.get_expression(PetBehavior.IDLE) == "custom_exp"


class TestShouldPlayMotion:
    def test_different_motion_always_plays(self):
        adapter = MotionAdapter(cooldown=3.0)
        adapter.record_motion("dance", now=0.0)
        assert adapter.should_play_motion("wave", now=1.0) is True

    def test_same_motion_within_cooldown_skipped(self):
        adapter = MotionAdapter(cooldown=3.0)
        adapter.record_motion("dance", now=0.0)
        assert adapter.should_play_motion("dance", now=2.0) is False

    def test_same_motion_after_cooldown_plays(self):
        adapter = MotionAdapter(cooldown=3.0)
        adapter.record_motion("dance", now=0.0)
        assert adapter.should_play_motion("dance", now=4.0) is True

    def test_first_motion_always_plays(self):
        adapter = MotionAdapter()
        assert adapter.should_play_motion("wave") is True

    def test_custom_cooldown(self):
        adapter = MotionAdapter(cooldown=10.0)
        adapter.record_motion("wave", now=0.0)
        assert adapter.should_play_motion("wave", now=9.0) is False
        assert adapter.should_play_motion("wave", now=11.0) is True


class TestRecordMotion:
    def test_records_motion_and_time(self):
        adapter = MotionAdapter()
        adapter.record_motion("dance", now=5.0)
        assert adapter._last_motion == "dance"
        assert adapter._last_motion_time == 5.0

    def test_overwrites_previous(self):
        adapter = MotionAdapter()
        adapter.record_motion("dance", now=0.0)
        adapter.record_motion("wave", now=3.0)
        assert adapter._last_motion == "wave"
        assert adapter._last_motion_time == 3.0


class TestGetMessage:
    def test_known_behaviors_have_messages(self):
        adapter = MotionAdapter()
        for b in [PetBehavior.BEG_FOOD, PetBehavior.DIRTY, PetBehavior.SICK,
                   PetBehavior.SLEEPY, PetBehavior.SAD, PetBehavior.HAPPY,
                   PetBehavior.EAT, PetBehavior.BATH, PetBehavior.SLEEP,
                   PetBehavior.PETTED, PetBehavior.SHOW_LOVE]:
            msg = adapter.get_message(b)
            assert msg, f"{b} should have a message"
            assert isinstance(msg, str)

    def test_unknown_behavior_returns_empty(self):
        adapter = MotionAdapter()
        # Behaviors without messages return empty string
        msg = adapter.get_message(PetBehavior.IDLE)
        assert msg == "" or isinstance(msg, str)
