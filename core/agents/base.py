import json
from typing import Any

from core.llm.base import LLMProvider
from core.schemas import AgentResult, Message, Role, ToolCall, ToolResult
from core.tools.base import ToolRegistry

MAX_TOOL_ROUNDS = 10


class BaseAgent:
    """Base agent that runs the LLM → tool call → LLM loop (multi-turn)."""

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str,
    ):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt

    async def run(
        self,
        messages: list[Message],
        user_id: int = 0,
    ) -> AgentResult:
        full_messages = [
            Message(role=Role.SYSTEM, content=self.system_prompt),
            *messages,
        ]

        tool_schemas = self.tools.to_ollama_schemas() or None
        all_tool_results: list[ToolResult] = []
        action = None

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self.llm.chat(full_messages, tools=tool_schemas)

            if "message" not in response:
                return AgentResult(
                    response="Failed to get a response from the model.",
                    tool_results=all_tool_results,
                    action=action,
                )

            msg = response["message"]
            content = msg.get("content", "")

            # Some small models write tool calls as text instead of using
            # the tool_calls field. Detect and parse them.
            if not msg.get("tool_calls") and "<tool_response>" in content:
                parsed = self._parse_text_tool_calls(content)
                if parsed:
                    msg["tool_calls"] = parsed
                    # Remove the fake tool_response from the text
                    import re
                    content = re.sub(
                        r"<tool_response>.*?</tool_response>\s*",
                        "",
                        content,
                        flags=re.DOTALL,
                    ).strip()
                    msg["content"] = content

            # No tool calls — final response, exit loop
            if not msg.get("tool_calls"):
                return AgentResult(
                    response=content or "An error occurred.",
                    tool_results=all_tool_results,
                    action=action,
                )

            # Execute tool calls
            round_results: list[ToolResult] = []
            for tool_call in msg["tool_calls"]:
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                arguments = func.get("arguments", {})

                if isinstance(arguments, str):
                    arguments = json.loads(arguments)

                result = await self.tools.execute(
                    tool_name, user_id=user_id, **arguments
                )
                tr = ToolResult(tool_name=tool_name, result=result)
                round_results.append(tr)
                all_tool_results.append(tr)

                if "action" in result:
                    action = result

            # Add assistant message + tool results to conversation
            full_messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=content,
                    tool_calls=[
                        ToolCall(
                            name=tc["function"]["name"],
                            arguments=tc["function"].get("arguments", {}),
                        )
                        for tc in msg["tool_calls"]
                    ],
                )
            )

            for tr in round_results:
                full_messages.append(
                    Message(
                        role=Role.TOOL,
                        content=json.dumps(tr.result, ensure_ascii=False),
                    )
                )

            # Loop continues — next iteration sends tools again

        # Exceeded max rounds
        return AgentResult(
            response="Failed to complete the request processing.",
            tool_results=all_tool_results,
            action=action,
        )

    @staticmethod
    def _parse_text_tool_calls(content: str) -> list[dict] | None:
        """Parse tool calls that small models write as text."""
        import re
        match = re.search(
            r"<tool_response>\s*(\[.*?\])\s*</tool_response>",
            content,
            re.DOTALL,
        )
        if not match:
            return None
        try:
            calls = json.loads(match.group(1))
            return [
                {
                    "function": {
                        "name": c.get("name", ""),
                        "arguments": c.get("arguments", {}),
                    }
                }
                for c in calls
                if isinstance(c, dict) and "name" in c
            ]
        except (json.JSONDecodeError, TypeError):
            return None