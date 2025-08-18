"""Pydantic model to inject event during the simulation"""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    NonNegativeFloat,
    PositiveFloat,
    model_validator,
)

from asyncflow.config.constants import EventDescription

# Event input schema:
# - Each event has its own identifier (event_id) and references the affected
#   component via target_id.
# - The event window is represented by two markers, Start and End.
# - We constrain kind with Literal[...] over EventDescription (a StrEnum),
#   so Pydantic enforces allowed values automatically for both Start and End.
# - Both marker models use ConfigDict(extra="forbid", frozen=True):
#   extra="forbid" rejects unknown fields (e.g., catches t_strat vs t_start);
#   frozen=True makes instances immutable at runtime for stability.

# Yaml example:
# event_id: ev-1
# target_id: srv-1
# start: { kind: SERVER_DOWN, t_start: 120.0 }
# end:   { kind: SERVER_UP, t_end: 240.0 }

class Start(BaseModel):
    """Start marker for an event window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Only "start" kinds allowed here
    kind: Literal[
        EventDescription.SERVER_DOWN,
        EventDescription.NETWORK_SPIKE_START,
    ]
    t_start: NonNegativeFloat  # seconds from simulation start


class End(BaseModel):
    """End marker for an event window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Only "end" kinds allowed here
    kind: Literal[
        EventDescription.SERVER_UP,
        EventDescription.NETWORK_SPIKE_END,
    ]
    t_end: PositiveFloat  # strictly > 0

class Event(BaseModel):
    """Definition of the input structure to define an event in the simulation"""

    event_id: str
    target_id: str
    start: Start
    end: End

    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_start_end_compatibility(
        cls, # noqa: N805
        model: "Event",
        ) -> "Event":
        """
        Check the compatibility between Start and End both at level
        of time interval and kind
        """
        # Ensure kind for Start and End are compatible
        start_to_end = {
            EventDescription.SERVER_DOWN: EventDescription.SERVER_UP,
            EventDescription.NETWORK_SPIKE_START: EventDescription.NETWORK_SPIKE_END,
            }

        expected = start_to_end[model.start.kind]
        if model.end.kind != expected:
            msg = (f"The event {model.event_id} must have" 
                   f"as value of kind in end {expected}")
            raise ValueError(msg)

        # Ensure the time sequence is well defined
        if model.start.t_start >= model.end.t_end:
            msg=(f"The starting time for the event {model.event_id}"
                 "must be smaller than the ending time")
            raise ValueError(msg)


