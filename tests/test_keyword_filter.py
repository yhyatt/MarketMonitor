"""Tests for keyword filter."""

import pytest
from dataclasses import dataclass

from market_monitor.filters.keyword import KeywordFilter


@dataclass
class MockItem:
    """Mock item for testing."""
    title: str
    abstract: str = ""

    @property
    def full_text(self) -> str:
        return f"{self.title} {self.abstract}"


class TestKeywordFilter:
    """Tests for KeywordFilter."""

    def test_positive_keyword_match(self):
        """Items with positive keywords should pass."""
        f = KeywordFilter()
        item = MockItem(
            title="Agentic AI for Enterprise",
            abstract="We explore multi-agent systems.",
        )
        assert f.passes(item)

    def test_positive_keyword_required(self):
        """Items without positive keywords should fail."""
        f = KeywordFilter()
        item = MockItem(
            title="Weather Prediction Methods",
            abstract="A study of meteorological forecasting.",
        )
        assert not f.passes(item)

    def test_negative_title_pattern_rejects(self):
        """Items matching negative title patterns should fail."""
        f = KeywordFilter()
        item = MockItem(
            title="Survey of Machine Learning Methods",
            abstract="We explore foundation models and LLM orchestration.",
        )
        assert not f.passes(item)

    def test_benchmark_comparison_rejected(self):
        """Benchmark comparison papers should be rejected."""
        f = KeywordFilter()
        item = MockItem(
            title="Benchmark Comparison of LLM Agents",
            abstract="Comparing agent frameworks.",
        )
        assert not f.passes(item)

    def test_dataset_for_rejected(self):
        """Dataset papers should be rejected."""
        f = KeywordFilter()
        item = MockItem(
            title="Dataset for Multi-Agent Training",
            abstract="A new dataset for agent training.",
        )
        assert not f.passes(item)

    def test_two_negative_keywords_rejects(self):
        """Items with 2+ negative keywords should fail."""
        f = KeywordFilter()
        item = MockItem(
            title="AI for Medical Imaging",
            abstract="Using medical imaging and protein folding to diagnose. Also explores LLM agents.",
        )
        assert not f.passes(item)

    def test_one_negative_keyword_passes(self):
        """Items with only 1 negative keyword should pass if positive match exists."""
        f = KeywordFilter()
        item = MockItem(
            title="LLM Agents for Healthcare",
            abstract="Using large language models for medical imaging analysis.",
        )
        assert f.passes(item)

    def test_filter_batch(self):
        """filter() should return only passing items."""
        f = KeywordFilter()
        items = [
            MockItem("Agentic AI Systems", "Multi-agent orchestration"),
            MockItem("Weather Prediction", "Meteorological models"),
            MockItem("Survey of LLM Methods", "Agent frameworks"),
            MockItem("Foundation Model Scaling", "Scaling laws for LLMs"),
        ]
        filtered = f.filter(items)
        assert len(filtered) == 2
        assert filtered[0].title == "Agentic AI Systems"
        assert filtered[1].title == "Foundation Model Scaling"

    def test_llm_keyword_case_insensitive(self):
        """Keywords should match case-insensitively."""
        f = KeywordFilter()
        item = MockItem(
            title="LLM vs llm vs Llm",
            abstract="Testing different cases.",
        )
        assert f.passes(item)

    def test_count_positive_matches(self):
        """count_positive_matches should count all matches."""
        f = KeywordFilter()
        text = "Agentic AI with multi-agent orchestration and LLM reasoning model"
        count = f.count_positive_matches(text)
        assert count >= 4  # agent, agentic, multi-agent, LLM, reasoning model

    def test_count_negative_matches(self):
        """count_negative_matches should count all matches."""
        f = KeywordFilter()
        text = "Medical imaging for protein folding and speech recognition"
        count = f.count_negative_matches(text)
        assert count == 3

    def test_get_matched_keywords(self):
        """get_matched_keywords should return lists of matches."""
        f = KeywordFilter()
        text = "Agentic AI for medical imaging"
        matches = f.get_matched_keywords(text)
        assert "agent" in matches["positive"] or "agentic" in matches["positive"]
        assert "medical imaging" in matches["negative"]

    def test_empty_item(self):
        """Empty items should fail (no positive match)."""
        f = KeywordFilter()
        item = MockItem(title="", abstract="")
        assert not f.passes(item)

    def test_foundation_model_passes(self):
        """Foundation model keyword should pass."""
        f = KeywordFilter()
        item = MockItem(
            title="New Foundation Model Architecture",
            abstract="A novel approach.",
        )
        assert f.passes(item)

    def test_chain_of_thought_passes(self):
        """Chain-of-thought keyword should pass."""
        f = KeywordFilter()
        item = MockItem(
            title="Improving Chain-of-Thought Reasoning",
            abstract="Better prompting strategies.",
        )
        assert f.passes(item)

    def test_rlhf_passes(self):
        """RLHF keyword should pass."""
        f = KeywordFilter()
        item = MockItem(
            title="RLHF Training Improvements",
            abstract="Better human feedback integration.",
        )
        assert f.passes(item)
