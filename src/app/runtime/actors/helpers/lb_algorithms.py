"""algorithms to simulate the load balancer during the simulation"""



from app.runtime.actors.edge import EdgeRuntime


def least_connections(list_edges: list[EdgeRuntime]) -> EdgeRuntime:
    """We send the state to the edge with less concurrent connections"""
    concurrent_connections = [edge.concurrent_connections for edge in list_edges]

    idx_min = concurrent_connections.index(min(concurrent_connections))

    return list_edges[idx_min]

def round_robin(edges: list[EdgeRuntime], idx: int) -> tuple[EdgeRuntime, int]:
    """
    We send states to different server in uniform way by
    rotating the list of edges that should transport the state
    to the correct server, we rotate the index and not the list
    to avoid aliasing since the list is shared by many components
    """
    idx %= len(edges)
    chosen = edges[idx]
    idx = (idx + 1) % len(edges)
    return chosen, idx




