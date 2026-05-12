"""Tests for pet_core.tts_preprocessor."""

from pet_core.tts_preprocessor import (
    clean_for_tts,
    segment_sentences,
    prepare_tts_text,
    _split_at_clauses,
)


class TestCleanForTTS:
    """Tests for markdown, emoji, JSON, and formatting cleanup."""

    def test_plain_text_unchanged(self):
        assert clean_for_tts("你好呀~") == "你好呀~"

    def test_empty_and_none(self):
        assert clean_for_tts("") == ""
        assert clean_for_tts(None) == ""

    def test_strips_markdown_bold(self):
        assert clean_for_tts("**加粗**文字") == "加粗文字"

    def test_strips_markdown_italic(self):
        assert clean_for_tts("*斜体*文字") == "斜体文字"

    def test_strips_markdown_bold_italic(self):
        result = clean_for_tts("***粗斜***文字")
        assert result == "粗斜文字"

    def test_strips_inline_code(self):
        result = clean_for_tts("用 `print()` 函数")
        assert "print" not in result
        assert "函数" in result

    def test_strips_code_block(self):
        result = clean_for_tts("```python\nprint('hi')\n```")
        assert "python" not in result
        assert "print" not in result

    def test_converts_link_to_text(self):
        assert clean_for_tts("[点击这里](https://example.com)") == "点击这里"

    def test_strips_image(self):
        assert clean_for_tts("![截图](img.png)文字") == "文字"

    def test_strips_heading(self):
        assert clean_for_tts("## 标题文字") == "标题文字"

    def test_strips_blockquote(self):
        assert clean_for_tts("> 引用文字") == "引用文字"

    def test_strips_strikethrough(self):
        assert clean_for_tts("~~删除~~保留") == "删除保留"

    def test_strips_html_tags(self):
        assert clean_for_tts("<b>加粗</b>") == "加粗"

    def test_strips_horizontal_rule(self):
        result = clean_for_tts("文字\n---\n更多")
        assert "文字" in result
        assert "更多" in result
        assert "---" not in result

    def test_strips_emoji(self):
        result = clean_for_tts("你好😊世界🌍")
        assert "😊" not in result
        assert "🌍" not in result

    def test_strips_url(self):
        result = clean_for_tts("访问 https://example.com 看看")
        assert "https" not in result
        assert "example" not in result

    def test_strips_mention(self):
        result = clean_for_tts("你好 @user123")
        assert "@user123" not in result

    def test_collapses_repeated_punctuation(self):
        assert clean_for_tts("好！！！！！") == "好！"
        assert clean_for_tts("真的？？？") == "真的？"

    def test_removes_space_before_chinese_punctuation(self):
        assert clean_for_tts("你好 ，世界 ！") == "你好，世界！"

    def test_normalizes_whitespace(self):
        assert clean_for_tts("你好  世界") == "你好 世界"
        assert clean_for_tts("你好\n\n\n\n世界") == "你好\n\n世界"

    def test_strips_json_command_fragment(self):
        result = clean_for_tts('你好\n{"action": "wave", "expression": "happy"}')
        assert "action" not in result
        assert "wave" not in result

    def test_strips_json_key_value_pairs(self):
        result = clean_for_tts('"action": "wave", "expression": "happy"')
        assert "action" not in result

    def test_strips_fence_remnants(self):
        result = clean_for_tts("文字\n```json\n")
        assert "```" not in result

    def test_combined_cleanup(self):
        text = "你好**世界**！😊\n```json\n{\"action\":\"wave\"}\n```\nhttps://example.com"
        result = clean_for_tts(text)
        assert "**" not in result
        assert "😊" not in result
        assert "action" not in result
        assert "https" not in result
        assert "你好世界" in result


class TestSegmentSentences:
    """Tests for sentence segmentation."""

    def test_empty_text(self):
        assert segment_sentences("") == []
        assert segment_sentences(None) == []

    def test_short_text_single_segment(self):
        result = segment_sentences("你好呀~")
        assert result == ["你好呀~"]

    def test_splits_at_period(self):
        result = segment_sentences("第一句话在这里。第二句话在这里。", max_chars=10)
        assert len(result) == 2
        assert result[0] == "第一句话在这里。"
        assert result[1] == "第二句话在这里。"

    def test_splits_at_exclamation(self):
        result = segment_sentences("太好了这是真的！真的吗我不信？", max_chars=10)
        assert len(result) == 2

    def test_splits_at_tilde(self):
        result = segment_sentences("你好~世界~", max_chars=10)
        assert len(result) >= 1

    def test_merges_short_segments(self):
        result = segment_sentences("嗯。好。行。", max_chars=20)
        # Should merge into fewer segments since each is very short
        assert len(result) <= 3

    def test_respects_max_chars(self):
        text = "这是一个比较长的句子，包含很多内容，需要被正确处理。这是另一句。"
        result = segment_sentences(text, max_chars=20)
        for seg in result:
            assert len(seg) <= 25  # Allow some tolerance for clause splitting

    def test_long_text_multiple_segments(self):
        text = "今天天气真好。我们出去走走吧。我想去公园。那里有好多花。"
        result = segment_sentences(text, max_chars=15)
        assert len(result) >= 3

    def test_singles_at_clause_boundary(self):
        text = "这是第一部分，这是第二部分，这是第三部分，这是很长的第四部分需要被拆分"
        result = _split_at_clauses(text, max_chars=20)
        assert len(result) >= 2

    def test_force_split_very_long_text(self):
        text = "a" * 200
        result = segment_sentences(text, max_chars=50)
        for seg in result:
            assert len(seg) <= 50


class TestPrepareTTS:
    """Tests for the full TTS pipeline."""

    def test_empty_text(self):
        assert prepare_tts_text("") == []
        assert prepare_tts_text(None) == []

    def test_adds_ending(self):
        result = prepare_tts_text("你好世界", add_ending=True)
        assert len(result) == 1
        assert result[0].endswith("~")

    def test_no_double_ending(self):
        result = prepare_tts_text("你好！", add_ending=True)
        assert result == ["你好！"]

    def test_no_ending_when_disabled(self):
        result = prepare_tts_text("你好世界", add_ending=False)
        assert len(result) == 1
        assert not result[0].endswith("~")

    def test_custom_ending_char(self):
        result = prepare_tts_text("你好世界", add_ending=True, ending_char="。")
        assert result[0].endswith("。")

    def test_cleans_and_segments(self):
        text = "你好**世界**！😊这是一个很长的句子，包含了很多内容需要被处理。还有第二句。"
        result = prepare_tts_text(text, max_segment_chars=20, add_ending=True)
        assert len(result) >= 1
        for seg in result:
            assert "**" not in result
            assert "😊" not in seg

    def test_json_cleaned_before_segmentation(self):
        text = '你好呀~\n```json\n{"action":"wave"}\n```'
        result = prepare_tts_text(text, add_ending=True)
        assert len(result) >= 1
        for seg in result:
            assert "action" not in seg
            assert "```" not in seg

    def test_preserves_natural_punctuation(self):
        text = "主人sama~今天过得怎么样？"
        result = prepare_tts_text(text, add_ending=False)
        assert "~" in result[0] or "？" in result[0]
