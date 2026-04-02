"""Tests for LLM scorer."""

import json
import sys
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

    @property
    def full_text(self) -> str:
        return f"{self.title} {self.abstract}"


@pytest.fixture
def mock_anthropic_module():
    """Mock the anthropic module before importing LLMScorer."""
    mock_module = MagicMock()
    with patch.dict(sys.modules, {"anthropic": mock_module}):
        yield mock_module


class TestLLMScorer:
    """Tests for LLMScorer."""

    def test_requires_api_token(self, temp_dir, mock_anthropic_module):
        """Scorer should require ANTHROPIC_API_TOKEN."""
        from market_monitor.filters.scorer import LLMScorer
        cfg = Config(
            memory_dir=temp_dir,
            anthropic_api_token=None,
        )
        with pytest.raises(ValueError, match="ANTHROPIC_API_TOKEN"):
            LLMScorer(cfg)

    def test_score_item_success(self, config, mock_anthropic_response, mock_anthropic_module):
        """Successful scoring should return ScoredItem."""
        from market_monitor.filters.scorer import LLMScorer

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_module.Anthropic.return_value = mock_client

        scorer = LLMScorer(config)
        item = MockItem("Test Title", "Test abstract about agents")
        result = scorer._score_item(item)

        assert result is not None
        assert result.score == 8
        assert result.thesis == "Multi-agent systems represent the next frontier"
        assert "agentic-AI" in result.themes
        assert result.original == item

    def test_score_items_parallel(self, config, mock_anthropic_response, mock_anthropic_module):
        """score_items should process items in parallel."""
        from market_monitor.filters.scorer import LLMScorer

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_module.Anthropic.return_value = mock_client

        scorer = LLMScorer(config)
        items = [
            MockItem("Title 1", "Abstract 1"),
            MockItem("Title 2", "Abstract 2"),
            MockItem("Title 3", "Abstract 3"),
        ]
        results = scorer.score_items(items)

        assert len(results) == 3
        # Should be sorted by score (all same score here)
        assert all(r.score == 8 for r in results)

    def test_filter_by_threshold(self, config, mock_anthropic_module):
        """filter_by_threshold should only return items above threshold."""
        from market_monitor.filters.scorer import LLMScorer

        # Mock different scores
        responses = [
            MagicMock(content=[MagicMock(text=json.dumps({"score": 9, "thesis": "T1", "themes": [], "strategic_signals": [], "why_it_matters": ""}))]),
            MagicMock(content=[MagicMock(text=json.dumps({"score": 5, "thesis": "T2", "themes": [], "strategic_signals": [], "why_it_matters": ""}))]),
            MagicMock(content=[MagicMock(text=json.dumps({"score": 8, "thesis": "T3", "themes": [], "strategic_signals": [], "why_it_matters": ""}))]),
        ]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = responses
        mock_anthropic_module.Anthropic.return_value = mock_client

        scorer = LLMScorer(config)
        items = [MockItem(f"Title {i}") for i in range(3)]
        results = scorer.filter_by_threshold(items, threshold=7, max_items=5)

        # Only score 9 and 8 should pass
        assert len(results) == 2
        assert results[0].score == 9
        assert results[1].score == 8

    def test_max_items_limit(self, config, mock_anthropic_response, mock_anthropic_module):
        """filter_by_threshold should respect max_items."""
        from market_monitor.filters.scorer import LLMScorer

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_anthropic_module.Anthropic.return_value = mock_client

        scorer = LLMScorer(config)
        items = [MockItem(f"Title {i}") for i in range(10)]
        results = scorer.filter_by_threshold(items, threshold=0, max_items=3)

        assert len(results) == 3

    def test_parse_json_response_direct(self, config, mock_anthropic_module):
        """_parse_json_response should parse direct JSON."""
        from market_monitor.filters.scorer import LLMScorer

        scorer = LLMScorer(config)
        result = scorer._parse_json_response('{"score": 7, "thesis": "Test"}')
        assert result["score"] == 7

    def test_parse_json_response_code_block(self, config, mock_anthropic_module):
        """_parse_json_response should extract JSON from code block."""
        from market_monitor.filters.scorer import LLMScorer

        scorer = LLMScorer(config)
        result = scorer._parse_json_response('```json\n{"score": 7, "thesis": "Test"}\n```')
        assert result["score"] == 7

    def test_parse_json_response_with_text(self, config, mock_anthropic_module):
        """_parse_json_response should extract JSON from mixed text."""
        from market_monitor.filters.scorer import LLMScorer

        scorer = LLMScorer(config)
        result = scorer._parse_json_response('Here is my analysis:\n{"score": 7, "thesis": "Test"}')
        assert result["score"] == 7

    def test_parse_json_response_invalid(self, config, mock_anthropic_module):
        """_parse_json_response should return None for invalid JSON."""
        from market_monitor.filters.scorer import LLMScorer

        scorer = LLMScorer(config)
        result = scorer._parse_json_response("This is not JSON at all")
        assert result is None

    def test_api_error_handling(self, config, mock_anthropic_module):
        """API errors should be handled gracefully."""
        from market_monitor.filters.scorer import LLMScorer

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic_module.Anthropic.return_value = mock_client

        scorer = LLMScorer(config)
        item = MockItem("Test")
        result = scorer._score_item(item)

        assert result is None


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
