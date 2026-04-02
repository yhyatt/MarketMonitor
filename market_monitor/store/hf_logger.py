"""HuggingFace logger - JSONL storage for HF releases."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from ..filters.scorer import ScoredItem
from ..collectors.huggingface import HFItem


class HFLogger:
    """Log HuggingFace items to JSONL file."""

    def __init__(self, config: Config):
        self.config = config
        self.path = config.hf_releases_jsonl

    def log(self, scored_item: ScoredItem) -> bool:
        """Log a scored HF item to JSONL.

        Args:
            scored_item: ScoredItem containing HF item and scoring data

        Returns:
            True if logged successfully
        """
        original = scored_item.original
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "id": getattr(original, "id", ""),
            "name": getattr(original, "name", ""),
            "type": getattr(original, "type", "unknown"),
            "description": getattr(original, "description", ""),
            "likes": getattr(original, "likes", 0),
            "downloads": getattr(original, "downloads", 0),
            "date": getattr(original, "date", ""),
            "url": getattr(original, "url", ""),
            "score": scored_item.score,
            "thesis": scored_item.thesis,
            "themes": scored_item.themes,
            "strategic_signals": scored_item.strategic_signals,
            "why_it_matters": scored_item.why_it_matters,
            "logged_at": now,
            "digest_sent": False,
        }

        return self._append_record(record)

    def log_batch(self, scored_items: list[ScoredItem]) -> int:
        """Log multiple HF items.

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

    def mark_sent(self, ids: list[str]) -> int:
        """Mark items as sent in digest.

        Args:
            ids: List of HF item IDs to mark

        Returns:
            Number of records updated
        """
        if not self.path.exists():
            return 0

        records = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        count = 0
        id_set = set(ids)
        for record in records:
            if record.get("id") in id_set and not record.get("digest_sent"):
                record["digest_sent"] = True
                count += 1

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        return count

    def get_unsent(self) -> list[dict]:
        """Get items not yet sent in digest.

        Returns:
            List of item records with digest_sent=False
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
            print(f"[HFLogger] Error writing: {e}")
            return False
