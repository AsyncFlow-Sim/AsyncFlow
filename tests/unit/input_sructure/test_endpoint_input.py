"""Unit tests for the Endpoint and Step Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    Metrics,
)
from app.schemas.system_topology_schema.endpoint_schema import Endpoint, Step


# --------------------------------------------------------------------------- #
# Helper functions to build minimal valid Step objects
# --------------------------------------------------------------------------- #
def cpu_step(value: float = 0.1) -> Step:
    """Return a minimal valid CPU-bound Step."""
    return Step(
        kind=EndpointStepCPU.CPU_BOUND_OPERATION,
        step_metrics={Metrics.CPU_TIME: value},
    )


def ram_step(value: int = 128) -> Step:
    """Return a minimal valid RAM Step."""
    return Step(
        kind=EndpointStepRAM.RAM,
        step_metrics={Metrics.NECESSARY_RAM: value},
    )


def io_step(value: float = 0.05) -> Step:
    """Return a minimal valid I/O Step."""
    return Step(
        kind=EndpointStepIO.WAIT,
        step_metrics={Metrics.IO_WAITING_TIME: value},
    )


# --------------------------------------------------------------------------- #
# Positive test cases
# --------------------------------------------------------------------------- #
def test_valid_cpu_step() -> None:
    """Test that a CPU step with correct 'cpu_time' metric passes validation."""
    step = cpu_step()
    # The metric value must match the input
    assert step.step_metrics[Metrics.CPU_TIME] == 0.1


def test_valid_ram_step() -> None:
    """Test that a RAM step with correct 'necessary_ram' metric passes validation."""
    step = ram_step()
    assert step.step_metrics[Metrics.NECESSARY_RAM] == 128


def test_valid_io_step() -> None:
    """Test that an I/O step with correct 'io_waiting_time' metric passes validation."""
    step = io_step()
    assert step.step_metrics[Metrics.IO_WAITING_TIME] == 0.05


def test_endpoint_with_mixed_steps() -> None:
    """Test that an Endpoint with multiple valid Step instances normalizes the name."""
    ep = Endpoint(
        endpoint_name="/Predict",
        steps=[cpu_step(), ram_step(), io_step()],
    )
    # endpoint_name should be lowercased by the validator
    assert ep.endpoint_name == "/predict"
    # All steps should be present in the list
    assert len(ep.steps) == 3


# --------------------------------------------------------------------------- #
# Negative test cases
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("kind", "bad_metrics"),
    [
        # CPU step with RAM metric
        (EndpointStepCPU.CPU_BOUND_OPERATION, {Metrics.NECESSARY_RAM: 64}),
        # RAM step with CPU metric
        (EndpointStepRAM.RAM, {Metrics.CPU_TIME: 0.2}),
        # I/O step with CPU metric
        (EndpointStepIO.DB, {Metrics.CPU_TIME: 0.05}),
    ],
)
def test_incoherent_kind_metric_pair(
    kind: EndpointStepCPU | EndpointStepRAM | EndpointStepIO,
    bad_metrics: dict[Metrics, float | int],
) -> None:
    """Test that mismatched kind and metric combinations raise ValidationError."""
    with pytest.raises(ValidationError):
        Step(kind=kind, step_metrics=bad_metrics)


def test_multiple_metrics_not_allowed() -> None:
    """Test that providing multiple metrics in a single Step raises ValidationError."""
    with pytest.raises(ValidationError):
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_metrics={
                Metrics.CPU_TIME: 0.1,
                Metrics.NECESSARY_RAM: 64,
            },
        )


def test_empty_metrics_rejected() -> None:
    """Test that an empty metrics dict is rejected by the validator."""
    with pytest.raises(ValidationError):
        Step(kind=EndpointStepCPU.CPU_BOUND_OPERATION, step_metrics={})


def test_wrong_metric_name_for_io() -> None:
    """Test that an I/O step with a non-I/O metric key is rejected."""
    with pytest.raises(ValidationError):
        Step(
            kind=EndpointStepIO.CACHE,
            step_metrics={Metrics.NECESSARY_RAM: 64},
        )
