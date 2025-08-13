"""Data structures representing the life-cycle of a single request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from asyncflow.config.constants import SystemEdges, SystemNodes


class Hop(NamedTuple):
    """A single traversal of a node or edge."""

    component_type: SystemNodes | SystemEdges
    component_id: str
    timestamp: float


@dataclass
class RequestState:
    """Mutable state carried by each request throughout the simulation."""

    id: int
    initial_time: float
    finish_time: float | None = None
    history: list[Hop] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # API                                                                #
    # ------------------------------------------------------------------ #

    def record_hop(
        self,
        component_type: SystemNodes | SystemEdges,
        component_id: str,
        now: float,
    ) -> None:
        """Append a new hop in chronological order."""
        self.history.append(Hop(component_type, component_id, now))

    # ------------------------------------------------------------------ #
    # Derived metrics                                                     #
    # ------------------------------------------------------------------ #

    @property
    def latency(self) -> float | None:
        """Total time inside the system or ``None`` if not yet completed."""
        if self.finish_time is None:
            return None
        return self.finish_time - self.initial_time
