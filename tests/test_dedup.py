"""Tests for deduplication filter."""

import json
import pytest
from dataclasses import dataclass

from market_monitor.filters.dedup import Deduplicator


@dataclass
class MockPaper:
    """Mock paper for testing."""
    arxiv_id: str
    title: str = "Test"


@dataclass
class MockHFItem:
    """Mock HuggingFace item for testing."""
    id: str
    name: str = "Test"


@dataclass
class MockGitHubSignal:
    """Mock GitHub signal for testing."""
    repo: str
    stars: int = 100


class TestDeduplicator:
    """Tests for Deduplicator."""

    def test_load_existing_ids_empty(self, config):
        """Should return empty set if no files exist."""
        dedup = Deduplicator(config)
        ids = dedup.load_existing_ids()

        assert ids == set()

    def test_load_existing_ids_from_papers(self, config):
        """Should load IDs from papers.jsonl."""
        # Write test data
        with open(config.papers_jsonl, "w") as f:
            f.write(json.dumps({"arxiv_id": "2603.12345", "title": "Test"}) + "\n")
            f.write(json.dumps({"arxiv_id": "2603.12346", "title": "Test2"}) + "\n")

        dedup = Deduplicator(config)
        ids = dedup.load_existing_ids()

        assert "2603.12345" in ids
        assert "2603.12346" in ids

    def test_load_existing_ids_from_hf(self, config):
        """Should load IDs from hf_releases.jsonl."""
        with open(config.hf_releases_jsonl, "w") as f:
            f.write(json.dumps({"id": "hf-paper-1", "name": "Test"}) + "\n")

        dedup = Deduplicator(config)
        ids = dedup.load_existing_ids()

        assert "hf-paper-1" in ids

    def test_load_existing_ids_from_github(self, config):
        """Should load repo names from github_signals.jsonl."""
        with open(config.github_signals_jsonl, "w") as f:
            f.write(json.dumps({"repo": "owner/repo", "stars": 100}) + "\n")

        dedup = Deduplicator(config)
        ids = dedup.load_existing_ids()

        assert "owner/repo" in ids

    def test_filter_removes_existing(self, config):
        """Should filter out items that already exist."""
        with open(config.papers_jsonl, "w") as f:
            f.write(json.dumps({"arxiv_id": "2603.12345"}) + "\n")

        dedup = Deduplicator(config)
        items = [
            MockPaper("2603.12345"),  # exists
            MockPaper("2603.99999"),  # new
        ]

        filtered = dedup.filter(items)

        assert len(filtered) == 1
        assert filtered[0].arxiv_id == "2603.99999"

    def test_filter_dedupes_batch(self, config):
        """Should deduplicate within same batch."""
        dedup = Deduplicator(config)
        items = [
            MockPaper("2603.11111"),
            MockPaper("2603.11111"),  # duplicate
            MockPaper("2603.22222"),
        ]

        filtered = dedup.filter(items)

        assert len(filtered) == 2

    def test_filter_different_sources(self, config):
        """Should work with different item types."""
        with open(config.papers_jsonl, "w") as f:
            f.write(json.dumps({"arxiv_id": "paper-1"}) + "\n")

        with open(config.hf_releases_jsonl, "w") as f:
            f.write(json.dumps({"id": "hf-1"}) + "\n")

        dedup = Deduplicator(config)

        papers = dedup.filter([MockPaper("paper-1"), MockPaper("paper-2")])
        hf_items = dedup.filter([MockHFItem("hf-1"), MockHFItem("hf-2")])

        assert len(papers) == 1
        assert len(hf_items) == 1

    def test_is_duplicate(self, config):
        """is_duplicate should check single item."""
        with open(config.papers_jsonl, "w") as f:
            f.write(json.dumps({"arxiv_id": "2603.12345"}) + "\n")

        dedup = Deduplicator(config)

        assert dedup.is_duplicate(MockPaper("2603.12345"))
        assert not dedup.is_duplicate(MockPaper("2603.99999"))

    def test_refresh_clears_cache(self, config):
        """refresh should clear cached IDs."""
        dedup = Deduplicator(config)

        # Load IDs
        dedup.load_existing_ids()
        assert dedup._existing_ids is not None

        # Refresh
        dedup.refresh()
        assert dedup._existing_ids is None

    def test_handle_invalid_jsonl(self, config):
        """Should handle malformed JSONL gracefully."""
        with open(config.papers_jsonl, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"arxiv_id": "valid-id"}) + "\n")
            f.write("also not json\n")

        dedup = Deduplicator(config)
        ids = dedup.load_existing_ids()

        assert "valid-id" in ids

    def test_get_item_id_from_dict(self, config):
        """Should extract ID from dict items."""
        dedup = Deduplicator(config)

        assert dedup._get_item_id({"arxiv_id": "test"}) == "test"
        assert dedup._get_item_id({"id": "test"}) == "test"
        assert dedup._get_item_id({"repo": "owner/repo"}) == "owner/repo"
        assert dedup._get_item_id({}) is None

    def test_caches_ids(self, config):
        """Should cache IDs after first load."""
        with open(config.papers_jsonl, "w") as f:
            f.write(json.dumps({"arxiv_id": "test"}) + "\n")

        dedup = Deduplicator(config)

        # First load
        ids1 = dedup.load_existing_ids()

        # Add more data
        with open(config.papers_jsonl, "a") as f:
            f.write(json.dumps({"arxiv_id": "new"}) + "\n")

        # Second load should use cache
        ids2 = dedup.load_existing_ids()

        assert ids1 is ids2  # Same object (cached)
        assert "new" not in ids2  # Cache wasn't updated

    def test_empty_items_filtered(self, config):
        """Items without IDs should be filtered out."""
        dedup = Deduplicator(config)

        @dataclass
        class NoIdItem:
            title: str

        items = [
            NoIdItem("test"),
            MockPaper("valid"),
        ]

        filtered = dedup.filter(items)
        assert len(filtered) == 1
