"""Application constants and configuration values."""

from enum import IntEnum


class TimeDefaults(IntEnum):
    """Default time-related constants (all in seconds)."""

    MIN_TO_SEC = 60            # 1 minute → 60 s
    SAMPLING_WINDOW = 60       # keep U(t) constant for 60 s
    SIMULATION_HORIZON = 3_600 # run 1 h if user gives no other value
