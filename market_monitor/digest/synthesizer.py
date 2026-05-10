"""Weekly synthesizer - generate "why this week matters" via Moonshot API (Kimi K2.6)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import Config
from ..filters.scorer import ScoredItem
from ..collectors.github_radar import GitHubSignal
from ..llm_client import chat


@dataclass
class WeeklySynthesizer:
    """Generate weekly synthesis paragraph using Moonshot Kimi K2.6."""

    config: Config
    model: str = "kimi-k2-6"

    def synthesize(
        self,
        papers: list[ScoredItem],
        hf_items: list[ScoredItem],
        github_signals: list[GitHubSignal],
    ) -> str:
        """Generate "why this week matters" synthesis.

        Args:
            papers: Scored papers included in digest
            hf_items: Scored HuggingFace items
            github_signals: Flagged GitHub signals

        Returns:
            2-3 sentence synthesis paragraph
        """
        # Build context from all items
        context_parts = []

        for item in papers[:5]:
            title = getattr(item.original, "title", "") or getattr(item.original, "name", "")
            context_parts.append(f"Paper: {title} — {item.thesis}")

        for item in hf_items[:3]:
            name = getattr(item.original, "name", "")
            context_parts.append(f"HuggingFace: {name} — {item.thesis}")

        for signal in github_signals[:5]:
            if signal.flagged:
                context_parts.append(
                    f"GitHub: {signal.repo} gained {signal.delta_stars_7d} stars (+{signal.velocity_pct:.1f}%)"
                )

        if not context_parts:
            return ""

        context = "\n".join(context_parts)

        prompt = f"""You are an AI strategist writing a weekly digest for enterprise AI leadership.

Based on these highlights from this week:

{context}

Write a 2-3 sentence "Why This Week Matters" synthesis that:
1. Identifies the key theme or shift across these signals
2. Connects it to enterprise AI strategy implications
3. Is actionable and forward-looking

Write ONLY the synthesis paragraph, no headers or labels."""

        try:
            content = chat(messages=[{"role": "user", "content": prompt}], max_tokens=200)
            return content.strip()

        except Exception as e:
            print(f"[Synthesizer] API error: {e}")
            return self._fallback_synthesis(papers, hf_items, github_signals)

    def _fallback_synthesis(
        self,
        papers: list[ScoredItem],
        hf_items: list[ScoredItem],
        github_signals: list[GitHubSignal],
    ) -> str:
        """Generate fallback synthesis without LLM."""
        themes = set()
        for item in papers[:5]:
            themes.update(item.themes[:2])
        for item in hf_items[:3]:
            themes.update(item.themes[:2])

        if not themes:
            return ""

        theme_str = ", ".join(sorted(themes)[:3])
        return f"This week's signals center on {theme_str}. Watch for enterprise adoption implications."
