"""Tests for ui.state_keys — Sprint 1 issue B5.

Single source of truth for session_state key strings.
"""
from __future__ import annotations

from ui.state_keys import (
    StateKey,
    ai_v2_key_for,
    ai_v2_key_input_for,
)


class TestSharedKeys:
    def test_comparison_results_value(self):
        assert StateKey.COMPARISON_RESULTS == "comparison_results"

    def test_blast_data_value(self):
        assert StateKey.BLAST_DATA == "blast_data"


class TestTableFilterKeys:
    def test_all_filter_keys_present(self):
        for k in (
            StateKey.TABLE_FILTER_SECTOR,
            StateKey.TABLE_FILTER_LEVEL,
            StateKey.TABLE_FILTER_SECTION,
            StateKey.TABLE_FILTER_BENCH,
        ):
            assert k.startswith("table_filter_")

    def test_table_sort_value(self):
        assert StateKey.TABLE_SORT == "table_sort"


class TestAIV2Keys:
    def test_all_ai_v2_keys_have_prefix(self):
        ai_keys = [
            StateKey.AI_V2_PROVIDER, StateKey.AI_V2_MODEL,
            StateKey.AI_V2_TEMPERATURE, StateKey.AI_V2_MAX_TOKENS,
            StateKey.AI_V2_TIMEOUT, StateKey.AI_V2_CACHE,
            StateKey.AI_V2_GENERATE, StateKey.AI_V2_FULL_REPORT,
        ]
        for k in ai_keys:
            assert k.startswith("ai_v2_"), f"{k} missing prefix"


class TestHelpers:
    def test_ai_v2_key_for_builds_per_provider_key(self):
        assert ai_v2_key_for("ollama") == "ai_v2_key_ollama"
        assert ai_v2_key_for("openrouter") == "ai_v2_key_openrouter"

    def test_ai_v2_key_input_for_builds_per_provider_key(self):
        assert ai_v2_key_input_for("ollama") == "ai_v2_key_input_ollama"


class TestUniqueness:
    def test_all_values_are_unique(self):
        keys = [v for k, v in vars(StateKey).items()
                if not k.startswith("_") and isinstance(v, str)]
        assert len(keys) == len(set(keys)), f"Duplicates: {[k for k in keys if keys.count(k) > 1]}"
