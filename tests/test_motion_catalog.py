"""Tests for the motion catalog — action name → (group, index) resolution."""

import pytest

from pet_core.motion_catalog import MotionCatalog


class TestMotionCatalog:
    @pytest.fixture
    def cat(self) -> MotionCatalog:
        return MotionCatalog()

    def test_resolve_direct_action(self, cat):
        result = cat.resolve("wave")
        assert result == ("", 0)

    def test_resolve_idle(self, cat):
        result = cat.resolve("idle")
        assert result == ("Idle", 0)

    def test_resolve_case_insensitive(self, cat):
        assert cat.resolve("DANCE") == ("", 1)
        assert cat.resolve("Nod") == ("", 2)

    def test_resolve_alias_english(self, cat):
        assert cat.resolve("hello") == ("", 0)  # alias for wave
        assert cat.resolve("agree") == ("", 2)  # alias for nod
        assert cat.resolve("no") == ("", 3)      # alias for shake_head

    def test_resolve_alias_chinese(self, cat):
        assert cat.resolve("挥手") == ("", 0)
        assert cat.resolve("点头") == ("", 2)
        assert cat.resolve("转圈") == ("", 4)

    def test_resolve_random_actions_return_none(self, cat):
        assert cat.resolve("stretch") is None
        assert cat.resolve("bow") is None
        assert cat.resolve("clap") is None

    def test_resolve_unknown_returns_none(self, cat):
        assert cat.resolve("nonexistent") is None

    def test_resolve_none_returns_none(self, cat):
        assert cat.resolve(None) is None  # type: ignore[arg-type]

    def test_name_of_known(self, cat):
        assert cat.name_of("", 0) == "wave"
        assert cat.name_of("Idle", 0) == "idle"

    def test_name_of_unknown_returns_none(self, cat):
        assert cat.name_of("", 99) is None
        assert cat.name_of("FakeGroup", 0) is None

    def test_count(self, cat):
        assert cat.count == 7

    def test_all_actions(self, cat):
        actions = cat.all_actions
        assert "wave" in actions
        assert "jump" in actions
        assert len(actions) == 7
