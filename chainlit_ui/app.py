# hiya! this script implements the ui for the chainlit application which should launch in your web browswer
from __future__ import annotations

import json
import os
from typing import Any

import chainlit as cl
from mcp import ClientSession
from ollama import AsyncClient, RequestError, ResponseError

from ollama_agent import MAX_TOOL_ROUNDS, SYSTEM_PROMPT, run_agent_turn


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))


def _thinking_mode() -> bool | str:
    configured = os.getenv("OLLAMA_THINK")
    if configured:
        normalized = configured.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return normalized

    if OLLAMA_MODEL.lower().startswith("gpt-oss"):
        return "low"
    return False


def _ollama_client() -> AsyncClient:
    return AsyncClient(host=OLLAMA_HOST)


def _tool_result_text(result: Any) -> str:
    """Turn an MCP CallToolResult into text that an LLM can consume."""
    if result.structuredContent is not None:
        payload: Any = result.structuredContent
    else:
        payload = [
            block.model_dump(mode="json")
            if hasattr(block, "model_dump")
            else str(block)
            for block in result.content
        ]

    return json.dumps(
        {
            "is_error": bool(result.isError),
            "result": payload,
        },
        default=str,
    )


@cl.on_chat_start
async def on_chat_start() -> None:
    cl.user_session.set(
        "messages",
        [{"role": "system", "content": SYSTEM_PROMPT}],
    )
    cl.user_session.set("mcp_tools", {})

    await cl.Message(
        content=(
            f"CDSS assistant ready with **{OLLAMA_MODEL}**. "
            "Connect the CDSS server with the MCP plug, then ask me to "
            "start or work through a case."
        )
    ).send()


@cl.on_mcp_connect
async def on_mcp_connect(
    connection: Any,
    session: ClientSession,
) -> None:
    result = await session.list_tools()
    current_tools = cl.user_session.get("mcp_tools", {})

    for tool in result.tools:
        current_tools[tool.name] = {
            "connection": connection.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }

    cl.user_session.set("mcp_tools", current_tools)

    tool_names = "\n".join(f"- `{tool.name}`" for tool in result.tools)
    await cl.Message(
        content=(
            f"Connected to **{connection.name}**. I can now use:\n\n"
            f"{tool_names}"
        )
    ).send()


@cl.on_mcp_disconnect
async def on_mcp_disconnect(
    name: str,
    session: ClientSession,
) -> None:
    current_tools = cl.user_session.get("mcp_tools", {})
    remaining_tools = {
        tool_name: details
        for tool_name, details in current_tools.items()
        if details["connection"] != name
    }
    cl.user_session.set("mcp_tools", remaining_tools)
    await cl.Message(content=f"Disconnected from **{name}**.").send()


async def _call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    tools = cl.user_session.get("mcp_tools", {})
    tool = tools.get(tool_name)

    if tool is None:
        return json.dumps(
            {
                "is_error": True,
                "error": f"Unknown or disconnected tool: {tool_name}",
            }
        )

    mcp_session_entry = cl.context.session.mcp_sessions.get(
        tool["connection"]
    )
    if mcp_session_entry is None:
        return json.dumps(
            {
                "is_error": True,
                "error": (
                    f"MCP connection {tool['connection']} is unavailable."
                ),
            }
        )

    mcp_session, _ = mcp_session_entry

    async with cl.Step(name=tool_name, type="tool") as step:
        step.input = json.dumps(arguments, indent=2)
        result = await mcp_session.call_tool(tool_name, arguments)
        output = _tool_result_text(result)
        step.output = output
        return output


@cl.on_message
async def on_message(message: cl.Message) -> None:
    mcp_tools = cl.user_session.get("mcp_tools", {})
    if not mcp_tools:
        await cl.Message(
            content=(
                "Connect the CDSS MCP server using the plug icon before "
                "asking me to work with a case."
            )
        ).send()
        return

    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": details["description"],
                "parameters": details["input_schema"],
            },
        }
        for tool_name, details in mcp_tools.items()
    ]

    messages = cl.user_session.get(
        "messages",
        [{"role": "system", "content": SYSTEM_PROMPT}],
    )
    messages.append({"role": "user", "content": message.content})

    try:
        answer = await run_agent_turn(
            client=_ollama_client(),
            model=OLLAMA_MODEL,
            messages=messages,
            tools=tool_definitions,
            call_tool=_call_mcp_tool,
            max_tool_rounds=MAX_TOOL_ROUNDS,
            think=_thinking_mode(),
            num_ctx=OLLAMA_NUM_CTX,
        )
    except ResponseError as error:
        answer = (
            f"Ollama returned an error: {error.error}\n\n"
            f"Check that Ollama is running and that `{OLLAMA_MODEL}` is "
            "installed."
        )
    except (RequestError, ConnectionError, OSError) as error:
        answer = (
            f"I could not reach Ollama at `{OLLAMA_HOST}`: {error}. "
            "Start Ollama and try again."
        )
    except Exception as error:
        answer = f"The model request failed: {error}"

    cl.user_session.set("messages", messages)
    await cl.Message(content=answer).send()
