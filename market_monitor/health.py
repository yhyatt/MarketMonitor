"""Health check module - per-collector diagnostics and metrics."""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Config
from .llm_client import check_moonshot

GOG_BIN = "/home/openclaw/.local/bin/gog"
GOG_KEYRING_PASSWORD = "kai-gog-keyring"
GOG_ACCOUNT = "hyatt.yonatan@gmail.com"


@dataclass
class CollectorHealth:
    """Health status for a single collector."""

    name: str
    status: str  # "ok", "degraded", "error", "skipped"
    latency_ms: int = 0
    items_found: int = 0
    items_after_filter: int = 0
    items_logged: int = 0
    error: str = ""
    details: dict = field(default_factory=dict)

    @property
    def emoji(self) -> str:
        if self.status == "ok":
            return "🟢"
        if self.status == "degraded":
            return "🟡"
        if self.status == "error":
            return "🔴"
        return "⚪"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["emoji"] = self.emoji
        return d


@dataclass
class PipelineHealth:
    """Full pipeline health report."""

    timestamp: str = ""
    collectors: list[CollectorHealth] = field(default_factory=list)
    delivery: dict = field(default_factory=dict)
    store_stats: dict = field(default_factory=dict)
    api_keys: dict = field(default_factory=dict)

    def add(self, health: CollectorHealth):
        self.collectors.append(health)

    @property
    def all_ok(self) -> bool:
        return all(c.status == "ok" for c in self.collectors)

    @property
    def has_errors(self) -> bool:
        return any(c.status == "error" for c in self.collectors)

    def summary(self) -> str:
        """One-line summary for logging."""
        statuses = " ".join(f"{c.emoji}{c.name}" for c in self.collectors)
        if self.all_ok:
            return f"✅ All {len(self.collectors)} collectors healthy: {statuses}"
        elif self.has_errors:
            failed = [c.name for c in self.collectors if c.status == "error"]
            return f"❌ Errors in: {', '.join(failed)} | {statuses}"
        else:
            return f"⚠️ Degraded: {statuses}"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def to_telegram(self) -> str:
        """Format for Telegram message."""
        lines = [f"📊 Market Monitor Health — {self.timestamp}", ""]

        for c in self.collectors:
            status_line = f"{c.emoji} **{c.name}**"
            if c.latency_ms > 0:
                status_line += f" ({c.latency_ms}ms)"
            lines.append(status_line)

            if c.error:
                lines.append(f"   ⚠️ {c.error}")
            else:
                parts = [f"found: {c.items_found}"]
                if c.items_after_filter != c.items_found:
                    parts.append(f"filtered: {c.items_after_filter}")
                if c.items_logged:
                    parts.append(f"logged: {c.items_logged}")
                lines.append(f"   {', '.join(parts)}")

            # Show extra details if present
            for k, v in c.details.items():
                if v is not None and v != "" and v != 0:
                    lines.append(f"   {k}: {v}")
            lines.append("")

        # Store stats
        if self.store_stats:
            lines.append("📁 **Store**")
            for name, stats in self.store_stats.items():
                lines.append(f"   {name}: {stats}")
            lines.append("")

        # API keys
        if self.api_keys:
            lines.append("🔑 **API Keys**")
            for name, val in self.api_keys.items():
                if isinstance(val, tuple):
                    st, msg = val
                    emoji = "✅" if st == "ok" else "❌"
                    lines.append(f"   {emoji} {name}: {msg}")
                else:
                    emoji = "✅" if val == "set" else "❌"
                    lines.append(f"   {emoji} {name}: {val}")
            lines.append("")

        # Delivery
        if self.delivery:
            lines.append("📤 **Delivery**")
            for channel, status in self.delivery.items():
                emoji = "✅" if status == "ok" else "❌"
                lines.append(f"   {emoji} {channel}: {status}")
            lines.append("")

        lines.append(self.summary())
        return "\n".join(lines)


def check_github_api(config: Config) -> tuple[bool, str, int]:
    """Check GitHub API accessibility and rate limit."""
    cmd = ["gh", "api", "rate_limit", "--jq", ".resources.core"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return False, result.stderr[:200], 0
        data = json.loads(result.stdout)
        remaining = data.get("remaining", 0)
        limit = data.get("limit", 0)
        reset = data.get("reset", 0)
        reset_str = datetime.fromtimestamp(reset, tz=timezone.utc).strftime("%H:%M UTC") if reset else "unknown"
        if remaining < 100:
            return True, f"Low: {remaining}/{limit} remaining (resets {reset_str})", remaining
        return True, f"{remaining}/{limit} remaining (resets {reset_str})", remaining
    except FileNotFoundError:
        return False, "gh CLI not found", 0
    except Exception as e:
        return False, str(e)[:200], 0


def check_gog_auth() -> tuple[bool, str]:
    """Check gog CLI auth status."""
    cmd = [
        GOG_BIN, "gmail", "search", "newer_than:1d",
        "-a", GOG_ACCOUNT,
        "-j", "--results-only",
    ]
    env = {**os.environ, "GOG_KEYRING_PASSWORD": GOG_KEYRING_PASSWORD}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=env)
        if result.returncode != 0:
            return False, result.stderr[:200]
        # If we get a JSON array back, auth is working
        try:
            data = json.loads(result.stdout.strip())
            if isinstance(data, list):
                return True, f"Authenticated ({len(data)} recent emails)"
            return False, "Unexpected response format"
        except json.JSONDecodeError:
            return False, "Auth check returned non-JSON"
    except FileNotFoundError:
        return False, "gog CLI not found"
    except Exception as e:
        return False, str(e)[:200]


