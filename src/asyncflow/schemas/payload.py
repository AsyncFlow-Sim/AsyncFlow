"""Definition of the full input for the simulation"""

from pydantic import BaseModel, field_validator, model_validator

from asyncflow.schemas.event.injection import EventInjection
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.workload.rqs_generator import RqsGenerator
from asyncflow.config.constants import EventDescription


class SimulationPayload(BaseModel):
    """Full input structure to perform a simulation"""

    rqs_input: RqsGenerator
    topology_graph: TopologyGraph
    sim_settings: SimulationSettings
    events: list[EventInjection] | None = None

    @field_validator("events", mode="after")
    def ensure_event_id_is_unique(
        cls, # noqa: N805
        v: list[EventInjection] | None,
        ) -> list[EventInjection] | None:
        """Ensure the id uniqueness of the events id"""
        if v is None:
            return v

        event_id = [event.event_id for event in v]
        set_event_id = set(event_id)

        if len(event_id) != len(set_event_id):
            msg = "The id's representing different events must be unique"
            raise ValueError(msg)
        return v

    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_components_ids_is_compatible(
        cls, # noqa: N805
        model: "SimulationPayload",
        ) -> "SimulationPayload":
        """
        Ensure the id related to the target component of the event
        exist
        """
        if model.events is None:
            return model

        servers_list = model.topology_graph.nodes.servers
        edges_list = model.topology_graph.edges
        valid_ids = (
            {server.id for server in servers_list}
            | {edge.id for edge in edges_list}
        )

        for event in model.events:
            if event.target_id not in valid_ids:
                msg = (f"The target id {event.target_id} related to "
                       f"the event {event.event_id} does not exist")
                raise ValueError(msg)

        return model
    
    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_event_time_inside_simulation_horizon(
        cls, # noqa: N805
        model: "SimulationPayload",
        ) -> "SimulationPayload":
        """
        The time interval associated to each event must be in
        the simulation horizon
        """
        if model.events is None:
            return model

        horizon = float(model.sim_settings.total_simulation_time)

        for ev in model.events:
            t_start = ev.start.t_start
            t_end = ev.end.t_end

            if t_start < 0.0:
                msg = (
                    f"Event '{ev.event_id}': start time t_start={t_start:.6f} "
                    "must be >= 0.0"
                )
                raise ValueError(msg)

            if t_start > horizon:
                msg = (
                    f"Event '{ev.event_id}': start time t_start={t_start:.6f} "
                    f"exceeds simulation horizon T={horizon:.6f}"
                )
                raise ValueError(msg)

            # t_end is PositiveFloat by schema, but still guard the horizon.
            if t_end > horizon:
                msg = (
                    f"Event '{ev.event_id}': end time t_end={t_end:.6f} "
                    f"exceeds simulation horizon T={horizon:.6f}"
                )
                raise ValueError(msg)

        return model
    
    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_compatibility_event_kind_target_id(
        cls, # noqa: N805
        model: "SimulationPayload",
        ) -> "SimulationPayload":
        """
        The kind of the event must be compatible with the target id
        type, for example we cannot have an event regarding a server
        with a target id associated to an edge
        """
        if model.events is None:
            return model
        
        servers_list = model.topology_graph.nodes.servers
        edges_list = model.topology_graph.edges
        
        # We need just the Start or End kind because
        # we have a validation for the coherence between
        # the starting event kind and the finishing event kind
        server_kind = {EventDescription.SERVER_DOWN}
        edge_kind = {EventDescription.NETWORK_SPIKE_START}
        
        servers_ids = {server.id for server in servers_list}
        edges_ids = {edge.id for edge in edges_list}
        
        for event in model.events:
            if event.start.kind in server_kind and event.target_id not in servers_ids:
                msg = (f"The event {event.event_id} regarding a server does not have " 
                      "a compatible target id")
                raise ValueError(msg)
            elif event.start.kind in edge_kind and event.target_id not in edges_ids:
                msg = (f"The event {event.event_id} regarding an edge does not have "
                      "a compatible target id")
                raise ValueError(msg)
                
            
        return model
    
    
    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_not_all_servers_are_down_simultaneously(
        cls, # noqa: N805
        model: "SimulationPayload",
        ) -> "SimulationPayload":
        """
        We will not accept the condition to have all server down
        at the same moment, always at least one server must be up 
        and running
        """
        
        if model.events is None:
            return model
        
        # First let us build a list of events related to the servers
        servers_list = model.topology_graph.nodes.servers
        servers_ids = {server.id for server in servers_list}
        server_events = [
            event for event in model.events 
            if event.target_id in servers_ids
        ]
        
        # Helpers needed in the algorithm to define a specific ordering
        # procedure
        START = "start"
        END = "end"
        
        # Let us define a list of tuple as a timeline, this approach ensure
        # the possibility to have different servers going up or down at the
        # same time, a more elegant approach through an hashmap has been
        # considered however it would require an extra assumption that all
        # the times had to be different, we thought that this would be too
        # strict
        timeline = []
        for event in server_events:
            timeline.append((event.start.t_start, START, event.target_id))
            timeline.append((event.end.t_end, END, event.target_id))

        # Let us order the timeline by time if there are multiple events at the
        # same time process first the end type events
        timeline.sort(key=lambda x: (x[0], x[1] == START))

        # Definition of a set to verify the condition that at least one server must 
        # be up
        server_down = set()
        for time, kind, server_id in timeline:
            if kind == START:
                server_down.discard(server_id)
            else:  # "start"
                server_down.add(server_id)
                if len(server_down) == len(servers_ids):
                    raise ValueError(
                        f"At time {time:.6f} all servers are down; keep at least one up."
                    )
            
        return model
    

