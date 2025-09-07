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

    def sweep_on_user(
        self,
        # we pass a validated payload from yaml or from
        # the pythonic builder
        payload: SimulationPayload,
        user_lower_bound: int,
        user_upper_bound: int,
        step: int,
        ) -> list[tuple[int, ResultsAnalyzer]]:
        """
        Function to prepare a list of results analzyer
        with all the data necessary to evaluate how the
        topology react on a given scenario by varying the
        average concurrent users
        """
        # Error handling to have a coherent interval
        if step <= 0:
            msg = "step must be > 0"
            raise ValueError(msg)

        if user_lower_bound <= 0 or user_upper_bound <= 0:
            msg = "The lower and upper bound must be strictly bigger than 0"
            raise ValueError(msg)

        if user_upper_bound < user_lower_bound:
            msg = "user_upper_bound must be >= user_lower_bound"
            raise ValueError(msg)

        # definition of the grid
        users_grid: list[int] = list(
            range(user_lower_bound, user_upper_bound + 1, step))
        self._last_users_grid = users_grid.copy()

        # last grid used
        self._last_users_grid = users_grid[:]

        results: list[tuple[int, ResultsAnalyzer]] = []

        # Iteration to populate the list
        for users in users_grid:
            # 1) payload override
            payload = payload.model_copy(deep=True)
            payload.rqs_input.avg_active_users = (
                    payload.rqs_input.avg_active_users.model_copy(
                        update={"mean": users},
            )
)

            # 2) instantiation of the new object for the simulation run
            runner = self.simulation_cls(
                env=self._default_env_factory(),
                simulation_input=payload,
            )

            analyzer = runner.run()

            # 3) Accumulation of the analyzer
            results.append((users, analyzer))

        return results




