"""Paper logger - JSONL storage for papers."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import Config
from ..filters.scorer import ScoredItem
from ..collectors.arxiv import ArxivPaper


class PaperLogger:
    """Log papers to JSONL file."""

    def __init__(self, config: Config):
        self.config = config
        self.path = config.papers_jsonl

    def log(self, scored_item: ScoredItem) -> bool:
        """Log a scored paper to JSONL.

        Args:
            scored_item: ScoredItem containing paper and scoring data

        Returns:
            True if logged successfully
        """
        original = scored_item.original
        now = datetime.now(timezone.utc).isoformat()

        # Build record
        record = {
            "arxiv_id": getattr(original, "arxiv_id", "") or getattr(original, "id", ""),
            "title": getattr(original, "title", "") or getattr(original, "name", ""),
            "authors": getattr(original, "authors", []),
            "affiliation": getattr(original, "affiliation", None),
            "date": getattr(original, "date", ""),
            "categories": getattr(original, "categories", []),
            "thesis": scored_item.thesis,
            "themes": scored_item.themes,
            "strategic_signals": scored_item.strategic_signals,
            "why_it_matters": scored_item.why_it_matters,
            "url": getattr(original, "url", ""),
            "score": scored_item.score,
            "source": self._get_source(original),
            "logged_at": now,
            "digest_sent": False,
        }

        return self._append_record(record)

    def log_batch(self, scored_items: list[ScoredItem]) -> int:
        """Log multiple papers.

        Args:
            scored_items: List of scored items to log

        Returns:
            Number of items successfully logged
        """
        count = 0
        for item in scored_items:
            if self.log(item):
                count += 1
        return count

    def mark_sent(self, arxiv_ids: list[str]) -> int:
        """Mark papers as sent in digest.

        Args:
            arxiv_ids: List of arXiv IDs to mark

        Returns:
            Number of records updated
        """
        if not self.path.exists():
            return 0

        # Read all records
        records = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Update matching records
        count = 0
        id_set = set(arxiv_ids)
        for record in records:
            if record.get("arxiv_id") in id_set and not record.get("digest_sent"):
                record["digest_sent"] = True
                count += 1

        # Rewrite file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        return count

    def get_unsent(self) -> list[dict]:
        """Get papers not yet sent in digest.

        Returns:
            List of paper records with digest_sent=False
        """
        if not self.path.exists():
            return []

        unsent = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if not record.get("digest_sent", False):
                            unsent.append(record)
                    except json.JSONDecodeError:
                        continue

        return unsent

    def _append_record(self, record: dict) -> bool:
        """Append a record to the JSONL file."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(record) + "\n")
            return True
        except Exception as e:
            print(f"[PaperLogger] Error writing: {e}")
            return False

    def _get_source(self, original: Any) -> str:
        """Determine source of the paper."""
        if hasattr(original, "arxiv_id"):
            return "arxiv"
        if hasattr(original, "type"):
            return f"huggingface_{original.type}"
        return "unknown"
