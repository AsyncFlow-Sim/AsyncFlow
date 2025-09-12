"""
class to define method to iterate over some variables of the input
to evaluate how a given scenario with different initial conditions
(for example the number of concurrent users), behave. It is really
useful to find insights and analyze eventual breakpoint on a given
topology. Right now the class will accept only as a varying parameter
the concurrent users, in the future we will extend it to arbitrary
parameters.
"""


import simpy

from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
from asyncflow.runner.simulation import SimulationRunner
from asyncflow.schemas.payload import SimulationPayload


class Sweep:
    """
    Class to manage scenario when we want to iterate over a
    set of initial data to see for example the impact on a defined
    topology varying the initial workload
    """

    def __init__(
        self,
        *,
        # passing the object class not instance of the class
        # Why:
        # - Each sweep run must be isolated: fresh Environment, fresh state,
        #   fresh queues.
        # - Reusing a single instance would carry state from the previous run
        #   (SimPy processes, resources, partial metrics, RNG state, etc.)
        #   → tainted results.
        # - By passing the CLASS we can instantiate on demand inside the loop,
        #   guaranteeing a fresh object for every grid point.
        simulation_cls: type[SimulationRunner] = SimulationRunner,
        ) -> None:
        """
        Instantiation of the sweep class
        Args:
            simulation_cls (type[SimulationRunner], optional): object of
            the SimulationRunner class
        """
        self.simulation_cls = simulation_cls

        # to trace the last grid
        self._last_users_grid: list[int] = []

    # ---------------------------------------------------
    # Helpers
    # ---------------------------------------------------

    @staticmethod
    def _default_env_factory() -> simpy.Environment:
        """Ritorna un Environment nuovo e pulito per ogni run."""
        return simpy.Environment()



    #----------------------------------------------------
    # Method to iterate over the users
    # ---------------------------------------------------

    def sweep_on_lambda(
    self,
    *,
    payload: SimulationPayload,
    lambda_lower_bound: float,
    lambda_upper_bound: float,
    step: float,
) -> list[tuple[float, ResultsAnalyzer]]:
        """
        Sweep the arrival rate (`lambda_rps`, requests/second) over a range and run a
        simulation for each value.

        Parameters
        ----------
        payload
            A fully validated `SimulationPayload` used as the base configuration.
            It will be deep-copied and patched with each `lambda_rps` value.
        lambda_lower_bound
            Inclusive lower bound for `lambda_rps` (> 0).
        lambda_upper_bound
            Inclusive upper bound for `lambda_rps` (>= lower bound, > 0).
        step
            Positive increment for the sweep grid.

        Returns
        -------
        list[tuple[float, ResultsAnalyzer]]
            A list of pairs `(lambda_rps, analyzer)` for each grid point.

        Notes
        -----
        - Uses `model_copy(deep=True)` (Pydantic v2) to avoid mutating the input payload
        - Builds the sweep grid robustly against floating-point accumulation errors.

        """
        # --- Validate inputs early for clear error messages ---
        if step <= 0.0:
            msg="step must be > 0"
            raise ValueError(msg)
        if lambda_lower_bound <= 0.0 or lambda_upper_bound <= 0.0:
            msg="The lower and upper bound must be strictly bigger than 0"
            raise ValueError(msg)
        if lambda_upper_bound < lambda_lower_bound:
            msg="lambda_upper_bound must be >= lambda_lower_bound"
            raise ValueError(msg)

        # --- Build a numerically robust grid of lambda values ---
        eps = step * 1e-9  # tiny slack to counter FP accumulation on the final step
        lam = float(lambda_lower_bound)
        lambda_grid: list[float] = []
        while lam <= lambda_upper_bound + eps:
            lambda_grid.append(float(lam))
            lam += step

        # Keep the last grid if your class wants to expose it later (optional).
        self._last_lambda_grid = lambda_grid[:]

        results: list[tuple[float, ResultsAnalyzer]] = []

        for lam in lambda_grid:
            # 1) Clone the payload and override the arrival rate
            pl = payload.model_copy(deep=True)
            pl.arrivals = pl.arrivals.model_copy(update={"lambda_rps": lam})

            # 2) Instantiate and run the simulation
            runner = self.simulation_cls(
                env=self._default_env_factory(),
                simulation_input=pl,
            )
            analyzer = runner.run()

            # 3) Accumulate the result
            results.append((lam, analyzer))

        return results
