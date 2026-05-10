"""Collectors package - data source collectors."""

from .base import BaseCollector
from .arxiv import ArxivCollector, ArxivPaper
from .huggingface import HuggingFaceCollector, HFItem
from .github_radar import GitHubRadar, GitHubSignal
from .alphasignal import AlphaSignalCollector, AlphaItem
from .aitldr import AITLDRCollector, AITLDRItem

__all__ = [
    "BaseCollector",
    "ArxivCollector",
    "ArxivPaper",
    "HuggingFaceCollector",
    "HFItem",
    "GitHubRadar",
    "GitHubSignal",
    "AlphaSignalCollector",
    "AlphaItem",
    "AITLDRCollector",
    "AITLDRItem",
]
