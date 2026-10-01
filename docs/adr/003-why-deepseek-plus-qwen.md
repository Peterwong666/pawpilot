# ADR 003: DeepSeek + Qwen as LLM providers

## Context

PawPilot needs LLM access for generation and evaluation. Options include OpenAI, Anthropic,
Google, DeepSeek, Qwen, and local models.

## Decision

Use **DeepSeek** as the primary provider and **Qwen** as the comparison provider.

## Rationale

- Cost efficiency. Running 100+ evaluation examples repeatedly would be expensive with Claude or
  GPT-4. DeepSeek and Qwen are cost-effective and support the OpenAI-compatible protocol.
- Native Chinese support. Qwen handles the Chinese SOP/FAQ documents in the knowledge base
  gracefully, while DeepSeek is strong for English.
- Interview story. The JDs ask for "评测对比 2 个模型"; dual-provider support makes this
  concrete.
- Simplicity. Both expose OpenAI-compatible endpoints, so the code stays provider-agnostic with
  a single client abstraction.

## Consequences

- Output quality may differ from Claude/GPT-4; we compensate with deterministic retrieval
  metrics and cross-model judging.
- Future work can add a local Ollama provider for offline demos.
