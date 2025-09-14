"""
Application-wide constants and configuration values.

This module groups all the static enumerations used by the AsyncFlow backend
so that:

 JSON / YAML payloads can be strictly validated with Pydantic.
 Front-end and simulation engine share a single source of truth.
 Ruff, mypy and IDEs can leverage the strong typing provided by Enum classes.
"""

from __future__ import annotations

from typing import Final  # needed for type-hinted module constants

from asyncflow.config.enums import VariabilityLevel

# ======================================================================
# CONSTANTS FOR THE RESOURCES OF A SERVER
# ======================================================================

class NodesResourcesDefaults:
    """Resources available for a single server"""

    CPU_CORES = 1
    MINIMUM_CPU_CORES = 1
    RAM_MB = 1024
    MINIMUM_RAM_MB = 256
    DB_CONNECTION_POOL = None


# ======================================================================
# CONSTANTS FOR NETWORK PARAMETERS
# ======================================================================

class NetworkParameters:
    """Parameters for the network."""

    MIN_DROPOUT_RATE = 0.0
    DROPOUT_RATE = 0.01
    MAX_DROPOUT_RATE = 1.0


# ======================================================================
# CONSTANTS FOR ARRIVAL VARIABILITY PRESETS (shared across samplers)
# ======================================================================

SCV_PRESETS: Final[dict[VariabilityLevel, float]] = {
    VariabilityLevel.LOW: 0.25,
    VariabilityLevel.MEDIUM: 1.0,
    VariabilityLevel.HIGH: 4.0,
}


# ======================================================================
# DERIVED SAMPLER TUNING CONSTANTS
# ======================================================================
class Tuning:
  """class of constants to tune behaviour of arrivals sampler"""

  PARETO_ALPHA_EPS: Final[float] = 1e-6   # ensure finite variance: alpha > 2
  WEIBULL_K_LOW: Final[float] = 2.10      # matches SCV≈0.25
  WEIBULL_K_MED: Final[float] = 1.0       # SCV=1 (exponential)
  WEIBULL_K_HIGH: Final[float] = 0.543    # matches SCV≈4
  UNIFORM_REL_HALF_WIDTH: Final[float] = 0.5  # c2 = w^2 / 3 ≈ 0.0833
