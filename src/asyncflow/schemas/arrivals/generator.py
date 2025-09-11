"""Define the schemas for the simulator"""

from typing import Self

from pydantic import BaseModel, PositiveFloat, model_validator

from asyncflow.config.constants import Distribution, SystemNodes, VariabilityLevel

FORBIDS_VARIABILITY = {
    Distribution.EXPONENTIAL,
    Distribution.DETERMINISTIC,
    Distribution.EMPIRICAL,
    Distribution.POISSON,
}

REQUIRES_VARIABILITY = {
    Distribution.LOG_NORMAL,
    Distribution.WEIBULL,
    Distribution.PARETO,
    Distribution.ERLANG,
    Distribution.UNIFORM,
}


class ArrivalGenerator(BaseModel):
    """Define the expected variables for the simulation"""

    id: str
    type: SystemNodes = SystemNodes.GENERATOR
    lambda_rps: PositiveFloat
    model: Distribution
    variability: None | VariabilityLevel = None

    @model_validator(mode="after")
    def _check_variability_semantics(self) -> Self:
        """
        Validate the semantic consistency between `model` and `variability`.

        - For models where variability cannot be configured, `variability` must be None.
        - For models that require a variability level to determine shape/dispersion,
          variability must be provided.
        """
        if self.model in FORBIDS_VARIABILITY and self.variability is not None:
            msg = (f"variability is not allowed for model={self.model} "
                  "(intrinsic or non-configurable variability).")
            raise ValueError(msg)

        if self.model in REQUIRES_VARIABILITY and self.variability is None:
            msg = (f"variability is required for model={self.model} "
                   "(specify low|medium|high).")
            raise ValueError(msg)

        return self

