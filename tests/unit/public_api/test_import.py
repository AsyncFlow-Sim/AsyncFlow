"""Unit tests for the public components import surface.

Verifies that:
- `asyncflow.components` exposes the expected `__all__`.
- All symbols in `__all__` are importable and are classes.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from asyncflow.components import (
    Client,
    Edge,
    Endpoint,
    LoadBalancer,
    Server,
    ServerResources,
)
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator, RVConfig

if TYPE_CHECKING:
    from collections.abc import Iterable



def _assert_all_equals(module_name: str, expected: Iterable[str]) -> None:
    """Assert that a module's __all__ exactly matches `expected`."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "__all__"), f"{module_name} is missing __all__"
    assert set(mod.__all__) == set(expected), (
        f"{module_name}.__all__ mismatch:\n"
        f"  expected: {set(expected)}\n"
        f"  actual:   {set(mod.__all__)}"
    )


def test_components_public_symbols() -> None:
    """`asyncflow.components` exposes the expected names."""
    expected = [
        "Client",
        "Edge",
        "Endpoint",
        "LoadBalancer",
        "Server",
        "ServerResources",
    ]
    _assert_all_equals("asyncflow.components", expected)


def test_components_symbols_are_importable_classes() -> None:
    """All public symbols are importable and are classes."""
    # Basic type sanity (avoid heavy imports/instantiation)
    for cls, name in [
        (Client, "Client"),
        (Edge, "Edge"),
        (Endpoint, "Endpoint"),
        (LoadBalancer, "LoadBalancer"),
        (Server, "Server"),
        (ServerResources, "ServerResources"),
    ]:
        assert isinstance(cls, type), f"{name} should be a class type"
        assert cls.__name__ == name

def test_workload_public_symbols() -> None:
    """`asyncflow.workload` exposes RVConfig and RqsGenerator."""
    _assert_all_equals("asyncflow.workload", ["RVConfig", "RqsGenerator"])


def test_workload_symbols_are_importable_classes() -> None:
    """Public symbols are importable and are classes."""
    for cls, name in [(RVConfig, "RVConfig"), (RqsGenerator, "RqsGenerator")]:
        assert isinstance(cls, type), f"{name} should be a class"
        assert cls.__name__ == name

def test_settings_public_symbols() -> None:
    """`asyncflow.settings` exposes SimulationSettings."""
    _assert_all_equals("asyncflow.settings", ["SimulationSettings"])


def test_settings_symbol_is_importable_class() -> None:
    """Public symbol is importable and is a class."""
    assert isinstance(SimulationSettings, type), "SimulationSettings should be a class"
    assert SimulationSettings.__name__ == "SimulationSettings"
