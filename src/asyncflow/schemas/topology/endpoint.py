"""Defining the input schema for the requests handler"""

from pydantic import (
    BaseModel,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

from asyncflow.config.enums import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    StepOperation,
)
from asyncflow.schemas.common.random_variables import RVConfig


class Step(BaseModel):
    """
    Steps to be executed inside an endpoint in terms of
    the resources needed to accomplish the single step
    """

    kind: EndpointStepIO | EndpointStepCPU | EndpointStepRAM
    step_operation: dict[StepOperation, PositiveFloat | PositiveInt | RVConfig]

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
        if (
            isinstance(model.kind, EndpointStepCPU)
            and operation_keys != {StepOperation.CPU_TIME}
        ):
                msg = (
                        "The operation to quantify a CPU BOUND step"
                        f"must be {StepOperation.CPU_TIME}"
                    )
                raise ValueError(msg)

        # Coherence RAM operation and operation
        if (
            isinstance(model.kind, EndpointStepRAM)
            and operation_keys != {StepOperation.NECESSARY_RAM}
        ):
                msg = (
                       "The operation to quantify a RAM step"
                       f"must be {StepOperation.NECESSARY_RAM}"
                    )
                raise ValueError(msg)

        # Coherence I/O operation and operation
        if (
            isinstance(model.kind, EndpointStepIO)
            and operation_keys != {StepOperation.IO_WAITING_TIME}
        ):

            msg = f"An I/O step must use {StepOperation.IO_WAITING_TIME}"
            raise ValueError(msg)

        return model

    @model_validator(mode="after")  # type: ignore[arg-type]
    def ensure_cpu_io_positive_rv(cls, model: "Step") -> "Step":  # noqa: N805
        """
        For CPU/IO steps: if the operation is an RVConfig, require mean > 0
        and variance ≥ 0. Deterministic PositiveFloat è già validato.
        """
        # safe anche se per qualche motivo ci fossero 0/2+ chiavi
        op_val = next(iter(model.step_operation.values()), None)
        if op_val is None:
            return model

        if isinstance(model.kind, EndpointStepCPU) and isinstance(op_val, RVConfig):
            if op_val.mean <= 0:
                msg = "CPU_TIME RVConfig.mean must be > 0"
                raise ValueError(msg)
            if op_val.variance is not None and op_val.variance < 0:
                msg = "CPU_TIME RVConfig.variance must be >= 0"
                raise ValueError(msg)

        if isinstance(model.kind, EndpointStepIO) and isinstance(op_val, RVConfig):
            if op_val.mean <= 0:
                msg = "IO_WAITING_TIME RVConfig.mean must be > 0"
                raise ValueError(msg)
            if op_val.variance is not None and op_val.variance < 0:
                msg = "IO_WAITING_TIME RVConfig.variance must be >= 0"
                raise ValueError(msg)

        return model

    @model_validator(mode="after")  # type: ignore[arg-type]
    def ensure_ram_positive_int(cls, model: "Step") -> "Step":  # noqa: N805
        """For RAM steps: operation must be a positive integer (no RVs/floats)"""
        if not isinstance(model.kind, EndpointStepRAM):
            return model

        op_val = next(iter(model.step_operation.values()), None)
        if op_val is None:
            return model

        if isinstance(op_val, RVConfig) or not isinstance(op_val, int):
            msg = "NECESSARY_RAM must be a positive integer"
            raise TypeError(msg)

        if op_val <= 0:
            msg = "NECESSARY_RAM must be > 0"
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


