"""Tests for HuggingFace collector."""

import json
import pytest
from unittest.mock import patch, MagicMock

from market_monitor.collectors.huggingface import HuggingFaceCollector, HFItem


class TestHFItem:
    """Tests for HFItem dataclass."""

    def test_full_text(self):
        """full_text should combine name and description."""
        item = HFItem(
            id="test-id",
            name="Test Model",
            type="model",
            description="A test model",
            likes=100,
            downloads=1000,
            date="2026-03-25",
            url="https://huggingface.co/test",
        )
        assert "Test Model" in item.full_text
        assert "A test model" in item.full_text


class TestHuggingFaceCollector:
    """Tests for HuggingFaceCollector."""

    def test_parse_daily_paper(self, config, sample_hf_papers):
        """Should parse daily paper JSON."""
        collector = HuggingFaceCollector(config)
        paper = collector._parse_daily_paper(sample_hf_papers[0], "2026-03-25")

        assert paper is not None
        assert paper.id == "2603.11111"
        assert paper.name == "Foundation Model Scaling Laws"
        assert paper.type == "paper"
        assert paper.likes == 42
        assert "huggingface.co/papers" in paper.url

    def test_parse_model(self, config, sample_hf_models):
        """Should parse model JSON."""
        collector = HuggingFaceCollector(config)
        model = collector._parse_model(sample_hf_models[0])

        assert model is not None
        assert model.id == "meta-llama/llama-4-70b"
        assert model.name == "llama-4-70b"
        assert model.type == "model"
        assert model.likes == 1000
        assert model.downloads == 50000
        assert "huggingface.co/meta-llama" in model.url

    def test_skip_lora_models(self, config):
        """Should skip LoRA models."""
        collector = HuggingFaceCollector(config)

        assert collector._should_skip_model("user/model-lora-v1")
        assert collector._should_skip_model("user/model-LoRA-adapters")
        assert not collector._should_skip_model("meta-llama/llama-4-70b")

    def test_skip_gguf_models(self, config):
        """Should skip GGUF models."""
        collector = HuggingFaceCollector(config)

        assert collector._should_skip_model("user/model-GGUF")
        assert collector._should_skip_model("user/model-gguf-q4")

    def test_skip_quantized_models(self, config):
        """Should skip quantized models."""
        collector = HuggingFaceCollector(config)

        assert collector._should_skip_model("user/model-gptq")
        assert collector._should_skip_model("user/model-awq-4bit")
        assert collector._should_skip_model("user/model-quantized")

    def test_skip_finetune_models(self, config):
        """Should skip fine-tuned models."""
        collector = HuggingFaceCollector(config)

        assert collector._should_skip_model("user/model-finetune")
        assert collector._should_skip_model("user/model-fine-tuned")
        assert collector._should_skip_model("user/model-ft")

    def test_allow_foundation_models(self, config):
        """Should allow foundation models."""
        collector = HuggingFaceCollector(config)

        assert not collector._should_skip_model("meta-llama/llama-4-70b")
        assert not collector._should_skip_model("openai/gpt-5")
        assert not collector._should_skip_model("deepseek-ai/DeepSeek-V4")

    @patch("urllib.request.urlopen")
    def test_collect_daily_papers(self, mock_urlopen, config, sample_hf_papers):
        """collect_daily_papers should fetch papers for each day."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_hf_papers).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        collector = HuggingFaceCollector(config)
        papers = collector._collect_daily_papers()

        assert len(papers) >= 1
        # Should be called multiple times (once per day in lookback)
        assert mock_urlopen.call_count == config.arxiv_lookback_days

    @patch("urllib.request.urlopen")
    def test_collect_trending_models(self, mock_urlopen, config, sample_hf_models):
        """collect_trending_models should fetch and filter models."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_hf_models).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        collector = HuggingFaceCollector(config)
        models = collector._collect_trending_models()

        # Should filter out LoRA and GGUF models
        assert len(models) == 1
        assert models[0].name == "llama-4-70b"

    @patch("urllib.request.urlopen")
    def test_collect_network_error(self, mock_urlopen, config):
        """Should handle network errors gracefully."""
        mock_urlopen.side_effect = Exception("Network error")

        collector = HuggingFaceCollector(config)
        items = collector.collect()

        # Should return empty list, not crash
        assert items == []

    def test_collector_name(self, config):
        """Collector should have correct name."""
        collector = HuggingFaceCollector(config)
        assert collector.name == "HuggingFace"

    def test_parse_paper_missing_fields(self, config):
        """Should handle papers with missing fields."""
        collector = HuggingFaceCollector(config)

        # Missing paper field
        result = collector._parse_daily_paper({}, "2026-03-25")
        assert result is None

        # Missing id
        result = collector._parse_daily_paper({"paper": {}}, "2026-03-25")
        assert result is None

    def test_parse_model_missing_fields(self, config):
        """Should handle models with missing fields."""
        collector = HuggingFaceCollector(config)

        result = collector._parse_model({})
        assert result is None

    def test_model_date_parsing(self, config):
        """Should parse model creation dates."""
        collector = HuggingFaceCollector(config)

        model = collector._parse_model({
            "modelId": "test/model",
            "createdAt": "2026-03-20T12:00:00Z",
        })

        assert model.date == "2026-03-20"

    def test_model_fallback_date(self, config):
        """Should use today's date if no creation date."""
        collector = HuggingFaceCollector(config)

        model = collector._parse_model({
            "modelId": "test/model",
        })

        # Should be today's date
        assert model.date is not None
        assert len(model.date) == 10  # YYYY-MM-DD format
