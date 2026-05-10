"""AI/TLDR store - persist and retrieve AI/TLDR items."""

import json
from pathlib import Path
from ..config import Config


class AITLDRLogger:
    """Log AI/TLDR items to JSONL for later digest."""

    def __init__(self, config: Config):
        self.path = config.memory_dir / "aitldr_items.jsonl"

    def log_batch(self, items: list) -> int:
        """Log a batch of AITLDRItem objects. Returns count logged."""
        if not items:
            return 0

        existing = self._load_existing_ids()
        logged = 0

        with open(self.path, "a") as f:
            for item in items:
                if item.id in existing:
                    continue
                record = {
                    "id": item.id,
                    "title": item.title,
                    "org": item.org,
                    "date": item.date,
                    "url": item.url,
                    "summary": item.summary,
                    "categories": item.categories,
                    "tags": item.tags,
                    "importance": item.importance,
                    "digest_sent": False,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing.add(item.id)
                logged += 1

        return logged

    def get_unsent(self) -> list[dict]:
        """Get items not yet included in a digest."""
        if not self.path.exists():
            return []

        items = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if not record.get("digest_sent", False):
                    items.append(record)

        # Sort by date descending
        items.sort(key=lambda x: x.get("date", ""), reverse=True)
        return items

    def mark_sent(self, ids: list[str]) -> int:
        """Mark items as sent by their IDs."""
        if not self.path.exists() or not ids:
            return 0

        id_set = set(ids)
        lines = []
        marked = 0

        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("id") in id_set and not record.get("digest_sent", False):
                    record["digest_sent"] = True
                    marked += 1
                lines.append(json.dumps(record, ensure_ascii=False))

        with open(self.path, "w") as f:
            for line in lines:
                f.write(line + "\n")

        return marked

    def _load_existing_ids(self) -> set[str]:
        """Load all existing item IDs to prevent duplicates."""
        if not self.path.exists():
            return set()

        ids = set()
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ids.add(record.get("id", ""))
                except json.JSONDecodeError:
                    pass
        return ids
