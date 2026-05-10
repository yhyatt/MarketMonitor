"""Tests for LLM scorer."""

import json
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from market_monitor.filters.scorer import ScoredItem
from market_monitor.config import Config


@dataclass
class MockItem:
    """Mock item for testing."""
    title: str
    abstract: str = ""
    authors: list = None

    def __post_init__(self):
        if self.authors is None:
            self.authors = []

    @property
    def full_text(self) -> str:
        return f"{self.title} {self.abstract}"


class TestLLMScorer:
    """Tests for LLMScorer."""

    def test_requires_api_key(self, temp_dir):
        """Scorer should require MOONSHOT_API_KEY (or ZAI_API_KEY via llm_client)."""
        from market_monitor.filters.scorer import LLMScorer
        cfg = Config(memory_dir=temp_dir)
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="MOONSHOT_API_KEY"):
                LLMScorer(cfg)

    @patch("market_monitor.filters.scorer.chat")
    def test_score_item_success(self, mock_chat_fn, config):
        """Successful scoring should return ScoredItem."""
        from market_monitor.filters.scorer import LLMScorer

        mock_chat_fn.return_value = json.dumps({
            "score": 8,
            "thesis": "Multi-agent systems represent the next frontier",
            "themes": ["agentic-AI", "multi-agent", "orchestration"],
            "strategic_signals": ["Enterprise adoption accelerating"],
            "why_it_matters": "This shifts the competitive landscape.",
        })

        scorer = LLMScorer(config)
        item = MockItem("Test Title", "Test abstract about agents")
        result = scorer._score_item(item)

        assert result is not None
        assert result.score == 8
        assert result.thesis == "Multi-agent systems represent the next frontier"
        assert "agentic-AI" in result.themes
        assert result.original == item

    @patch("market_monitor.filters.scorer.chat")
    def test_score_items_parallel(self, mock_chat_fn, config):
        """score_items should process items in parallel."""
        from market_monitor.filters.scorer import LLMScorer

        mock_chat_fn.return_value = json.dumps({
            "score": 8,
            "thesis": "Multi-agent systems represent the next frontier",
            "themes": ["agentic-AI"],
            "strategic_signals": ["Enterprise adoption accelerating"],
            "why_it_matters": "This shifts the competitive landscape.",
        })

        scorer = LLMScorer(config)
        items = [
            MockItem("Title 1", "Abstract 1"),
            MockItem("Title 2", "Abstract 2"),
            MockItem("Title 3", "Abstract 3"),
        ]
        results = scorer.score_items(items)

        assert len(results) == 3
        assert all(r.score == 8 for r in results)

    @patch("market_monitor.filters.scorer.chat")
    def test_filter_by_threshold(self, mock_chat_fn, config):
        """filter_by_threshold should only return items above threshold."""
        from market_monitor.filters.scorer import LLMScorer

        mock_chat_fn.side_effect = [
            json.dumps({"score": 9, "thesis": "T1", "themes": [], "strategic_signals": [], "why_it_matters": ""}),
            json.dumps({"score": 5, "thesis": "T2", "themes": [], "strategic_signals": [], "why_it_matters": ""}),
            json.dumps({"score": 8, "thesis": "T3", "themes": [], "strategic_signals": [], "why_it_matters": ""}),
        ]

        scorer = LLMScorer(config)
        items = [MockItem(f"Title {i}") for i in range(3)]
        results = scorer.filter_by_threshold(items, threshold=7, max_items=5)

        assert len(results) == 2
        assert results[0].score == 9
        assert results[1].score == 8

    @patch("market_monitor.filters.scorer.chat")
    def test_max_items_limit(self, mock_chat_fn, config):
        """filter_by_threshold should respect max_items."""
        from market_monitor.filters.scorer import LLMScorer

        mock_chat_fn.return_value = json.dumps({
            "score": 8, "thesis": "T", "themes": [],
            "strategic_signals": [], "why_it_matters": "",
        })

        scorer = LLMScorer(config)
        items = [MockItem(f"Title {i}") for i in range(10)]
        results = scorer.filter_by_threshold(items, threshold=0, max_items=3)

        assert len(results) == 3

    def test_parse_json_response_direct(self, config):
        """_parse_json_response should parse direct JSON."""
        from market_monitor.filters.scorer import LLMScorer
        scorer = LLMScorer(config)
        result = scorer._parse_json_response('{"score": 7, "thesis": "Test"}')
        assert result["score"] == 7

    def test_parse_json_response_code_block(self, config):
        """_parse_json_response should extract JSON from code block."""
        from market_monitor.filters.scorer import LLMScorer
        scorer = LLMScorer(config)
        result = scorer._parse_json_response('```json\n{"score": 7, "thesis": "Test"}\n```')
        assert result["score"] == 7

    def test_parse_json_response_with_text(self, config):
        """_parse_json_response should extract JSON from mixed text."""
        from market_monitor.filters.scorer import LLMScorer
        scorer = LLMScorer(config)
        result = scorer._parse_json_response('Here is my analysis:\n{"score": 7, "thesis": "Test"}')
        assert result["score"] == 7

    def test_parse_json_response_invalid(self, config):
        """_parse_json_response should return None for invalid JSON."""
        from market_monitor.filters.scorer import LLMScorer
        scorer = LLMScorer(config)
        result = scorer._parse_json_response("This is not JSON at all")
        assert result is None

    @patch("market_monitor.filters.scorer.chat")
    def test_api_error_handling(self, mock_chat_fn, config):
        """API errors should be handled gracefully."""
        from market_monitor.filters.scorer import LLMScorer

        mock_chat_fn.side_effect = Exception("API Error")
        scorer = LLMScorer(config)
        item = MockItem("Test")
        result = scorer._score_item(item)

        assert result is None

    @patch("market_monitor.filters.scorer.chat")
    def test_high_signal_author_boost(self, mock_chat_fn, config):
        """High-signal authors should get +1 score boost."""
        from market_monitor.filters.scorer import LLMScorer

        mock_chat_fn.return_value = json.dumps({
            "score": 7, "thesis": "T", "themes": [],
            "strategic_signals": [], "why_it_matters": "",
        })

        scorer = LLMScorer(config)
        item = MockItem("Test Paper", "Abstract", authors=["Andrej Karpathy"])
        result = scorer._score_item(item)

        assert result is not None
        assert result.score == 8  # 7 + 1 boost


class TestScoredItem:
    """Tests for ScoredItem dataclass."""

    def test_passes_threshold(self):
        """passes_threshold should check score >= 7."""
        item = ScoredItem(
            original=MockItem("Test"),
            score=7,
            thesis="Test",
            themes=[],
            strategic_signals=[],
            why_it_matters="",
        )
        assert item.passes_threshold

    def test_fails_threshold(self):
        """passes_threshold should return False for low scores."""
        item = ScoredItem(
            original=MockItem("Test"),
            score=6,
            thesis="Test",
            themes=[],
            strategic_signals=[],
            why_it_matters="",
        )
        assert not item.passes_threshold
