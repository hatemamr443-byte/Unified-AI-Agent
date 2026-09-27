from __future__ import annotations

import inspect
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Callable

from .models import Task, TaskStatus
from .policy import Decision, PolicyEngine
from .router import Route, Router
from .results import ExecutionResult, ExecutionStatus
from .verification import VerificationEngine, VerificationStatus


class ExecutionError(Exception):
    pass


class RetryableExecutionError(ExecutionError):
    pass


class BudgetExceededError(ExecutionError):
    pass


class ExecutionCancelledError(ExecutionError):
    pass


@dataclass
class CancellationToken:
    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


@dataclass
class ExecutionContext:
    task: Task
    cancellation_token: CancellationToken
    started_at: float
    deadline: float | None
    steps: int = 0
    tool_calls: int = 0
    worker_calls: int = 0
    retry_count: int = 0

    def check(self, clock: Callable[[], float] = time.monotonic) -> None:
        if self.cancellation_token.is_cancelled:
            raise ExecutionCancelledError("Execution was cancelled")
        if self.deadline is not None and clock() >= self.deadline:
            raise BudgetExceededError("Task time budget exceeded")
        if self.steps >= self.task.budget.max_steps:
            raise BudgetExceededError("Maximum execution steps exceeded")

    def consume_call(self, execution_type: str) -> None:
        self.steps += 1
        if execution_type == "worker":
            if self.worker_calls >= self.task.budget.max_worker_calls:
                raise BudgetExceededError("Maximum worker calls exceeded")
            self.worker_calls += 1
        else:
            if self.tool_calls >= self.task.budget.max_tool_calls:
                raise BudgetExceededError("Maximum tool calls exceeded")
            self.tool_calls += 1

    @property
    def remaining_seconds(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())


