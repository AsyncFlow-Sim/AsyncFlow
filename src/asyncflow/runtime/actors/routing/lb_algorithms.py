"""algorithms to simulate the load balancer during the simulation"""

from collections import OrderedDict
from collections.abc import Callable

from asyncflow.config.constants import LbAlgorithmsName
from asyncflow.runtime.actors.edge import EdgeRuntime


def least_connections(
    edges: OrderedDict[str, EdgeRuntime],
    ) -> EdgeRuntime:
    """Return the edge with the fewest concurrent connections"""
    # Here we use a O(n) operation, considering the amount of edges
    # for the average simulation it should be ok, however, in the
    # future we might consider to implement an heap structure to
    # reduce the time complexity, especially if we will see
    # during the Montecarlo analysis not good performances
    name = min(edges, key=lambda k: edges[k].concurrent_connections)
    return edges[name]

def round_robin(
    edges: OrderedDict[str, EdgeRuntime],
    ) -> EdgeRuntime:
    """
    We send states to different server in uniform way by
    rotating the ordered dict, given the pydantic validation
    we don't have to manage the edge case where the dict
    is empty
    """
    # we use iter next creating all time a new iterator
    # to be sure that we return always the first element
    key, value = next(iter(edges.items()))
    edges.move_to_end(key)

    return value


LB_TABLE: dict[LbAlgorithmsName,
               Callable[[OrderedDict[str, EdgeRuntime]], EdgeRuntime]] = {
    LbAlgorithmsName.LEAST_CONNECTIONS: least_connections,
    LbAlgorithmsName.ROUND_ROBIN: round_robin,
}


