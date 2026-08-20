from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


sys.path.insert(0, str(Path(__file__).resolve().parent))

from ollama_agent import SYSTEM_PROMPT, run_agent_turn


def _response(
    content: str = "",
    tool_calls=None,
    thinking: str = "",
):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=tool_calls or [],
            thinking=thinking,
        )
    )


def _tool_call(name: str, arguments: dict):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        )
    )


class RunAgentTurnTests(unittest.IsolatedAsyncioTestCase):
    def test_system_prompt_treats_medkit_as_closed_world(self):
        self.assertIn(
            "Treat that tool's result as a closed world",
            SYSTEM_PROMPT,
        )

    def test_system_prompt_stops_after_assessment_batch(self):
        self.assertIn(
            "include all requested",
            SYSTEM_PROMPT,
        )
        self.assertIn(
            "Clinical guidance requires a separate user message",
            SYSTEM_PROMPT,
        )
        self.assertIn(
            "Do not add or substitute treatments",
            SYSTEM_PROMPT,
        )

    async def test_returns_answer_without_tool_call(self):
        client = SimpleNamespace(
            chat=AsyncMock(return_value=_response("Hello"))
        )
        messages = [{"role": "user", "content": "Hello"}]

        answer = await run_agent_turn(
            client=client,
            model="test-model",
            messages=messages,
            tools=[],
            call_tool=AsyncMock(),
        )

        self.assertEqual(answer, "Hello")
        self.assertEqual(messages[-1]["role"], "assistant")

    async def test_calls_tool_then_returns_natural_language(self):
        client = SimpleNamespace(
            chat=AsyncMock(
                side_effect=[
                    _response(
                        tool_calls=[
                            _tool_call(
                                "start_case",
                                {"scenario_id": "case_001"},
                            )
                        ],
                        thinking="private reasoning state",
                    ),
                    _response("Case 001 has started."),
                ]
            )
        )
        call_tool = AsyncMock(return_value='{"started": true}')
        messages = [
            {
                "role": "user",
                "content": "Start case 001",
            }
        ]

        answer = await run_agent_turn(
            client=client,
            model="test-model",
            messages=messages,
            tools=[{"type": "function", "function": {}}],
            call_tool=call_tool,
        )

        self.assertEqual(answer, "Case 001 has started.")
        call_tool.assert_awaited_once_with(
            "start_case",
            {"scenario_id": "case_001"},
        )
        self.assertEqual(messages[-2]["role"], "tool")
        self.assertEqual(messages[-2]["tool_name"], "start_case")
        first_assistant = messages[-3]
        self.assertEqual(
            first_assistant["thinking"],
            "private reasoning state",
        )
        second_call_messages = client.chat.await_args_list[1].kwargs[
            "messages"
        ]
        self.assertEqual(
            second_call_messages[-3]["thinking"],
            "private reasoning state",
        )

    async def test_passes_thinking_level_and_context_size(self):
        client = SimpleNamespace(
            chat=AsyncMock(return_value=_response("Done"))
        )

        await run_agent_turn(
            client=client,
            model="gpt-oss:20b",
            messages=[{"role": "user", "content": "Help"}],
            tools=[],
            call_tool=AsyncMock(),
            think="low",
            num_ctx=8192,
        )

        call = client.chat.await_args
        self.assertEqual(call.kwargs["think"], "low")
        self.assertEqual(call.kwargs["options"]["num_ctx"], 8192)

    async def test_assessment_batch_is_displayed_before_differential(self):
        client = SimpleNamespace(
            chat=AsyncMock(
                side_effect=[
                    _response(
                        tool_calls=[
                            _tool_call(
                                "perform_assessment",
                                {"trigger_id": "measure_heart_rate"},
                            ),
                            _tool_call(
                                "get_clinical_guidance",
                                {"task": "differential"},
                            ),
                        ]
                    ),
                    _response(
                        tool_calls=[
                            _tool_call(
                                "perform_assessment",
                                {"trigger_id": "measure_spo2"},
                            ),
                        ]
                    ),
                    _response("Assessment batch complete."),
                    _response(
                        "Recorded: heart rate 110 beats/min and SpO2 58%."
                    ),
                ]
            )
        )
        call_tool = AsyncMock(return_value='{"accepted": true}')
        messages = [
            {
                "role": "user",
                "content": "Measure heart rate and SpO2.",
            }
        ]

        answer = await run_agent_turn(
            client=client,
            model="test-model",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {"name": "perform_assessment"},
                },
                {
                    "type": "function",
                    "function": {"name": "get_clinical_guidance"},
                },
            ],
            call_tool=call_tool,
        )

        self.assertIn("heart rate 110", answer)
        self.assertEqual(call_tool.await_count, 2)
        self.assertEqual(
            [call.args for call in call_tool.await_args_list],
            [
                (
                    "perform_assessment",
                    {"trigger_id": "measure_heart_rate"},
                ),
                (
                    "perform_assessment",
                    {"trigger_id": "measure_spo2"},
                ),
            ],
        )
        self.assertEqual(client.chat.await_count, 4)
        continuation_tools = client.chat.await_args_list[1].kwargs["tools"]
        self.assertEqual(len(continuation_tools), 1)
        self.assertEqual(
            continuation_tools[0]["function"]["name"],
            "perform_assessment",
        )
        self.assertEqual(client.chat.await_args_list[3].kwargs["tools"], [])
        deferred = [
            message
            for message in messages
            if message.get("role") == "tool"
            and "deferred_until_next_user_turn" in message["content"]
        ]
        self.assertEqual(len(deferred), 1)


if __name__ == "__main__":
    unittest.main()
