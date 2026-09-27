# Unified AI Agent

A modular personal AI control plane for research, coding, browser automation, tools, MCP services, and resilient execution.

## Phase 1 — Foundation

This repository currently implements the core contracts only:

- Task envelope and execution budgets
- Capability registry
- Provider abstraction
- Capability-based routing
- Risk/confirmation policy
- Worker interface
- Minimal automated tests

External agent runtimes are intentionally not added yet. MCP and specialized workers will be evaluated only after the foundation establishes the required interfaces.

## Architecture

User / Main Agent
    -> Capability Registry
    -> Policy
    -> Router
    -> Provider / Worker
    -> Verification (future phase)
    -> State / Resume (future phase)

## Development

Python 3.11+.

Run:

    python -m pytest

Phase 1 is intentionally small. Later phases will add execution, verification, durable state, MCP adapters, and specialized workers.
