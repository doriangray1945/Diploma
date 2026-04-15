from core.agents.base import BaseAgent
from core.agents.orchestrator import OrchestratorAgent
from core.agents.planner import PlannerAgent
from core.agents.validator import ValidatorAgent
from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.providers.base import DataProvider
from core.schemas import AgentResult, Complexity, Message, Role, UserContext
from core.tools.base import ToolRegistry


def _build_system_prompt(tools: ToolRegistry, config: CoreConfig) -> str:
    """Build system prompt from business context + auto-generated tool guide."""
    parts = []

    if config.business_prompt:
        parts.append(config.business_prompt)

    tools_list = tools.all()
    if tools_list:
        parts.append(
            "CRITICAL RULES:\n"
            "- You MUST call your tools to perform ANY action (search, filter, add to cart, create order, etc.)\n"
            "- NEVER describe how to call a tool — just call it directly\n"
            "- NEVER pretend you performed an action without calling the tool\n"
            "- NEVER say 'done' or 'added' unless you actually called the tool and got a result\n"
            "- When the user asks to do something with ALL products, you MUST call the tool for EACH product. "
            "Do not skip any. Do not stop halfway.\n"
            "- You have NO internal data. All information comes from tool results only\n"
            "- All IDs are numbers from tool results only. NEVER invent IDs\n"
            "- NEVER invent or list product names, prices, or details from memory. "
            "The user sees real products in the catalog UI"
        )

    parts.append(f"ALWAYS respond in {config.language}. Be concise.")

    return "\n\n".join(parts)


class Pipeline:
    """Main entry point: text in -> structured result out."""

    def __init__(
        self,
        llm: LLMProvider,
        provider: DataProvider,
        config: CoreConfig | None = None,
    ):
        self.llm = llm
        self.provider = provider
        self.config = config or CoreConfig()

    async def run(
        self,
        text: str,
        tools: ToolRegistry,
        user_context: UserContext,
    ) -> AgentResult:
        # 1. Orchestrator: classify complexity
        orchestrator = OrchestratorAgent(self.llm)
        complexity = await orchestrator.classify(text)

        # Build message history
        messages = [*user_context.history, Message(role=Role.USER, content=text)]

        # Build system prompt: business context + tools + rules
        system_prompt = _build_system_prompt(tools, self.config)

        # 2. Execute based on complexity
        agent = BaseAgent(self.llm, tools, system_prompt)

        if complexity == Complexity.COMPLEX:
            planner = PlannerAgent(self.llm, tools)
            steps = await planner.plan(text, user_context.history)

            if steps and steps[0].tool_name:
                result = await planner.execute_plan(
                    steps, agent, messages, user_id=user_context.user_id
                )
            else:
                result = await agent.run(messages, user_id=user_context.user_id)
        else:
            result = await agent.run(messages, user_id=user_context.user_id)

        result.complexity = complexity

        # 3. Validator checks the result
        validator = ValidatorAgent(self.provider)
        result = await validator.validate(result)

        return result