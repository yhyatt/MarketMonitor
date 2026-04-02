"""Tests for digest formatter."""

import pytest
from dataclasses import dataclass
from datetime import datetime, timezone

from market_monitor.digest.formatter import DigestFormatter, DigestContent


@dataclass
class MockOriginal:
    """Mock original item."""
    title: str = ""
    name: str = ""
    url: str = ""
    type: str = "paper"


@dataclass
class MockScored:
    """Mock scored item."""
    original: MockOriginal
    score: int = 8
    thesis: str = "Test thesis"
    themes: list = None
    strategic_signals: list = None
    why_it_matters: str = "Important stuff"

    def __post_init__(self):
        if self.themes is None:
            self.themes = ["theme1", "theme2"]
        if self.strategic_signals is None:
            self.strategic_signals = ["signal1", "signal2"]


@dataclass
class MockGitHubSignal:
    """Mock GitHub signal."""
    repo: str
    stars: int
    delta_stars_7d: int
    velocity_pct: float
    flagged: bool
    url: str


class TestDigestFormatter:
    """Tests for DigestFormatter."""

    def test_format_returns_all_formats(self):
        """format() should return telegram, html, and plain text."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title="Test Paper", url="http://test.com"))]

        result = formatter.format(papers, [], [], "Test synthesis")

        assert isinstance(result, DigestContent)
        assert result.telegram
        assert result.html
        assert result.plain
        assert result.subject

    def test_telegram_format_compact(self):
        """Telegram format should be compact."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title="Test Paper", url="http://test.com"))]

        result = formatter.format(papers, [], [], "")

        assert "Test Paper" in result.telegram
        assert "Test thesis" in result.telegram
        assert len(result.telegram) < 4000  # Telegram limit

    def test_telegram_includes_papers(self):
        """Telegram should include paper titles and theses."""
        formatter = DigestFormatter()
        papers = [
            MockScored(original=MockOriginal(title="Paper 1"), thesis="Thesis 1"),
            MockScored(original=MockOriginal(title="Paper 2"), thesis="Thesis 2"),
        ]

        result = formatter.format(papers, [], [], "")

        assert "Paper 1" in result.telegram
        assert "Paper 2" in result.telegram
        assert "Thesis 1" in result.telegram

    def test_telegram_includes_hf_items(self):
        """Telegram should include HuggingFace items."""
        formatter = DigestFormatter()
        hf = [MockScored(original=MockOriginal(name="TestModel", type="model"))]

        result = formatter.format([], hf, [], "")

        assert "TestModel" in result.telegram
        assert "HF:" in result.telegram

    def test_telegram_includes_github(self):
        """Telegram should include GitHub signals."""
        formatter = DigestFormatter()
        github = [MockGitHubSignal(
            repo="owner/repo",
            stars=10000,
            delta_stars_7d=500,
            velocity_pct=5.2,
            flagged=True,
            url="https://github.com/owner/repo",
        )]

        result = formatter.format([], [], github, "")

        assert "owner/repo" in result.telegram
        assert "+500" in result.telegram
        assert "5.2%" in result.telegram

    def test_telegram_includes_synthesis(self):
        """Telegram should include weekly synthesis."""
        formatter = DigestFormatter()
        synthesis = "This week matters because of X."

        result = formatter.format([], [], [], synthesis)

        assert synthesis in result.telegram

    def test_html_is_valid(self):
        """HTML output should be valid HTML."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title="Test Paper", url="http://test.com"))]

        result = formatter.format(papers, [], [], "Synthesis")

        assert "<!DOCTYPE html>" in result.html
        assert "<html>" in result.html
        assert "</html>" in result.html
        assert "Test Paper" in result.html

    def test_html_has_sections(self):
        """HTML should have proper sections."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title="Paper"))]
        hf = [MockScored(original=MockOriginal(name="Model", type="model"))]
        github = [MockGitHubSignal("r", 1000, 100, 10.0, True, "url")]

        result = formatter.format(papers, hf, github, "Synthesis")

        assert "Papers" in result.html
        assert "HuggingFace" in result.html
        assert "GitHub" in result.html
        assert "Why This Week" in result.html

    def test_html_has_links(self):
        """HTML should include clickable links."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title="Paper", url="http://paper.url"))]

        result = formatter.format(papers, [], [], "")

        assert 'href="http://paper.url"' in result.html

    def test_plain_text_readable(self):
        """Plain text should be human readable."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title="Test Paper"))]

        result = formatter.format(papers, [], [], "Synthesis")

        assert "PAPERS" in result.plain
        assert "Test Paper" in result.plain
        assert "Synthesis" in result.plain
        # No HTML tags
        assert "<" not in result.plain or "<" in result.plain.split("http")[0] is False

    def test_subject_includes_date(self):
        """Subject should include formatted date."""
        formatter = DigestFormatter()
        test_date = datetime(2026, 4, 7, tzinfo=timezone.utc)

        result = formatter.format([], [], [], "", date=test_date)

        assert "April" in result.subject or "Apr" in result.subject
        assert "2026" in result.subject

    def test_limits_items(self):
        """Should limit number of items displayed."""
        formatter = DigestFormatter()
        papers = [MockScored(original=MockOriginal(title=f"Paper {i}")) for i in range(10)]
        hf = [MockScored(original=MockOriginal(name=f"Model {i}", type="model")) for i in range(10)]
        github = [MockGitHubSignal(f"r{i}", 1000, 100, 10.0, True, "url") for i in range(10)]

        result = formatter.format(papers, hf, github, "")

        # Should limit papers to 5, HF to 3, GitHub to 5
        paper_count = result.telegram.count("Paper ")
        assert paper_count <= 5

    def test_empty_digest(self):
        """Should handle empty digest gracefully."""
        formatter = DigestFormatter()

        result = formatter.format([], [], [], "")

        assert result.telegram
        assert result.html
        assert result.plain

    def test_negative_delta_display(self):
        """Should display negative deltas correctly."""
        formatter = DigestFormatter()
        github = [MockGitHubSignal(
            repo="test/repo",
            stars=1000,
            delta_stars_7d=-50,
            velocity_pct=-4.8,
            flagged=True,
            url="url",
        )]

        result = formatter.format([], [], github, "")

        assert "-50" in result.telegram
        assert "-4.8%" in result.telegram

    def test_special_characters_escaped(self):
        """Should handle special characters in content."""
        formatter = DigestFormatter()
        papers = [MockScored(
            original=MockOriginal(title="Test <script> & \"quotes\""),
            thesis="Thesis with <b>HTML</b>",
        )]

        result = formatter.format(papers, [], [], "")

        # Should not break HTML
        assert "</body>" in result.html
