from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from asyncflow.config.enums import TimeDefaults
from asyncflow.runner.sweep import Sweep
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import Client, TopologyNodes

if TYPE_CHECKING:
    import simpy

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
    from asyncflow.runner.simulation import SimulationRunner


def _make_min_payload(
    *,
    sim_time: int = TimeDefaults.MIN_SIMULATION_TIME,
    lambda_rps: float = 20.0,
) -> SimulationPayload:
    """Return a minimal, validated payload (client only, no servers)."""
    arrivals = ArrivalsGenerator(id="gen", lambda_rps=lambda_rps, model="poisson")
    client = Client(id="cli")
    nodes = TopologyNodes(servers=[], client=client, load_balancer=None)
    graph = TopologyGraph(nodes=nodes, edges=[])
    settings = SimulationSettings(total_simulation_time=sim_time)
    return SimulationPayload(
        arrivals=arrivals, topology_graph=graph, sim_settings=settings)


class _DummyAnalyzer:
    """Trivial object we return as analyzer surrogate in the fake runner."""

    def __init__(self, tag: int) -> None:
        self.tag = tag
        """instance for the analyzer"""


class FakeSimulationRunner:
    """Test double: records calls and returns a dummy analyzer."""

    run_calls: ClassVar[list[tuple[simpy.Environment, SimulationPayload]]] = []

    def __init__(
        self,
        *,
        env: simpy.Environment,
        simulation_input: SimulationPayload,
    ) -> None:
        """Instance for the fakerunner"""
        self.env = env
        self.payload = simulation_input


    def run(self) -> ResultsAnalyzer:
        """Function to return the resultanalyzer after the simulation"""
        FakeSimulationRunner.run_calls.append((self.env, self.payload))
        tag = int(self.payload.arrivals.lambda_rps)
        return cast("ResultsAnalyzer", _DummyAnalyzer(tag))


@pytest.fixture(autouse=True)
def _reset_fake_runner() -> None:
    FakeSimulationRunner.run_calls.clear()


def test_sweep_on_user_inclusive_grid_and_preserves_payload() -> None:
    payload = _make_min_payload(lambda_rps=7.0)
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    res = sweeper.sweep_on_lambda(
        payload=payload, lambda_lower_bound=2, lambda_upper_bound=6, step=2,
    )

    assert [u for (u, _a) in res] == [2, 4, 6]
    assert sweeper._last_lambda_grid == [2, 4, 6]  # noqa: SLF001

    assert payload.arrivals.lambda_rps == 7.0

    seen = [int(p.arrivals.lambda_rps) for (_e, p) in FakeSimulationRunner.run_calls]
    assert seen, "Expected at least one sweep point."
    assert min(seen) >= 2
    assert max(seen) <= 6

    diffs = [b - a for a, b in pairwise(seen)]
    assert all(d % 2 == 0 for d in diffs)

    for (_e, p) in FakeSimulationRunner.run_calls:
        assert p is not payload


def test_sweep_on_user_creates_fresh_env_per_run() -> None:
    """Test to assert new sweep on a new env"""
    payload = _make_min_payload()
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    _ = sweeper.sweep_on_lambda(
        payload=payload, lambda_lower_bound=1, lambda_upper_bound=3, step=1,
    )

    env_ids = [id(e) for (e, _p) in FakeSimulationRunner.run_calls]
    assert len(set(env_ids)) == 3
    assert all(e.now == 0 for (e, _p) in FakeSimulationRunner.run_calls)


@pytest.mark.parametrize(
    ("lo", "hi", "step", "msg_substr"),
    [
        (1, 5, 0, "step must be > 0"),
        (0, 5, 1, "strictly bigger than 0"),
        (1, 0, 1, "strictly bigger than 0"),
        (5, 1, 1, "lambda_upper_bound must be >= lambda_lower_bound"),
    ],
)
def test_sweep_on_user_invalid_inputs_raise(
    lo: int, hi: int, step: int, msg_substr: str,
) -> None:
    """Test to assert return of error on invalid input"""
    payload = _make_min_payload()
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    with pytest.raises(ValueError, match=msg_substr):
        sweeper.sweep_on_lambda(
            payload=payload,
            lambda_lower_bound=lo,
            lambda_upper_bound=hi,
            step=step,
        )


def test_sweep_on_user_returns_pairs_with_analyzers() -> None:
    """Test to assert correct pairs are returned"""
    payload = _make_min_payload()
    sweeper = Sweep(
        simulation_cls=cast("type[SimulationRunner]", FakeSimulationRunner),
    )

    res = sweeper.sweep_on_lambda(
        payload=payload, lambda_lower_bound=2, lambda_upper_bound=4, step=1,
    )

    users_list = [u for (u, _a) in res]
    assert users_list == [2, 3, 4]

    tags = [getattr(a, "tag", None) for (_u, a) in res]
    assert tags == [2, 3, 4]
