"""Unit tests for the Endpoint and Step Pydantic schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asyncflow.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    StepOperation,
)
from asyncflow.schemas.system_topology.endpoint import Endpoint, Step


# --------------------------------------------------------------------------- #
# Helper functions to build minimal valid Step objects
# --------------------------------------------------------------------------- #
def cpu_step(value: float = 0.1) -> Step:
    """Return a minimal valid CPU-bound Step."""
    return Step(
        kind=EndpointStepCPU.CPU_BOUND_OPERATION,
        step_operation={StepOperation.CPU_TIME: value},
    )


def ram_step(value: int = 128) -> Step:
    """Return a minimal valid RAM Step."""
    return Step(
        kind=EndpointStepRAM.RAM,
        step_operation={StepOperation.NECESSARY_RAM: value},
    )


def io_step(value: float = 0.05) -> Step:
    """Return a minimal valid I/O Step."""
    return Step(
        kind=EndpointStepIO.WAIT,
        step_operation={StepOperation.IO_WAITING_TIME: value},
    )


# --------------------------------------------------------------------------- #
# Positive test cases
# --------------------------------------------------------------------------- #
def test_valid_cpu_step() -> None:
    """Test that a CPU step with correct 'cpu_time' operation passes validation."""
    step = cpu_step()
    # The operation value must match the input
    assert step.step_operation[StepOperation.CPU_TIME] == 0.1


def test_valid_ram_step() -> None:
    """Test that a RAM step with correct 'necessary_ram' operation passes validation."""
    step = ram_step()
    assert step.step_operation[StepOperation.NECESSARY_RAM] == 128


def test_valid_io_step() -> None:
    """
    Test that an I/O step with correct 'io_waiting_time'
    operation passes validation.
    """
    step = io_step()
    assert step.step_operation[StepOperation.IO_WAITING_TIME] == 0.05


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
    ("kind", "bad_operation"),
    [
        # CPU step with RAM operation
        (EndpointStepCPU.CPU_BOUND_OPERATION, {StepOperation.NECESSARY_RAM: 64}),
        # RAM step with CPU operation
        (EndpointStepRAM.RAM, {StepOperation.CPU_TIME: 0.2}),
        # I/O step with CPU operation
        (EndpointStepIO.DB, {StepOperation.CPU_TIME: 0.05}),
    ],
)
def test_incoherent_kind_operation_pair(
    kind: EndpointStepCPU | EndpointStepRAM | EndpointStepIO,
    bad_operation: dict[StepOperation, float | int],
) -> None:
    """Test that mismatched kind and operation combinations raise ValidationError."""
    with pytest.raises(ValidationError):
        Step(kind=kind, step_operation=bad_operation)


def test_multiple_operation_not_allowed() -> None:
    """
    Test that providing multiple operation in a single Step
    raises ValidationError.
    """
    with pytest.raises(ValidationError):
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={
                StepOperation.CPU_TIME: 0.1,
                StepOperation.NECESSARY_RAM: 64,
            },
        )


def test_empty_operation_rejected() -> None:
    """Test that an empty operation dict is rejected by the validator."""
    with pytest.raises(ValidationError):
        Step(kind=EndpointStepCPU.CPU_BOUND_OPERATION, step_operation={})


def test_wrong_operation_name_for_io() -> None:
    """Test that an I/O step with a non-I/O operation key is rejected."""
    with pytest.raises(ValidationError):
        Step(
            kind=EndpointStepIO.CACHE,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        )
