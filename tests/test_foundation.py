from unified_agent.models import RiskLevel, Task
from unified_agent.policy import Decision, PolicyEngine
from unified_agent.registry import Capability, CapabilityRegistry
from unified_agent.router import Router


class FakeProvider:
    id = "fake"
    capabilities = ["test.echo"]

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"ok": True}


def test_registry_and_router():
    registry = CapabilityRegistry()
    registry.register_capability(Capability(id="test.echo", name="Echo", category="test", description="Test capability", availability="available"))
    registry.register_provider(FakeProvider())
    route = Router(registry).route(Task(task_id="1", goal="test"), "test.echo")
    assert route.provider.id == "fake"


def test_high_risk_requires_confirmation():
    task = Task(task_id="2", goal="danger", risk_level=RiskLevel.HIGH)
    assert PolicyEngine().evaluate(task) == Decision.CONFIRM


def test_missing_provider_fails_explicitly():
    registry = CapabilityRegistry()
    registry.register_capability(Capability(id="missing.capability", name="Missing", category="test", description="No provider"))
    try:
        Router(registry).route(Task(task_id="3", goal="test"), "missing.capability")
    except LookupError as exc:
        assert "missing.capability" in str(exc)
    else:
        raise AssertionError("Expected LookupError")
