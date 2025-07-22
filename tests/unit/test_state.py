"""Unit-tests for :class:`RequestState` and :class:`Hop`."""
from __future__ import annotations

from app.config.constants import SystemEdges, SystemNodes
from app.runtime.rqs_state import Hop, RequestState

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _state() -> RequestState:
    """Return a fresh RequestState with id='42' and t0=0.0."""
    return RequestState(id=42, initial_time=0.0)


def _hop(
    c_type: SystemNodes | SystemEdges,
    c_id: str,
    ts: float,
) -> Hop:
    """Shorthand to build an Hop literal in tests."""
    return Hop(c_type, c_id, ts)


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_record_hop_appends_tuple() -> None:
    """record_hop stores a :class:`Hop` instance with all three fields."""
    st = _state()
    st.record_hop(SystemNodes.GENERATOR, "gen-1", now=1.23456)

    expected = [_hop(SystemNodes.GENERATOR, "gen-1", 1.23456)]
    assert st.history == expected
    assert isinstance(st.history[0], Hop)


def test_multiple_hops_preserve_global_order() -> None:
    """History keeps exact insertion order for successive hops."""
    st = _state()
    st.record_hop(SystemNodes.GENERATOR, "gen-1", 0.1)
    st.record_hop(SystemEdges.NETWORK_CONNECTION, "edge-7", 0.2)
    st.record_hop(SystemNodes.SERVER, "api-A", 0.3)

    expected: list[Hop] = [
        _hop(SystemNodes.GENERATOR, "gen-1", 0.1),
        _hop(SystemEdges.NETWORK_CONNECTION, "edge-7", 0.2),
        _hop(SystemNodes.SERVER, "api-A", 0.3),
    ]
    assert st.history == expected


def test_latency_none_until_finish_time_set() -> None:
    """Latency is ``None`` if *finish_time* has not been assigned."""
    st = _state()
    assert st.latency is None


def test_latency_returns_difference() -> None:
    """Latency equals ``finish_time - initial_time`` once closed."""
    st = _state()
    st.finish_time = 5.5
    assert st.latency == 5.5  # 5.5 - 0.0
