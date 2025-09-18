"""Unit tests for QueueTheoryBase base class.

Covers:
- is_compatible() truthiness for compatible/incompatible analyzers
- validate_or_raise() no-op vs ValueError with exact message
- Abstract method enforcement (cannot instantiate without override)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from asyncflow.queue_theory_analysis.base import QueueTheoryBase

if TYPE_CHECKING:
    from asyncflow.schemas.payload import SimulationPayload


class AlwaysCompatible(QueueTheoryBase):
    """Dummy analyzer that is always compatible."""

    def explain_incompatibilities(
        self,
        _: SimulationPayload,
    ) -> list[str]:
        """Return an empty list → compatible."""
        return []


class AlwaysIncompatible(QueueTheoryBase):
    """Dummy analyzer that always reports the provided reasons."""

    def __init__(self, reasons: list[str] | None = None) -> None:
        """Store reasons to be returned by explain_incompatibilities()."""
        self._reasons = reasons or ["incompat-1", "incompat-2"]

    def explain_incompatibilities(
        self,
        _: SimulationPayload,
    ) -> list[str]:
        """Return a copy of the stored reasons."""
        return list(self._reasons)


def test_is_compatible_true_and_validate_noop() -> None:
    """When no reasons, compatible=True and validate_or_raise is no-op."""
    payload = cast("SimulationPayload", object())
    an = AlwaysCompatible()

    assert an.is_compatible(payload) is True
    assert an.explain_incompatibilities(payload) == []

    # Must not raise
    an.validate_or_raise(payload)


def test_is_compatible_false_and_validate_raises_with_message() -> None:
    """validate_or_raise must raise with bullet-formatted reasons."""
    payload = cast("SimulationPayload", object())
    reasons = ["topology must include at least one edge.", "c must be >= 1."]
    an = AlwaysIncompatible(reasons)

    assert an.is_compatible(payload) is False

    with pytest.raises(
        ValueError,
        match=r"^Payload is not compatible with this queueing model:",
    ) as exc:
        an.validate_or_raise(payload)

    msg = str(exc.value)
    expected = (
        "Payload is not compatible with this queueing model:\n"
        " - topology must include at least one edge.\n"
        " - c must be >= 1."
    )
    assert msg == expected


def test_abstract_enforcement_prevents_instantiation() -> None:
    """A subclass without explain_incompatibilities cannot be instantiated."""

    class BrokenAnalyzer(QueueTheoryBase):
        """Intentionally missing explain_incompatibilities()."""


    with pytest.raises(TypeError, match="Can't instantiate"):
        BrokenAnalyzer()  # type: ignore[abstract]
