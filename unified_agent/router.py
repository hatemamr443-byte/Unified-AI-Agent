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
        capability = self.registry.get_capability(capability_id)
        providers = self.registry.providers_for(capability_id)
        if not providers:
            raise LookupError(f"No available provider for capability: {capability_id}")
        return Route(capability=capability, provider=providers[0])
