"""AlphaSignal collector - parse AlphaSignal emails from Gmail via gog CLI."""

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .base import BaseCollector
from ..config import Config

GOG_BIN = "/home/openclaw/.local/bin/gog"
GOG_KEYRING_PASSWORD = "kai-gog-keyring"
DEFAULT_ACCOUNT = "hyatt.yonatan@gmail.com"


@dataclass
class AlphaItem:
    """Represents an item extracted from AlphaSignal email."""

    title: str
    source: str
    summary: str
    date: str  # YYYY-MM-DD
    url: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Combined title and summary for filtering."""
        return f"{self.title} {self.summary}"


class AlphaSignalCollector(BaseCollector):
    """Collector for AlphaSignal email digests via gog CLI."""

    SEARCH_QUERY = "label:Digest_sources"
    SEARCH_QUERY_FALLBACK = "from:alphasignal"
    LIMIT = 10

    def __init__(self, config: Config):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "AlphaSignal"

    def collect(self) -> list[AlphaItem]:
        """Fetch and parse AlphaSignal emails from Gmail."""
        # Try label-based search first, fall back to sender search
        email_ids = self._search_emails(self.SEARCH_QUERY)
        if not email_ids:
            print(f"[AlphaSignal] No emails found with label search, trying sender fallback")
            email_ids = self._search_emails(self.SEARCH_QUERY_FALLBACK)
        if not email_ids:
            print("[AlphaSignal] No emails found")
            return []

        items = []
        for email_id in email_ids[:self.LIMIT]:
            email_items = self._parse_email(email_id)
            items.extend(email_items)

        return items

    def _run_gog(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a gog command with keyring password."""
        cmd = [GOG_BIN] + args
        env = {**os.environ, "GOG_KEYRING_PASSWORD": GOG_KEYRING_PASSWORD}
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)

    def _search_emails(self, query: str) -> list[str]:
        """Search for AlphaSignal emails in Gmail."""
        try:
            result = self._run_gog([
                "gmail", "search", query,
                "-a", DEFAULT_ACCOUNT,
                "-j", "--results-only",
            ])

            if result.returncode != 0:
                print(f"[AlphaSignal] gog search failed: {result.stderr}")
                return []

            data = json.loads(result.stdout.strip())
            # gog returns flat array of threads with 'id' field
            threads = data if isinstance(data, list) else []
            return [msg.get("id", "") for msg in threads if msg.get("id")]

        except subprocess.TimeoutExpired:
            print("[AlphaSignal] gog search timed out")
            return []
        except FileNotFoundError:
            print("[AlphaSignal] gog command not found")
            return []
        except Exception as e:
            print(f"[AlphaSignal] Error searching emails: {e}")
            return []

    def _parse_email(self, email_id: str) -> list[AlphaItem]:
        """Read and parse a single email."""
        try:
            result = self._run_gog([
                "gmail", "get", email_id,
                "-a", DEFAULT_ACCOUNT,
                "-j",
            ])

            if result.returncode != 0:
                return []

            msg_data = json.loads(result.stdout.strip())
            # gog returns {body, headers, message, snippet}
            body = msg_data.get("body", "") or msg_data.get("snippet", "")
            return self._extract_items(body)

        except Exception as e:
            print(f"[AlphaSignal] Error reading email {email_id}: {e}")
            return []

    def _extract_items(self, email_body: str) -> list[AlphaItem]:
        """Extract paper titles, model names, and highlights from email body."""
        items = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        url_pattern = r"(https?://[^\s<>\"]+)"

        lines = email_body.split("\n")
        current_section = "general"
        current_url = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r"^(?:Papers?|Research|Models?|News|Highlights?):?\s*$", line, re.I):
                current_section = line.lower().split(":")[0].strip()
                continue

            url_match = re.search(url_pattern, line)
            if url_match:
                current_url = url_match.group(1)

            if len(line) > 30 and line[0].isupper():
                if len(line) > 200:
                    continue

                title = re.sub(r"\s+", " ", line)
                title = re.sub(url_pattern, "", title).strip()

                if len(title) > 20:
                    items.append(AlphaItem(
                        title=title[:150],
                        source="AlphaSignal",
                        summary=f"From {current_section} section",
                        date=today,
                        url=current_url,
                    ))
                    current_url = None

                    if len(items) >= 10:
                        break

        return items
