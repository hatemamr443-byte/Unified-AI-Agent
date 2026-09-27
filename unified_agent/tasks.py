from __future__ import annotations

from typing import Any

from .execution import ExecutionEngine
from .models import Task, TaskStatus
from .results import ExecutionResult
from .state import StateStore


class TaskManager:
    """Small task lifecycle facade over the durable state store."""

    def __init__(self, state_store: StateStore, execution_engine: ExecutionEngine):
        self.state_store = state_store
        self.execution_engine = execution_engine

    def submit(self, task: Task) -> Task:
        task.status = TaskStatus.PENDING
        self.state_store.save_task(task)
        return task

    def get(self, task_id: str) -> Task | None:
        return self.state_store.load_task(task_id)

    def result(self, task_id: str) -> ExecutionResult | None:
        return self.state_store.load_result(task_id)

    def run(self, task: Task, capability_id: str) -> ExecutionResult:
        self.state_store.save_task(task)
        return self.execution_engine.execute(task, capability_id)

    def resume(self, task_id: str, capability_id: str) -> ExecutionResult:
        task = self.state_store.load_task(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        if task.status == TaskStatus.COMPLETED:
            existing = self.state_store.load_result(task_id)
            if existing is not None:
                return existing
        return self.execution_engine.resume(task, capability_id)
