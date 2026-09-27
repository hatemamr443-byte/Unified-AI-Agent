from unified_agent.models import RiskLevel, Task
from unified_agent.registry import Capability, CapabilityRegistry
from unified_agent.router import Router


class CheapProvider:
    id = "cheap"
    capabilities = ["route.test"]
    reliability = 0.60
    cost_rank = 5
    latency_rank = 50
    priority = 50

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"answer": "cheap"}


class ReliableProvider:
    id = "reliable"
    capabilities = ["route.test"]
    reliability = 0.99
    cost_rank = 80
    latency_rank = 50
    priority = 10

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"answer": "reliable"}


def test_router_prefers_reliability_for_high_risk():
    registry = CapabilityRegistry()
    registry.register_capability(Capability(
        id="route.test", name="Route", category="test", description="routing"
    ))
    registry.register_provider(CheapProvider())
    registry.register_provider(ReliableProvider())
    route = Router(registry).route(
        Task(task_id="route-1", goal="route", risk_level=RiskLevel.HIGH),
        "route.test",
    )
    assert route.provider.id == "reliable"
