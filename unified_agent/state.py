from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from .models import Budget, RiskLevel, Task, TaskStatus
from .results import ExecutionResult


class StateStore(Protocol):
    def save_task(self, task: Task) -> None: ...
    def load_task(self, task_id: str) -> Task | None: ...
    def save_result(self, result: ExecutionResult) -> None: ...
    def load_result(self, task_id: str) -> ExecutionResult | None: ...


def _task_dict(task: Task) -> dict[str, Any]:
    data = asdict(task)
    data["risk_level"] = task.risk_level.value
    data["status"] = task.status.value
    data["budget"] = asdict(task.budget)
    return data


def _task_from_dict(data: dict[str, Any]) -> Task:
    return Task(
        task_id=data["task_id"],
        goal=data["goal"],
        parent_task_id=data.get("parent_task_id"),
        constraints=data.get("constraints", {}),
        requested_capabilities=data.get("requested_capabilities", []),
        risk_level=RiskLevel(data.get("risk_level", RiskLevel.LOW.value)),
        budget=Budget(**data.get("budget", {})),
        state=data.get("state", {}),
        artifacts=data.get("artifacts", []),
        evidence=data.get("evidence", []),
        status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
    )


class JsonFileStateStore:
    """Small durable store for local development and single-process deployments."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def save_task(self, task: Task) -> None:
        self._write(self.directory / f"task-{task.task_id}.json", _task_dict(task))

    def load_task(self, task_id: str) -> Task | None:
        path = self.directory / f"task-{task_id}.json"
        if not path.exists():
            return None
        return _task_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_result(self, result: ExecutionResult) -> None:
        self._write(self.directory / f"result-{result.task_id}.json", result.to_dict())

    def load_result(self, task_id: str) -> ExecutionResult | None:
        path = self.directory / f"result-{task_id}.json"
        if not path.exists():
            return None
        return ExecutionResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
