# Unified AI Agent

A modular personal AI control plane for research, coding, browser automation, tools, MCP services, and resilient execution.

## Phase 1 — Foundation

The repository implements the core control-plane contracts:

- Task envelope and execution budgets
- Capability registry
- Provider abstraction
- Capability-based routing
- Risk/confirmation policy
- Worker interface
- Minimal automated tests

External agent runtimes are intentionally not added yet. MCP and specialized workers will be evaluated only after the foundation establishes the required interfaces.

## Phase 2 — Execution Engine

Phase 2 turns the contracts into a controlled execution path:

- Routes a task to an available provider.
- Applies the Phase 1 policy decision before execution.
- Enforces step, tool-call, worker-call, retry, and wall-clock budgets.
- Supports explicit cancellation through a cancellation token.
- Retries only failures explicitly marked as `RetryableExecutionError`.
- Returns a stable `ExecutionResult` contract containing status, output, evidence, errors, attempts, retries, timing, tools used, changed files, confidence, and human-review state.
- Preserves compatibility with Phase 1 providers that accept only `(task, capability)` while allowing providers to opt into an execution context.
- Uses `ThreadPoolExecutor` for bounded waiting around synchronous providers. A timeout does not forcibly terminate a provider that is already running; providers that need hard isolation must later be moved behind a process/container worker.

The execution engine is deliberately not a distributed worker system yet. Durable state, verification, MCP adapters, and specialized external workers remain later phases.

## Architecture

User / Main Agent
    -> Capability Registry
    -> Policy
    -> Router
    -> Execution Engine
    -> Provider / Worker
    -> Result Contract
    -> Verification (future phase)
    -> Durable State (future phase)

## Development

Python 3.11+.

Run:

    python -m pytest

Phase 2 is intentionally bounded. Later phases will add verification, durable state/resume, MCP adapters, and specialized workers.
