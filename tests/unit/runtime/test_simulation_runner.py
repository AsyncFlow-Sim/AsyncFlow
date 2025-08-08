"""Unit-tests for :pyclass:`app.runtime.simulation_runner.SimulationRunner`.

Purpose
-------
Validate each private builder in isolation and run a minimal end-to-end
execution without relying on the full integration scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import simpy
import yaml

from app.metrics.analyzer import ResultsAnalyzer
from app.runtime.simulation_runner import SimulationRunner

if TYPE_CHECKING:
    from pathlib import Path

    from app.runtime.actors.client import ClientRuntime
    from app.runtime.actors.rqs_generator import RqsGeneratorRuntime
    from app.schemas.full_simulation_input import SimulationPayload


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def env() -> simpy.Environment:
    """Return a fresh SimPy environment for every unit test."""
    return simpy.Environment()


@pytest.fixture
def runner(
    env: simpy.Environment,
    payload_base: SimulationPayload,
) -> SimulationRunner:
    """Factory producing an **un-started** SimulationRunner."""
    return SimulationRunner(env=env, simulation_input=payload_base)


# --------------------------------------------------------------------------- #
# Builder-level tests                                                         #
# --------------------------------------------------------------------------- #
def test_build_rqs_generator_populates_dict(runner: SimulationRunner) -> None:
    """_build_rqs_generator() must register one generator runtime."""
    runner._build_rqs_generator()  # noqa: SLF001
    assert len(runner._rqs_runtime) == 1  # noqa: SLF001
    gen_rt: RqsGeneratorRuntime = next(
        iter(runner._rqs_runtime.values()),  # noqa: SLF001
    )
    assert gen_rt.rqs_generator_data.id == runner.rqs_generator.id


def test_build_client_populates_dict(runner: SimulationRunner) -> None:
    """_build_client() must register exactly one client runtime."""
    runner._build_client()  # noqa: SLF001
    assert len(runner._client_runtime) == 1  # noqa: SLF001
    cli_rt: ClientRuntime = next(
        iter(runner._client_runtime.values()),  # noqa: SLF001
    )
    assert cli_rt.client_config.id == runner.client.id
    assert cli_rt.out_edge is None


def test_build_servers_keeps_empty_with_minimal_topology(
    runner: SimulationRunner,
) -> None:
    """Zero servers in the payload → dict stays empty."""
    runner._build_servers()  # noqa: SLF001
    assert runner._servers_runtime == {}  # noqa: SLF001


def test_build_load_balancer_noop_when_absent(
    runner: SimulationRunner,
) -> None:
    """No LB in the payload → builder leaves dict empty."""
    runner._build_load_balancer()  # noqa: SLF001
    assert runner._lb_runtime == {}  # noqa: SLF001


# --------------------------------------------------------------------------- #
# Edges builder                                                               #
# --------------------------------------------------------------------------- #
def test_build_edges_with_stub_edge(runner: SimulationRunner) -> None:
    """
    `_build_edges()` must register exactly one `EdgeRuntime`, corresponding
    to the single stub edge (generator → client) present in the minimal
    topology fixture.
    """
    runner._build_rqs_generator()        # noqa: SLF001
    runner._build_client()               # noqa: SLF001
    runner._build_edges()                # noqa: SLF001
    assert len(runner._edges_runtime) == 1  # noqa: SLF001


# --------------------------------------------------------------------------- #
# End-to-end “mini” run                                                       #
# --------------------------------------------------------------------------- #
def test_run_returns_results_analyzer(runner: SimulationRunner) -> None:
    """
    `.run()` must complete even though the client is a sink node. We patch
    `_build_client` to assign a no-op edge to avoid assertions.
    """

    class _NoOpEdge:
        """Edge stub that silently discards transported states."""

        def transport(self) -> None:
            return

    def patched_build_client(self: SimulationRunner) -> None:
        # Call the original builder
        SimulationRunner._build_client(self) # noqa: SLF001
        cli_rt = next(iter(self._client_runtime.values()))
        cli_rt.out_edge = _NoOpEdge()  # type: ignore[assignment]

    with patch.object(runner, "_build_client", patched_build_client.__get__(runner)):
        results: ResultsAnalyzer = runner.run()

    assert isinstance(results, ResultsAnalyzer)
    assert (
        pytest.approx(runner.env.now)
        == runner.simulation_settings.total_simulation_time
    )


# --------------------------------------------------------------------------- #
# from_yaml utility                                                           #
# --------------------------------------------------------------------------- #
def test_from_yaml_minimal(tmp_path: Path, env: simpy.Environment) -> None:
    """from_yaml() parses YAML, validates via Pydantic and returns a runner."""
    yml_payload = {
        "rqs_input": {
            "id": "gen-yaml",
            "avg_active_users": {"mean": 1},
            "avg_request_per_minute_per_user": {"mean": 2},
            "user_sampling_window": 10,
        },
        "topology_graph": {
            "nodes": {"client": {"id": "cli-yaml"}, "servers": []},
            "edges": [],
        },
        "sim_settings": {"total_simulation_time": 5},
    }

    yml_path: Path = tmp_path / "scenario.yml"
    yml_path.write_text(yaml.safe_dump(yml_payload))

    runner = SimulationRunner.from_yaml(env=env, yaml_path=yml_path)

    assert isinstance(runner, SimulationRunner)
    assert runner.rqs_generator.id == "gen-yaml"
    assert runner.client.id == "cli-yaml"
