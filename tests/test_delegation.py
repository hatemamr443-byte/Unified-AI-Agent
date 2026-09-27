from unified_agent.execution import ExecutionEngine
from unified_agent.models import Task
from unified_agent.registry import Capability, CapabilityRegistry
from unified_agent.router import Router
from unified_agent.workers import DelegationEngine, InProcessWorker, WorkerProvider


def handler(task, capability, context=None):
    return {
        "answer": "delegated",
        "evidence": [{"source": "worker", "claim": "delegated", "quality": 1.0}],
    }


def test_real_delegation_round_trip():
    worker = InProcessWorker("research-worker", ["research.lookup"], handler)
    capability = Capability(
        id="research.lookup",
        name="Research",
        category="research",
        description="delegated research",
        output_schema={"type": "object", "required": ["answer"]},
        execution_type="worker",
    )
    registry = CapabilityRegistry()
    registry.register_capability(capability)
    registry.register_provider(WorkerProvider(worker))
    engine = ExecutionEngine(Router(registry))
    parent = Task(task_id="parent-1", goal="delegate")
    child, result = DelegationEngine(engine).delegate(parent, "research.lookup")
    assert child.parent_task_id == "parent-1"
    assert parent.state["children"] == [child.task_id]
    assert result.status.value == "success"
    assert result.output["answer"] == "delegated"
