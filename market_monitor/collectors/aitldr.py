"""AI/TLDR collector - scrape weekly AI release digest from ai-tldr.blackpc-me.workers.dev."""

import re
import subprocess
from dataclasses import dataclass, field
from .base import BaseCollector
from ..config import Config

AITLDR_URL = "https://ai-tldr.blackpc-me.workers.dev/"
JS_BUNDLE_PATTERN = re.compile(r'/assets/index-[A-Za-z0-9_-]+\.js')


@dataclass
class AITLDRItem:
    """Represents an item from the AI/TLDR weekly digest."""

    id: str
    title: str
    org: str
    date: str  # YYYY-MM-DD
    url: str
    summary: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    importance: str = ""

    @property
    def full_text(self) -> str:
        return f"{self.title} {self.summary} {' '.join(self.tags)}"


class AITLDRCollector(BaseCollector):
    """Collector for AI/TLDR weekly AI release digest.

    Scrapes the React SPA's JS bundle to extract structured item data.
    The site is a Cloudflare Workers deployment with data baked into
    the JS bundle using backtick template literals.
    """

    def __init__(self, config: Config):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "AI/TLDR"

    def collect(self) -> list[AITLDRItem]:
        """Fetch and parse AI/TLDR items from the JS bundle."""
        html = self._fetch(AITLDR_URL)
        if not html:
            print("[AI/TLDR] Failed to fetch page")
            return []

        match = JS_BUNDLE_PATTERN.search(html)
        if not match:
            print("[AI/TLDR] Could not find JS bundle URL in page")
            return []

        bundle_url = f"https://ai-tldr.blackpc-me.workers.dev{match.group(0)}"
        print(f"[AI/TLDR] Found bundle: {bundle_url}")

        js_content = self._fetch(bundle_url)
        if not js_content:
            print("[AI/TLDR] Failed to fetch JS bundle")
            return []

        items = self._parse_items(js_content)
        print(f"[AI/TLDR] Extracted {len(items)} items")
        return items

    def _fetch(self, url: str) -> str:
        """Fetch URL content using curl."""
        try:
            result = subprocess.run(
                ["curl", "-sL", "--max-time", "30", url],
                capture_output=True, text=True, timeout=35,
            )
            if result.returncode != 0:
                print(f"[AI/TLDR] curl error: {result.stderr[:200]}")
                return ""
            return result.stdout
        except subprocess.TimeoutExpired:
            print("[AI/TLDR] Fetch timed out")
            return ""
        except FileNotFoundError:
            print("[AI/TLDR] curl not found")
            return ""

    def _parse_items(self, js_content: str) -> list[AITLDRItem]:
        """Extract structured item data from JS bundle.

        AI/TLDR uses backtick template literals for string values.
        Items live in an `items:[{...},{...}]` array.
        """
        # Find the items array
        items_match = re.search(r'items:\[', js_content)
        if not items_match:
            print("[AI/TLDR] Could not find items array in JS bundle")
            return []

        # Extract items array content by matching brackets
        items_start = items_match.end()
        depth = 1
        pos = items_start
        while pos < len(js_content) and depth > 0:
            if js_content[pos] == '[':
                depth += 1
            elif js_content[pos] == ']':
                depth -= 1
            pos += 1
        items_str = js_content[items_start:pos - 1]

        # Split into individual item objects by finding {id:` occurrences
        seen_ids = set()
        items = []

        item_starts = [m.start() for m in re.finditer(r'\{id:`', items_str)]

        for start in item_starts:
            # Find matching closing brace
            brace_depth = 0
            end = start
            while end < len(items_str):
                if items_str[end] == '{':
                    brace_depth += 1
                elif items_str[end] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        break
                end += 1

            item_text = items_str[start:end + 1]

            def extract(field_name: str) -> str:
                m = re.search(rf'{field_name}:`([^`]*)`', item_text)
                return m.group(1) if m else ""

            def extract_array(field_name: str) -> list[str]:
                m = re.search(rf'{field_name}:\[([^\]]*)\]', item_text)
                if not m:
                    return []
                return re.findall(r'`([^`]*)`', m.group(1))

            item_id = extract("id")
            if not item_id or len(item_id) < 3 or item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            title = extract("title")
            date = extract("date")

            if not title or not date:
                continue

            items.append(AITLDRItem(
                id=item_id,
                title=title,
                org=extract("org"),
                date=date,
                url=extract("url"),
                summary=extract("summary"),
                categories=extract_array("categories"),
                tags=extract_array("tags"),
                importance=extract("importance"),
            ))

        items.sort(key=lambda x: x.date, reverse=True)
        return items
