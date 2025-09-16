"""algorithms to simulate the load balancer during the simulation"""
import random
from collections import OrderedDict
from collections.abc import Callable, Mapping

from asyncflow.config.enums import LbAlgorithmsName
from asyncflow.runtime.actors.edge import EdgeRuntime


def fcfs_picker(
    edges: OrderedDict[str, EdgeRuntime],
    busy: Mapping[str, int],
) -> tuple[str, EdgeRuntime] | None:
    """
    Return the first *free* edge in insertion order (busy == 0).
    Pure function: it does NOT mutate `edges`.

    It is intentionally a *picker* (not a mutator), so the LB can manage
    waiting and mark busy/free transitions without hidden side effects here.
    """
    for edge_id, edge_rt in edges.items():
        if busy.get(edge_id, 0) == 0:
            return edge_id, edge_rt
    return None

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

def random_choice(
    edges: OrderedDict[str, EdgeRuntime],
) -> EdgeRuntime:
    """Pick a random outgoing edge uniformly"""
    idx = random.randrange(len(edges)) # noqa: S311
    for i, edge in enumerate(edges.values()):
        if i == idx:
            return edge

    return next(iter(edges.values()))

LB_TABLE: dict[LbAlgorithmsName,
               Callable[[OrderedDict[str, EdgeRuntime]], EdgeRuntime]] = {
    LbAlgorithmsName.LEAST_CONNECTIONS: least_connections,
    LbAlgorithmsName.ROUND_ROBIN: round_robin,
    LbAlgorithmsName.RANDOM: random_choice,
}