class ExecutionEngine:
    def __init__(
        self,
        router: Router,
        policy: PolicyEngine | None = None,
        *,
        verifier: VerificationEngine | None = None,
        state_store: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        backoff_seconds: float = 0.0,
    ) -> None:
        self.router = router
        self.policy = policy or PolicyEngine()
        self.verifier = verifier or VerificationEngine()
        self.state_store = state_store
        self.clock = clock
        self.sleeper = sleeper
        self.backoff_seconds = max(0.0, backoff_seconds)

    def execute(
        self,
        task: Task,
        capability_id: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult:
        started_at = self.clock()
        token = cancellation_token or CancellationToken()
        errors: list[dict[str, str]] = []

        try:
            routes = self.router.routes(task, capability_id)
        except Exception as exc:
            task.status = TaskStatus.FAILED
            return self._finish(task, started_at, ExecutionStatus.FAILED,
                                errors=[self._error(exc)], requires_human_review=True)

        if not routes:
            task.status = TaskStatus.FAILED
            return self._finish(
                task, started_at, ExecutionStatus.FAILED,
                errors=[{"type": "LookupError", "message": f"No available provider for capability: {capability_id}"}],
                requires_human_review=True,
            )

        decision = self.policy.evaluate(task, routes[0].capability.requires_confirmation)
        if decision == Decision.CONFIRM:
            return self._finish(task, started_at, ExecutionStatus.REQUIRES_CONFIRMATION, requires_human_review=True)
        if decision == Decision.DENY:
            task.status = TaskStatus.FAILED
            return self._finish(task, started_at, ExecutionStatus.DENIED, requires_human_review=True)

        deadline = None
        if task.budget.max_time_seconds is not None:
            deadline = started_at + task.budget.max_time_seconds
        context = ExecutionContext(task=task, cancellation_token=token, started_at=started_at, deadline=deadline)
        task.status = TaskStatus.RUNNING
        self._persist_task(task)

        route_index = 0
        while True:
            route = routes[route_index]
            try:
                context.check(self.clock)
                context.consume_call(route.capability.execution_type)
                raw = self._invoke_with_timeout(route.provider, task, route.capability, context)
                evidence = raw.get("evidence", task.evidence) if isinstance(raw, dict) else task.evidence
                verification = self.verifier.verify(task, route.capability, raw, evidence=evidence)

                if verification.status == VerificationStatus.PASSED:
                    task.status = TaskStatus.COMPLETED
                    return self._finish(
                        task, started_at, ExecutionStatus.SUCCESS, output=raw, evidence=evidence,
                        attempts=context.steps, retries=context.retry_count, verification=verification.to_dict(),
                        confidence=verification.confidence,
                    )

                errors.extend({"type": "VerificationError", "message": item} for item in verification.failures)
                if verification.status == VerificationStatus.NEEDS_REVIEW:
                    task.status = TaskStatus.COMPLETED
                    return self._finish(
                        task, started_at, ExecutionStatus.NEEDS_REVIEW, output=raw, evidence=evidence,
                        errors=errors, attempts=context.steps, retries=context.retry_count,
                        verification=verification.to_dict(), confidence=verification.confidence,
                        requires_human_review=True,
                    )

                if route_index + 1 < len(routes):
                    route_index += 1
                    continue

                task.status = TaskStatus.FAILED
                return self._finish(
                    task, started_at, ExecutionStatus.VERIFICATION_FAILED, output=raw, evidence=evidence,
                    errors=errors, attempts=context.steps, retries=context.retry_count,
                    verification=verification.to_dict(), confidence=verification.confidence,
                    requires_human_review=True,
                )
            except ExecutionCancelledError as exc:
                task.status = TaskStatus.CANCELLED
                errors.append(self._error(exc))
                return self._finish(task, started_at, ExecutionStatus.CANCELLED, errors=errors,
                                    attempts=context.steps, retries=context.retry_count)
            except BudgetExceededError as exc:
                task.status = TaskStatus.FAILED
                errors.append(self._error(exc))
                return self._finish(task, started_at, ExecutionStatus.BUDGET_EXCEEDED, errors=errors,
                                    attempts=context.steps, retries=context.retry_count, requires_human_review=True)
            except FutureTimeoutError as exc:
                task.status = TaskStatus.FAILED
                errors.append(self._error(exc, "Provider execution timed out"))
                return self._finish(task, started_at, ExecutionStatus.TIMEOUT, errors=errors,
                                    attempts=context.steps, retries=context.retry_count, requires_human_review=True)
            except RetryableExecutionError as exc:
                errors.append(self._error(exc))
                if route_index + 1 < len(routes):
                    route_index += 1
                    continue
                if context.retry_count >= task.budget.max_retries:
                    task.status = TaskStatus.FAILED
                    return self._finish(task, started_at, ExecutionStatus.FAILED, errors=errors,
                                        attempts=context.steps, retries=context.retry_count, requires_human_review=True)
                context.retry_count += 1
                if self.backoff_seconds:
                    remaining = context.remaining_seconds
                    if remaining is not None and remaining <= 0:
                        raise BudgetExceededError("No time remains for retry")
                    self.sleeper(self.backoff_seconds if remaining is None else min(self.backoff_seconds, remaining))
            except Exception as exc:
                task.status = TaskStatus.FAILED
                errors.append(self._error(exc))
                return self._finish(task, started_at, ExecutionStatus.FAILED, errors=errors,
                                    attempts=context.steps, retries=context.retry_count, requires_human_review=True)

    def resume(self, task: Task, capability_id: str) -> ExecutionResult:
        """Resume a persisted task by starting a new bounded execution.

        Provider-specific continuation state belongs in task.state; this method
        deliberately avoids pretending that arbitrary providers are resumable.
        """
        task.status = TaskStatus.PENDING
        return self.execute(task, capability_id)

    def _invoke_with_timeout(self, provider: Any, task: Task, capability: Any, context: ExecutionContext) -> Any:
        remaining = context.remaining_seconds
        if remaining is not None and remaining <= 0:
            raise BudgetExceededError("Task time budget exceeded")
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="unified-agent")
        future = executor.submit(self._invoke_provider, provider, task, capability, context)
        try:
            return future.result(timeout=remaining)
        except FutureTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _invoke_provider(provider: Any, task: Task, capability: Any, context: ExecutionContext) -> Any:
        execute = provider.execute
        parameters = inspect.signature(execute).parameters
        if "context" in parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            return execute(task, capability, context=context)
        if len(parameters) >= 3:
            return execute(task, capability, context)
        return execute(task, capability)

    @staticmethod
    def _error(exc: BaseException, message: str | None = None) -> dict[str, str]:
        return {"type": type(exc).__name__, "message": message or str(exc) or type(exc).__name__}

    def _finish(self, task: Task, started_at: float, status: ExecutionStatus, *,
                output: Any = None, evidence: list[dict[str, Any]] | None = None,
                errors: list[dict[str, str]] | None = None, attempts: int = 0, retries: int = 0,
                requires_human_review: bool = False, verification: dict[str, Any] | None = None,
                confidence: float | None = None) -> ExecutionResult:
        files_changed: list[str] = []
        tools_used: list[str] = []
        if isinstance(output, dict):
            if isinstance(output.get("files_changed"), list):
                files_changed = [str(item) for item in output["files_changed"]]
            if isinstance(output.get("tools_used"), list):
                tools_used = [str(item) for item in output["tools_used"]]
        result = ExecutionResult(
            task_id=task.task_id, status=status, output=output,
            evidence=list(evidence if evidence is not None else task.evidence),
            files_changed=files_changed, tools_used=tools_used, errors=list(errors or []),
            confidence=confidence, requires_human_review=requires_human_review,
            attempts=attempts, retries=retries, elapsed_seconds=max(0.0, self.clock() - started_at),
            verification=verification,
        )
        self._persist_task(task)
        self._persist_result(result)
        return result

    def _persist_task(self, task: Task) -> None:
        if self.state_store is not None:
            self.state_store.save_task(task)

    def _persist_result(self, result: ExecutionResult) -> None:
        if self.state_store is not None:
            self.state_store.save_result(result)
