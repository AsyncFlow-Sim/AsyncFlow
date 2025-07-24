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
    StepOperation,
)


class Step(BaseModel):
    """
    Steps to be executed inside an endpoint in terms of
    the resources needed to accomplish the single step
    """

    kind: EndpointStepIO | EndpointStepCPU | EndpointStepRAM
    step_operation: dict[StepOperation, PositiveFloat | PositiveInt]

    @field_validator("step_operation", mode="before")
    def ensure_non_empty(
        cls, # noqa: N805
        v: dict[StepOperation, PositiveFloat | PositiveInt],
        ) -> dict[StepOperation, PositiveFloat | PositiveInt]:
        """Ensure the dict step operation exist"""
        if not v:
            msg = "step_operation cannot be empty"
            raise ValueError(msg)
        return v

    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_coherence_type_operation(
        cls, # noqa: N805
        model: "Step",
        ) -> "Step":
        """
        Validation to couple kind and operation only when they are
        valid for example ram cannot have associated a cpu time
        """
        operation_keys = set(model.step_operation)

        # Control of the length of the set to be sure only on key is passed
        if len(operation_keys) != 1:
            msg = "step_operation must contain exactly one entry"
            raise ValueError(msg)

        # Coherence CPU bound operation and operation
        if isinstance(model.kind, EndpointStepCPU):
            if operation_keys != {StepOperation.CPU_TIME}:
                msg = (
                        "The operation to quantify a CPU BOUND step"
                        f"must be {StepOperation.CPU_TIME}"
                    )
                raise ValueError(msg)

        # Coherence RAM operation and operation
        elif isinstance(model.kind, EndpointStepRAM):
            if operation_keys != {StepOperation.NECESSARY_RAM}:
                msg = (
                       "The operation to quantify a RAM step"
                       f"must be {StepOperation.NECESSARY_RAM}"
                    )
                raise ValueError(msg)

        # Coherence I/O operation and operation
        elif operation_keys != {StepOperation.IO_WAITING_TIME}:
            msg = (
                "The operation to quantify an I/O step"
                f"must be {StepOperation.IO_WAITING_TIME}"
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


