# pet-core: framework-agnostic virtual pet system
# No Electron, DOM, React, or PySide6 dependencies.

from .state import (
    PetState,
    PetBehavior,
    tick_pet,
    feed,
    clean,
    pet_action,
    sleep_action,
    clamp,
    compute_health,
    BEHAVIOR_MESSAGE,
    check_level_up,
    time_of_day_context,
    absence_greeting,
    exp_to_next_level,
)
from .behavior import BehaviorPlanner
from .persistence import PetPersistence
from .motion_adapter import MotionAdapter
from .expression_catalog import ExpressionCatalog
from .motion_catalog import MotionCatalog
from .tts_preprocessor import clean_for_tts, segment_sentences, prepare_tts_text

__all__ = [
    # State
    "PetState",
    "PetBehavior",
    "tick_pet",
    "feed",
    "clean",
    "pet_action",
    "sleep_action",
    "clamp",
    "compute_health",
    "BEHAVIOR_MESSAGE",
    "check_level_up",
    "time_of_day_context",
    "absence_greeting",
    "exp_to_next_level",
    # Behavior
    "BehaviorPlanner",
    # Persistence
    "PetPersistence",
    # Motion
    "MotionAdapter",
    # Catalog
    "ExpressionCatalog",
    "MotionCatalog",
    # TTS Preprocessor
    "clean_for_tts",
    "segment_sentences",
    "prepare_tts_text",
]
