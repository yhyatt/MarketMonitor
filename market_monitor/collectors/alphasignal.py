"""AlphaSignal collector - parse AlphaSignal emails from Gmail via googleworkspace CLI."""

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .base import BaseCollector
from ..config import Config

GWS_BIN = "/usr/local/bin/googleworkspace"


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
    """Collector for AlphaSignal email digests via googleworkspace CLI."""

    GMAIL_ACCOUNT = "me"
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

    def _search_emails(self, query: str) -> list[str]:
        """Search for AlphaSignal emails in Gmail."""
        cmd = [
            GWS_BIN, "gmail", "users", "messages", "list",
            "--params", json.dumps({
                "userId": self.GMAIL_ACCOUNT,
                "q": query,
                "maxResults": self.LIMIT,
            }),
            "--format", "json",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"[AlphaSignal] gws search failed: {result.stderr}")
                return []

            data = json.loads(result.stdout.strip())
            return [msg["id"] for msg in data.get("messages", [])]

        except subprocess.TimeoutExpired:
            print("[AlphaSignal] gws search timed out")
            return []
        except FileNotFoundError:
            print("[AlphaSignal] googleworkspace command not found")
            return []
        except Exception as e:
            print(f"[AlphaSignal] Error searching emails: {e}")
            return []

    def _parse_email(self, email_id: str) -> list[AlphaItem]:
        """Read and parse a single email."""
        cmd = [
            GWS_BIN, "gmail", "users", "messages", "get",
            "--params", json.dumps({
                "userId": self.GMAIL_ACCOUNT,
                "id": email_id,
                "format": "full",
            }),
            "--format", "json",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                return []

            msg_data = json.loads(result.stdout.strip())
            # Extract body from payload
            body = self._extract_body(msg_data.get("payload", {}))
            return self._extract_items(body)

        except Exception as e:
            print(f"[AlphaSignal] Error reading email {email_id}: {e}")
            return []

    def _extract_body(self, payload: dict) -> str:
        """Extract text body from Gmail API payload."""
        import base64

        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
        if payload.get("mimeType", "").startswith("text/html") and payload.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
            return re.sub(r"<[^>]+>", " ", html)
        for part in payload.get("parts", []):
            body = self._extract_body(part)
            if body:
                return body
        return ""

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
