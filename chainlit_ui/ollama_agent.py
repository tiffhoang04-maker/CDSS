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

When the user requests one or more assessments, include all requested
perform_assessment calls in the same tool-call batch. After any assessment
results are returned, summarize the newly recorded results and the current
model-visible patient record, then stop and return control to the user. Never
call get_clinical_guidance or generate a differential in the same turn as an
assessment. Clinical guidance requires a separate user message.

If get_clinical_guidance returns no_graph_matches, formulate a provisional
clinical name using only the observed patient facts. Label that name as model
inference, then call resolve_graph_candidate.

resolve_graph_candidate searches Disease first and Condition second. Use the
exact candidate_id and candidate_type returned by that tool when calling
get_medkit_treatment_options.

A successful name resolution establishes that a node exists in the graph. It
does not independently confirm the diagnosis.

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

ASSESSMENT_TOOL = "perform_assessment"
ASSESSMENT_CONTINUE_PROMPT = """
Continue only the assessment batch from my original request. If an assessment
I explicitly requested has not yet been performed in this turn, call
perform_assessment for it now using its exact available trigger ID. Do not
repeat a completed assessment, add an unrequested assessment, call clinical
guidance, or generate a differential. If all explicitly requested assessments
are complete, respond that the assessment batch is complete without calling a
tool.
""".strip()
ASSESSMENT_SUMMARY_PROMPT = """
The assessment batch is complete. Using only the tool results already in the
conversation, show the user:

1. the result of each assessment performed in this turn; and
2. a concise summary of all information currently recorded in the
   model-visible patient state.

Clearly separate recorded observations from clinical interpretation. Do not
call tools, generate a differential diagnosis, rank diagnoses, or recommend a
diagnosis. End by asking the user whether they want another assessment or want
to request clinical guidance.
""".strip()


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

        assessment_calls = [
            tool_call
            for tool_call in tool_calls
            if tool_call["function"]["name"] == ASSESSMENT_TOOL
        ]
        if assessment_calls:
            assessment_tools = [
                tool
                for tool in tools
                if tool.get("function", {}).get("name") == ASSESSMENT_TOOL
            ]
            completed_trigger_ids: set[str] = set()
            pending_tool_calls = tool_calls

            for _ in range(max_tool_rounds):
                for tool_call in pending_tool_calls:
                    function = tool_call["function"]
                    tool_name = function["name"]
                    arguments = function["arguments"]
                    trigger_id = str(arguments.get("trigger_id", ""))

                    if (
                        tool_name == ASSESSMENT_TOOL
                        and trigger_id not in completed_trigger_ids
                    ):
                        try:
                            result = await call_tool(tool_name, arguments)
                        except Exception as error:
                            result = json.dumps(
                                {
                                    "is_error": True,
                                    "error": (
                                        f"{type(error).__name__}: {error}"
                                    ),
                                }
                            )
                        completed_trigger_ids.add(trigger_id)
                    else:
                        result = json.dumps(
                            {
                                "is_error": False,
                                "status": "deferred_until_next_user_turn",
                                "message": (
                                    f"{tool_name} was not executed because "
                                    "the assessment batch must be shown to "
                                    "the user before another workflow step."
                                ),
                            }
                        )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": tool_name,
                            "content": result,
                        }
                    )

                messages.append(
                    {
                        "role": "user",
                        "content": ASSESSMENT_CONTINUE_PROMPT,
                    }
                )
                continuation_response = await client.chat(
                    model=model,
                    messages=messages,
                    tools=assessment_tools,
                    stream=False,
                    think=think,
                    options={
                        "temperature": 0,
                        "num_ctx": num_ctx,
                    },
                )
                continuation = _assistant_message(
                    continuation_response.message
                )
                messages.append(continuation)
                pending_tool_calls = continuation.get("tool_calls", [])
                if not pending_tool_calls:
                    break

            messages.append(
                {
                    "role": "user",
                    "content": ASSESSMENT_SUMMARY_PROMPT,
                }
            )
            summary_response = await client.chat(
                model=model,
                messages=messages,
                tools=[],
                stream=False,
                think=think,
                options={
                    "temperature": 0,
                    "num_ctx": num_ctx,
                },
            )
            summary = _assistant_message(summary_response.message)
            summary.pop("tool_calls", None)
            messages.append(summary)
            content = summary["content"].strip()
            return content or (
                "The assessment results were recorded. Would you like "
                "another assessment or clinical guidance?"
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
