"""Tests for arXiv collector and parser."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from market_monitor.collectors.arxiv import ArxivCollector, ArxivPaper
from market_monitor.config import Config


class TestArxivPaper:
    """Tests for ArxivPaper dataclass."""

    def test_full_text(self):
        """full_text should combine title and abstract."""
        paper = ArxivPaper(
            arxiv_id="2603.12345",
            title="Test Title",
            authors=["Author"],
            abstract="Test abstract",
            categories=["cs.AI"],
            date="2026-03-25",
            url="https://arxiv.org/abs/2603.12345",
        )
        assert "Test Title" in paper.full_text
        assert "Test abstract" in paper.full_text


class TestArxivCollector:
    """Tests for ArxivCollector."""

    def test_parse_response(self, config, sample_arxiv_xml):
        """Should parse valid arXiv XML response."""
        collector = ArxivCollector(config)
        papers = collector._parse_response(sample_arxiv_xml)

        assert len(papers) >= 1
        paper = papers[0]
        assert paper.arxiv_id == "2603.12345"
        assert "Agentic AI" in paper.title
        assert "Multi-Agent Paradigm" in paper.title
        assert "John Smith" in paper.authors
        assert "Jane Doe" in paper.authors
        assert "cs.AI" in paper.categories
        assert "multi-agent" in paper.abstract.lower()

    def test_parse_entry_extracts_id(self, config, sample_arxiv_xml):
        """Should extract arXiv ID from URL."""
        collector = ArxivCollector(config)
        papers = collector._parse_response(sample_arxiv_xml)

        assert papers[0].arxiv_id == "2603.12345"

    def test_parse_entry_builds_url(self, config, sample_arxiv_xml):
        """Should build correct arXiv URL."""
        collector = ArxivCollector(config)
        papers = collector._parse_response(sample_arxiv_xml)

        assert papers[0].url == "https://arxiv.org/abs/2603.12345"

    def test_parse_entry_cleans_whitespace(self, config):
        """Should clean whitespace in title and abstract."""
        recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.12345v1</id>
    <published>{recent_date}</published>
    <title>
      Title with
      extra    whitespace
    </title>
    <summary>Abstract   with   spaces</summary>
    <author><name>Author</name></author>
    <arxiv:primary_category term="cs.AI"/>
  </entry>
</feed>"""
        collector = ArxivCollector(config)
        papers = collector._parse_response(xml)

        assert papers[0].title == "Title with extra whitespace"
        assert "with spaces" in papers[0].abstract

    def test_filter_by_date(self, config):
        """Should filter out papers older than lookback_days."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.12345v1</id>
    <published>{old_date}</published>
    <title>Old Paper</title>
    <summary>Old abstract</summary>
    <author><name>Author</name></author>
    <arxiv:primary_category term="cs.AI"/>
  </entry>
</feed>"""
        collector = ArxivCollector(config)
        papers = collector._parse_response(xml)

        assert len(papers) == 0

    def test_handle_missing_fields(self, config):
        """Should handle entries with missing optional fields."""
        recent_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.12345v1</id>
    <published>{recent_date}</published>
    <title>Minimal Paper</title>
    <author><name>Author</name></author>
    <arxiv:primary_category term="cs.AI"/>
  </entry>
</feed>"""
        collector = ArxivCollector(config)
        papers = collector._parse_response(xml)

        assert len(papers) == 1
        assert papers[0].abstract == ""

    def test_handle_invalid_xml(self, config):
        """Should handle invalid XML gracefully."""
        collector = ArxivCollector(config)
        papers = collector._parse_response("not valid xml")

        assert papers == []

    def test_handle_empty_response(self, config):
        """Should handle empty feed."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
        collector = ArxivCollector(config)
        papers = collector._parse_response(xml)

        assert papers == []

    def test_extract_arxiv_id_variations(self, config):
        """Should extract arXiv ID from various URL formats."""
        collector = ArxivCollector(config)

        assert collector._extract_arxiv_id("http://arxiv.org/abs/2603.12345v1") == "2603.12345"
        assert collector._extract_arxiv_id("http://arxiv.org/abs/2301.00001") == "2301.00001"
        assert collector._extract_arxiv_id("invalid") is None

    @patch("urllib.request.urlopen")
    def test_collect_success(self, mock_urlopen, config, sample_arxiv_xml):
        """collect() should fetch and parse papers."""
        mock_response = MagicMock()
        mock_response.read.return_value = sample_arxiv_xml.encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        collector = ArxivCollector(config)
        papers = collector.collect()

        assert len(papers) >= 1
        assert mock_urlopen.called

    @patch("urllib.request.urlopen")
    def test_collect_network_error(self, mock_urlopen, config):
        """collect() should handle network errors gracefully."""
        mock_urlopen.side_effect = Exception("Network error")

        collector = ArxivCollector(config)
        papers = collector.collect()

        assert papers == []

    def test_collector_name(self, config):
        """Collector should have correct name."""
        collector = ArxivCollector(config)
        assert collector.name == "arXiv"

    def test_collector_uses_config(self, config):
        """Collector should use config values."""
        collector = ArxivCollector(config)
        assert collector.lookback_days == config.arxiv_lookback_days
        assert collector.max_results == config.arxiv_max_results
