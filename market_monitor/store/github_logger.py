"""GitHub logger - JSONL storage for GitHub signals."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import Config
from ..collectors.github_radar import GitHubSignal


class GitHubLogger:
    """Log GitHub signals to JSONL file."""

    def __init__(self, config: Config):
        self.config = config
        self.signals_path = config.github_signals_jsonl
        self.baseline_path = config.github_baseline_json

    def log(self, signal: GitHubSignal) -> bool:
        """Log a GitHub signal to JSONL.

        Args:
            signal: GitHubSignal to log

        Returns:
            True if logged successfully
        """
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "repo": signal.repo,
            "stars": signal.stars,
            "delta_stars_7d": signal.delta_stars_7d,
            "velocity_pct": signal.velocity_pct,
            "flagged": signal.flagged,
            "url": signal.url,
            "description": signal.description,
            "logged_at": now,
            "digest_sent": False,
        }

        return self._append_record(record)

    def log_batch(self, signals: list[GitHubSignal]) -> int:
        """Log multiple signals.

        Args:
            signals: List of signals to log

        Returns:
            Number of items successfully logged
        """
        count = 0
        for signal in signals:
            if self.log(signal):
                count += 1
        return count

    def log_flagged(self, signals: list[GitHubSignal]) -> int:
        """Log only flagged signals.

        Args:
            signals: List of signals (only flagged will be logged)

        Returns:
            Number of items logged
        """
        flagged = [s for s in signals if s.flagged]
        return self.log_batch(flagged)

    def mark_sent(self, repos: list[str]) -> int:
        """Mark signals as sent in digest.

        Args:
            repos: List of repo names to mark

        Returns:
            Number of records updated
        """
        if not self.signals_path.exists():
            return 0

        records = []
        with open(self.signals_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        count = 0
        repo_set = set(repos)
        for record in records:
            if record.get("repo") in repo_set and not record.get("digest_sent"):
                record["digest_sent"] = True
                count += 1

        self.signals_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.signals_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        return count

    def get_unsent_flagged(self) -> list[dict]:
        """Get flagged signals not yet sent in digest.

        Returns:
            List of signal records
        """
        if not self.signals_path.exists():
            return []

        unsent = []
        with open(self.signals_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if record.get("flagged") and not record.get("digest_sent", False):
                            unsent.append(record)
                    except json.JSONDecodeError:
                        continue

        return unsent

    def update_baseline(self, signals: list[GitHubSignal]) -> None:
        """Update baseline with current star counts.

        Args:
            signals: Current signals to use for baseline
        """
        baseline = {s.repo: s.stars for s in signals}

        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.baseline_path, "w") as f:
            json.dump(baseline, f, indent=2)

    def _append_record(self, record: dict) -> bool:
        """Append a record to the JSONL file."""
        try:
            self.signals_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.signals_path, "a") as f:
                f.write(json.dumps(record) + "\n")
            return True
        except Exception as e:
            print(f"[GitHubLogger] Error writing: {e}")
            return False
