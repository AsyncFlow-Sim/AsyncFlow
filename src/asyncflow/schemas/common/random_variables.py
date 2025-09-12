"""Definition of the schema for a Random variable"""

from pydantic import BaseModel, NonNegativeFloat, model_validator

from asyncflow.config.enums import Distribution


class RVConfig(BaseModel):
    """class to configure random variables"""

    mean: NonNegativeFloat
    distribution: Distribution = Distribution.POISSON
    variance: NonNegativeFloat | None = None

    @model_validator(mode="after")  # type: ignore[arg-type]
    def default_variance(cls, model: "RVConfig") -> "RVConfig":  # noqa: N805
        """Set variance = mean when distribution require and variance is missing."""
        needs_variance: set[Distribution] = {
            Distribution.LOG_NORMAL,
        }

        if model.variance is None and model.distribution in needs_variance:
            model.variance = model.mean
        return model
