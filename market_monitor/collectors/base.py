"""Base collector abstract class."""

from abc import ABC, abstractmethod
from typing import Any
from ..config import Config


class BaseCollector(ABC):
    """Abstract base class for all collectors."""

    def __init__(self, config: Config):
        self.config = config

    @abstractmethod
    def collect(self) -> list[Any]:
        """Collect items from the data source.

        Returns:
            List of collected items (dataclass instances).
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the collector for logging."""
        pass
