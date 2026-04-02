"""GitHub radar - track star velocity for AI repos."""

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import BaseCollector
from ..config import Config


@dataclass
class GitHubSignal:
    """Represents a GitHub repo signal."""

    repo: str
    stars: int
    delta_stars_7d: int
    velocity_pct: float
    flagged: bool
    url: str
    description: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Combined repo and description for filtering."""
        return f"{self.repo} {self.description or ''}"


class GitHubRadar(BaseCollector):
    """Collector for GitHub star velocity signals."""

    GITHUB_API_URL = "https://api.github.com/repos"

    def __init__(self, config: Config):
        super().__init__(config)
        self.tracked_repos = config.github_tracked_repos
        self.velocity_threshold = config.github_velocity_threshold_pct
        self.delta_threshold = config.github_delta_threshold
        self.baseline_path = config.github_baseline_json

    @property
    def name(self) -> str:
        return "GitHub"

    def collect(self) -> list[GitHubSignal]:
        """Fetch current stars and compare against baseline.

        First-run behaviour: baseline doesn't exist yet, so we also fetch
        GitHub Trending (7-day) to surface repos already spiking this week,
        even before our own baseline has accumulated a week of data.
        """
        baseline = self._load_baseline()
        baseline_age_days = self._baseline_age_days(baseline)
        signals = []

        for repo in self.tracked_repos:
            signal = self._fetch_repo_signal(repo, baseline)
            if signal:
                signals.append(signal)

        # Update baseline with current stars + timestamp
        new_baseline = self._load_baseline()
        for s in signals:
            new_baseline[s.repo] = s.stars
        new_baseline["__updated_at__"] = datetime.now(timezone.utc).isoformat()
        self._save_baseline(new_baseline)

        # If baseline is fresh (<2 days old), supplement with GitHub Trending
        if baseline_age_days < 2:
            print(f"[GitHub] Baseline is {baseline_age_days:.1f}d old — supplementing with GitHub Trending")
            trending = self._fetch_github_trending()
            # Add trending repos that aren't already in our tracked list
            for t in trending:
                if not any(s.repo == t.repo for s in signals):
                    signals.append(t)

        return signals

    def _baseline_age_days(self, baseline: dict) -> float:
        """Return age of baseline in days. Returns 999 if no timestamp."""
        ts = baseline.get("__updated_at__")
        if not ts:
            return 999.0
        try:
            updated = datetime.fromisoformat(ts)
            delta = datetime.now(timezone.utc) - updated
            return delta.total_seconds() / 86400
        except Exception:
            return 999.0

    # AI-relevant keywords for trending filter
    AI_KEYWORDS = [
        "llm", "ai", "agent", "gpt", "model", "transformer", "langchain",
        "llama", "mistral", "inference", "rag", "embedding", "vector",
        "claude", "openai", "anthropic", "diffusion", "research", "scientist",
        "reasoning", "copilot", "assistant", "chatbot", "deepseek", "gemma",
        "vllm", "dspy", "autogen", "workflow", "agentic",
    ]

    def _fetch_github_trending(self) -> list[GitHubSignal]:
        """Scrape GitHub Trending (weekly) for AI-relevant repos.

        Uses direct HTML scraping of github.com/trending since unofficial
        JSON APIs are unreliable. Filters for AI-relevant repos by keyword.
        """
        import re
        signals = []

        # Fetch both Python and all-language trending
        urls = [
            "https://github.com/trending/python?since=weekly",
            "https://github.com/trending?since=weekly",
        ]

        seen_repos = set()

        for url in urls:
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")

                # Extract repo names (href="/owner/repo")
                repo_pattern = re.compile(r'href="/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"')
                star_pattern = re.compile(r"([\d,]+)\s+stars this week")

                repo_matches = repo_pattern.findall(html)
                star_matches = star_pattern.findall(html)

                # Deduplicate repo names while preserving order
                unique_repos = []
                for r in repo_matches:
                    if r not in seen_repos and "/" in r and "sponsors/" not in r and "apps/" not in r:
                        unique_repos.append(r)
                        seen_repos.add(r)

                for repo, stars_str in zip(unique_repos[:25], star_matches[:25]):
                    stars_this_week = int(stars_str.replace(",", ""))

                    # Filter: must be AI-relevant by name or we'll fetch description
                    repo_lower = repo.lower()
                    if not any(kw in repo_lower for kw in self.AI_KEYWORDS):
                        # Skip low-star repos if not obviously AI
                        if stars_this_week < 1000:
                            continue

                    # Fetch current total stars + description from API
                    total_stars, description = self._fetch_repo_meta(repo)

                    # Re-check with description
                    desc_lower = (description or "").lower()
                    if not any(kw in repo_lower or kw in desc_lower for kw in self.AI_KEYWORDS):
                        continue

                    velocity_pct = (stars_this_week / max(total_stars - stars_this_week, 1)) * 100

                    signals.append(GitHubSignal(
                        repo=repo,
                        stars=total_stars,
                        delta_stars_7d=stars_this_week,
                        velocity_pct=round(velocity_pct, 2),
                        flagged=True,  # All trending items are flagged by definition
                        url=f"https://github.com/{repo}",
                        description=description,
                    ))

                    if len(signals) >= 8:
                        break

            except Exception as e:
                print(f"[GitHub] Trending scrape failed for {url}: {e}")

        # Sort by weekly stars descending
        signals.sort(key=lambda x: x.delta_stars_7d, reverse=True)
        return signals[:5]

    def _fetch_repo_meta(self, repo: str) -> tuple[int, str]:
        """Fetch current star count and description for a repo."""
        url = f"{self.GITHUB_API_URL}/{repo}"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "market-monitor/1.0"}
        if self.config.github_token:
            headers["Authorization"] = f"token {self.config.github_token}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.load(resp)
            return data.get("stargazers_count", 0), data.get("description", "")
        except Exception:
            return 0, ""

    def _load_baseline(self) -> dict[str, int]:
        """Load baseline star counts from JSON file."""
        if not self.baseline_path.exists():
            return {}

        try:
            with open(self.baseline_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_baseline(self, baseline: dict[str, int]) -> None:
        """Save baseline star counts to JSON file."""
        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.baseline_path, "w") as f:
            json.dump(baseline, f, indent=2)

    def _fetch_repo_signal(self, repo: str, baseline: dict[str, int]) -> Optional[GitHubSignal]:
        """Fetch repo data and compute signal."""
        url = f"{self.GITHUB_API_URL}/{repo}"

        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "market-monitor/1.0"}

        if self.config.github_token:
            headers["Authorization"] = f"token {self.config.github_token}"

        request = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)
        except Exception as e:
            print(f"[GitHub] Error fetching {repo}: {e}")
            return None

        current_stars = data.get("stargazers_count", 0)
        description = data.get("description", "")
        baseline_stars = baseline.get(repo, current_stars)

        delta = current_stars - baseline_stars
        velocity_pct = (delta / baseline_stars * 100) if baseline_stars > 0 else 0

        flagged = velocity_pct > self.velocity_threshold or delta > self.delta_threshold

        return GitHubSignal(
            repo=repo,
            stars=current_stars,
            delta_stars_7d=delta,
            velocity_pct=round(velocity_pct, 2),
            flagged=flagged,
            url=f"https://github.com/{repo}",
            description=description,
        )

    def get_flagged_signals(self) -> list[GitHubSignal]:
        """Collect and return only flagged signals."""
        return [s for s in self.collect() if s.flagged]
