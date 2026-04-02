"""Pytest configuration and fixtures."""

import json
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from market_monitor.config import Config


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config(temp_dir):
    """Create a test config with temporary directories."""
    cfg = Config(
        memory_dir=temp_dir / "memory" / "market",
        anthropic_api_token="test-token",
        github_token="test-gh-token",
        gog_keyring_password="test-password",
    )
    cfg.ensure_memory_dir()
    return cfg


@pytest.fixture
def sample_arxiv_xml():
    """Sample arXiv API response XML with dynamic dates."""
    # Use dates within lookback period
    today = datetime.now(timezone.utc)
    date1 = (today - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    date2 = (today - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.12345v1</id>
    <published>{date1}</published>
    <title>Agentic AI Systems: A Multi-Agent Paradigm</title>
    <summary>This paper explores multi-agent orchestration and the emergence of agentic AI systems with reasoning capabilities.</summary>
    <author><name>John Smith</name></author>
    <author><name>Jane Doe</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2603.12346v1</id>
    <published>{date2}</published>
    <title>Medical Imaging with Deep Learning</title>
    <summary>A survey of medical imaging techniques using deep learning for protein folding analysis.</summary>
    <author><name>Bob Wilson</name></author>
    <arxiv:primary_category term="cs.CV"/>
    <category term="cs.CV"/>
  </entry>
</feed>"""


@pytest.fixture
def sample_hf_papers():
    """Sample HuggingFace daily papers response."""
    return [
        {
            "paper": {
                "id": "2603.11111",
                "title": "Foundation Model Scaling Laws",
                "summary": "We study scaling laws for large language models and their implications.",
            },
            "numLikes": 42,
        },
        {
            "paper": {
                "id": "2603.22222",
                "title": "Object Detection Benchmark",
                "summary": "A new benchmark for object detection in autonomous vehicles.",
            },
            "numLikes": 10,
        },
    ]


@pytest.fixture
def sample_hf_models():
    """Sample HuggingFace trending models response."""
    return [
        {
            "modelId": "meta-llama/llama-4-70b",
            "pipeline_tag": "text-generation",
            "likes": 1000,
            "downloads": 50000,
            "createdAt": "2026-03-20T00:00:00Z",
        },
        {
            "modelId": "user/model-lora-v1",
            "pipeline_tag": "text-generation",
            "likes": 50,
            "downloads": 100,
        },
        {
            "modelId": "user/model-gguf-q4",
            "pipeline_tag": "text-generation",
            "likes": 30,
            "downloads": 200,
        },
    ]


@pytest.fixture
def sample_github_response():
    """Sample GitHub API response."""
    return {
        "stargazers_count": 15000,
        "description": "A high-performance inference engine",
    }


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps({
        "score": 8,
        "thesis": "Multi-agent systems represent the next frontier",
        "themes": ["agentic-AI", "multi-agent", "orchestration"],
        "strategic_signals": ["Enterprise adoption accelerating"],
        "why_it_matters": "This shifts the competitive landscape.",
    }))]
    return mock
