"""Structured JSON logging for market-monitor."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class StructuredLogger:
    """Write structured JSON logs to /tmp/market-monitor-YYYY-MM-DD.log."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path("/tmp")
        self._file: Optional[Any] = None
        self._date: str = ""
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Open today's log file if not already open."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._date or self._file is None:
            if self._file:
                self._file.close()
            self._date = today
            log_path = self.log_dir / f"market-monitor-{today}.log"
            self._file = open(log_path, "a", buffering=1)

    def _write(self, record: dict) -> None:
        """Write a JSON line to the log file."""
        self._ensure_file()
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def log_collector_start(self, name: str) -> None:
        """Log collector start."""
        self._write({
            "event": "collector_start",
            "collector": name,
        })

    def log_collector_end(self, name: str, items_found: int, status: str = "ok", error: str = "", latency_ms: int = 0) -> None:
        """Log collector end."""
        self._write({
            "event": "collector_end",
            "collector": name,
            "items_found": items_found,
            "status": status,
            "error": error,
            "latency_ms": latency_ms,
        })

    def log_scoring_start(self, item_count: int) -> None:
        """Log scoring batch start."""
        self._write({
            "event": "scoring_start",
            "item_count": item_count,
        })

    def log_scoring_end(self, items_scored: int, items_passed: int, latency_ms: int = 0) -> None:
        """Log scoring batch end."""
        self._write({
            "event": "scoring_end",
            "items_scored": items_scored,
            "items_passed": items_passed,
            "latency_ms": latency_ms,
        })

    def log_delivery(self, channel: str, status: str, error: str = "") -> None:
        """Log delivery attempt."""
        self._write({
            "event": "delivery",
            "channel": channel,
            "status": status,
            "error": error,
        })

    def log_pipeline_start(self, command: str) -> None:
        """Log pipeline start."""
        self._write({
            "event": "pipeline_start",
            "command": command,
        })

    def log_pipeline_end(self, command: str, status: str, error: str = "") -> None:
        """Log pipeline end."""
        self._write({
            "event": "pipeline_end",
            "command": command,
            "status": status,
            "error": error,
        })

    def log_error(self, component: str, error: str, details: Optional[dict] = None) -> None:
        """Log an error."""
        record = {
            "event": "error",
            "component": component,
            "error": error,
        }
        if details:
            record["details"] = details
        self._write(record)

    def close(self) -> None:
        """Close the log file."""
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_logger() -> StructuredLogger:
    """Get the default structured logger."""
    return StructuredLogger()
