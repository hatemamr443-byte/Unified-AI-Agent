from typing import Any, Protocol

from .models import Task


class Worker(Protocol):
    id: str
    capabilities: list[str]

    def execute(self, task: Task, capability_id: str, context: Any = None) -> Any: ...
    def cancel(self, task_id: str) -> None: ...
    def status(self, task_id: str) -> str: ...
    def resume(self, task: Task) -> Any: ...


class WorkerProvider:
    """Adapter exposing a specialized Worker through the Provider contract."""

    def __init__(self, worker: Worker):
        self.worker = worker

    @property
    def id(self) -> str:
        return self.worker.id

    @property
    def capabilities(self) -> list[str]:
        return list(self.worker.capabilities)

    def is_available(self) -> bool:
        return True

    def execute(self, task: Task, capability: Any, context: Any = None) -> Any:
        return self.worker.execute(task, capability.id, context=context)


class InProcessWorker:
    """Reference worker for deterministic delegation and integration tests."""

    def __init__(self, worker_id: str, capabilities: list[str], handler):
        self.id = worker_id
        self.capabilities = capabilities
        self._handler = handler
        self._states: dict[str, str] = {}

    def execute(self, task: Task, capability_id: str, context: Any = None) -> Any:
        self._states[task.task_id] = "running"
        try:
            value = self._handler(task, capability_id, context)
            self._states[task.task_id] = "completed"
            return value
        except Exception:
            self._states[task.task_id] = "failed"
            raise

    def cancel(self, task_id: str) -> None:
        self._states[task_id] = "cancelled"

    def status(self, task_id: str) -> str:
        return self._states.get(task_id, "unknown")

    def resume(self, task: Task) -> Any:
        capability_id = task.requested_capabilities[0]
        return self.execute(task, capability_id)


class DelegationEngine:
    """Creates bounded child tasks and routes them through the same control plane."""

    def __init__(self, execution_engine):
        self.execution_engine = execution_engine

    def delegate(self, parent: Task, capability_id: str, goal: str | None = None,
                 constraints: dict[str, Any] | None = None):
        child_number = len(parent.state.get("children", [])) + 1
        child_id = f"{parent.task_id}:child:{child_number}"
        child = Task(
            task_id=child_id,
            goal=goal or parent.goal,
            parent_task_id=parent.task_id,
            constraints=constraints if constraints is not None else dict(parent.constraints),
            requested_capabilities=[capability_id],
            risk_level=parent.risk_level,
            budget=parent.budget,
            state={"delegated_from": parent.task_id},
        )
        parent.state.setdefault("children", []).append(child_id)
        result = self.execution_engine.execute(child, capability_id)
        return child, result
