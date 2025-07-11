"""Application constants and configuration values."""

from enum import IntEnum, StrEnum

# --------------------------------------------------------
# CONSTANTS FOR THE REQUESTS GENERATOR
# --------------------------------------------------------

class TimeDefaults(IntEnum):
    """Default time-related constants (all in seconds)."""

    MIN_TO_SEC = 60 # 1 minute → 60 s
    USER_SAMPLING_WINDOW = 60 # keep U(t) constant for 60 s, default
    SIMULATION_TIME = 3_600  # run 1 h if user gives no other value
    MIN_SIMULATION_TIME = 1800 # min simulation time
    MIN_USER_SAMPLING_WINDOW = 1 # 1 second
    MAX_USER_SAMPLING_WINDOW = 120 # 2 minutes


class Distribution(StrEnum):
    """Allowed probability distributions for an RVConfig."""

    POISSON = "poisson"
    NORMAL = "normal"

# --------------------------------------------------------
# CONSTANTS FOR THE REQUESTS ENDPOINT STRUCTURE IN THE
# REQUESTS HANDLER
# --------------------------------------------------------

# Idea here is to create an ordered nested dict with
# this structure: {endpoint_name: {
    #                        operation_type:
    #                           latency (s)/ram (kb): value}}
# we need Enum to have a better control on the dict keys in the
# pydantic schema

class EndpointIO(StrEnum):
    """Name of I/O operations"""

    IO_WITH_CHILD = "io_new_coroutine" #Child task exit
    IO_LLM_BOUND = "io_llm" # Llm speicif task
    IO_SLEEP = "i/o_bound"  # No child task


class EndpointCPU(StrEnum):
    """Name of CPU bound operations"""

    INITIAL_PARSING = "initial_parsing"
    CPU_BOUND_OPERATION = "cpu_bound_operation"


class EndpointRAM(StrEnum):
    """Name of the operation to add ram"""

    RAM = "ram"


class MetricKeys(StrEnum):
    """
    Name of the key to quantify the operation
    in terms of Ram or latency
    """

    LATENCY = "latency"
    NECESSARY_RAM = "necessary_ram"

