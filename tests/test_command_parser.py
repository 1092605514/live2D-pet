"""Tests for the LLM-reply -> PetCommand parser."""

import pytest

from pet_core.command_parser import parse, strip_command_block
from pet_core.commands import PetCommand, validate


# ═══════════════════════════════════════════════════════════════
# parse() — happy path
# ═══════════════════════════════════════════════════════════════

class TestParseFenced:
    def test_basic_fenced_json(self):
        text = '你好~\n```json\n{"action": "wave", "expression": "happy", "text": "hi"}\n```'
        cmd = parse(text)
        assert cmd == PetCommand(action="wave", expression="happy", text="hi")

    def test_fence_without_lang_tag(self):
        text = 'reply\n```\n{"action": "dance"}\n```'
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "dance"

    def test_uppercase_json_tag(self):
        text = 'reply\n```JSON\n{"action": "nod"}\n```'
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "nod"

    def test_last_fence_wins(self):
        text = (
            '```json\n{"action": "idle"}\n```\n'
            'middle\n'
            '```json\n{"action": "spin"}\n```'
        )
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "spin"


class TestParseBareJson:
    def test_bare_json_object(self):
        text = '前言 {"action": "jump", "expression": "surprised"} 后记'
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "jump"
        assert cmd.expression == "surprised"

    def test_bare_json_at_end(self):
        text = 'sure! {"action": "wave"}'
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "wave"

    def test_multiple_bare_objects_last_wins(self):
        text = '{"action": "idle"} then {"action": "dance"}'
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "dance"


# ═══════════════════════════════════════════════════════════════
# parse() — robustness
# ═══════════════════════════════════════════════════════════════

class TestParseRobustness:
    def test_empty_string(self):
        assert parse("") is None

    def test_none_input(self):
        assert parse(None) is None  # type: ignore[arg-type]

    def test_no_json_at_all(self):
        assert parse("just plain text, no json here") is None

    def test_malformed_json_in_fence_returns_none(self):
        text = '```json\n{action: wave}\n```'  # not valid JSON
        assert parse(text) is None

    def test_fenced_takes_priority_over_bare(self):
        text = (
            '{"action": "idle"}\n'
            '```json\n{"action": "dance"}\n```'
        )
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "dance"

    def test_unclosed_fence_falls_back_to_bare_scan(self):
        text = '```json\n{"action": "wave"}'  # no closing ```
        cmd = parse(text)
        assert cmd is not None
        assert cmd.action == "wave"

    def test_garbage_braces_dont_crash(self):
        text = "the } pet {smiles} happily}"
        assert parse(text) is None

    def test_non_dict_json_ignored(self):
        text = '```json\n["wave", "dance"]\n```'
        assert parse(text) is None


# ═══════════════════════════════════════════════════════════════
# validate() — whitelist + normalisation
# ═══════════════════════════════════════════════════════════════

class TestValidate:
    def test_known_action_passes(self):
        cmd = validate({"action": "wave"})
        assert cmd.action == "wave"

    def test_unknown_action_dropped(self):
        cmd = validate({"action": "explode"})
        assert cmd.action is None

    def test_action_normalised_to_lower(self):
        cmd = validate({"action": " WAVE "})
        assert cmd.action == "wave"

    def test_unknown_expression_dropped(self):
        cmd = validate({"expression": "smug"})
        assert cmd.expression is None

    def test_text_stripped(self):
        cmd = validate({"text": "  hello  "})
        assert cmd.text == "hello"

    def test_text_truncated(self):
        cmd = validate({"text": "x" * 10_000})
        assert cmd.text is not None
        assert len(cmd.text) == 500

    def test_empty_text_becomes_none(self):
        cmd = validate({"text": "   "})
        assert cmd.text is None

    def test_wrong_types_become_none(self):
        cmd = validate({"action": 42, "expression": [], "text": {"x": 1}})
        assert cmd.action is None
        assert cmd.expression is None
        assert cmd.text is None

    def test_non_dict_input(self):
        assert validate(["wave"]).is_empty()  # type: ignore[arg-type]
        assert validate(None).is_empty()  # type: ignore[arg-type]
        assert validate("wave").is_empty()  # type: ignore[arg-type]

    def test_partial_command(self):
        cmd = validate({"expression": "happy"})
        assert cmd.action is None
        assert cmd.expression == "happy"
        assert cmd.text is None
        assert not cmd.is_empty()

    def test_empty_dict(self):
        assert validate({}).is_empty()


# ═══════════════════════════════════════════════════════════════
# strip_command_block() — for clean speech-bubble text
# ═══════════════════════════════════════════════════════════════

class TestStripCommandBlock:
    def test_removes_fenced_block(self):
        text = '你好呀~\n```json\n{"action": "wave"}\n```'
        assert strip_command_block(text) == "你好呀~"

    def test_no_fence_returns_input_trimmed(self):
        assert strip_command_block("  hello  ") == "hello"

    def test_handles_none(self):
        assert strip_command_block(None) == ""  # type: ignore[arg-type]

    def test_removes_multiple_fences(self):
        text = '```json\n{"a":1}\n``` middle ```json\n{"b":2}\n```'
        assert strip_command_block(text) == "middle"

    def test_strips_orphaned_json_kv(self):
        """LLM response split across audio slices leaves bare JSON KVs."""
        text = '"expression": "love", "text": "那好嘞，咱俩来个脑力问答怎么样？'
        assert strip_command_block(text) == ""

    def test_strips_orphaned_closing_brace_and_fence(self):
        text = '"}\n```'
        assert strip_command_block(text) == ""

    def test_strips_orphaned_opening_fence(self):
        text = '你好\n```json\n{"action": "wave", "expression": "happy"'
        assert strip_command_block(text) == "你好"

    def test_preserves_pure_natural_text(self):
        text = "你能想出几个编程中的恶趣味梗吗？"
        assert strip_command_block(text) == text

    def test_strips_complete_bare_json_object(self):
        """LLM returns a full JSON object as display_text (no fences)."""
        text = '{"action": "nod", "expression": "happy", "text": "为啥程序员的代码里边总是有很多注释呢？"}'
        assert strip_command_block(text) == ""

    def test_strips_unclosed_json_object(self):
        """Audio slice has unclosed JSON (missing closing brace)."""
        text = '{"action": "nod", "text": "继续加油主人sama！'
        assert strip_command_block(text) == ""
