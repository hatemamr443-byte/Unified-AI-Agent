# Unified AI Agent

A modular personal AI control plane for research, coding, browser automation, tools, MCP services, and resilient execution.

## Current implementation

The repository now contains the core control plane through the completion track:

- Task envelope, risk policy, capability registry, routing, providers, and workers.
- Controlled execution with step/tool/worker/time/retry budgets.
- Explicit cancellation and bounded synchronous-provider waiting.
- Retryable failure handling and provider fallback.
- Deterministic result verification for output schemas, evidence, structured constraints, and basic consistency.
- Evidence-aware confidence calculation with explicit human-review states.
- Stable execution results with verification metadata.
- Durable local task/result persistence with atomic JSON replacement.
- Resume entry point that reuses persisted task state without pretending arbitrary providers are magically resumable.
- Automated pytest suite and GitHub Actions CI.

## Architecture

User
    -> Control Plane
    -> Policy
    -> Capability Registry
    -> Router
    -> Execution Engine
    -> Provider / Worker
    -> Verification Engine
    -> Result
    -> Durable State

Failures can route to another provider for the same capability before escalating. Verification failures are explicit; the system does not equate provider execution success with task success.

## Verification model

Verification checks:

1. Output schema.
2. Evidence presence and evidence quality when evidence is required.
3. Structured constraints (required_keys, max, min, equals).
4. Basic structured claim consistency.

Confidence is derived from those checks rather than accepted from provider self-reporting.

Unsupported free-form constraints are reported as warnings instead of being silently treated as verified.

## Durable state

JsonFileStateStore is intentionally small and suitable for local development or a single-process deployment. It atomically writes task and result JSON files.

A production multi-process/distributed deployment should replace this adapter with a transactional database-backed implementation while keeping the StateStore contract.

## Timeout and cancellation boundary

Thread-based timeout provides bounded waiting but cannot forcibly terminate a provider that is already running. Hard process/container isolation remains a worker-level responsibility.

Cancellation is cooperative through CancellationToken; providers that support the execution context can observe it during their own work.

## External agents, MCP, and ACP

No external agent runtime, MCP adapter, or ACP bridge is added merely for completeness. The current core does not require one to satisfy its control-plane contracts.

When a real capability gap appears, integrations should be added behind the existing provider/worker contracts rather than bypassing policy, budgets, state, or verification.

## Development

Python 3.11+.

Install test dependencies:

    pip install -e ".[test]"

Run:

    python -m pytest

GitHub Actions runs the same pytest command on pushes and pull requests.

## Important limitation

The repository currently provides the control-plane and local persistence contracts. It does not itself ship a privileged terminal daemon, browser daemon, or external coding agent. Those are capability-specific workers to be attached only when their concrete execution boundary is required.
