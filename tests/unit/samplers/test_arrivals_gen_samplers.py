"""Unit tests for inter-arrival samplers (arrival gap generators).

Covers:
* Horizon truncation (sum of gaps never exceeds the horizon).
* Families that ignore variability: EXPONENTIAL, POISSON, DETERMINISTIC,
  UNIFORM.
* Families that require variability: LOG_NORMAL, WEIBULL, PARETO, ERLANG.
* EMPIRICAL timestamps path, including validation errors.
* Determinism with seeded RNG where applicable.

All tests use minimal, observable properties (positivity, bounds, horizon)
rather than tight statistical checks, to keep them stable and fast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from asyncflow.config.enums import Distribution, VariabilityLevel
from asyncflow.samplers.arrivals import (
    _build_empirical_from_timestamps as build_empirical,
)
from asyncflow.samplers.arrivals import (
    general_interarrivals,
)
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator

if TYPE_CHECKING:
    from collections.abc import Iterable

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _collect_all(gaps: Iterable[float]) -> list[float]:
    """Materialize a finite generator/sequence into a list of floats."""
    return [float(x) for x in gaps]


def _mk_gen(
    *,
    model: Distribution,
    lambda_rps: float = 10.0,
    variability: VariabilityLevel | None = None,
    empirical: Iterable[float] | None = None,
) -> ArrivalsGenerator:
    """Small factory for ArrivalsGenerator respecting schema constraints."""
    return ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=lambda_rps,
        model=model,
        variability=variability,
        empirical_data=empirical,
    )


# --------------------------------------------------------------------------- #
# Horizon truncation & positivity                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("model", "var"),
    [
        (Distribution.EXPONENTIAL, None),
        (Distribution.POISSON, None),
        (Distribution.DETERMINISTIC, None),
        (Distribution.UNIFORM, None),
        (Distribution.LOG_NORMAL, VariabilityLevel.MEDIUM),
        (Distribution.WEIBULL, VariabilityLevel.MEDIUM),
        (Distribution.PARETO, VariabilityLevel.MEDIUM),
        (Distribution.ERLANG, VariabilityLevel.MEDIUM),
    ],
)
def test_horizon_truncation_and_positivity(model: Distribution,
                                           var: VariabilityLevel | None) -> None:
    """Sum of gaps never exceeds horizon; all gaps are strictly positive."""
    rng = np.random.default_rng(123)
    horizon = 3  # small to force truncation with moderate λ
    gen = _mk_gen(model=model, lambda_rps=5.0, variability=var)
    it = general_interarrivals(
        simulation_time_s=horizon,
        rng=rng,
        arrivals=gen,
    )
    gaps = _collect_all(it)

    assert all(g > 0.0 for g in gaps)
    total = sum(gaps)
    assert total <= float(horizon) + 1e-12  # numerical tolerance


# --------------------------------------------------------------------------- #
# Deterministic model                                                         #
# --------------------------------------------------------------------------- #

def test_deterministic_interarrivals_are_constant() -> None:
    """D(R=λ) produces constant period 1/λ and respects horizon."""
    rng = np.random.default_rng(0)
    lam = 4.0
    horizon = 5
    gen = _mk_gen(model=Distribution.DETERMINISTIC, lambda_rps=lam)
    gaps = _collect_all(
        general_interarrivals(simulation_time_s=horizon, rng=rng, arrivals=gen),
    )
    assert gaps  # at least one
    period = 1.0 / lam
    assert all(abs(g - period) < 1e-12 for g in gaps)
    assert sum(gaps) <= float(horizon) + 1e-12


# --------------------------------------------------------------------------- #
# Uniform model (bounded gap check)                                           #
# --------------------------------------------------------------------------- #

def test_uniform_interarrivals_are_within_band() -> None:
    """Uniform gaps stay within [mu*(1-w), mu*(1+w)] and respect horizon."""
    rng = np.random.default_rng(1)
    lam = 8.0
    mu = 1.0 / lam
    # The code uses Tuning.UNIFORM_REL_HALF_WIDTH, but we do not import it.
    # Check using a relaxed band around mu to avoid coupling on constants.
    loose = 0.5
    a = mu * (1.0 - loose)
    b = mu * (1.0 + loose)

    gen = _mk_gen(model=Distribution.UNIFORM, lambda_rps=lam)
    gaps = _collect_all(
        general_interarrivals(simulation_time_s=4, rng=rng, arrivals=gen),
    )
    assert gaps
    assert all(a <= g <= b for g in gaps)


# --------------------------------------------------------------------------- #
# Families that ignore variability                                            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(("model", "var"), [
    (Distribution.EXPONENTIAL, None),
    (Distribution.POISSON, None),
])
def test_models_ignore_variability_do_not_require_it(
    model: Distribution,
    var: VariabilityLevel | None,
) -> None:
    """EXPONENTIAL and POISSON work with variability=None per schema."""
    rng = np.random.default_rng(2)
    gen = _mk_gen(model=model, lambda_rps=6.0, variability=var)
    gaps = _collect_all(
        general_interarrivals(simulation_time_s=5, rng=rng, arrivals=gen),
    )
    assert gaps
    assert all(g > 0.0 for g in gaps)


# --------------------------------------------------------------------------- #
# Families that require variability                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "model",
    [
        Distribution.LOG_NORMAL,
        Distribution.WEIBULL,
        Distribution.PARETO,
        Distribution.ERLANG,
    ],
)
def test_models_require_variability_and_generate_positive_gaps(
    model: Distribution,
) -> None:
    """Models with tunable SCV require a level and produce positive gaps."""
    rng = np.random.default_rng(3)
    gen = _mk_gen(
        model=model,
        lambda_rps=5.0,
        variability=VariabilityLevel.LOW,
    )
    gaps = _collect_all(
        general_interarrivals(simulation_time_s=5, rng=rng, arrivals=gen),
    )
    assert gaps
    assert all(g > 0.0 for g in gaps)


# --------------------------------------------------------------------------- #
# EMPIRICAL timestamps path                                                   #
# --------------------------------------------------------------------------- #

def test_empirical_builds_gaps_from_timestamps_sorted() -> None:
    """First gap is t0-origin; remaining are consecutive differences."""
    ts = [0.5, 1.0, 2.2, 3.0]
    gaps = _collect_all(
        build_empirical(timestamps_s=ts, origin_s=0.0, assume_sorted=True),
    )
    assert gaps == pytest.approx([0.5, 0.5, 1.2, 0.8])


def test_empirical_discards_before_origin_and_sorts() -> None:
    """Timestamps < origin are discarded; input need not be sorted."""
    ts = [-1.0, 2.0, 1.0, 4.0, 3.0]
    gaps = _collect_all(
        build_empirical(timestamps_s=ts, origin_s=1.0, assume_sorted=False),
    )
    # Remaining timestamps: [1.0, 2.0, 3.0, 4.0]
    assert gaps == pytest.approx([0.0, 1.0, 1.0, 1.0])


def test_empirical_clamps_nonpositive_gaps_to_min() -> None:
    """Non-positive gaps are clamped to `clamp_min_s`."""
    ts = [1.0, 1.0, 1.000000001, 0.999999999, 2.0]
    gaps = _collect_all(
        build_empirical(
            timestamps_s=ts,
            origin_s=1.0,
            assume_sorted=True,
            clamp_min_s=0.01,
        ),
    )
    # first gap 0; second ~1e-9 (clamped); third negative (clamped)
    assert gaps[0] == pytest.approx(0.01)
    assert gaps[1] == pytest.approx(0.01)
    assert gaps[2] == pytest.approx(0.01)
    assert gaps[-1] > 0.01  # the 2.0 - 0.999999999 part


def test_empirical_errors_on_empty_sequence() -> None:
    """Empty empirical sequence is invalid."""
    with pytest.raises(ValueError, match="sequence is empty"):
        _ = _collect_all(build_empirical(timestamps_s=[], origin_s=0.0))


def test_empirical_errors_on_non_finite() -> None:
    """Non-finite values in empirical timestamps raise a ValueError."""
    ts = [0.1, float("nan"), 0.3]
    with pytest.raises(ValueError, match="non-finite value"):
        _ = _collect_all(build_empirical(timestamps_s=ts, origin_s=0.0))


def test_empirical_errors_when_all_before_origin() -> None:
    """If no timestamps are at/after origin, it raises a ValueError."""
    ts = [-2.0, -1.0, -0.5]
    with pytest.raises(ValueError, match="no timestamps at or after origin"):
        _ = _collect_all(build_empirical(timestamps_s=ts, origin_s=0.0))


def test_general_interarrivals_empirical_path_is_finite() -> None:
    """general_interarrivals returns a finite generator on EMPIRICAL model."""
    rng = np.random.default_rng(7)
    ts = [0.3, 0.9, 1.2]
    gen = _mk_gen(
        model=Distribution.EMPIRICAL,
        empirical=ts,
        lambda_rps=10.0,  # ignored for empirical
    )
    gaps = _collect_all(
        general_interarrivals(simulation_time_s=100, rng=rng, arrivals=gen),
    )
    assert gaps == pytest.approx([0.3, 0.6, 0.3])


# --------------------------------------------------------------------------- #
# Determinism (seeded RNG)                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("model", "var"),
    [
        (Distribution.EXPONENTIAL, None),
        (Distribution.POISSON, None),
        (Distribution.UNIFORM, None),
        (Distribution.LOG_NORMAL, VariabilityLevel.HIGH),
        (Distribution.WEIBULL, VariabilityLevel.LOW),
        (Distribution.PARETO, VariabilityLevel.MEDIUM),
        (Distribution.ERLANG, VariabilityLevel.MEDIUM),
    ],
)
def test_seeded_rng_reproducibility(model: Distribution,
                                    var: VariabilityLevel | None) -> None:
    """Same seed and inputs → identical gap sequences."""
    seed = 4242
    g1 = _mk_gen(model=model, lambda_rps=9.0, variability=var)
    g2 = _mk_gen(model=model, lambda_rps=9.0, variability=var)

    gaps1 = _collect_all(
        general_interarrivals(
            simulation_time_s=6, rng=np.random.default_rng(seed), arrivals=g1,
        ),
    )
    gaps2 = _collect_all(
        general_interarrivals(
            simulation_time_s=6, rng=np.random.default_rng(seed), arrivals=g2,
        ),
    )
    assert gaps1 == pytest.approx(gaps2)
