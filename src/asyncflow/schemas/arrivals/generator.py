"""Define the schemas for the simulator"""

from collections.abc import Iterable
from typing import Self

from pydantic import BaseModel, PositiveFloat, model_validator

from asyncflow.config.enums import Distribution, SystemNodes, VariabilityLevel

FORBIDS_VARIABILITY = {
    Distribution.EXPONENTIAL,
    Distribution.DETERMINISTIC,
    Distribution.EMPIRICAL,
    Distribution.POISSON,
    Distribution.UNIFORM,
}

REQUIRES_VARIABILITY = {
    Distribution.LOG_NORMAL,
    Distribution.WEIBULL,
    Distribution.PARETO,
    Distribution.ERLANG,
}

class ArrivalsGenerator(BaseModel):
    """Define the expected variables for the simulation"""

    id: str
    type: SystemNodes = SystemNodes.GENERATOR
    lambda_rps: PositiveFloat
    model: Distribution
    variability: None | VariabilityLevel = None
    empirical_data: Iterable[float] | None = None

    @model_validator(mode="after")
    def _check_variability_semantics(self) -> Self:
        """
        Validate the semantic consistency between model and variability.

        - For models where variability cannot be configured, variability must be None.
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


    @model_validator(mode="after")
    def _check_empirical_semantics(self) -> Self:
        """
        Validate presence/absence of empirical_data based on the model.

        Rules
        -----
        * If model is EMPIRICAL, empirical_data MUST be provided (not None).
        * If model is not EMPIRICAL, empirical_data MUST be None.
        """
        if self.model is Distribution.EMPIRICAL:
            if self.empirical_data is None:
                msg="empirical_data must be provided when model=EMPIRICAL."
                raise ValueError(msg)
        elif self.empirical_data is not None:
            msg="empirical_data is only allowed when model=EMPIRICAL."
            raise ValueError(msg)

        return self

