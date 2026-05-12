"""
Persistence layer for pet state. JSON-file based with schema versioning.
Pure Python, no framework dependencies.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Optional

from .state import PetState

DEFAULT_SAVE_DIR = Path.home() / ".miaogiang-pet"
DEFAULT_SAVE_FILE = "pet_save.json"


class PetPersistence:
    """Save and load PetState to/from a local JSON file."""

    def __init__(self, save_dir: Optional[Path] = None):
        self._dir = Path(save_dir) if save_dir else DEFAULT_SAVE_DIR
        self._file = self._dir / DEFAULT_SAVE_FILE

    @property
    def save_path(self) -> Path:
        return self._file

    def save(self, state: PetState) -> bool:
        """Persist pet state to disk. Returns True on success."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            data = state.to_dict()
            # Atomic write: temp file → rename
            tmp = self._file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._file)
            return True
        except Exception as e:
            print(f"[PetCore] Save failed: {e}")
            return False

    def load(self) -> PetState:
        """Load pet state from disk. Returns default state if file missing or corrupt."""
        if not self._file.exists():
            return PetState()

        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))

            # Schema migration
            version = data.get("version", 0)
            if version < 1:
                data = self._migrate_to_v1(data)
            if version < 2:
                data = self._migrate_to_v2(data)

            return PetState.from_dict(data)

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            print(f"[PetCore] Save file corrupt: {e}")
            # Backup the corrupt file for debugging
            self._backup_corrupt()
            return PetState()

    def _backup_corrupt(self):
        """Move corrupt save file to .corrupt backup."""
        try:
            corrupt_path = self._file.with_suffix(".corrupt.json")
            shutil.copy2(self._file, corrupt_path)
            print(f"[PetCore] Corrupt save backed up to {corrupt_path}")
        except Exception:
            pass

    @staticmethod
    def _migrate_to_v1(data: dict) -> dict:
        """Migrate older schema versions to v1."""
        data["version"] = 1
        return data

    @staticmethod
    def _migrate_to_v2(data: dict) -> dict:
        """Migrate v1 to v2: add last_interaction_at."""
        data["version"] = 2
        data.setdefault("last_interaction_at", None)
        return data

    def exists(self) -> bool:
        return self._file.exists()

    def delete(self):
        """Remove save file (factory reset)."""
        try:
            self._file.unlink(missing_ok=True)
        except Exception:
            pass
