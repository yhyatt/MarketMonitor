"""AlphaSignal collector - parse AlphaSignal emails from Gmail."""

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .base import BaseCollector
from ..config import Config


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
    """Collector for AlphaSignal email digests via gog gmail."""

    GMAIL_ACCOUNT = "hyatt.yonatan@gmail.com"
    # Primary: label-based (Gmail label "Digest_sources" applied to AlphaSignal emails)
    # Fallback: sender-based search
    SEARCH_QUERY = "label:Digest_sources"
    SEARCH_QUERY_FALLBACK = "from:alphasignal"
    LIMIT = 10

    def __init__(self, config: Config):
        super().__init__(config)
        self.gog_password = config.gog_keyring_password

    @property
    def name(self) -> str:
        return "AlphaSignal"

    def collect(self) -> list[AlphaItem]:
        """Fetch and parse AlphaSignal emails from Gmail."""
        if not self.gog_password:
            print("[AlphaSignal] Warning: GOG_KEYRING_PASSWORD not set, skipping")
            return []

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

    def _search_emails(self, query: str) -> list[str]:
        """Search for AlphaSignal emails in Gmail."""
        cmd = [
            "gog", "gmail", "search", query,
            "--account", self.GMAIL_ACCOUNT,
            "--limit", str(self.LIMIT),
        ]

        env = {"GOG_KEYRING_PASSWORD": self.gog_password}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env={**subprocess.os.environ, **env},
            )

            if result.returncode != 0:
                print(f"[AlphaSignal] gog search failed: {result.stderr}")
                return []

            # Parse email IDs from output (one per line or JSON)
            output = result.stdout.strip()
            if not output:
                return []

            # Try JSON parse first
            try:
                data = json.loads(output)
                if isinstance(data, list):
                    return [str(item.get("id", item)) for item in data if item]
            except json.JSONDecodeError:
                pass

            # Fall back to line-based parsing
            return [line.strip() for line in output.splitlines() if line.strip()]

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
        cmd = [
            "gog", "gmail", "read", email_id,
            "--account", self.GMAIL_ACCOUNT,
        ]

        env = {"GOG_KEYRING_PASSWORD": self.gog_password}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                env={**subprocess.os.environ, **env},
            )

            if result.returncode != 0:
                return []

            return self._extract_items(result.stdout)

        except Exception as e:
            print(f"[AlphaSignal] Error reading email {email_id}: {e}")
            return []

    def _extract_items(self, email_body: str) -> list[AlphaItem]:
        """Extract paper titles, model names, and highlights from email body."""
        items = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Extract section headers and content
        # AlphaSignal typically has sections like "Papers", "Models", "News"

        # Pattern for paper titles (often have arxiv links or numbered lists)
        paper_patterns = [
            r"(?:^|\n)(?:\d+[\.\)]\s*)?([A-Z][^.!?\n]{20,100})\s*(?:\n|$)",
            r"(?:arxiv\.org/abs/\S+)\s*[-:]?\s*([^\n]+)",
        ]

        # Pattern for URLs
        url_pattern = r"(https?://[^\s<>\"]+)"

        # Split into sections and extract highlights
        lines = email_body.split("\n")
        current_section = "general"
        current_title = None
        current_url = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for section headers
            if re.match(r"^(?:Papers?|Research|Models?|News|Highlights?):?\s*$", line, re.I):
                current_section = line.lower().split(":")[0].strip()
                continue

            # Extract URLs
            url_match = re.search(url_pattern, line)
            if url_match:
                current_url = url_match.group(1)

            # Look for titles (capitalized, longer text)
            if len(line) > 30 and line[0].isupper():
                # Skip if it looks like a paragraph (too long)
                if len(line) > 200:
                    continue

                # This might be a title
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

                    # Limit items per email
                    if len(items) >= 10:
                        break

        return items
