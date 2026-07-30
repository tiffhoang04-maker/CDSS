from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from ollama import AsyncClient


MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """
You are the conversational interface for a clinical decision-support
simulation. This is a training environment, not a substitute for real medical
care.

Use MCP tools to retrieve patient facts and graph evidence. You may use
general medical knowledge to interpret those facts and rank a provisional
differential. Clearly distinguish:

1. observed patient facts;
2. knowledge-graph-supported conclusions;
3. model inference based on general medical knowledge.

Never claim that an inferred diagnosis is graph-supported when it is not.
Do not invent patient findings.

When the user asks for treatment options specifically from MedKit or the
knowledge graph, call get_medkit_treatment_options with an exact diagnosis ID
from the current differential. Treat that tool's result as a closed world:

- Return only exact options and identifiers present in its options list.
- Do not add or substitute treatments from general medical knowledge.
- If option_count is zero, say that no graph-supported MedKit treatment option
  was found for that diagnosis.
- Never imply that a procedure, facility, staff capability, or item is
  available merely because it would be medically useful.

After tool calls, explain the result in concise, readable Markdown. Include the
current workflow stage, important findings, and the recommended next step when
available. Do not dump raw JSON unless the user explicitly asks for it. Clearly
state tool errors or missing information.
""".strip()

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[str]]


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _normalize_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        return parsed
    if hasattr(arguments, "model_dump"):
        return arguments.model_dump(mode="json")
    raise ValueError("Tool arguments must be an object.")


def _assistant_message(message: Any) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "role": "assistant",
        "content": _value(message, "content", "") or "",
    }

    thinking = _value(message, "thinking", None)
    if thinking:
        # Preserve reasoning state for the next Ollama request, as required
        # for thinking-model tool loops. It is never returned to the UI.
        normalized["thinking"] = thinking

    tool_calls = _value(message, "tool_calls", None) or []
    if tool_calls:
        normalized["tool_calls"] = [
            {
                "function": {
                    "name": _value(
                        _value(call, "function"),
                        "name",
                    ),
                    "arguments": _normalize_arguments(
                        _value(
                            _value(call, "function"),
                            "arguments",
                            {},
                        )
                    ),
                }
            }
            for call in tool_calls
        ]

    return normalized


async def run_agent_turn(
    *,
    client: AsyncClient,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    call_tool: ToolCaller,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    think: bool | str | None = None,
    num_ctx: int = 8192,
) -> str:
    """Let Ollama choose MCP tools until it produces a final response."""
    for _ in range(max_tool_rounds):
        response = await client.chat(
            model=model,
            messages=messages,
            tools=tools,
            stream=False,
            think=think,
            options={
                "temperature": 0,
                "num_ctx": num_ctx,
            },
        )
        assistant = _assistant_message(response.message)
        messages.append(assistant)

        tool_calls = assistant.get("tool_calls", [])
        if not tool_calls:
            content = assistant["content"].strip()
            return content or (
                "The model completed without returning a response. "
                "Please try rephrasing the request."
            )

        for tool_call in tool_calls:
            function = tool_call["function"]
            tool_name = function["name"]
            arguments = function["arguments"]

            try:
                result = await call_tool(tool_name, arguments)
            except Exception as error:
                result = json.dumps(
                    {
                        "is_error": True,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": result,
                }
            )

    return (
        "I stopped after too many consecutive tool-call rounds. "
        "Please review the visible tool results or make a more specific request."
    )
