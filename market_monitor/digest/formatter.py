"""Digest formatter - Telegram and HTML email templates."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ..filters.scorer import ScoredItem
from ..collectors.github_radar import GitHubSignal
from ..collectors.huggingface import HFItem


@dataclass
class DigestContent:
    """Formatted digest content for different channels."""

    telegram: str
    html: str
    plain: str
    subject: str


class DigestFormatter:
    """Format digest content for Telegram and email."""

    def format(
        self,
        papers: list[ScoredItem],
        hf_items: list[ScoredItem],
        github_signals: list[GitHubSignal],
        weekly_synthesis: str = "",
        date: Optional[datetime] = None,
    ) -> DigestContent:
        """Format all digest content.

        Args:
            papers: Scored papers to include
            hf_items: Scored HuggingFace items
            github_signals: Flagged GitHub signals
            weekly_synthesis: LLM-generated "why this week matters"
            date: Date for the digest (defaults to today)

        Returns:
            DigestContent with telegram, html, and plain text versions
        """
        if date is None:
            date = datetime.now(timezone.utc)

        date_str = date.strftime("%b %d")
        week_str = date.strftime("Week of %B %d, %Y")

        telegram = self._format_telegram(papers, hf_items, github_signals, weekly_synthesis, date_str)
        html = self._format_html(papers, hf_items, github_signals, weekly_synthesis, week_str)
        plain = self._format_plain(papers, hf_items, github_signals, weekly_synthesis, week_str)
        subject = f"🧠 AI Market Pulse — {week_str}"

        return DigestContent(
            telegram=telegram,
            html=html,
            plain=plain,
            subject=subject,
        )

    def _format_telegram(
        self,
        papers: list[ScoredItem],
        hf_items: list[ScoredItem],
        github_signals: list[GitHubSignal],
        weekly_synthesis: str,
        date_str: str,
    ) -> str:
        """Format compact Telegram message."""
        lines = [f"🧠 AI Market Pulse — {date_str}", ""]

        # Papers
        for item in papers[:5]:
            original = item.original
            title = getattr(original, "title", "") or getattr(original, "name", "")
            url = getattr(original, "url", "")
            signal = item.strategic_signals[0] if item.strategic_signals else ""

            lines.append(f"📄 {title}")
            lines.append(f"   {item.thesis}")
            if url:
                lines.append(f"   {url}")
            if signal:
                lines.append(f"   ⚡ {signal}")
            lines.append("")

        # HuggingFace items
        for item in hf_items[:3]:
            original = item.original
            name = getattr(original, "name", "")
            item_type = getattr(original, "type", "item")
            emoji = "📦" if item_type == "model" else "📑"
            lines.append(f"{emoji} HF: {name} — {item.thesis}")

        if hf_items:
            lines.append("")

        # GitHub signals
        for signal in github_signals[:3]:
            delta_str = f"+{signal.delta_stars_7d}" if signal.delta_stars_7d > 0 else str(signal.delta_stars_7d)
            velocity_str = f"+{signal.velocity_pct:.1f}%" if signal.velocity_pct > 0 else f"{signal.velocity_pct:.1f}%"
            lines.append(f"🚀 GitHub: {signal.repo} {delta_str}★ ({velocity_str} this week)")

        if github_signals:
            lines.append("")

        # Weekly synthesis
        if weekly_synthesis:
            lines.append(weekly_synthesis)

        return "\n".join(lines)

    def _format_html(
        self,
        papers: list[ScoredItem],
        hf_items: list[ScoredItem],
        github_signals: list[GitHubSignal],
        weekly_synthesis: str,
        week_str: str,
    ) -> str:
        """Format rich HTML email with inline CSS."""
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Market Pulse — {week_str}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8f9fa;">
<div style="background-color: #fff; border-radius: 8px; padding: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">

<h1 style="color: #1a1a2e; font-size: 24px; margin-bottom: 24px; border-bottom: 2px solid #6366f1; padding-bottom: 12px;">
🧠 AI Market Pulse — {week_str}
</h1>
"""

        # Papers section
        if papers:
            html += """<h2 style="color: #4f46e5; font-size: 18px; margin-top: 24px;">📄 Papers</h2>"""
            for item in papers[:5]:
                original = item.original
                title = getattr(original, "title", "") or getattr(original, "name", "")
                url = getattr(original, "url", "")
                signals = ", ".join(item.strategic_signals[:2]) if item.strategic_signals else ""

                html += f"""
<div style="margin-bottom: 16px; padding: 12px; background-color: #f8fafc; border-radius: 6px; border-left: 3px solid #6366f1;">
<strong style="color: #1e293b;"><a href="{url}" style="color: #4f46e5; text-decoration: none;">{title}</a></strong>
<p style="margin: 8px 0 4px 0; color: #475569; font-size: 14px;">{item.thesis}</p>
<p style="margin: 4px 0; color: #64748b; font-size: 13px;">⚡ {signals}</p>
</div>
"""

        # HuggingFace section
        if hf_items:
            html += """<h2 style="color: #4f46e5; font-size: 18px; margin-top: 24px;">📦 HuggingFace</h2>"""
            for item in hf_items[:3]:
                original = item.original
                name = getattr(original, "name", "")
                url = getattr(original, "url", "")
                item_type = getattr(original, "type", "item")
                emoji = "📦" if item_type == "model" else "📑"

                html += f"""
<div style="margin-bottom: 12px; padding: 10px; background-color: #fef3c7; border-radius: 6px;">
<strong>{emoji} <a href="{url}" style="color: #d97706; text-decoration: none;">{name}</a></strong>
<span style="color: #78716c; font-size: 14px;"> — {item.thesis}</span>
</div>
"""

        # GitHub section
        if github_signals:
            html += """<h2 style="color: #4f46e5; font-size: 18px; margin-top: 24px;">🚀 GitHub Momentum</h2>"""
            for signal in github_signals[:5]:
                delta_str = f"+{signal.delta_stars_7d}" if signal.delta_stars_7d > 0 else str(signal.delta_stars_7d)
                velocity_str = f"+{signal.velocity_pct:.1f}%" if signal.velocity_pct > 0 else f"{signal.velocity_pct:.1f}%"

                html += f"""
<div style="margin-bottom: 8px; padding: 8px; background-color: #ecfdf5; border-radius: 6px;">
<a href="{signal.url}" style="color: #059669; text-decoration: none; font-weight: 500;">{signal.repo}</a>
<span style="color: #047857;"> {delta_str}★ ({velocity_str} this week)</span>
</div>
"""

        # Weekly synthesis
        if weekly_synthesis:
            html += f"""
<h2 style="color: #4f46e5; font-size: 18px; margin-top: 24px;">💡 Why This Week Matters</h2>
<div style="padding: 16px; background-color: #f0f9ff; border-radius: 8px; border-left: 4px solid #0ea5e9;">
<p style="margin: 0; color: #0c4a6e; font-style: italic;">{weekly_synthesis}</p>
</div>
"""

        html += """
</div>
<p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 16px;">
Generated by market-monitor • <a href="https://github.com/openclaw/openclaw" style="color: #6366f1;">OpenClaw</a>
</p>
</body>
</html>"""

        return html

    def _format_plain(
        self,
        papers: list[ScoredItem],
        hf_items: list[ScoredItem],
        github_signals: list[GitHubSignal],
        weekly_synthesis: str,
        week_str: str,
    ) -> str:
        """Format plain text email."""
        lines = [f"AI Market Pulse — {week_str}", "=" * 40, ""]

        if papers:
            lines.append("PAPERS")
            lines.append("-" * 20)
            for item in papers[:5]:
                original = item.original
                title = getattr(original, "title", "") or getattr(original, "name", "")
                url = getattr(original, "url", "")
                lines.append(f"• {title}")
                lines.append(f"  {item.thesis}")
                if url:
                    lines.append(f"  {url}")
                lines.append("")

        if hf_items:
            lines.append("HUGGINGFACE")
            lines.append("-" * 20)
            for item in hf_items[:3]:
                original = item.original
                name = getattr(original, "name", "")
                lines.append(f"• {name} — {item.thesis}")
            lines.append("")

        if github_signals:
            lines.append("GITHUB MOMENTUM")
            lines.append("-" * 20)
            for signal in github_signals[:5]:
                delta_str = f"+{signal.delta_stars_7d}" if signal.delta_stars_7d > 0 else str(signal.delta_stars_7d)
                lines.append(f"• {signal.repo} {delta_str}★ (+{signal.velocity_pct:.1f}%)")
            lines.append("")

        if weekly_synthesis:
            lines.append("WHY THIS WEEK MATTERS")
            lines.append("-" * 20)
            lines.append(weekly_synthesis)
            lines.append("")

        lines.append("---")
        lines.append("Generated by market-monitor | OpenClaw")

        return "\n".join(lines)
