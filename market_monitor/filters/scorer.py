"""LLM scorer - stage 2 scoring via Anthropic API."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import Config

# Researchers whose work tends to have outsized strategic signal
# These get a +1 score boost to push borderline papers over threshold
HIGH_SIGNAL_RESEARCHERS = [
    # AI labs - leadership/research directors
    "andrej karpathy", "yann lecun", "geoffrey hinton", "yoshua bengio",
    "ilya sutskever", "sam altman", "dario amodei", "demis hassabis",
    "jeff dean", "oriol vinyals", "blaise agüera y arcas", "blaise aguera y arcas",
    # Key researchers with strategic track record
    "omar khattab",       # DSPy, Meta-Harness — systems that move the field
    "chelsea finn",       # Meta-learning, Stanford
    "percy liang",        # HELM, foundation model evaluation
    "christopher manning", # Stanford NLP
    "pieter abbeel",      # Robotics/RL, Covariant
    "chelsea finn",
    "benjamin bratton",   # AI paradigm/governance
    "jason wei",          # Chain-of-thought, Google
    "denny zhou",         # Reasoning, Google
    "noam shazeer",       # Transformer architect
    "quoc le",            # Google Brain
    "luke zettlemoyer",   # Meta AI
    "tim dettmers",       # Quantization, efficient inference
    "tri dao",            # Flash attention
]


@dataclass
class ScoredItem:
    """Item with LLM scoring metadata."""

    original: Any
    score: int
    thesis: str
    themes: list[str]
    strategic_signals: list[str]
    why_it_matters: str

    @property
    def passes_threshold(self) -> bool:
        """Check if score meets inclusion threshold."""
        return self.score >= 7


@dataclass
class LLMScorer:
    """Score items using Anthropic's claude-haiku-4-5 model."""

    config: Config
    model: str = "claude-haiku-4-5"
    max_workers: int = 5
    _client: Any = field(default=None, repr=False)

    def __post_init__(self):
        if not self.config.anthropic_api_token:
            raise ValueError("ANTHROPIC_API_TOKEN is required for LLM scoring")

        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_api_token)
        except ImportError:
            raise ImportError("anthropic package is required: pip install anthropic")

    def score_items(self, items: list[Any]) -> list[ScoredItem]:
        """Score multiple items in parallel.

        Args:
            items: List of items with full_text property

        Returns:
            List of ScoredItem objects, sorted by score descending
        """
        scored = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._score_item, item): item for item in items}

            for future in as_completed(futures):
                item = futures[future]
                try:
                    result = future.result()
                    if result:
                        scored.append(result)
                except Exception as e:
                    print(f"[Scorer] Error scoring item: {e}")

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def filter_by_threshold(
        self,
        items: list[Any],
        threshold: int = 7,
        max_items: int = 5,
    ) -> list[ScoredItem]:
        """Score items and filter by threshold.

        Args:
            items: Items to score
            threshold: Minimum score for inclusion
            max_items: Maximum items to return

        Returns:
            Top scoring items above threshold
        """
        scored = self.score_items(items)
        filtered = [s for s in scored if s.score >= threshold]
        return filtered[:max_items]

    def _has_high_signal_author(self, item: Any) -> bool:
        """Check if any author is on the high-signal researcher list."""
        authors = getattr(item, "authors", []) or []
        author_text = " ".join(authors).lower()
        return any(name in author_text for name in HIGH_SIGNAL_RESEARCHERS)

    def _strategic_check(self, item: Any, scored: "ScoredItem") -> "ScoredItem":
        """For borderline items (score 6-7), do a focused second-pass check.

        Asks a single targeted question: is there a genuine strategic element,
        or is this just technically interesting? Costs ~150 tokens per call.
        Returns the item with score potentially bumped to 7 (include) or dropped to 5 (exclude).
        """
        # item here is the raw original item (not a ScoredItem)
        title_str = getattr(item, "title", "") or getattr(item, "name", "") or "Unknown"
        text = item.full_text if hasattr(item, "full_text") else ""

        prompt = f"""Quick strategic assessment (1 sentence answer + JSON score adjustment).

Paper: {title_str}
Thesis: {scored.thesis}

Is there a concrete strategic implication for enterprise AI adoption, market positioning, or paradigm shift?
- If YES (genuine strategic element): respond with {{"adjust": 1, "reason": "one line"}}
- If NO (just technically interesting, no clear enterprise/market angle): respond with {{"adjust": -1, "reason": "one line"}}
- If UNCERTAIN: respond with {{"adjust": 0, "reason": "one line"}}

JSON only."""

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json_response(response.content[0].text)
            if result and "adjust" in result:
                adj = result["adjust"]
                reason = result.get("reason", "")
                new_score = max(0, min(10, scored.score + adj))
                if adj != 0:
                    print(f"[Scorer] Strategic check: '{title_str[:50]}' {scored.score}→{new_score} ({reason})")
                return ScoredItem(
                    original=scored.original,
                    score=new_score,
                    thesis=scored.thesis,
                    themes=scored.themes,
                    strategic_signals=scored.strategic_signals,
                    why_it_matters=scored.why_it_matters,
                )
        except Exception as e:
            print(f"[Scorer] Strategic check error: {e}")

        return scored

    def _score_item(self, item: Any) -> Optional[ScoredItem]:
        """Score a single item via LLM."""
        text = item.full_text if hasattr(item, "full_text") else str(item)
        title = getattr(item, "title", "") or getattr(item, "name", "") or "Unknown"

        prompt = f"""Analyze this AI research item for strategic relevance to Yonatan Hyatt, AI Strategist at Siemens.

Title: {title}

Content:
{text[:2000]}

## His interest profile (score higher for these):
- HIGH INTEREST: Agentic AI, multi-agent systems, orchestration, AI paradigm shifts, foundation model positioning
- HIGH INTEREST: "Auto-research" — AI systems that autonomously do research, planning, synthesis (e.g., Karpathy-style deep research reports, autonomous agents doing scientific/technical work)
- HIGH INTEREST: Open-source LLMs and frameworks (LLaMA, Mistral, Gemma, vllm, dspy, etc.) — market dynamics, capabilities
- HIGH INTEREST: Human-AI collaboration patterns, centaur workflows, enterprise deployment architecture
- MEDIUM INTEREST: AI governance, alignment, institutional considerations — only surface if major/paradigm-level
- LOW INTEREST: Security vulnerabilities — only score 8+ if it's a truly systemic/novel threat (not incremental attack variants)
- LOW INTEREST: Narrow benchmarks, incremental improvements on existing tasks

## Scoring guide:
- 9-10: Paradigm shift, major lab positioning move, breakthrough in agentic/auto-research/OS models
- 7-8: Clearly relevant advance for enterprise AI strategy or OS ecosystem
- 5-6: Interesting but not immediately strategic
- 0-4: Incremental, niche, or primarily security/benchmark focused

Return JSON only:
{{
  "score": <0-10>,
  "thesis": "<full 1-2 sentence strategic thesis — do NOT truncate>",
  "themes": ["<theme1>", "<theme2>", ...],
  "strategic_signals": ["<signal1>", "<signal2>", "<signal3>"],
  "why_it_matters": "<2-3 sentence explanation specifically for Yonatan's context at Siemens>"
}}"""

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            result = self._parse_json_response(content)

            if result:
                scored = ScoredItem(
                    original=item,
                    score=result.get("score", 0),
                    thesis=result.get("thesis", ""),
                    themes=result.get("themes", []),
                    strategic_signals=result.get("strategic_signals", []),
                    why_it_matters=result.get("why_it_matters", ""),
                )

                # High-signal author boost: +1 for known strategic researchers
                if self._has_high_signal_author(item):
                    old_score = scored.score
                    scored = ScoredItem(
                        original=scored.original,
                        score=min(10, scored.score + 1),
                        thesis=scored.thesis,
                        themes=scored.themes,
                        strategic_signals=scored.strategic_signals,
                        why_it_matters=scored.why_it_matters,
                    )
                    if scored.score != old_score:
                        print(f"[Scorer] Author boost: '{title[:50]}' {old_score}→{scored.score}")

                # Borderline items (6-7): second-pass strategic check (~150 tokens)
                if scored.score in (6, 7):
                    scored = self._strategic_check(item, scored)  # pass raw item

                return scored

        except Exception as e:
            print(f"[Scorer] API error for '{title}': {e}")

        return None

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block
        import re
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try to find JSON in code block
        code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        return None
