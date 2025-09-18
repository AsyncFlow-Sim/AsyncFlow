"""Base interfaces for queueing-theory analyzers.

Each concrete analyzer (e.g. MM1) must:
- declare its compatibility rules against an AsyncFlow payload
- compute closed-form KPIs when assumptions are satisfied
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncflow.schemas.payload import SimulationPayload


class QueueTheoryBase(ABC):
    """Abstract base for all queue-theory analyzers."""

    @abstractmethod
    def explain_incompatibilities(self, payload: SimulationPayload) -> list[str]:
        """Return a list of human-readable reasons why the payload is incompatible.
        Empty list means 'compatible'.
        """

    def is_compatible(self, payload: SimulationPayload) -> bool:
        """Shorthand boolean check."""
        return not self.explain_incompatibilities(payload)

    def validate_or_raise(self, payload: SimulationPayload) -> None:
        """Raise ValueError with a compact message if incompatible."""
        errs = self.explain_incompatibilities(payload)
        if errs:
            bullet = "\n - "
            msg = "Payload is not compatible with this queueing model:" + bullet
            msg += bullet.join(errs)
            raise ValueError(msg)
