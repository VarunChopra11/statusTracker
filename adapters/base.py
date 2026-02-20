from abc import ABC, abstractmethod
from datetime import datetime
from pydantic import BaseModel, Field

class NormalizedEvent(BaseModel):
    product: str
    status: str
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    provider: str = Field(default="unknown")
    raw: dict = Field(default_factory=dict)


class BaseAdapter(ABC):
    # Subclasses should override this to name their provider.
    provider_name: str = "unknown"

    @abstractmethod
    def parse(self, payload: dict) -> NormalizedEvent:
        """Parse the raw payload from the provider and return a NormalizedEvent."""
        pass