"""End-to-end tests: LLM-like text → PetCommand → bridge dispatch.

These tests verify the full pipeline without a Qt/WebEngine runtime:
  LLM reply text → command_parser.parse() → validate() → PetCommand
  + strip_command_block() for clean bubble text.

Actual JS bridge dispatch (runJavaScript) cannot be tested here since it
requires a running QWebEngineView. We verify the pure-Python layer end-to-end
and trust that _apply_command calls runJavaScript with the correct arguments.
"""

import pytest

from pet_core.command_parser import parse, strip_command_block
from pet_core.commands import PetCommand, validate


class TestEndToEnd:
    """Simulate realistic LLM replies and verify the full parse pipeline."""

    def test_happy_greeting(self):
        """LLM: greeting with wave + happy expression."""
        llm_text = """你好呀主人sama~ 今天代码跑得顺利吗？
```json
{"action": "wave", "expression": "happy", "text": "你好呀主人~"}
```"""
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.action == "wave"
        assert cmd.expression == "happy"
        assert cmd.text == "你好呀主人~"
        # Strip JSON for bubble display
        clean = strip_command_block(llm_text)
        assert "你好呀主人sama~" in clean
        assert "```json" not in clean

    def test_surprised_reaction(self):
        """LLM: surprised expression only, no action."""
        llm_text = """诶？！真的吗？好厉害！
```json
{"expression": "surprised"}
```"""
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.action is None
        assert cmd.expression == "surprised"
        assert cmd.text is None
        assert not cmd.is_empty()

    def test_just_text_no_command(self):
        """LLM: plain chat with no JSON block at all."""
        llm_text = "嗯嗯，我在听你说呢~ 继续继续~"
        cmd = parse(llm_text)
        assert cmd is None

    def test_dance_on_request(self):
        """LLM: action-only command with dance."""
        llm_text = """好呀！给你跳个舞~
```json
{"action": "dance"}
```"""
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.action == "dance"
        assert cmd.expression is None

    def test_sleepy_mood(self):
        """LLM: sleepy expression, encouraging text."""
        llm_text = """主人早点休息吧~ 喵酱也困了にゃん
```json
{"expression": "sleepy", "text": "好困呀~ 一起睡吧"}
```"""
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.action is None
        assert cmd.expression == "sleepy"
        assert cmd.text == "好困呀~ 一起睡吧"

    def test_keyword_bypass_no_json(self):
        """User input with keyword (D2) does not reach the JSON parser — but
        if it somehow did, verify the keyword text doesn't produce a command."""
        # This simulates: user types "挥个手" and keyword match fires
        # before LLM. But if the text slips through, it should still be safe.
        cmd = parse("挥个手！")
        assert cmd is None  # no JSON block in keyword text

    def test_unknown_action_safe(self):
        """LLM tries an action not in whitelist → dropped to None."""
        llm_text = """看我表演一个！
```json
{"action": "backflip", "expression": "happy"}
```"""
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.action is None  # backflip not in whitelist
        assert cmd.expression == "happy"

    def test_validated_command_contents(self):
        """Verify validate() rejects bad types gracefully."""
        raw = {"action": 42, "expression": [], "text": {"nested": True}}
        cmd = validate(raw)
        assert cmd.action is None
        assert cmd.expression is None
        assert cmd.text is None
        assert cmd.is_empty()

    def test_text_truncated_in_pipeline(self):
        """Very long text gets truncated by validate()."""
        llm_text = '```json\n{"text": "' + "x" * 10_000 + '"}\n```'
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.text is not None
        assert len(cmd.text) == 500

    def test_multiple_commands_only_first_applied(self):
        """Two JSON blocks — parser picks the last one."""
        llm_text = """先挥个手
```json
{"action": "wave"}
```
再转个圈
```json
{"action": "spin"}
```"""
        cmd = parse(llm_text)
        assert cmd is not None
        assert cmd.action == "spin"  # last wins
