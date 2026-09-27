import json
from pathlib import Path

from unified_agent.execution import ExecutionEngine, RetryableExecutionError
from unified_agent.models import Budget, Task
from unified_agent.registry import Capability, CapabilityRegistry
from unified_agent.router import Router
from unified_agent.state import JsonFileStateStore
from unified_agent.verification import VerificationStatus


class ValidProvider:
    id = "valid"
    capabilities = ["test.verify"]

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"answer": "ok", "evidence": [{"source": "test", "claim": "answer", "quality": 1.0}]}


class InvalidProvider:
    id = "invalid"
    capabilities = ["test.verify"]

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"wrong": True}


class FallbackProvider:
    id = "fallback"
    capabilities = ["test.fallback"]

    def is_available(self):
        return True

    def execute(self, task, capability):
        return {"answer": "fallback"}


class RetryProvider:
    id = "retry"
    capabilities = ["test.retry_fallback"]

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, task, capability):
        self.calls += 1
        raise RetryableExecutionError("temporary")


def make_engine(capability, *providers, state_store=None):
    registry = CapabilityRegistry()
    registry.register_capability(capability)
    for provider in providers:
        registry.register_provider(provider)
    return ExecutionEngine(Router(registry), state_store=state_store)


def test_verification_passes_and_populates_confidence():
    capability = Capability(
        id="test.verify",
        name="Verify",
        category="test",
        description="verification",
        output_schema={"type": "object", "required": ["answer"]},
    )
    task = Task(task_id="v1", goal="verify", constraints={"requires_evidence": True})
    result = make_engine(capability, ValidProvider()).execute(task, "test.verify")
    assert result.status.value == "success"
    assert result.verification["status"] == VerificationStatus.PASSED.value
    assert result.confidence == 1.0


def test_schema_failure_is_not_reported_as_success():
    capability = Capability(
        id="test.verify",
        name="Verify",
        category="test",
        description="verification",
        output_schema={"type": "object", "required": ["answer"]},
    )
    result = make_engine(capability, InvalidProvider()).execute(Task(task_id="v2", goal="verify"), "test.verify")
    assert result.status.value == "verification_failed"
    assert result.requires_human_review is True
    assert result.verification["passed"] is False


def test_provider_fallback_reaches_second_provider():
    capability = Capability(
        id="test.verify",
        name="Verify",
        category="test",
        description="verification",
        output_schema={"type": "object", "required": ["answer"]},
    )
    result = make_engine(capability, InvalidProvider(), ValidProvider()).execute(
        Task(task_id="v3", goal="fallback"), "test.verify"
    )
    assert result.status.value == "success"
    assert result.output["answer"] == "ok"


def test_durable_state_round_trip(tmp_path: Path):
    store = JsonFileStateStore(tmp_path)
    task = Task(task_id="state-1", goal="persist", constraints={"x": 1})
    store.save_task(task)
    loaded = store.load_task("state-1")
    assert loaded is not None
    assert loaded.goal == "persist"
    assert loaded.constraints == {"x": 1}

    capability = Capability(id="test.verify", name="Verify", category="test", description="verification")
    result = make_engine(capability, ValidProvider(), state_store=store).execute(task, "test.verify")
    saved = store.load_result(task.task_id)
    assert saved is not None
    assert saved.task_id == result.task_id
    assert json.loads((tmp_path / "result-state-1.json").read_text())["status"] == "success"


def test_requires_evidence_without_evidence_fails():
    capability = Capability(id="test.verify", name="Verify", category="test", description="verification")
    task = Task(task_id="v4", goal="evidence", constraints={"requires_evidence": True})
    result = make_engine(capability, ValidProvider()).execute(task, "test.verify")
    assert result.status.value == "verification_failed"
