from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from asyncfow.config.enums importDistribution, TimeDefaults
from asyncflow.runner.sweep import Sweep
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import Client, TopologyNodes
from asyncflow.schemas.workload.rqs_generator import RqsGenerator

if TYPE_CHECKING:
    import simpy

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
    from asyncflow.runner.simulation import SimulationRunner


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _make_min_payload(
    *,
    users_mean: int = 1,
    rpm_mean: int = 2,
    sim_time: int = TimeDefaults.MIN_SIMULATION_TIME,
) -> SimulationPayload:
    """Return a minimal, validated payload (client only, no servers)."""
    rqs = RqsGenerator(
        id="gen",
        avg_active_users=RVConfig(
            mean=users_mean, distribution=Distribution.POISSON,
        ),
        avg_request_per_minute_per_user=RVConfig(
            mean=rpm_mean, distribution=Distribution.POISSON,
        ),
    )
    client = Client(id="cli")
    nodes = TopologyNodes(servers=[], client=client, load_balancer=None)
    graph = TopologyGraph(nodes=nodes, edges=[])
    settings = SimulationSettings(total_simulation_time=sim_time)
    return SimulationPayload(
        rqs_input=rqs, topology_graph=graph, sim_settings=settings,
    )


class _DummyAnalyzer:
    """Trivial object we return as analyzer surrogate in the fake runner."""

    def __init__(self, tag: int) -> None:
        self.tag = tag


class FakeSimulationRunner:
    """
    Test double for SimulationRunner:
    - records every (env, payload) received
    - returns a dummy analyzer-like object
    """

    run_calls: ClassVar[list[tuple[simpy.Environment, SimulationPayload]]] = []

    def __init__(
        self,
        *,
        env: simpy.Environment,
        simulation_input: SimulationPayload,
    ) -> None:
        """Store args for inspection; does not start any real process."""
        self.env = env
        self.payload = simulation_input

    def run(self) -> ResultsAnalyzer:
        """Record call and return a dummy analyzer marked with users mean."""
        FakeSimulationRunner.run_calls.append((self.env, self.payload))
        tag = int(self.payload.rqs_input.avg_active_users.mean)
        return cast("ResultsAnalyzer", _DummyAnalyzer(tag))


@pytest.fixture(autouse=True)
def _reset_fake_runner() -> None:
    """Ensure fake runner call log is clean before each test."""
    FakeSimulationRunner.run_calls.clear()


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_sweep_on_user_inclusive_grid_and_preserves_payload() -> None:
    payload = _make_min_payload(users_mean=7)
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    res = sweeper.sweep_on_user(
        payload=payload, user_lower_bound=2, user_upper_bound=6, step=2,
    )

    # Inclusive grid [2, 4, 6]
    assert [u for (u, _a) in res] == [2, 4, 6]
    assert sweeper._last_users_grid == [2, 4, 6]  # noqa: SLF001

    # Underlying payload not mutated by the sweep
    assert payload.rqs_input.avg_active_users.mean == 7

    # Fake runner saw three runs with the expected users injected
    seen = [
        int(p.rqs_input.avg_active_users.mean)
        for (_e, p) in FakeSimulationRunner.run_calls
    ]
    assert seen == [2, 4, 6]

    # Each run got a fresh copy (not the same object)
    for (_e, p) in FakeSimulationRunner.run_calls:
        assert p is not payload


def test_sweep_on_user_creates_fresh_env_per_run() -> None:
    payload = _make_min_payload()
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    res = sweeper.sweep_on_user(
        payload=payload, user_lower_bound=1, user_upper_bound=3, step=1,
    )
    assert len(res) == 3

    env_ids = [id(e) for (e, _p) in FakeSimulationRunner.run_calls]
    assert len(set(env_ids)) == 3  # all distinct envs
    # brand-new SimPy environments start at t=0
    assert all(e.now == 0 for (e, _p) in FakeSimulationRunner.run_calls)


@pytest.mark.parametrize(
    ("lo", "hi", "step", "msg_substr"),
    [
        (1, 5, 0, "step must be > 0"),
        (0, 5, 1, "strictly bigger than 0"),
        (1, 0, 1, "strictly bigger than 0"),
        (5, 1, 1, "user_upper_bound must be >= user_lower_bound"),
    ],
)
def test_sweep_on_user_invalid_inputs_raise(
    lo: int, hi: int, step: int, msg_substr: str,
) -> None:
    payload = _make_min_payload()
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    with pytest.raises(ValueError, match=msg_substr):
        sweeper.sweep_on_user(
            payload=payload,
            user_lower_bound=lo,
            user_upper_bound=hi,
            step=step,
        )


def test_sweep_on_user_returns_pairs_with_analyzers() -> None:
    payload = _make_min_payload()
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    res = sweeper.sweep_on_user(
        payload=payload, user_lower_bound=2, user_upper_bound=4, step=1,
    )

    # Tuple shape: (users, analyzer)
    users_list = [u for (u, _a) in res]
    assert users_list == [2, 3, 4]

    # Analyzer is the dummy object we returned (check runtime marker)
    tags = [getattr(a, "tag", None) for (_u, a) in res]
    assert tags == [2, 3, 4]
