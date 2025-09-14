from asyncflow.config.enums import EndpointStepCPU, StepOperation
from asyncflow.schemas.topology.endpoint import Endpoint, Step


def make_min_ep(ep_id: str = "ep-1", cpu_time: float = 0.1) -> Endpoint:
    return Endpoint(
        endpoint_name=ep_id,
        steps=[
            Step(
                kind=EndpointStepCPU.CPU_BOUND_OPERATION,
                step_operation={StepOperation.CPU_TIME: cpu_time},
            ),
        ],
    )
