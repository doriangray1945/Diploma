from __future__ import annotations

from core.agents.args_filler import ArgsFiller
from core.agents.base import BaseAgent
from core.agents.decomposer import Decomposer
from core.agents.plan_executor import PlanExecutor
from core.agents.schema_planner import SchemaPlannerAgent
from core.agents.validator import ValidatorAgent
from core.config import CoreConfig
from core.llm.base import LLMProvider
from core.parsing import parse_user_text
from core.providers.base import DataProvider
from core.schemas import (
    AgentResult,
    Complexity,
    Intent,
    Message,
    Role,
    SessionContext,
    UserContext,
)
from core.tools.base import ToolRegistry


def _build_legacy_system_prompt(tools: ToolRegistry, config: CoreConfig) -> str:
    """System prompt used ONLY in the legacy native-tool-calling path.

    Schema Router uses its own PLANNER_SYSTEM_PROMPT, which is incompatible with
    these aggressive 'always call a tool' rules.
    """
    parts: list[str] = []

    if config.business_prompt:
        parts.append(config.business_prompt)

    if tools.all():
        parts.append(
            "CRITICAL RULES:\n"
            "- You MUST call your tools to perform ANY action (search, filter, "
            "add to cart, create order, etc.)\n"
            "- NEVER describe how to call a tool — just call it directly\n"
            "- NEVER pretend you performed an action without calling the tool\n"
            "- NEVER say 'done' or 'added' unless you actually called the tool "
            "and got a result\n"
            "- When the user asks to do something with ALL products, you MUST "
            "call the tool for EACH product. Do not skip any. Do not stop "
            "halfway.\n"
            "- You have NO internal data. All information comes from tool "
            "results only\n"
            "- All IDs are numbers from tool results only. NEVER invent IDs\n"
            "- NEVER invent or list product names, prices, or details from "
            "memory. The user sees real products in the catalog UI"
        )

    parts.append(f"ALWAYS respond in {config.language}. Be concise.")
    return "\n\n".join(parts)


class Pipeline:
    """Main entry point: text in -> structured result out.

    Two modes (toggled by `config.use_structured_output`):

    * Schema Router (default): one constrained-decoding LLM call returns a
      StructuredPlan with intent + plan + user_message. Plan is executed
      deterministically with reference resolution.
    * Legacy: original Orchestrator -> Planner -> BaseAgent native
      tool-calling loop. Kept for A/B benchmarking.
    """

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
        session_context: SessionContext | None = None,
    ) -> AgentResult:
        session_context = session_context or SessionContext()
        messages = [
            *user_context.history,
            Message(role=Role.USER, content=text),
        ]

        if self.config.use_structured_output:
            result = await self._run_structured(
                messages, tools, user_context, session_context
            )
        else:
            result = await self._run_legacy(messages, tools, user_context)

        validator = ValidatorAgent(self.provider)
        return await validator.validate(result)

    # ---------- Schema Router path ----------

    async def _run_structured(
        self,
        messages: list[Message],
        tools: ToolRegistry,
        user_context: UserContext,
        session_context: SessionContext,
    ) -> AgentResult:
        # Filter the tool registry by user role — non-admins must not see
        # admin tools (add_product/update_product/delete_product) in either
        # the schema enum or the prompt.
        tools = tools.for_role(user_context.role)

        # Dynamic enum values (categories, colors) from DB via provider
        filter_options = await self.provider.get_filter_options()

        # Deterministic pre-parsing of the user's last message
        last_user_text = next(
            (m.content for m in reversed(messages) if m.role == Role.USER),
            "",
        )
        hints = parse_user_text(
            last_user_text, filter_options.get("categories", []) if filter_options else []
        )

        # Stale-context reset on new category or new price filter — clears
        # visible_product_ids from prior search so this turn starts fresh.
        if hints.triggers_reset:
            session_context.last_search = None
            session_context.visible_product_ids = []
            session_context.current_filters = {}

        # Optional 0-th LLM call: rephrase tangled multi-action queries
        # (with typos or "X и Y, остальные по N" grammar) into a clean
        # numbered list. Skipped for short simple queries (no latency cost).
        # Parser hints + args_filler keep working on the ORIGINAL text.
        decomposer = Decomposer(self.llm, self.config)
        effective_text = await decomposer.maybe_decompose(last_user_text)
        messages_for_skeleton = list(messages)
        if effective_text != last_user_text and messages_for_skeleton:
            messages_for_skeleton[-1] = Message(
                role=Role.USER, content=effective_text
            )

        planner = SchemaPlannerAgent(self.llm, tools, self.config)
        args_filler = ArgsFiller(self.llm, tools, self.config)
        executor = PlanExecutor(tools, args_filler)

        # Hybrid pipeline call 1: tool sequence only (no args). The skeleton
        # schema can't leak fields between tools because there is no `args`
        # field at all — args are filled per-step by ArgsFiller below.
        plan = await planner.plan_skeleton(
            messages_for_skeleton, session_context,
            filter_options=filter_options, hints=hints,
        )

        tool_results = []
        issues = []
        if plan.intent == Intent.EXECUTE and plan.plan:
            _, tool_results, issues = await executor.execute(
                plan.plan, session_context, user_context.user_id,
                hints=hints, filter_options=filter_options,
                last_user_text=last_user_text,
            )

            # One corrective retry only for LLM-mistake issues, not for
            # objective semantic outcomes (e.g. "no remaining products
            # after cart consumed everything" — retrying produces garbage).
            retryable = [
                i for i in issues
                if "product_ids is empty" not in i.message
                and "каталог пуст" not in i.message
            ]
            if retryable:
                correction = (
                    "ОШИБКА в предыдущем плане: "
                    + "; ".join(i.message for i in retryable)
                    + ". Сгенерируй исправленный план."
                )
                plan = await planner.plan_skeleton(
                    messages_for_skeleton, session_context,
                    filter_options=filter_options, hints=hints,
                    extra_system=correction,
                )
                if plan.intent == Intent.EXECUTE and plan.plan:
                    _, tool_results, issues = await executor.execute(
                        plan.plan, session_context, user_context.user_id,
                        hints=hints, filter_options=filter_options,
                        last_user_text=last_user_text,
                    )

        action = None
        for tr in reversed(tool_results):
            if isinstance(tr.result, dict) and "action" in tr.result:
                action = tr.result
                break

        return AgentResult(
            response=plan.user_message,
            complexity=Complexity.COMPLEX if len(plan.plan) > 1 else Complexity.SIMPLE,
            tool_results=tool_results,
            action=action,
            validation_issues=issues,
        )

    # ---------- Legacy path (native tool calling) ----------

    async def _run_legacy(
        self,
        messages: list[Message],
        tools: ToolRegistry,
        user_context: UserContext,
    ) -> AgentResult:
        """Fallback: native tool-calling loop via BaseAgent.

        Kept for A/B benchmarking (set use_structured_output=False).
        """
        system_prompt = _build_legacy_system_prompt(tools, self.config)
        agent = BaseAgent(self.llm, tools, system_prompt)
        return await agent.run(messages, user_id=user_context.user_id)
