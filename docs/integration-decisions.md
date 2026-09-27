# Unified AI Agent — Integration Decisions

## Goal

The original specification requires one primary interface with many capabilities, specialized workers where they add real value, interoperable task/result envelopes, evidence-first verification, persistent state, fallbacks, and a €0/month target where practical.

The repository now has a provider/worker boundary that can host native providers, in-process workers, or external JSON-lines worker processes.

## Current external ecosystem assessment

### Hermes

Hermes currently exposes MCP integration and an ACP server, and its ACP toolset can include files, terminal/process, web/browser, memory, skills, code execution, and delegation. It is therefore a strong candidate for a specialized execution worker when terminal/browser autonomy is required.

Sources:
- https://github.com/NousResearch/hermes-agent
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md
- https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/acp.md

Decision: integrate through a worker adapter when that execution boundary is needed; do not embed Hermes into the core.

### OpenClaw

OpenClaw provides a Gateway-oriented session architecture and currently exposes both MCP and ACP paths. Its ACP bridge maps ACP sessions to Gateway session keys, while ACP Agents can run external harnesses.

Sources:
- https://github.com/openclaw/openclaw
- https://github.com/openclaw/openclaw/blob/main/docs/cli/acp.md
- https://github.com/openclaw/openclaw/blob/main/docs/cli/mcp.md
- https://github.com/openclaw/openclaw/blob/main/docs/tools/acp-agents.md

Decision: treat OpenClaw as an optional gateway/session runtime, not as the unified agent core. It becomes valuable when persistent messaging/session orchestration is required.

### OpenHands

The current OpenHands CLI repository states that the OpenHands CLI is no longer actively maintained and points users toward Agent Canvas.

Source:
- https://github.com/OpenHands/OpenHands-CLI

Decision: do not make the legacy OpenHands CLI a core dependency.

### Qwen Code

Qwen Code currently supports specialized subagents with separate context and controlled tools, and supports MCP server configuration.

Sources:
- https://github.com/QwenLM/qwen-code
- https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/sub-agents.md
- https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/mcp.md

Decision: useful as a coding/reasoning worker when its CLI/runtime is available. Do not duplicate its subagent system inside the core.

### Kilo

Kilo currently provides a CLI coding agent, MCP management, and an ACP server.

Sources:
- https://kilo.ai/docs
- https://kilo.ai/docs/code-with-ai/platforms/cli
- https://kilo.ai/docs/code-with-ai/platforms/cli-reference
- https://kilo.ai/docs/automate/mcp/using-in-cli

Decision: useful as an alternative coding worker. Do not add it alongside multiple equivalent coding workers unless routing measurements justify the duplication.

## Interoperability strategy

The core does not assume that MCP and ACP are interchangeable.

- MCP: tool/resource interoperability.
- ACP: agent/client interoperability and session delegation.
- CLI: process-level execution.
- API: programmatic service integration.
- Gateway: routing/session infrastructure.

The external process adapter provides a minimal local process boundary without tying the core to a vendor protocol. Protocol-specific adapters can be added later behind the same Worker/Provider contract.

## €0/month strategy

Prefer:

1. Native capabilities.
2. Existing connected integrations.
3. Local/open-source workers.
4. Free-tier services only when necessary.
5. Persistent state and fallback routing to reduce dependence on one limited resource.

The goal is not to defeat provider limits. The goal is to avoid unnecessary dependence on any one provider.

## Security boundary

The external process adapter uses an explicit argument vector and shell=False. It does not provide a sandbox by itself.

Any worker that can execute arbitrary terminal commands must be treated as a high-risk capability and placed behind explicit policy/approval and, for untrusted work, a process/container sandbox.

## First delegation proof

The repository contains an in-process worker proof and an external JSON-lines worker adapter. Both enter through the same capability registry, router, execution engine, verification engine, and result contract.

This keeps the architecture:

User -> Control Plane -> Router -> Worker -> Verification -> Durable State -> Result

rather than turning each external agent into a separate competing control plane.
