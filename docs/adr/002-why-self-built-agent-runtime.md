# ADR 002: Self-built agent runtime instead of Dify/LangGraph

## Context

PawPilot needs an agent loop for the listing generation and review analysis scenarios.
Candidates:

1. Dify (visual workflow platform)
2. LangGraph (framework)
3. Self-built runtime (small Python loop)

## Decision

Build a **minimal deterministic agent runtime** in Python.

## Rationale

- Demonstrates depth. FDE job descriptions repeatedly ask for "Agent orchestration" and the
  ability to explain "why Agent dead loops and how to prevent them." A small self-built runtime
  is the strongest evidence.
- Avoids platform magic. Dify is excellent for quick prototypes but hides the loop, state
  management, and guardrails. A reviewer cannot tell whether the candidate understands them.
- Controlled scope. The runtime is under 200 lines: tool registry, max-iteration guard, timeout,
  and conversation memory. It is easy to explain in interviews.
- MCP alignment. Tool definitions are reused for FastMCP, proving the same logic serves API and
  external clients.

## Consequences

- More code to maintain than using a framework.
- Future complex workflows (multi-agent, branching) may justify migrating to LangGraph. The
  current abstraction keeps that path open without over-engineering.
