import json

from core.agents.base import BaseAgent
from core.llm.base import LLMProvider
from core.schemas import AgentResult, Message, PlanStep, Role
from core.tools.base import ToolRegistry


PLANNER_PROMPT = """You are a planner. Given a complex user request, break it down into concrete steps.

Available tools:
{tools_description}

For each step specify:
1. Action description
2. Which tool to use
3. With what parameters

Respond in JSON format:
{{
  "steps": [
    {{"description": "step description", "tool_name": "tool_name", "tool_args": {{}}}},
    ...
  ],
  "summary": "overall plan description"
}}

Be specific. Do not add unnecessary steps."""


class PlannerAgent:
    """Decomposes complex requests into executable steps."""

    def __init__(self, llm: LLMProvider, tools: ToolRegistry):
        self.llm = llm
        self.tools = tools

    async def plan(self, user_message: str, history: list[Message]) -> list[PlanStep]:
        tools_desc = "\n".join(
            f"- {t.name}: {t.description}" for t in self.tools.all()
        )

        messages = [
            Message(
                role=Role.SYSTEM,
                content=PLANNER_PROMPT.format(tools_description=tools_desc),
            ),
            *history,
            Message(role=Role.USER, content=user_message),
        ]

        response = await self.llm.chat(messages, temperature=0.1)

        content = ""
        if "message" in response:
            content = response["message"].get("content", "")

        return self._parse_plan(content)

    async def execute_plan(
        self,
        steps: list[PlanStep],
        agent: BaseAgent,
        history: list[Message],
        user_id: int = 0,
    ) -> AgentResult:
        all_results = []

        for step in steps:
            if step.tool_name:
                result = await self.tools.execute(
                    step.tool_name, user_id=user_id, **step.tool_args
                )
                all_results.append(result)

        # Ask agent to summarize all results
        summary_content = json.dumps(
            {"plan_results": all_results}, ensure_ascii=False
        )
        summary_messages = [
            *history,
            Message(
                role=Role.USER,
                content=f"Plan execution results:\n{summary_content}\n\nSummarize what was found/done for the user.",
            ),
        ]

        result = await agent.run(summary_messages, user_id=user_id)
        result.plan_steps = steps
        return result

    def _parse_plan(self, content: str) -> list[PlanStep]:
        try:
            # Try to extract JSON from the response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
                steps = data.get("steps", [])
                return [
                    PlanStep(
                        description=s.get("description", ""),
                        tool_name=s.get("tool_name"),
                        tool_args=s.get("tool_args", {}),
                    )
                    for s in steps
                ]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return [PlanStep(description="Execute user request")]
