"""Tests for the expression catalog — name→index resolution and aliases."""

import pytest

from pet_core.expression_catalog import ExpressionCatalog


class TestExpressionCatalog:
    @pytest.fixture
    def cat(self) -> ExpressionCatalog:
        return ExpressionCatalog()

    def test_resolve_primary_name(self, cat):
        assert cat.resolve("happy") == 3
        assert cat.resolve("sad") == 1
        assert cat.resolve("neutral") == 0
        assert cat.resolve("love") == 7

    def test_resolve_case_insensitive(self, cat):
        assert cat.resolve("HAPPY") == 3
        assert cat.resolve("Happy") == 3

    def test_resolve_alias_english(self, cat):
        assert cat.resolve("joy") == 3
        assert cat.resolve("blush") == 4
        assert cat.resolve("mad") == 2

    def test_resolve_alias_chinese(self, cat):
        assert cat.resolve("开心") == 3
        assert cat.resolve("生气") == 2
        assert cat.resolve("难过") == 1
        assert cat.resolve("困") == 6

    def test_resolve_unknown_returns_default(self, cat):
        assert cat.resolve("nonexistent") == 0

    def test_resolve_none_returns_default(self, cat):
        assert cat.resolve(None) == 0  # type: ignore[arg-type]

    def test_resolve_empty_string_returns_default(self, cat):
        assert cat.resolve("") == 0

    def test_name_of_known(self, cat):
        assert cat.name_of(3) == "happy"
        assert cat.name_of(0) == "neutral"

    def test_name_of_unknown_returns_none(self, cat):
        assert cat.name_of(99) is None

    def test_count(self, cat):
        assert cat.count == 8

    def test_all_names(self, cat):
        names = cat.all_names
        assert "happy" in names
        assert "sad" in names
        assert len(names) == 8

    def test_as_mapping_includes_aliases(self, cat):
        mapping = cat.as_mapping()
        assert mapping["happy"] == 3
        assert mapping["joy"] == 3  # alias
        assert mapping["开心"] == 3  # chinese alias
