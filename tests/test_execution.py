import time

from unified_agent.execution import CancellationToken, ExecutionEngine, RetryableExecutionError
from unified_agent.models import Budget, RiskLevel, Task
from unified_agent.policy import PolicyEngine
from unified_agent.registry import Capability, CapabilityRegistry
from unified_agent.results import ExecutionStatus
from unified_agent.router import Router


class SuccessProvider:
    id = "success"
    capabilities = ["test.execute"]

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"answer": "ok", "tools_used": ["success"]}


class RetryProvider:
    id = "retry"
    capabilities = ["test.retry"]
    calls = 0

    def is_available(self):
        return True

    def execute(self, task, capability):
        self.calls += 1
        if self.calls == 1:
            raise RetryableExecutionError("temporary failure")
        return {"answer": "recovered"}


class SlowProvider:
    id = "slow"
    capabilities = ["test.slow"]

    def is_available(self):
        return True

    def execute(self, task, capability):
        time.sleep(2)
        return {"answer": "late"}


def make_engine(capability, provider):
    registry = CapabilityRegistry()
    registry.register_capability(capability)
    registry.register_provider(provider)
    return ExecutionEngine(Router(registry), PolicyEngine())


def test_success_returns_contract():
    engine = make_engine(
        Capability(id="test.execute", name="Execute", category="test", description="success", availability="available"),
        SuccessProvider(),
    )
    result = engine.execute(Task(task_id="success-1", goal="run"), "test.execute")
    assert result.status == ExecutionStatus.SUCCESS
    assert result.output["answer"] == "ok"
    assert result.tools_used == ["success"]
    assert result.attempts == 1
    assert result.task_id == "success-1"


def test_retryable_provider_failure_is_retried():
    provider = RetryProvider()
    engine = make_engine(
        Capability(id="test.retry", name="Retry", category="test", description="retry", availability="available"),
        provider,
    )
    task = Task(task_id="retry-1", goal="retry", budget=Budget(max_retries=1))
    result = engine.execute(task, "test.retry")
    assert result.status == ExecutionStatus.SUCCESS
    assert provider.calls == 2
    assert result.retries == 1


def test_timeout_returns_timeout_status():
    engine = make_engine(
        Capability(id="test.slow", name="Slow", category="test", description="slow", availability="available"),
        SlowProvider(),
    )
    task = Task(task_id="timeout-1", goal="slow", budget=Budget(max_time_seconds=1))
    started = time.monotonic()
    result = engine.execute(task, "test.slow")
    elapsed = time.monotonic() - started
    assert result.status == ExecutionStatus.TIMEOUT
    assert result.requires_human_review is True
    assert elapsed < 1.5


def test_cancellation_before_provider_call():
    engine = make_engine(
        Capability(id="test.execute", name="Execute", category="test", description="success", availability="available"),
        SuccessProvider(),
    )
    token = CancellationToken()
    token.cancel()
    result = engine.execute(Task(task_id="cancel-1", goal="cancel"), "test.execute", cancellation_token=token)
    assert result.status == ExecutionStatus.CANCELLED


def test_tool_budget_is_enforced():
    engine = make_engine(
        Capability(id="test.execute", name="Execute", category="test", description="success", availability="available"),
        SuccessProvider(),
    )
    task = Task(task_id="budget-1", goal="budget", budget=Budget(max_tool_calls=0))
    result = engine.execute(task, "test.execute")
    assert result.status == ExecutionStatus.BUDGET_EXCEEDED


def test_confirmation_stops_execution():
    engine = make_engine(
        Capability(
            id="test.confirm",
            name="Confirm",
            category="test",
            description="needs confirmation",
            requires_confirmation=True,
        ),
        SuccessProvider(),
    )
    result = engine.execute(Task(task_id="confirm-1", goal="confirm"), "test.confirm")
    assert result.status == ExecutionStatus.REQUIRES_CONFIRMATION
    assert result.requires_human_review is True


def test_high_risk_stops_execution():
    engine = make_engine(
        Capability(id="test.execute", name="Execute", category="test", description="success", availability="available"),
        SuccessProvider(),
    )
    result = engine.execute(
        Task(task_id="risk-1", goal="high risk", risk_level=RiskLevel.HIGH),
        "test.execute",
    )
    assert result.status == ExecutionStatus.REQUIRES_CONFIRMATION
