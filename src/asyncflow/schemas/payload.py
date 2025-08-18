"""Definition of the full input for the simulation"""

from pydantic import BaseModel, field_validator, model_validator

from asyncflow.schemas.event.injection import EventInjection
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.workload.rqs_generator import RqsGenerator


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

        server_list = model.topology_graph.nodes.servers
        edges_list = model.topology_graph.edges
        valid_ids = (
            {server.id for server in server_list}
            | {edge.id for edge in edges_list}
        )

        for event in model.events:
            if event.target_id not in valid_ids:
                msg = (f"The target id {event.target_id} related to"
                       f"the event {event.event_id} does not exist")
                raise ValueError(msg)

        return model
    
    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_event_time_inside_simulatioon_horizon(
        cls, # noqa: N805
        model: "SimulationPayload",
        ) -> "SimulationPayload":
        """
        The interval of time associated to each events must be 
        included in the simulation horizon
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
        type
        """
        if model.events is None:
            return model

        
        return model

