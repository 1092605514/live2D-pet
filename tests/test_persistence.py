"""Tests for pet_core.persistence — JSON save/load with corruption recovery."""

import json
import pytest
from pathlib import Path
from pet_core.persistence import PetPersistence, DEFAULT_SAVE_DIR, DEFAULT_SAVE_FILE
from pet_core.state import PetState, PetBehavior


@pytest.fixture
def tmp_save(tmp_path):
    """Provide a PetPersistence instance using a temp directory."""
    return PetPersistence(save_dir=tmp_path)


@pytest.fixture
def sample_state():
    """A non-default PetState for testing roundtrips."""
    return PetState(
        hunger=42, cleanliness=65, mood=88, health=95, fatigue=20,
        affection=70, level=3, exp=120, coins=50,
        current_behavior=PetBehavior.HAPPY,
    )


class TestSaveLoad:
    def test_roundtrip_preserves_all_fields(self, tmp_save, sample_state):
        assert tmp_save.save(sample_state) is True
        loaded = tmp_save.load()
        assert loaded.hunger == sample_state.hunger
        assert loaded.cleanliness == sample_state.cleanliness
        assert loaded.mood == sample_state.mood
        assert loaded.health == sample_state.health
        assert loaded.fatigue == sample_state.fatigue
        assert loaded.affection == sample_state.affection
        assert loaded.level == sample_state.level
        assert loaded.exp == sample_state.exp
        assert loaded.coins == sample_state.coins
        assert loaded.current_behavior == PetBehavior.HAPPY

    def test_roundtrip_preserves_behavior(self, tmp_save):
        state = PetState(current_behavior=PetBehavior.EAT)
        tmp_save.save(state)
        loaded = tmp_save.load()
        assert loaded.current_behavior == PetBehavior.EAT

    def test_save_creates_file(self, tmp_save, sample_state):
        assert not tmp_save.save_path.exists()
        tmp_save.save(sample_state)
        assert tmp_save.save_path.exists()

    def test_save_returns_true_on_success(self, tmp_save, sample_state):
        assert tmp_save.save(sample_state) is True

    def test_load_returns_default_when_no_file(self, tmp_save):
        loaded = tmp_save.load()
        default = PetState()
        assert loaded.hunger == default.hunger
        assert loaded.cleanliness == default.cleanliness
        assert loaded.mood == default.mood
        assert loaded.level == 1

    def test_save_uses_atomic_write(self, tmp_save, sample_state):
        tmp_save.save(sample_state)
        # The .tmp file should not exist after atomic write
        tmp_file = tmp_save.save_path.with_suffix(".tmp")
        assert not tmp_file.exists()
        # The actual file should exist
        assert tmp_save.save_path.exists()


class TestCorruption:
    def test_corrupt_json_returns_default(self, tmp_save):
        tmp_save.save_path.write_text("not valid json {{{", encoding="utf-8")
        loaded = tmp_save.load()
        default = PetState()
        assert loaded.hunger == default.hunger
        assert loaded.level == 1

    def test_corrupt_file_is_backed_up(self, tmp_save):
        tmp_save.save_path.write_text("corrupt", encoding="utf-8")
        tmp_save.load()
        backup = tmp_save.save_path.with_suffix(".corrupt.json")
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == "corrupt"

    def test_empty_file_returns_default(self, tmp_save):
        tmp_save.save_path.write_text("", encoding="utf-8")
        loaded = tmp_save.load()
        assert loaded.level == 1

    def test_missing_keys_returns_default(self, tmp_save):
        tmp_save.save_path.write_text('{"hunger": 50}', encoding="utf-8")
        # Missing required fields should either crash or return default
        # The code catches TypeError/KeyError, so it should return default
        loaded = tmp_save.load()
        assert isinstance(loaded, PetState)


class TestSchemaMigration:
    def test_version_0_migrates_to_v1(self, tmp_save):
        data = {
            "hunger": 30, "cleanliness": 70, "mood": 60, "health": 80,
            "fatigue": 40, "affection": 50, "level": 2, "exp": 80, "coins": 20,
            "current_behavior": "IDLE", "version": 0,
        }
        tmp_save.save_path.write_text(json.dumps(data), encoding="utf-8")
        loaded = tmp_save.load()
        assert loaded.level == 2
        assert loaded.hunger == 30

    def test_version_1_migrates_to_v2(self, tmp_save):
        data = {
            "hunger": 30, "cleanliness": 70, "mood": 60, "health": 80,
            "fatigue": 40, "affection": 50, "level": 2, "exp": 80, "coins": 20,
            "current_behavior": "IDLE", "version": 1,
        }
        tmp_save.save_path.write_text(json.dumps(data), encoding="utf-8")
        loaded = tmp_save.load()
        assert loaded.level == 2
        assert loaded.last_interaction_at is None

    def test_version_0_migrates_to_v2(self, tmp_save):
        """Version 0 should migrate all the way to v2."""
        data = {
            "hunger": 30, "cleanliness": 70, "mood": 60, "health": 80,
            "fatigue": 40, "affection": 50, "level": 2, "exp": 80, "coins": 20,
            "current_behavior": "IDLE", "version": 0,
        }
        tmp_save.save_path.write_text(json.dumps(data), encoding="utf-8")
        loaded = tmp_save.load()
        assert loaded.last_interaction_at is None

    def test_v2_roundtrip_preserves_last_interaction_at(self, tmp_save):
        state = PetState(hunger=50, last_interaction_at=1234567890.0)
        tmp_save.save(state)
        loaded = tmp_save.load()
        assert loaded.last_interaction_at == 1234567890.0


class TestExistsDelete:
    def test_exists_returns_false_when_no_file(self, tmp_save):
        assert tmp_save.exists() is False

    def test_exists_returns_true_after_save(self, tmp_save, sample_state):
        tmp_save.save(sample_state)
        assert tmp_save.exists() is True

    def test_delete_removes_file(self, tmp_save, sample_state):
        tmp_save.save(sample_state)
        assert tmp_save.exists() is True
        tmp_save.delete()
        assert tmp_save.exists() is False

    def test_delete_when_no_file_does_not_crash(self, tmp_save):
        tmp_save.delete()  # Should not raise

    def test_save_path_property(self, tmp_save):
        assert tmp_save.save_path == tmp_save._dir / DEFAULT_SAVE_FILE


class TestDefaultSaveDir:
    def test_default_dir_is_home_relative(self):
        p = PetPersistence()
        assert str(DEFAULT_SAVE_DIR) in str(p.save_path) or p.save_path == DEFAULT_SAVE_DIR / DEFAULT_SAVE_FILE
