"""Unit-tests for :class:`RequestState`."""
from __future__ import annotations

from app.config.rqs_state import RequestState

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _state() -> RequestState:
    """Return a fresh RequestState with id=42 and t0=0.0."""
    return RequestState(id=42, initial_time=0.0)


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_record_hop_appends_formatted_entry() -> None:
    """Calling *record_hop* stores 'node@timestamp' with 3-dec precision."""
    st = _state()
    st.record_hop("generator", now=1.23456)
    assert st.history == ["generator@1.235"]  # rounded to 3 decimals


def test_multiple_hops_preserve_order() -> None:
    """History keeps insertion order for consecutive hops."""
    st = _state()
    st.record_hop("A", 0.1)
    st.record_hop("B", 0.2)
    st.record_hop("C", 0.3)
    assert st.history == ["A@0.100", "B@0.200", "C@0.300"]


def test_latency_none_until_finish_time_set() -> None:
    """Latency is None if *finish_time* not assigned."""
    st = _state()
    assert st.latency is None


def test_latency_returns_difference() -> None:
    """Latency equals finish_time - initial_time once completed."""
    st = _state()
    st.finish_time = 5.5
    assert st.latency == 5.5  # 5.5 - 0.0
