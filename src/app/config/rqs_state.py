"""
defining a state in a one to one correspondence
with the requests generated that will go through
all the node necessary to accomplish the user request
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RequestState:
    """
    State object carried by each request through the simulation.

    Attributes:
        id: Unique identifier of the request.
        t0: Timestamp (simulated env.now) when the request was generated.
        history: List of hop records, each noting a node/edge visit.
        finish_time: Timestamp when the requests is satisfied

    """

    id: int                                # Unique request identifier
    initial_time: float                    # Generation timestamp (env.now)
    finish_time: float | None = None       # a requests might be dropped
    history: list[str] = field(default_factory=list)  # Trace of hops

    def record_hop(self, node_name: str, now: float) -> None:
        """
        Append a record of visiting a node or edge.

        Args:
            node_name: Name of the node or edge being recorded.
            now: register the time of the operation

        """
        # Record hop as "NodeName@Timestamp"
        self.history.append(f"{node_name}@{now:.3f}")

    @property
    def latency(self) -> float | None:
        """
        Return the total time in the system (finish_time - initial_time),
        or None if the request hasn't completed yet.
        """
        if self.finish_time is None:
            return None
        return self.finish_time - self.initial_time
