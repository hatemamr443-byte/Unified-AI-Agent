from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from typing import Any, Sequence

from .models import Task


class ExternalWorkerError(RuntimeError):
    pass


class JsonLineProcessWorker:
    """Adapter for an external agent/worker exposing a JSON-lines stdin/stdout contract.

    The executable and argument list are explicit; no shell is invoked. The worker
    receives one task envelope and must return one JSON object. This adapter can
    host CLIs or local agent runtimes without coupling the control plane to one
    vendor protocol.
    """

    def __init__(
        self,
        worker_id: str,
        capabilities: list[str],
        command: Sequence[str],
        *,
        timeout_seconds: float = 300,
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.id = worker_id
        self.capabilities = list(capabilities)
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self._states: dict[str, str] = {}

    def execute(self, task: Task, capability_id: str, context: Any = None) -> dict[str, Any]:
        if capability_id not in self.capabilities:
            raise ExternalWorkerError(f"Worker does not support capability: {capability_id}")

        self._states[task.task_id] = "running"
        envelope = {
            "task_id": task.task_id,
            "parent_task_id": task.parent_task_id,
            "goal": task.goal,
            "objective": task.goal,
            "context": task.state,
            "constraints": task.constraints,
            "requested_capabilities": task.requested_capabilities,
            "risk_level": task.risk_level.value,
            "budget": asdict(task.budget),
            "artifacts": task.artifacts,
            "evidence": task.evidence,
        }
        try:
            completed = subprocess.run(
                list(self.command),
                input=json.dumps(envelope, ensure_ascii=False) + "\n",
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._states[task.task_id] = "timeout"
            raise ExternalWorkerError("External worker timed out") from exc
        except OSError as exc:
            self._states[task.task_id] = "failed"
            raise ExternalWorkerError(f"Could not start external worker: {exc}") from exc

        if completed.returncode != 0:
            self._states[task.task_id] = "failed"
            raise ExternalWorkerError(
                f"External worker exited with code {completed.returncode}: {completed.stderr.strip()}"
            )

        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self._states[task.task_id] = "failed"
            raise ExternalWorkerError("External worker returned invalid JSON") from exc

        if not isinstance(result, dict):
            self._states[task.task_id] = "failed"
            raise ExternalWorkerError("External worker result must be a JSON object")

        self._states[task.task_id] = "completed"
        return result

    def cancel(self, task_id: str) -> None:
        # subprocess.run is intentionally synchronous; cancellation is recorded
        # but cannot forcibly terminate an already completed call. Use a managed
        # worker runtime for hard cancellation.
        self._states[task_id] = "cancelled"

    def status(self, task_id: str) -> str:
        return self._states.get(task_id, "unknown")

    def resume(self, task: Task) -> dict[str, Any]:
        capability_id = task.requested_capabilities[0]
        return self.execute(task, capability_id)
