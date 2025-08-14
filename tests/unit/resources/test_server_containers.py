"""Unit test: build_containers must return full containers."""

import simpy

from asyncflow.config.constants import ServerResourceName
from asyncflow.resources.server_containers import build_containers
from asyncflow.schemas.topology.nodes import ServerResources


def test_containers_start_full() -> None:
    env = simpy.Environment()
    spec = ServerResources(cpu_cores=4, ram_mb=2048)
    containers = build_containers(env, spec)

    cpu = containers[ServerResourceName.CPU.value]
    ram = containers[ServerResourceName.RAM.value]

    assert cpu.level == cpu.capacity == 4
    assert ram.level == ram.capacity == 2048
