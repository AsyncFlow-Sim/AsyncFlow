"""
Application-wide constants and configuration values.

This module groups all the *static* enumerations used by the FastSim backend
so that:

* JSON / YAML payloads can be strictly validated with Pydantic.
* Front-end and simulation engine share a single source of truth.
* Ruff, mypy and IDEs can leverage the strong typing provided by Enum classes.

**IMPORTANT:** Changing any enum *value* is a breaking-change for every
stored configuration file.  Add new members whenever possible instead of
renaming existing ones.
"""

from enum import IntEnum, StrEnum

# ======================================================================
# CONSTANTS FOR THE REQUEST-GENERATOR COMPONENT
# ======================================================================


class TimeDefaults(IntEnum):
    """
    Default time-related constants (expressed in **seconds**).

    These values are used when the user omits an explicit parameter.  They also
    serve as lower / upper bounds for validation for the requests generator.
    """

    MIN_TO_SEC = 60                     # 1 minute  → 60 s
    USER_SAMPLING_WINDOW = 60           # keep U(t) constant for 60 s
    SIMULATION_TIME = 3_600             # run 1 h if user gives no value
    MIN_SIMULATION_TIME = 1_800         # enforce at least 30 min
    MIN_USER_SAMPLING_WINDOW = 1        # 1 s minimum
    MAX_USER_SAMPLING_WINDOW = 120      # 2 min maximum


class Distribution(StrEnum):
    """
    Probability distributions accepted by :class:`~app.schemas.RVConfig`.

    The *string value* is exactly the identifier that must appear in JSON
    payloads.  The simulation engine will map each name to the corresponding
    random sampler (e.g. ``numpy.random.poisson``).
    """

    POISSON = "poisson"
    NORMAL = "normal"
    LOG_NORMAL = "log_normal"
    EXPONENTIAL = "exponential"

# ======================================================================
# CONSTANTS FOR ENDPOINT STEP DEFINITION (REQUEST-HANDLER)
# ======================================================================

# The JSON received by the API for an endpoint step is expected to look like:
#
# {
#   "endpoint_name": "/predict",
#   "kind": "io_llm",
#   "metrics": {
#       "cpu_time": 0.150,
#       "necessary_ram": 256
#   }
# }
#
# The Enum classes below guarantee that only valid *kind* and *metric* keys
# are accepted by the Pydantic schema.


class EndpointIO(StrEnum):
    """
    I/O-bound operation categories that can occur inside an endpoint *step*.

    .. list-table::
       :header-rows: 1

       * - Constant
         - Meaning (executed by coroutine)
       * - ``TASK_SPAWN``
         - Spawns an additional ``asyncio.Task`` and returns immediately.
       * - ``LLM``
         - Performs a remote Large-Language-Model inference call.
       * - ``WAIT``
         - Passive, *non-blocking* wait for I/O completion; no new task spawned.
       * - ``DB``
         - Round-trip to a relational / NoSQL database.
       * - ``CACHE``
         - Access to a local or distributed cache layer.

    The *value* of each member (``"io_llm"``, ``"io_db"``, …) is the exact
    identifier expected in external JSON.
    """

    TASK_SPAWN = "io_task_spawn"
    LLM        = "io_llm"
    WAIT       = "io_wait"
    DB         = "io_db"
    CACHE      = "io_cache"


class EndpointCPU(StrEnum):
    """
    CPU-bound operation categories inside an endpoint step.

    Use these when the coroutine keeps the Python interpreter busy
    (GIL-bound or compute-heavy code) rather than waiting for I/O.
    """

    INITIAL_PARSING      = "initial_parsing"
    CPU_BOUND_OPERATION  = "cpu_bound_operation"


class EndpointRAM(StrEnum):
    """
    Memory-related operations inside a step.

    Currently limited to a single category, but kept as an Enum so that future
    resource types (e.g. GPU memory) can be added without schema changes.
    """

    RAM = "ram"


class MetricKeys(StrEnum):
    """
    Keys used inside the ``metrics`` dictionary of a *step*.

    * ``NETWORK_LATENCY`` - Mean latency (seconds) incurred on a network edge
      *outside* the service (used mainly for validation when steps model
      short in-service hops).
    * ``CPU_TIME`` - Service time (seconds) during which the coroutine occupies
      the CPU / GIL.
    * ``NECESSARY_RAM`` - Peak memory (MB) required by the step.
    """

    NETWORK_LATENCY = "network_latency"
    CPU_TIME        = "cpu_time"
    NECESSARY_RAM   = "necessary_ram"

# ======================================================================
# CONSTANTS FOR THE RESOURCES OF A SERVER
# ======================================================================

class ServerResourcesDefaults:
    """Resources available for a single server"""

    CPU_CORES = 1
    MINIMUM_CPU_CORES = 1
    RAM_MB = 1024
    MINIMUM_RAM_MB = 256
    DB_CONNECTION_POOL = None

# ======================================================================
# CONSTANTS FOR THE MACRO-TOPOLOGY GRAPH
# ======================================================================

class SystemNodes(StrEnum):
    """
    High-level node categories of the system topology graph.

    Each member represents a *macro-component* that may have its own SimPy
    resources (CPU cores, DB pool, etc.).
    """

    SERVER        = "server"
    CLIENT        = "client"
    LOAD_BALANCER = "load_balancer"
    API_GATEWAY   = "api_gateway"
    DATABASE      = "database"
    CACHE         = "cache"


class SystemEdges(StrEnum):
    """
    Edge categories connecting different :class:`SystemNodes`.

    Currently only network links are modeled; new types (IPC queue, message
    bus, stream) can be added without impacting existing payloads.
    """

    NETWORK_CONNECTION = "network_connection"
