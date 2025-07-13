"""Defining the input schema for the requests handler"""

from pydantic import (
    BaseModel,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

from app.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    Metrics,
)


class Step(BaseModel):
    """
    Steps to be executed inside an endpoint in terms of
    the resources needed to accomplish the single step
    """

    kind: EndpointStepIO | EndpointStepCPU | EndpointStepRAM
    step_metrics: dict[Metrics, PositiveFloat | PositiveInt]

    @field_validator("step_metrics", mode="before")
    def ensure_non_empty(
        cls, # noqa: N805
        v: dict[Metrics, PositiveFloat | PositiveInt],
        ) -> dict[Metrics, PositiveFloat | PositiveInt]:
        """Ensure the dict step metrics exist"""
        if not v:
            msg = "step_metrics cannot be empty"
            raise ValueError(msg)
        return v

    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_coherence_kind_metrics(
        cls, # noqa: N805
        model: "Step",
        ) -> "Step":
        """
        Validation to couple kind and metrics only when they are
        valid for example ram cannot have associated a cpu time
        """
        metrics_keys = set(model.step_metrics)

        # Control of the length of the set to be sure only on key is passed
        if len(metrics_keys) != 1:
            msg = "step_metrics must contain exactly one entry"
            raise ValueError(msg)

        # Coherence CPU bound operation and metric
        if isinstance(model.kind, EndpointStepCPU):
            if metrics_keys != {Metrics.CPU_TIME}:
                msg = (
                        "The metric to quantify a CPU BOUND step"
                        f"must be {Metrics.CPU_TIME}"
                    )
                raise ValueError(msg)

        # Coherence RAM operation and metric
        elif isinstance(model.kind, EndpointStepRAM):
            if metrics_keys != {Metrics.NECESSARY_RAM}:
                msg = (
                       "The metric to quantify a RAM step"
                       f"must be {Metrics.NECESSARY_RAM}"
                    )
                raise ValueError(msg)

        # Coherence I/O operation and metric
        elif metrics_keys != {Metrics.IO_WAITING_TIME}:
            msg = (
                "The metric to quantify an I/O step"
                f"must be {Metrics.IO_WAITING_TIME}"
            )
            raise ValueError(msg)

        return model




class Endpoint(BaseModel):
    """full endpoint structure to be validated with pydantic"""

    endpoint_name: str
    steps: list[Step]

    @field_validator("endpoint_name", mode="before")
    def name_to_lower(cls, v: str) -> str: # noqa: N805
        """Standardize endpoint name to be lowercase"""
        return v.lower()


