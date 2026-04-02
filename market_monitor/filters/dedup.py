"""Deduplication filter - prevent duplicate entries across store files."""

import json
from pathlib import Path
from typing import Any, Optional, Set

from ..config import Config


class Deduplicator:
    """Deduplicator against existing JSONL store files."""

    def __init__(self, config: Config):
        self.config = config
        self._existing_ids: Optional[Set[str]] = None

    def load_existing_ids(self) -> Set[str]:
        """Load all existing IDs from store JSONL files."""
        if self._existing_ids is not None:
            return self._existing_ids

        ids = set()

        # Load from papers.jsonl
        ids.update(self._load_ids_from_jsonl(
            self.config.papers_jsonl,
            id_fields=["arxiv_id", "id"],
        ))

        # Load from hf_releases.jsonl
        ids.update(self._load_ids_from_jsonl(
            self.config.hf_releases_jsonl,
            id_fields=["id"],
        ))

        # Load from github_signals.jsonl
        ids.update(self._load_ids_from_jsonl(
            self.config.github_signals_jsonl,
            id_fields=["repo"],
        ))

        self._existing_ids = ids
        return ids

    def _load_ids_from_jsonl(self, path: Path, id_fields: list[str]) -> Set[str]:
        """Load IDs from a JSONL file."""
        ids = set()

        if not path.exists():
            return ids

        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        for field in id_fields:
                            if field in record:
                                ids.add(str(record[field]))
                                break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[Dedup] Error loading {path}: {e}")

        return ids

    def filter(self, items: list[Any]) -> list[Any]:
        """Filter out items that already exist in stores.

        Also deduplicates within the same batch.

        Args:
            items: List of items with id, arxiv_id, or repo attribute

        Returns:
            List of unique, not-yet-logged items
        """
        existing_ids = self.load_existing_ids()
        seen_in_batch: Set[str] = set()
        filtered = []

        for item in items:
            item_id = self._get_item_id(item)
            if not item_id:
                continue

            # Skip if already exists in store
            if item_id in existing_ids:
                continue

            # Skip if already seen in this batch
            if item_id in seen_in_batch:
                continue

            seen_in_batch.add(item_id)
            filtered.append(item)

        return filtered

    def _get_item_id(self, item: Any) -> Optional[str]:
        """Extract unique ID from item."""
        # Try different ID fields
        for field in ["arxiv_id", "id", "repo", "name"]:
            value = getattr(item, field, None)
            if value:
                return str(value)

        # Try dict access
        if isinstance(item, dict):
            for field in ["arxiv_id", "id", "repo", "name"]:
                if field in item:
                    return str(item[field])

        return None

    def is_duplicate(self, item: Any) -> bool:
        """Check if a single item is a duplicate."""
        existing_ids = self.load_existing_ids()
        item_id = self._get_item_id(item)
        return item_id in existing_ids if item_id else False

    def refresh(self) -> None:
        """Clear cached IDs to force reload."""
        self._existing_ids = None
