# ACP integration status

This repository contains an ACP process worker boundary for agent runtimes that expose JSON-RPC over stdio.

## Evidence levels

- Implemented: `unified_agent/acp.py` provides an ACP v1 process adapter and a Hermes-specific command wrapper.
- Unit-tested: the adapter is tested against a deterministic fake ACP server for initialization, session creation, streaming updates, permission requests, and resume.
- Real-runtime smoke test: opt-in only via `RUN_HERMES_ACP_SMOKE=1`. It is not part of default CI because it requires a configured Hermes runtime/model provider and may incur model usage.
- Production integration: not claimed until the opt-in smoke test passes against the installed Hermes runtime.

Hermes documents `hermes acp` as a JSON-RPC-over-stdio ACP server with session creation, prompt streaming, permission requests, cancellation, and session load/resume support. The Unified Agent therefore treats Hermes as a specialized worker behind the existing control plane rather than as a second control plane.

The ACP worker deliberately answers permission requests with cancellation for now. This keeps the default integration least-privilege; approval delegation is a separate policy/UX problem and must not be silently enabled.

The external process boundary is not a sandbox. High-risk terminal/browser execution still requires an isolation layer before untrusted workloads are allowed.