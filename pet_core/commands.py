"""
PetCommand — the structured intent emitted by the LLM and consumed by the
Live2D bridge.

The LLM is expected to append a fenced JSON block at the end of each reply,
shaped like:

    {"action": "wave", "expression": "happy", "text": "你好~"}

All three fields are optional. command_parser.py extracts and normalises this
into a PetCommand. The renderer applies whichever fields are present.

Whitelists below are intentionally loose for the first iteration — stage C of
roadmap.md replaces them with proper expression/motion catalogs derived from
the active Live2D model.
"""

from dataclasses import dataclass
from typing import Optional


# ── Whitelists (placeholder — stage C replaces with model-driven catalogs) ──
DEFAULT_ACTIONS: frozenset[str] = frozenset({
    "idle", "wave", "dance", "nod", "shake_head",
    "spin", "jump", "stretch", "bow", "clap",
})

DEFAULT_EXPRESSIONS: frozenset[str] = frozenset({
    "neutral", "happy", "shy", "surprised",
    "angry", "sad", "sleepy", "love", "wink",
})

MAX_TEXT_LEN = 500


@dataclass(frozen=True)
class PetCommand:
    """Structured instruction from the LLM to the Live2D pet.

    Any field may be None: the renderer skips fields it doesn't have.
    Construct via `validate()` to get a normalised, whitelisted instance.
    """

    action: Optional[str] = None
    expression: Optional[str] = None
    text: Optional[str] = None

    def is_empty(self) -> bool:
        return self.action is None and self.expression is None and not self.text


def _normalise(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v or None


def validate(
    raw: dict,
    allowed_actions: frozenset[str] = DEFAULT_ACTIONS,
    allowed_expressions: frozenset[str] = DEFAULT_EXPRESSIONS,
) -> PetCommand:
    """Turn a raw dict (from JSON) into a normalised PetCommand.

    - Unknown action / expression names are dropped (set to None).
    - text is truncated to MAX_TEXT_LEN and stripped.
    - Wrong types degrade to None instead of raising — the LLM should not
      crash the pet by emitting malformed JSON.
    """
    if not isinstance(raw, dict):
        return PetCommand()

    action = _normalise(raw.get("action"))
    if action is not None and action not in allowed_actions:
        action = None

    expression = _normalise(raw.get("expression"))
    if expression is not None and expression not in allowed_expressions:
        expression = None

    text_raw = raw.get("text")
    text: Optional[str] = None
    if isinstance(text_raw, str):
        stripped = text_raw.strip()
        if stripped:
            text = stripped[:MAX_TEXT_LEN]

    return PetCommand(action=action, expression=expression, text=text)
