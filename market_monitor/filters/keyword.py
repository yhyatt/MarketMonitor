"""Keyword filter - stage 1 pre-filtering based on keywords."""

import re
from dataclasses import dataclass
from typing import Any, Protocol


class Filterable(Protocol):
    """Protocol for items that can be filtered."""

    @property
    def full_text(self) -> str:
        """Text to search for keywords."""
        ...


@dataclass
class KeywordFilter:
    """Two-stage keyword filter for AI market intelligence."""

    # Positive keywords - at least 1 must match in title+abstract
    POSITIVE_KEYWORDS: list[str] = None  # type: ignore

    # Negative keywords - 2+ matches = reject
    NEGATIVE_KEYWORDS: list[str] = None  # type: ignore

    # Negative title patterns - 1 match = reject
    NEGATIVE_TITLE_PATTERNS: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.POSITIVE_KEYWORDS is None:
            self.POSITIVE_KEYWORDS = [
                # Agentic AI (high priority)
                "agent",
                "agentic",
                "multi-agent",
                "orchestration",
                "society of thought",
                "reasoning model",
                # Auto-research / autonomous research (high priority)
                "deep research",
                "autonomous research",
                "research agent",
                "auto-research",
                "AI researcher",
                "automated discovery",
                "scientific agent",
                "AI-driven research",
                # OS LLMs and frameworks (high priority)
                "open source model",
                "open-source LLM",
                "LLaMA",
                "Mistral",
                "Gemma",
                "DeepSeek",
                "Qwen",
                "vllm",
                "dspy",
                "DSPy",
                "inference framework",
                "model serving",
                # Paradigm / strategic
                "paradigm",
                "foundation model",
                "large language model",
                "LLM",
                "intelligence explosion",
                "emergent",
                "scaling law",
                # Enterprise / deployment
                "harness",
                "context management",
                "human-AI",
                "enterprise AI",
                "deployment",
                # Governance (medium — scored contextually)
                "alignment",
                "governance",
                "institutional",
                "RLHF",
                # Reasoning
                "chain-of-thought",
                "tool use",
                "function calling",
            ]

        if self.NEGATIVE_KEYWORDS is None:
            self.NEGATIVE_KEYWORDS = [
                "medical imaging",
                "protein folding",
                "climate model",
                "robotics locomotion",
                "speech recognition",
                "object detection",
                "sentiment analysis",
                "geographic NLP",
            ]

        if self.NEGATIVE_TITLE_PATTERNS is None:
            self.NEGATIVE_TITLE_PATTERNS = [
                r"^survey",
                r"benchmark comparison",
                r"dataset for",
            ]

        # Pre-compile patterns for efficiency
        self._positive_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            for kw in self.POSITIVE_KEYWORDS
        ]
        self._negative_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            for kw in self.NEGATIVE_KEYWORDS
        ]
        self._negative_title_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.NEGATIVE_TITLE_PATTERNS
        ]

    def filter(self, items: list[Any]) -> list[Any]:
        """Filter items based on keyword rules.

        Args:
            items: List of items with full_text property and title attribute

        Returns:
            Filtered list of items that pass all criteria
        """
        return [item for item in items if self.passes(item)]

    def passes(self, item: Any) -> bool:
        """Check if a single item passes all filter criteria.

        Args:
            item: Item with full_text property and optional title attribute

        Returns:
            True if item passes all filters
        """
        text = item.full_text if hasattr(item, "full_text") else str(item)
        title = getattr(item, "title", "") or getattr(item, "name", "") or ""

        # Check negative title patterns (1 match = reject)
        for pattern in self._negative_title_patterns:
            if pattern.search(title):
                return False

        # Check negative keywords (2+ matches = reject)
        negative_count = sum(1 for p in self._negative_patterns if p.search(text))
        if negative_count >= 2:
            return False

        # Check positive keywords (at least 1 must match)
        positive_match = any(p.search(text) for p in self._positive_patterns)
        return positive_match

    def count_positive_matches(self, text: str) -> int:
        """Count number of positive keyword matches."""
        return sum(1 for p in self._positive_patterns if p.search(text))

    def count_negative_matches(self, text: str) -> int:
        """Count number of negative keyword matches."""
        return sum(1 for p in self._negative_patterns if p.search(text))

    def get_matched_keywords(self, text: str) -> dict[str, list[str]]:
        """Get lists of matched positive and negative keywords."""
        positive = [
            kw for kw, p in zip(self.POSITIVE_KEYWORDS, self._positive_patterns)
            if p.search(text)
        ]
        negative = [
            kw for kw, p in zip(self.NEGATIVE_KEYWORDS, self._negative_patterns)
            if p.search(text)
        ]
        return {"positive": positive, "negative": negative}
