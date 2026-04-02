"""arXiv collector - fetches AI papers from arXiv API."""

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .base import BaseCollector
from ..config import Config


@dataclass
class ArxivPaper:
    """Represents an arXiv paper."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    date: str  # YYYY-MM-DD
    url: str
    affiliation: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Combined title and abstract for filtering."""
        return f"{self.title} {self.abstract}"


class ArxivCollector(BaseCollector):
    """Collector for arXiv papers in AI-related categories."""

    ARXIV_API_URL = "http://export.arxiv.org/api/query"
    CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.MA"]
    NAMESPACE = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    def __init__(self, config: Config):
        super().__init__(config)
        self.lookback_days = config.arxiv_lookback_days
        self.max_results = config.arxiv_max_results

    @property
    def name(self) -> str:
        return "arXiv"

    def collect(self) -> list[ArxivPaper]:
        """Fetch recent papers from arXiv API."""
        query = "+OR+".join(f"cat:{cat}" for cat in self.CATEGORIES)
        url = (
            f"{self.ARXIV_API_URL}?search_query={query}"
            f"&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={self.max_results}"
        )

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                xml_data = response.read().decode("utf-8")
        except Exception as e:
            print(f"[arXiv] Error fetching data: {e}")
            return []

        return self._parse_response(xml_data)

    def _parse_response(self, xml_data: str) -> list[ArxivPaper]:
        """Parse Atom XML response into ArxivPaper objects."""
        papers = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            print(f"[arXiv] Error parsing XML: {e}")
            return []

        for entry in root.findall("atom:entry", self.NAMESPACE):
            paper = self._parse_entry(entry, cutoff_date)
            if paper:
                papers.append(paper)

        return papers

    def _parse_entry(self, entry: ET.Element, cutoff_date: datetime) -> Optional[ArxivPaper]:
        """Parse a single entry element."""
        # Extract published date
        published_el = entry.find("atom:published", self.NAMESPACE)
        if published_el is None or not published_el.text:
            return None

        try:
            published_date = datetime.fromisoformat(published_el.text.replace("Z", "+00:00"))
        except ValueError:
            return None

        # Filter by date
        if published_date < cutoff_date:
            return None

        # Extract ID
        id_el = entry.find("atom:id", self.NAMESPACE)
        if id_el is None or not id_el.text:
            return None

        arxiv_id = self._extract_arxiv_id(id_el.text)
        if not arxiv_id:
            return None

        # Extract title (clean whitespace)
        title_el = entry.find("atom:title", self.NAMESPACE)
        title = self._clean_text(title_el.text if title_el is not None else "")
        if not title:
            return None

        # Extract abstract
        summary_el = entry.find("atom:summary", self.NAMESPACE)
        abstract = self._clean_text(summary_el.text if summary_el is not None else "")

        # Extract authors
        authors = []
        for author_el in entry.findall("atom:author", self.NAMESPACE):
            name_el = author_el.find("atom:name", self.NAMESPACE)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # Extract categories
        categories = []
        for cat_el in entry.findall("arxiv:primary_category", self.NAMESPACE):
            term = cat_el.get("term")
            if term:
                categories.append(term)
        for cat_el in entry.findall("atom:category", self.NAMESPACE):
            term = cat_el.get("term")
            if term and term not in categories:
                categories.append(term)

        # Build URL
        url = f"https://arxiv.org/abs/{arxiv_id}"

        return ArxivPaper(
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            abstract=abstract,
            categories=categories,
            date=published_date.strftime("%Y-%m-%d"),
            url=url,
        )

    def _extract_arxiv_id(self, id_url: str) -> Optional[str]:
        """Extract arXiv ID from URL like http://arxiv.org/abs/2301.12345v1."""
        match = re.search(r"arxiv\.org/abs/(\d+\.\d+)", id_url)
        if match:
            return match.group(1)
        return None

    def _clean_text(self, text: str) -> str:
        """Clean whitespace from text."""
        if not text:
            return ""
        # Replace multiple whitespace with single space
        return re.sub(r"\s+", " ", text).strip()
