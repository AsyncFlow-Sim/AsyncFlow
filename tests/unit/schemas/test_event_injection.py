"""Unit tests for the EventInjection Pydantic models.

This suite verifies:
- Family coherence: SERVER_DOWN→SERVER_UP and
  NETWORK_SPIKE_START→NETWORK_SPIKE_END.
- Temporal ordering: t_start < t_end, with field constraints.
- Spike semantics: spike_s is required only for NETWORK_SPIKE_START
  and forbidden otherwise.
- Strictness: unknown fields are rejected; models are frozen.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError

from asyncflow.config.constants import EventDescription
from asyncflow.schemas.events.injection import End, EventInjection, Start

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_server_down(start_t: float, end_t: float) -> EventInjection:
    """Build a minimal server down/up event with the given times."""
    start = Start(kind=EventDescription.SERVER_DOWN, t_start=start_t)
    end = End(kind=EventDescription.SERVER_UP, t_end=end_t)
    return EventInjection(
        event_id="ev-server-1",
        target_id="srv-1",
        start=start,
        end=end,
    )


def _mk_network_spike(
    start_t: float,
    end_t: float,
    spike_s: float | None,
) -> EventInjection:
    """Build a minimal network spike event with the given times and spike."""
    start = Start(
        kind=EventDescription.NETWORK_SPIKE_START,
        t_start=start_t,
        spike_s=spike_s,
    )
    end = End(kind=EventDescription.NETWORK_SPIKE_END, t_end=end_t)
    return EventInjection(
        event_id="ev-spike-1",
        target_id="edge-1",
        start=start,
        end=end,
    )


# ---------------------------------------------------------------------------
# Start/End family coherence
# ---------------------------------------------------------------------------

def test_family_coherence_server_ok() -> None:
    """SERVER_DOWN followed by SERVER_UP should validate."""
    model = _mk_server_down(start_t=10.0, end_t=20.0)
    assert model.start.kind is EventDescription.SERVER_DOWN
    assert model.end.kind is EventDescription.SERVER_UP


def test_family_coherence_network_ok() -> None:
    """NETWORK_SPIKE_START followed by NETWORK_SPIKE_END should validate."""
    model = _mk_network_spike(start_t=1.0, end_t=2.0, spike_s=0.005)
    assert model.start.kind is EventDescription.NETWORK_SPIKE_START
    assert model.end.kind is EventDescription.NETWORK_SPIKE_END


def test_family_mismatch_raises() -> None:
    """Mismatched start/end families must raise a ValueError."""
    start = Start(kind=EventDescription.SERVER_DOWN, t_start=1.0)
    end = End(kind=EventDescription.NETWORK_SPIKE_END, t_end=2.0)
    with pytest.raises(ValueError, match=r"must have .* kind in end"):
        EventInjection(
            event_id="ev-bad",
            target_id="srv-1",
            start=start,
            end=end,
        )


# ---------------------------------------------------------------------------
# Temporal ordering & per-field constraints
# ---------------------------------------------------------------------------

def test_time_ordering_start_before_end() -> None:
    """t_start must be strictly less than t_end."""
    with pytest.raises(ValueError, match=r"smaller than the ending time"):
        _mk_server_down(start_t=10.0, end_t=10.0)


def test_start_non_negative_enforced() -> None:
    """Start.t_start is NonNegativeFloat; negatives raise ValidationError."""
    with pytest.raises(ValidationError):
        Start(kind=EventDescription.SERVER_DOWN, t_start=-1.0)


def test_end_positive_enforced() -> None:
    """End.t_end is PositiveFloat; non-positive values raise ValidationError."""
    with pytest.raises(ValidationError):
        End(kind=EventDescription.SERVER_UP, t_end=0.0)


# ---------------------------------------------------------------------------
# Spike semantics
# ---------------------------------------------------------------------------

def test_network_spike_requires_spike_s() -> None:
    """NETWORK_SPIKE_START requires spike_s (seconds) to be present."""
    # Define the event id for the matching condition.
    event_id = "ev-spike-1"

    # Define the full message to be matched
    expected_message = (
        f"The field spike_s for the event {event_id} "
         "must be defined as a positive float"
    )

    with pytest.raises(ValidationError, match=re.escape(expected_message)):
        _mk_network_spike(start_t=0.5, end_t=1.5, spike_s=None)


def test_network_spike_positive_spike_s_enforced() -> None:
    """spike_s uses PositiveFloat; negative values raise ValidationError."""
    with pytest.raises(ValidationError):
        _mk_network_spike(start_t=0.0, end_t=1.0, spike_s=-0.001)


def test_spike_s_forbidden_for_server_events() -> None:
    """For non-network events, spike_s must be omitted."""
    event_id = "ev-bad-spike"
    expected_message = f"Event {event_id}: spike_s must be omitted"
    start = Start(
        kind=EventDescription.SERVER_DOWN,
        t_start=0.0,
        spike_s=0.001,
    )
    end = End(kind=EventDescription.SERVER_UP, t_end=1.0)
    with pytest.raises(ValueError, match=re.escape(expected_message)):
        EventInjection(
            event_id="ev-bad-spike",
            target_id="srv-1",
            start=start,
            end=end,
        )


# ---------------------------------------------------------------------------
# Strictness (extra fields) and immutability (frozen models)
# ---------------------------------------------------------------------------

def test_extra_fields_forbidden_in_start() -> None:
    """Unknown fields in Start must be rejected due to extra='forbid'."""
    payload: dict[str, Any] = {
        "kind": EventDescription.SERVER_DOWN,
        "t_start": 0.0,
        "unknown_field": 123,
    }
    with pytest.raises(ValidationError):
        Start.model_validate(payload)


def test_extra_fields_forbidden_in_end() -> None:
    """Unknown fields in End must be rejected due to extra='forbid'."""
    payload: dict[str, Any] = {
        "kind": EventDescription.SERVER_UP,
        "t_end": 1.0,
        "unknown_field": True,
    }
    with pytest.raises(ValidationError):
        End.model_validate(payload)


def test_start_is_frozen_and_immutable() -> None:
    """Start is frozen; attempting to mutate fields must raise an error."""
    start = Start(kind=EventDescription.SERVER_DOWN, t_start=0.0)
    # Cast to Any to avoid mypy's read-only property check; runtime must fail.
    start_any: Any = start
    with pytest.raises(ValidationError, match="Instance is frozen"):
        start_any.t_start = 1.0


def test_end_is_frozen_and_immutable() -> None:
    """End is frozen; attempting to mutate fields must raise an error."""
    end = End(kind=EventDescription.SERVER_UP, t_end=1.0)
    end_any: Any = end
    with pytest.raises(ValidationError, match="Instance is frozen"):
        end_any.t_end = 2.0
