"""Application constants and configuration values."""

from enum import IntEnum


class TimeDefaults(IntEnum):
    """Default time-related constants (all in seconds)."""

    MIN_TO_SEC = 60 # 1 minute → 60 s
    USER_SAMPLING_WINDOW = 60 # keep U(t) constant for 60 s, default
    SIMULATION_TIME = 3_600  # run 1 h if user gives no other value
    MIN_SIMULATION_TIME = 1800 # min simulation time
    MIN_USER_SAMPLING_WINDOW = 1 # 1 second
    MAX_USER_SAMPLING_WINDOW = 120 # 2 minutes
