"""Defining the input schema for the requests handler"""

from pydantic import BaseModel, PositiveFloat, PositiveInt, field_validator

from app.config.constants import EndpointCPU, EndpointIO, EndpointRAM, MetricKeys


class Step(BaseModel):
    """Full step structure to be validated with pydantic"""

    # TODO ADD validation to couple kind and metrics only when they are
    # valid, for example ram cannot have cpu time and so on

    kind: EndpointIO | EndpointCPU | EndpointRAM
    metrics: dict[MetricKeys, PositiveFloat | PositiveInt]

    @field_validator("metrics", mode="before")
    def ensure_metric_exist_positive(
        cls, # noqa: N805
        v:  dict[MetricKeys, float | int],
        ) -> dict[MetricKeys, float | int]:
        """Ensure the measure of an operation exist and is positive"""
        for key, value in v.items():
            if not value:
                msg = f"{key} must be a positive number"
                raise ValueError(msg)
        return v


class Endpoint(BaseModel):
    """full endpoint structure to be validated with pydantic"""

    endpoint_name: str
    steps: list[Step]

    @field_validator("endpoint_name", mode="before")
    def name_to_lower(cls, v: str) -> str: # noqa: N805
        """Standardize endpoint name to be lowercase"""
        return v.lower()


