"""
Unit tests for the Edge schema.

Covers:
- Required fields and defaults
- Source/target validator
- Dropout rate bounds
- Latency validator for both deterministic (PositiveFloat) and RVConfig cases
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asyncflow.config.constants import NetworkParameters, SystemEdges
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.topology.edges import Edge

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _rv(mean: float, variance: float | None = None) -> RVConfig:
    """Build a minimal RVConfig with mean and optional variance."""
    return RVConfig(mean=mean, variance=variance)


# --------------------------------------------------------------------------- #
# Basic construction and defaults                                             #
# --------------------------------------------------------------------------- #


def test_edge_minimal_construction_uses_default_edge_type() -> None:
    """Minimal valid Edge uses NETWORK_CONNECTION as default edge_type."""
    e = Edge(
        id="e1",
        source="a",
        target="b",
        latency=_rv(mean=0.01),
    )
    assert e.edge_type is SystemEdges.NETWORK_CONNECTION


def test_edge_requires_id_source_target() -> None:
    """Omitting required fields raises ValidationError."""
    with pytest.raises(ValidationError):
        Edge(  # type: ignore[call-arg]
            source="a",
            target="b",
            latency=_rv(mean=0.01),
        )
    with pytest.raises(ValidationError):
        Edge(  # type: ignore[call-arg]
            id="e1",
            target="b",
            latency=_rv(mean=0.01),
        )
    with pytest.raises(ValidationError):
        Edge(  # type: ignore[call-arg]
            id="e1",
            source="a",
            latency=_rv(mean=0.01),
        )


# --------------------------------------------------------------------------- #
# Source != Target                                                            #
# --------------------------------------------------------------------------- #


def test_edge_source_equals_target_fails() -> None:
    """Validator forbids identical source and target."""
    with pytest.raises(ValidationError):
        Edge(
            id="loop",
            source="x",
            target="x",
            latency=_rv(mean=0.01),
        )


# --------------------------------------------------------------------------- #
# Dropout rate bounds                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad_rate",
    [-0.001, NetworkParameters.MAX_DROPOUT_RATE + 1e-6],
)
def test_edge_dropout_rate_out_of_bounds(bad_rate: float) -> None:
    """Dropout rate outside configured bounds is rejected."""
    with pytest.raises(ValidationError):
        Edge(
            id="ed",
            source="a",
            target="b",
            latency=_rv(mean=0.01),
            dropout_rate=bad_rate,
        )


@pytest.mark.parametrize(
    "ok_rate",
    [
        NetworkParameters.MIN_DROPOUT_RATE,
        NetworkParameters.MAX_DROPOUT_RATE,
        (NetworkParameters.MIN_DROPOUT_RATE + NetworkParameters.MAX_DROPOUT_RATE) / 2,
    ],
)
def test_edge_dropout_rate_in_bounds(ok_rate: float) -> None:
    """Boundary and mid-range dropout rates are accepted."""
    e = Edge(
        id="ed",
        source="a",
        target="b",
        latency=_rv(mean=0.01),
        dropout_rate=ok_rate,
    )
    assert e.dropout_rate == ok_rate


# --------------------------------------------------------------------------- #
# Latency validation: deterministic (PositiveFloat)                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("good_latency", [0.001, 0.1, 5.0])
def test_edge_deterministic_latency_positivefloat_ok(good_latency: float) -> None:
    """Deterministic latency validates as PositiveFloat when > 0."""
    e = Edge(
        id="dt",
        source="a",
        target="b",
        latency=good_latency,
    )
    # pydantic casts PositiveFloat to float at runtime
    assert isinstance(e.latency, float)
    assert e.latency == good_latency


@pytest.mark.parametrize("bad_latency", [0.0, -0.001, -5.0])
def test_edge_deterministic_latency_non_positive_fails(bad_latency: float) -> None:
    """Non-positive deterministic latency is rejected by PositiveFloat."""
    with pytest.raises(ValidationError):
        Edge(
            id="dt-bad",
            source="a",
            target="b",
            latency=bad_latency,
    )


# --------------------------------------------------------------------------- #
# Latency validation: RVConfig branch                                         #
# --------------------------------------------------------------------------- #


def test_edge_rvconfig_latency_ok_with_zero_variance() -> None:
    """RVConfig with mean>0 and variance==0 is accepted."""
    e = Edge(
        id="rv0",
        source="a",
        target="b",
        latency=_rv(mean=0.02, variance=0.0),
    )
    assert isinstance(e.latency, RVConfig)
    assert e.latency.mean == 0.02
    assert e.latency.variance == 0.0


def test_edge_rvconfig_latency_ok_with_none_variance() -> None:
    """RVConfig with mean>0 and variance=None is accepted."""
    e = Edge(
        id="rvn",
        source="a",
        target="b",
        latency=_rv(mean=0.02, variance=None),
    )
    assert isinstance(e.latency, RVConfig)
    assert e.latency.mean == 0.02
    assert e.latency.variance is None


@pytest.mark.parametrize("bad_mean", [0.0, -1e-9, -1.0])
def test_edge_rvconfig_latency_non_positive_mean_fails(bad_mean: float) -> None:
    """RVConfig with non-positive mean is rejected by the field validator."""
    with pytest.raises(ValidationError):
        Edge(
            id="rv-bad-mean",
            source="a",
            target="b",
            latency=_rv(mean=bad_mean, variance=0.0),
        )


def test_edge_rvconfig_latency_negative_variance_fails() -> None:
    """RVConfig with negative variance is rejected by the field validator."""
    with pytest.raises(ValidationError):
        Edge(
            id="rv-bad-var",
            source="a",
            target="b",
            latency=_rv(mean=0.02, variance=-0.0001),
        )