def check_store(path: Path, name: str) -> dict:
    """Get stats for a JSONL store file."""
    if not path.exists():
        return f"{name}: file missing"
    try:
        total = 0
        unsent = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    record = json.loads(line)
                    if not record.get("digest_sent", False):
                        unsent += 1
                except json.JSONDecodeError:
                    pass
        return f"{name}: {total} total, {unsent} unsent"
    except Exception as e:
        return f"{name}: error reading ({e})"


def run_health_check(config: Config) -> PipelineHealth:
    """Run full pipeline health check and return structured report."""
    report = PipelineHealth(timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    # --- Check each collector ---

    # 1. arXiv
    t0 = time.time()
    try:
        from .collectors import ArxivCollector
        arxiv = ArxivCollector(config)
        papers = arxiv.collect()
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="arXiv",
            status="ok" if papers else "degraded",
            latency_ms=elapsed,
            items_found=len(papers),
            details={"lookback_days": config.arxiv_lookback_days},
        ))
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="arXiv",
            status="error",
            latency_ms=elapsed,
            error=str(e)[:200],
        ))

    # 2. HuggingFace
    t0 = time.time()
    try:
        from .collectors import HuggingFaceCollector
        hf = HuggingFaceCollector(config)
        items = hf.collect()
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="HuggingFace",
            status="ok" if items else "degraded",
            latency_ms=elapsed,
            items_found=len(items),
            details={"trending_limit": config.hf_trending_limit},
        ))
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="HuggingFace",
            status="error",
            latency_ms=elapsed,
            error=str(e)[:200],
        ))

    # 3. GitHub
    t0 = time.time()
    try:
        from .collectors import GitHubRadar
        github = GitHubRadar(config)
        signals = github.collect()
        flagged = [s for s in signals if s.flagged]
        elapsed = int((time.time() - t0) * 1000)
        gh_ok, gh_msg, gh_remaining = check_github_api(config)
        report.add(CollectorHealth(
            name="GitHub",
            status="ok" if gh_ok and signals else ("degraded" if signals else "error"),
            latency_ms=elapsed,
            items_found=len(signals),
            items_after_filter=len(flagged),
            details={"tracked_repos": len(config.github_tracked_repos), "api": gh_msg},
        ))
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="GitHub",
            status="error",
            latency_ms=elapsed,
            error=str(e)[:200],
        ))

    # 4. AlphaSignal
    t0 = time.time()
    try:
        from .collectors import AlphaSignalCollector
        alpha = AlphaSignalCollector(config)
        items = alpha.collect()
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="AlphaSignal",
            status="ok" if items else "degraded",
            latency_ms=elapsed,
            items_found=len(items),
            details={"source": "Gmail label:Digest_sources"},
        ))
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="AlphaSignal",
            status="error",
            latency_ms=elapsed,
            error=str(e)[:200],
        ))

    # 5. AI/TLDR
    t0 = time.time()
    try:
        from .collectors import AITLDRCollector
        aitldr = AITLDRCollector(config)
        items = aitldr.collect()
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="AI/TLDR",
            status="ok" if items else "degraded",
            latency_ms=elapsed,
            items_found=len(items),
            details={"source": "ai-tldr.blackpc-me.workers.dev"},
        ))
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        report.add(CollectorHealth(
            name="AI/TLDR",
            status="error",
            latency_ms=elapsed,
            error=str(e)[:200],
        ))

    # --- Store stats ---
    report.store_stats = {
        "papers": check_store(config.papers_jsonl, "papers"),
        "hf_releases": check_store(config.hf_releases_jsonl, "hf"),
        "github_signals": check_store(config.github_signals_jsonl, "github"),
    }

    # --- API keys ---
    gog_ok, gog_msg = check_gog_auth()
    moonshot_ok, moonshot_msg = check_moonshot()
    gh_ok, gh_msg, _ = check_github_api(config)
    report.api_keys = {
        "GitHub (gh CLI)": ("ok" if gh_ok else "error", gh_msg),
        "Moonshot (Kimi)": ("ok" if moonshot_ok else "error", moonshot_msg),
        "gog (Gmail)": ("ok" if gog_ok else "error", gog_msg),
    }

    return report
