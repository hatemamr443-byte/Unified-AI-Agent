from dataclasses import dataclass

from .models import Task
from .registry import Capability, CapabilityRegistry, Provider


@dataclass
class Route:
    capability: Capability
    provider: Provider


class Router:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def route(self, task: Task, capability_id: str) -> Route:
        routes = self.routes(task, capability_id)
        if not routes:
            raise LookupError(f"No available provider for capability: {capability_id}")
        return routes[0]

    def routes(self, task: Task, capability_id: str) -> list[Route]:
        capability = self.registry.get_capability(capability_id)
        return [Route(capability=capability, provider=provider)
                for provider in self.registry.providers_for(capability_id)]
