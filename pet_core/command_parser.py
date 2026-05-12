"""
Extract a PetCommand from an LLM reply.

The LLM is asked (see prompts/action_protocol.md, stage B1) to append a fenced
JSON block at the end of each message:

    你好呀~
    ```json
    {"action": "wave", "expression": "happy"}
    ```

This module extracts that block. It tolerates: missing fences, multiple blocks,
trailing text, malformed JSON, wrong types. Failure modes return None — never
raise — because a single bad reply must not kill the pet's render loop.

Strategy:
  1. Look for fenced ```json ... ``` blocks; prefer the LAST one (closest to
     the end of the reply, where the LLM was asked to put it).
  2. If no fenced blocks, scan for raw `{...}` JSON objects via
     json.JSONDecoder.raw_decode; prefer the last decodable one.
  3. Hand whichever we found to commands.validate() for whitelisting.
"""

import json
import re
from typing import Optional

from .commands import PetCommand, validate

# Matches ```json {...} ``` and ``` {...} ```. Non-greedy so adjacent fences
# don't merge.
_FENCED_RE = re.compile(r"```(?:json|JSON)?\s*(\{.*?\})\s*```", re.DOTALL)

# Matches orphaned JSON fragments that leak into TTS when the LLM response
# is split across multiple audio slices.  Catches:
#   - opening fence without closing: ```json\n{...
#   - closing fence without opening: "}\n```
#   - bare JSON key-value pairs:     "action": "wave", "expression": "happy"
#   - lone closing brace:            "}
#   - full/incomplete JSON object:   {"action": "nod", "expression": ...
_ORPHAN_FENCE_OPEN = re.compile(r"```(?:json|JSON)?\s*\{[^`]*$", re.DOTALL)
_ORPHAN_FENCE_CLOSE = re.compile(r"^[\s\S]*?\}\s*```", re.DOTALL)
_ORPHAN_JSON_KV = re.compile(
    r'[\s,]*"(?:action|expression|text)"\s*:\s*"[^"]*"[^}]*',
    re.DOTALL | re.MULTILINE,
)
_ORPHAN_BRACE_CLOSE = re.compile(r'^\s*"\s*\}\s*`*', re.DOTALL | re.MULTILINE)
_ORPHAN_JSON_OBJ = re.compile(
    r'\{[^{}]*"(?:action|expression|text)"\s*:[^}]*\}?',
    re.DOTALL,
)
# Matches incomplete JSON objects starting with { and containing known keys
# but missing the closing brace entirely (e.g., split across audio slices)
_ORPHAN_JSON_OPEN = re.compile(
    r'\{[^{}]*"(?:action|expression|text)"\s*:.*$',
    re.DOTALL,
)
# Catch-all: any remaining JSON-like fragment with known keys (no braces needed)
_ORPHAN_JSON_ANY = re.compile(
    r'"(?:action|expression)"\s*:\s*"[^"]*"[^}]*',
    re.DOTALL,
)


def _scan_raw_json_objects(text: str) -> list[dict]:
    """Find every top-level JSON object in `text` using raw_decode.

    Stops trying at each '{' that fails to parse and moves to the next one,
    so trailing prose like "the cat said {hi}" doesn't break the scanner.
    """
    decoder = json.JSONDecoder()
    found: list[dict] = []
    i = 0
    n = len(text)
    while i < n:
        idx = text.find("{", i)
        if idx == -1:
            break
        try:
            obj, end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            i = idx + 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i = idx + end
    return found


def parse(text: str, *, allowed_actions=None, allowed_expressions=None) -> Optional[PetCommand]:
    """Extract a PetCommand from LLM text. Returns None if nothing usable."""
    if not isinstance(text, str) or not text:
        return None

    kwargs = {}
    if allowed_actions is not None:
        kwargs["allowed_actions"] = allowed_actions
    if allowed_expressions is not None:
        kwargs["allowed_expressions"] = allowed_expressions

    # ── Pass 1: fenced ```json``` blocks ──
    fenced = _FENCED_RE.findall(text)
    for raw in reversed(fenced):  # last fence wins
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        cmd = validate(data, **kwargs)
        if not cmd.is_empty():
            return cmd

    # ── Pass 2: bare JSON objects anywhere in the text ──
    for data in reversed(_scan_raw_json_objects(text)):
        cmd = validate(data, **kwargs)
        if not cmd.is_empty():
            return cmd

    return None


def strip_command_block(text: str) -> str:
    """Return `text` with any JSON command block or fragment removed.

    Handles:
      - Well-formed fenced blocks: ```json {...} ```
      - Orphaned opening fence:    ```json\n{"action": ...
      - Orphaned closing fence:    "}\n```
      - Bare JSON key-value pairs: "action": "wave", "expression": "happy"
      - Lone closing brace:        "}
    """
    if not isinstance(text, str):
        return ""

    # 1. Remove well-formed fenced blocks
    text = _FENCED_RE.sub("", text)

    # 2. Remove orphaned opening fence (```json\n{... at end)
    text = _ORPHAN_FENCE_OPEN.sub("", text)

    # 3. Remove orphaned closing fence (}\n``` at start)
    text = _ORPHAN_FENCE_CLOSE.sub("", text)

    # 4. Remove full/incomplete JSON objects with known command keys
    text = _ORPHAN_JSON_OBJ.sub("", text)

    # 4b. Remove unclosed JSON objects (opening { with known keys, no closing })
    text = _ORPHAN_JSON_OPEN.sub("", text)

    # 5. Remove bare JSON key-value lines (action/expression/text)
    text = _ORPHAN_JSON_KV.sub("", text)

    # 6. Remove orphaned closing brace with optional backticks
    text = _ORPHAN_BRACE_CLOSE.sub("", text)

    # 7. Catch-all: remove any remaining JSON-like fragments with known keys
    text = _ORPHAN_JSON_ANY.sub("", text)

    return text.strip()
