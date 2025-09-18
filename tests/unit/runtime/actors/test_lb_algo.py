"""Unit tests for LB algorithms (FCFS picker, RR, LC, Random).

Covers:
- FCFS 'picker' semantics (no mutation, respect of busy map).
- Side-effects on the OrderedDict for RR (rotation).
- Deterministic behavior of random_choice via monkeypatch.
- LB_TABLE wiring (FCFS is handled outside the table).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, cast

from asyncflow.config.enums import LbAlgorithmsName
from asyncflow.runtime.actors.routing.lb_algorithms import (
    LB_TABLE,
    least_connections,
    random_choice,
    round_robin,
)

if TYPE_CHECKING:
    import pytest

    from asyncflow.runtime.actors.edge import EdgeRuntime


class _DummyEdge:
    """Minimal stub exposing only what algorithms read."""

    def __init__(self, cc: int) -> None:
        self.concurrent_connections = cc

    def __repr__(self) -> str:
        return f"DummyEdge(cc={self.concurrent_connections})"


def _mk_edges(pairs: list[tuple[str, int]]) -> OrderedDict[str, _DummyEdge]:
    """Build an OrderedDict of dummy edges from (key, concurrent_conns)."""
    return OrderedDict((k, _DummyEdge(cc)) for k, cc in pairs)


# ----------------------------- Other algorithms ----------------------------- #

def test_round_robin_rotates_and_returns_first() -> None:
    """RR returns first edge and rotates it to the end."""
    od = _mk_edges([("a", 0), ("b", 0), ("c", 0)])
    first = next(iter(od.values()))
    edges = cast("OrderedDict[str, EdgeRuntime]", od)

    e = cast("_DummyEdge", round_robin(edges))
    assert e is first
    assert list(od.keys()) == ["b", "c", "a"], "must rotate order"


def test_least_connections_picks_minimal() -> None:
    """LC must choose the edge with the smallest concurrent connections."""
    od = _mk_edges([("a", 3), ("b", 1), ("c", 2)])
    edges = cast("OrderedDict[str, EdgeRuntime]", od)

    e = cast("_DummyEdge", least_connections(edges))
    assert e is od["b"]


def test_least_connections_tie_prefers_first_minimal() -> None:
    """On ties, min() returns the first minimal by insertion order."""
    od = _mk_edges([("a", 2), ("b", 1), ("c", 1), ("d", 3)])
    edges = cast("OrderedDict[str, EdgeRuntime]", od)

    e = cast("_DummyEdge", least_connections(edges))
    assert e is od["b"], "first minimal should be selected"


def test_random_choice_monkeypatched_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """random_choice should pick edge at the patched index."""
    od = _mk_edges([("a", 0), ("b", 0), ("c", 0)])
    edges = cast("OrderedDict[str, EdgeRuntime]", od)

    def _fake_randrange(n: int) -> int:
        assert n == 3
        return 1  # pick key 'b'

    monkeypatch.setattr(
        "asyncflow.runtime.actors.routing.lb_algorithms.random.randrange",
        _fake_randrange,
    )

    e = cast("_DummyEdge", random_choice(edges))
    assert e is od["b"]


# ------------------------------ LB_TABLE wiring ----------------------------- #

def test_lb_table_wiring_has_no_fcfs() -> None:
    """FCFS is handled by the LB runtime; it must not be in LB_TABLE."""
    table = LB_TABLE
    assert LbAlgorithmsName.FCFS not in table
    assert table[LbAlgorithmsName.ROUND_ROBIN] is round_robin
    assert table[LbAlgorithmsName.LEAST_CONNECTIONS] is least_connections
    assert table[LbAlgorithmsName.RANDOM] is random_choice
