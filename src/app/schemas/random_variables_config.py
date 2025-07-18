"""Definition of the schema for a Random variable"""

from pydantic import BaseModel, field_validator, model_validator

from app.config.constants import Distribution


class RVConfig(BaseModel):
    """class to configure random variables"""

    mean: float
    distribution: Distribution = Distribution.POISSON
    variance: float | None = None

    @field_validator("mean", mode="before")
    def ensure_mean_is_numeric(
        cls, # noqa: N805
        v: float,
        ) -> float:
        """Ensure `mean` is numeric, then coerce to float."""
        err_msg = "mean must be a number (int or float)"
        if not isinstance(v, (float, int)):
            raise ValueError(err_msg)  # noqa: TRY004
        return float(v)

    @model_validator(mode="after")  # type: ignore[arg-type]
    def default_variance(cls, model: "RVConfig") -> "RVConfig":  # noqa: N805
        """Set variance = mean when distribution require and variance is missing."""
        needs_variance: set[Distribution] = {
            Distribution.NORMAL,
            Distribution.LOG_NORMAL,
        }

        if model.variance is None and model.distribution in needs_variance:
            model.variance = model.mean
        return model
