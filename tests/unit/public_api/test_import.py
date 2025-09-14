"""Unit tests for the public import surface of the asyncflow package.

Checks:
- Each public module exposes the expected `__all__`.
- Symbols referenced in `__all__` are importable.
- Symbols are of the expected kind (class or Enum).
"""

from __future__ import annotations

import importlib
from enum import Enum
from typing import TYPE_CHECKING

# Root facade
from asyncflow import AsyncFlow, SimulationRunner, Sweep

# Public subpackages
from asyncflow.analysis import MMc, ResultsAnalyzer, SweepAnalyzer
from asyncflow.components import (
    ArrivalsGenerator,
    Client,
    Edge,
    Endpoint,
    EventInjection,
    LoadBalancer,
    NodesResources,
    Server,
)
from asyncflow.enums import (
    Distribution,
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    EventMetricName,
    LbAlgorithmsName,
    SampledMetricName,
    StepOperation,
)
from asyncflow.settings import SimulationSettings

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _assert_all_equals(module_name: str, expected: Iterable[str]) -> None:
    """Assert that a module's __all__ exactly matches `expected`."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "__all__"), f"{module_name} is missing __all__"
    assert set(mod.__all__) == set(expected), (
        f"{module_name}.__all__ mismatch:\n"
        f"  expected: {set(expected)}\n"
        f"  actual:   {set(mod.__all__)}"
    )


# --------------------------------------------------------------------------- #
# Root facade                                                                 #
# --------------------------------------------------------------------------- #
def test_root_public_symbols() -> None:
    """`asyncflow` exposes the expected facade symbols."""
    _assert_all_equals(
        "asyncflow",
        ["AsyncFlow", "SimulationRunner", "Sweep"],
    )


def test_root_symbols_are_classes() -> None:
    """Facade symbols are importable classes."""
    for cls, name in [
        (AsyncFlow, "AsyncFlow"),
        (SimulationRunner, "SimulationRunner"),
        (Sweep, "Sweep"),
    ]:
        assert isinstance(cls, type), f"{name} should be a class"
        assert cls.__name__ == name


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
def test_enums_public_symbols() -> None:
    """`asyncflow.enums` exposes the expected enum types."""
    expected = [
        "Distribution",
        "EndpointStepCPU",
        "EndpointStepIO",
        "EndpointStepRAM",
        "EventMetricName",
        "LbAlgorithmsName",
        "SampledMetricName",
        "StepOperation",
    ]
    _assert_all_equals("asyncflow.enums", expected)


def test_enums_symbols_are_enum_types() -> None:
    """All public symbols in enums are Enum subclasses."""
    for enum_type, name in [
        (Distribution, "Distribution"),
        (EndpointStepCPU, "EndpointStepCPU"),
        (EndpointStepIO, "EndpointStepIO"),
        (EndpointStepRAM, "EndpointStepRAM"),
        (EventMetricName, "EventMetricName"),
        (LbAlgorithmsName, "LbAlgorithmsName"),
        (SampledMetricName, "SampledMetricName"),
        (StepOperation, "StepOperation"),
    ]:
        assert isinstance(enum_type, type), f"{name} should be a type"
        assert issubclass(enum_type, Enum), f"{name} should be an Enum"
        assert enum_type.__name__ == name


# --------------------------------------------------------------------------- #
# Analysis                                                                     #
# --------------------------------------------------------------------------- #
def test_analysis_public_symbols() -> None:
    """`asyncflow.analysis` exposes the expected names."""
    _assert_all_equals(
        "asyncflow.analysis",
        ["MMc", "ResultsAnalyzer", "SweepAnalyzer"],
    )


def test_analysis_symbols_are_classes() -> None:
    """All analysis symbols are classes."""
    for cls, name in [
        (MMc, "MMc"),
        (ResultsAnalyzer, "ResultsAnalyzer"),
        (SweepAnalyzer, "SweepAnalyzer"),
    ]:
        assert isinstance(cls, type), f"{name} should be a class"
        assert cls.__name__ == name


# --------------------------------------------------------------------------- #
# Components                                                                   #
# --------------------------------------------------------------------------- #
def test_components_public_symbols() -> None:
    """`asyncflow.components` exposes the expected names."""
    expected = [
        "ArrivalsGenerator",
        "Client",
        "Edge",
        "Endpoint",
        "EventInjection",
        "LoadBalancer",
        "NodesResources",
        "Server",
    ]
    _assert_all_equals("asyncflow.components", expected)


def test_components_symbols_are_importable_classes() -> None:
    """All public symbols are importable and are classes."""
    for cls, name in [
        (ArrivalsGenerator, "ArrivalsGenerator"),
        (Client, "Client"),
        (Edge, "Edge"),
        (Endpoint, "Endpoint"),
        (EventInjection, "EventInjection"),
        (LoadBalancer, "LoadBalancer"),
        (NodesResources, "NodesResources"),
        (Server, "Server"),
    ]:
        assert isinstance(cls, type), f"{name} should be a class"
        assert cls.__name__ == name


# --------------------------------------------------------------------------- #
# Settings                                                                     #
# --------------------------------------------------------------------------- #
def test_settings_public_symbols() -> None:
    """`asyncflow.settings` exposes SimulationSettings."""
    _assert_all_equals("asyncflow.settings", ["SimulationSettings"])


def test_settings_symbol_is_importable_class() -> None:
    """Public symbol is importable and is a class."""
    assert isinstance(SimulationSettings, type), "must be a class"
    assert SimulationSettings.__name__ == "SimulationSettings"
