"""
initialization of the structure to gather the metrics
for the client of the system
"""

from typing import NamedTuple


class RqsClock(NamedTuple):
    """
    structure to register time of generation and
    time of elaboration for each request
    """

    start: float
    finish: float


