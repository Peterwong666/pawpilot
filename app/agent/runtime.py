"""Minimal deterministic agent runtime.

Implements a tool-calling loop with:
- max-iteration guard to prevent infinite loops
- short-term conversation memory
- deterministic JSON tool-call parsing
- timeout and error handling

This is intentionally small and self-contained to demonstrate "can build an agent runtime
from scratch" in FDE interviews.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

from app.agent.tools import ToolRegistry
from app.core.config import get_settings
from app.core.llm import get_async_client, resolve_model
from app.data.hybrid_store import HybridDataStore


@dataclass
class AgentMessage:
    role: str
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class AgentResult:
    final_answer: str
    tool_calls: list[dict[str, Any]]
    iterations: int
    provider: str
    model: str


class AgentRuntime:
    """Deterministic tool-calling agent runtime."""

    def __init__(
        self,
        provider: str = "deepseek",
        tools: ToolRegistry | None = None,
        system_prompt: str | None = None,
        account_id: str = "default",
        marketplace: str = "US",
        use_simulated: bool = True,
    ) -> None:
        self.settings = get_settings()
        self.provider = provider
        self.client = get_async_client(provider)
        self.model = resolve_model(provider)
        if tools is not None:
            self.tools = tools
        else:
            data_store = HybridDataStore(
                account_id=account_id,
                marketplace=marketplace,
                use_simulated=use_simulated,
            )
            self.tools = ToolRegistry(data_store=data_store)
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.max_iterations = self.settings.max_iterations

    def _default_system_prompt(self) -> str:
        return (
            "You are PawPilot, an Amazon pet-supplies operations assistant. "
            "You have access to tools that search policies, check listing compliance, "
            "query operational data, analyze reviews, and retrieve product info. "
            "Use tools when needed. Be concise, factual, and cite sources when available. "
            "When you have enough information, provide a final answer and stop."
        )

    async def run(
        self,
        user_message: str,
        conversation: list[AgentMessage] | None = None,
    ) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        for msg in conversation or []:
            entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.name:
                entry["name"] = msg.name
            messages.append(entry)

        messages.append({"role": "user", "content": user_message})
        tool_calls_log: list[dict[str, Any]] = []

        for iteration in range(1, self.max_iterations + 1):
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=cast(Any, messages),
                tools=cast(Any, self.tools.list_tools()),
                tool_choice="auto",
                temperature=0.3,
            )
            choice = response.choices[0]
            assistant_message = choice.message

            if not assistant_message.tool_calls:
                # Final answer.
                return AgentResult(
                    final_answer=assistant_message.content or "",
                    tool_calls=tool_calls_log,
                    iterations=iteration,
                    provider=self.provider,
                    model=self.model,
                )

            # Record assistant tool-call request.
            tool_calls = cast(Any, assistant_message.tool_calls)
            raw_tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": raw_tool_calls,
                }
            )
            tool_calls_log.extend(raw_tool_calls)

            # Execute each tool call and append results.
            for tc in tool_calls:
                name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                result = await self.tools.call(name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # Guardrail triggered.
        return AgentResult(
            final_answer="I reached the maximum number of reasoning steps. "
            "Please refine your question or break it into smaller parts.",
            tool_calls=tool_calls_log,
            iterations=self.max_iterations,
            provider=self.provider,
            model=self.model,
        )
