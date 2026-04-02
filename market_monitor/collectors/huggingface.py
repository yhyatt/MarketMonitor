"""HuggingFace collector - daily papers and trending models."""

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from .base import BaseCollector
from ..config import Config


@dataclass
class HFItem:
    """Represents an item from HuggingFace (paper or model)."""

    id: str
    name: str
    type: Literal["paper", "model"]
    description: str
    likes: int
    downloads: int
    date: str  # YYYY-MM-DD
    url: str

    @property
    def full_text(self) -> str:
        """Combined name and description for filtering."""
        return f"{self.name} {self.description}"


class HuggingFaceCollector(BaseCollector):
    """Collector for HuggingFace daily papers and trending models."""

    DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
    TRENDING_MODELS_URL = "https://huggingface.co/api/models"

    # Patterns to filter out non-foundation models
    SKIP_MODEL_PATTERNS = [
        r"(?i)lora",
        r"(?i)gguf",
        r"(?i)gptq",
        r"(?i)awq",
        r"(?i)quantized?",
        r"(?i)fine[-_]?tune",
        r"(?i)finetune",
        r"(?i)-ft\b",
        r"(?i)adapter",
        r"(?i)merged",
    ]

    def __init__(self, config: Config):
        super().__init__(config)
        self.lookback_days = config.arxiv_lookback_days
        self.trending_limit = config.hf_trending_limit

    @property
    def name(self) -> str:
        return "HuggingFace"

    def collect(self) -> list[HFItem]:
        """Collect daily papers and trending models."""
        items = []
        items.extend(self._collect_daily_papers())
        items.extend(self._collect_trending_models())
        return items

    def _collect_daily_papers(self) -> list[HFItem]:
        """Fetch daily papers for the last N days."""
        papers = []
        today = datetime.now(timezone.utc).date()

        for days_ago in range(self.lookback_days):
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            url = f"{self.DAILY_PAPERS_URL}?date={date_str}"

            try:
                with urllib.request.urlopen(url, timeout=15) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except Exception as e:
                print(f"[HuggingFace] Error fetching papers for {date_str}: {e}")
                continue

            for item in data if isinstance(data, list) else []:
                paper = self._parse_daily_paper(item, date_str)
                if paper:
                    papers.append(paper)

        return papers

    def _parse_daily_paper(self, item: dict, date_str: str) -> Optional[HFItem]:
        """Parse a daily paper item."""
        try:
            paper_info = item.get("paper", {})
            paper_id = paper_info.get("id", "")
            title = paper_info.get("title", "")
            summary = paper_info.get("summary", "")

            if not paper_id or not title:
                return None

            return HFItem(
                id=paper_id,
                name=title,
                type="paper",
                description=summary[:500] if summary else "",
                likes=item.get("numLikes", 0) or paper_info.get("upvotes", 0),
                downloads=0,
                date=date_str,
                url=f"https://huggingface.co/papers/{paper_id}",
            )
        except Exception:
            return None

    def _collect_trending_models(self) -> list[HFItem]:
        """Fetch trending models, filtering out LoRA/GGUF/quantized variants."""
        # sort=trending is broken on HF API (returns 400) — use likes7d (7-day likes) instead
        # which is a strong proxy for trending momentum
        url = f"{self.TRENDING_MODELS_URL}?sort=likes7d&direction=-1&limit={self.trending_limit}"

        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"[HuggingFace] Error fetching trending models: {e}")
            return []

        models = []
        for item in data if isinstance(data, list) else []:
            model = self._parse_model(item)
            if model and not self._should_skip_model(model.id):
                models.append(model)

        return models

    def _parse_model(self, item: dict) -> Optional[HFItem]:
        """Parse a model item."""
        try:
            model_id = item.get("modelId", "") or item.get("id", "")
            if not model_id:
                return None

            # Extract name (last part of modelId)
            name = model_id.split("/")[-1] if "/" in model_id else model_id

            # Get description from tags or pipeline_tag
            tags = item.get("tags", [])
            pipeline_tag = item.get("pipeline_tag", "")
            description = pipeline_tag if pipeline_tag else ", ".join(tags[:5])

            # Parse date
            created_at = item.get("createdAt", "") or item.get("lastModified", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            else:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            return HFItem(
                id=model_id,
                name=name,
                type="model",
                description=description,
                likes=item.get("likes", 0),
                downloads=item.get("downloads", 0),
                date=date_str,
                url=f"https://huggingface.co/{model_id}",
            )
        except Exception:
            return None

    def _should_skip_model(self, model_id: str) -> bool:
        """Check if model should be skipped (LoRA, GGUF, quantized, etc.)."""
        for pattern in self.SKIP_MODEL_PATTERNS:
            if re.search(pattern, model_id):
                return True
        return False
