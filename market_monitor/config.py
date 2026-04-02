"""Configuration management for market-monitor."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Market monitor configuration loaded from environment."""

    workspace_root: Path = field(default_factory=lambda: Path("/home/openclaw/.openclaw/workspace"))
    memory_dir: Path = field(default_factory=lambda: Path("/home/openclaw/.openclaw/workspace/memory/market"))

    anthropic_api_token: Optional[str] = None
    github_token: Optional[str] = None
    gog_keyring_password: Optional[str] = None

    # Scoring thresholds
    score_threshold: int = 7
    max_digest_items: int = 5

    # Collector settings
    arxiv_lookback_days: int = 7
    arxiv_max_results: int = 200
    hf_trending_limit: int = 30

    # GitHub repos to track
    github_tracked_repos: list[str] = field(default_factory=lambda: [
        "vllm-project/vllm",
        "stanford-oval/storm",
        "stanfordnlp/dspy",
        "langchain-ai/langgraph",
        "openai/openai-python",
        "huggingface/transformers",
        "microsoft/autogen",
        "crewAIInc/crewAI",
        "deepseek-ai/DeepSeek-V3",
        "meta-llama/llama3",
        "openclaw/openclaw",
        "mistralai/mistral-src",
        "ollama/ollama",
        "langchain-ai/langchain",
        "BerriAI/litellm",
    ])

    # GitHub velocity thresholds
    github_velocity_threshold_pct: float = 5.0
    github_delta_threshold: int = 500

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            anthropic_api_token=os.environ.get("ANTHROPIC_API_TOKEN"),
            github_token=os.environ.get("GITHUB_TOKEN"),
            gog_keyring_password=os.environ.get("GOG_KEYRING_PASSWORD"),
        )

    @property
    def papers_jsonl(self) -> Path:
        return self.memory_dir / "papers.jsonl"

    @property
    def github_signals_jsonl(self) -> Path:
        return self.memory_dir / "github_signals.jsonl"

    @property
    def github_baseline_json(self) -> Path:
        return self.memory_dir / "github_baseline.json"

    @property
    def hf_releases_jsonl(self) -> Path:
        return self.memory_dir / "hf_releases.jsonl"

    def ensure_memory_dir(self) -> None:
        """Ensure memory directory exists."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
