from dataclasses import dataclass

from .models import Task
from .registry import Capability, CapabilityRegistry, Provider


@dataclass
class Route:
    capability: Capability
    provider: Provider
    score: float = 0.0


class Router:
    """Capability router with deterministic provider scoring.

    Providers can optionally expose:
      priority: lower is preferred
      reliability: 0..1
      cost_rank: lower is cheaper
      latency_rank: lower is faster
    Missing metadata receives neutral defaults, preserving Phase 1 providers.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def route(self, task: Task, capability_id: str) -> Route:
        routes = self.routes(task, capability_id)
        if not routes:
            raise LookupError(f"No available provider for capability: {capability_id}")
        return routes[0]

    def routes(self, task: Task, capability_id: str) -> list[Route]:
        capability = self.registry.get_capability(capability_id)
        routes = [
            Route(capability=capability, provider=provider, score=self._score(task, capability, provider))
            for provider in self.registry.providers_for(capability_id)
        ]
        return sorted(routes, key=lambda route: (-route.score, getattr(route.provider, "priority", 100)))

    @staticmethod
    def _score(task: Task, capability: Capability, provider: Provider) -> float:
        reliability = min(1.0, max(0.0, float(getattr(provider, "reliability", 0.5))))
        priority = float(getattr(provider, "priority", 100))
        cost_rank = float(getattr(provider, "cost_rank", 50))
        latency_rank = float(getattr(provider, "latency_rank", 50))

        reliability_weight = 0.55 if task.risk_level.value == "high" else 0.35
        cost_weight = 0.15 if task.risk_level.value == "high" else 0.35
        latency_weight = 0.10 if task.risk_level.value == "high" else 0.20
        priority_weight = 0.20

        return (
            reliability_weight * reliability
            + cost_weight * (1.0 - min(cost_rank, 100.0) / 100.0)
            + latency_weight * (1.0 - min(latency_rank, 100.0) / 100.0)
            + priority_weight * (1.0 - min(priority, 100.0) / 100.0)
        )
