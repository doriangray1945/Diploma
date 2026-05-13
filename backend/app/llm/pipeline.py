"""Single-shot pipeline for the fine-tuned furniture model.

The fine-tuned `qwen2.5-3b-furniture` model emits a complete
`{"plan": [{tool, args}, ...]}` from one LLM call given a JSON-Schema
system prompt. We feed it that prompt (built from the role-filtered tool
registry with current DB enums), parse the JSON response, and let
`PlanExecutor` + `ParseHints` handle quantifier resolution and numeric
corrections.

Single execution path — the specialist model handles tool selection +
arg filling end-to-end.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator

from app.llm.agents.plan_executor import PlanExecutor
from app.llm.agents.validator import ValidatorAgent
from app.llm.config import CoreConfig
from app.llm.clients.base import LLMProvider
from app.llm.parsing import parse_user_text
from app.llm.prompts.system import build_system_prompt
from app.llm.providers.base import DataProvider
from app.llm.schemas import (
    AgentResult,
    Complexity,
    Message,
    PlanStepV2,
    Role,
    SessionContext,
    UserContext,
)
from app.llm.tools.base import ToolRegistry
from app.services import plan_cache


# Cosine-similarity threshold above which we trust a cached plan and skip
# the fine-tuned LLM call entirely. 0.95 is conservative — normalized text
# strips numbers/categories/qualifiers before embed, so siblings like
# «диваны до 50k» and «диваны до 90k» map to the same canonical query.
_CACHE_TRUST_THRESHOLD = 0.95


# Human-readable status per tool — shown in UI thinking-block. One step per
# planned tool call. Keys must match Tool.name values exactly.
_THINKING_LABELS: dict[str, str] = {
    "apply_filters":          "Ищу товары…",
    "add_to_cart":            "Добавляю в корзину…",
    "add_to_favorites":       "Сохраняю в избранное…",
    "clear_cart":             "Очищаю корзину…",
    "clear_favorites":        "Очищаю избранное…",
    "remove_from_cart":       "Убираю из корзины…",
    "remove_from_favorites":  "Убираю из избранного…",
    "update_prices":          "Меняю цены…",
    "update_stock":           "Обновляю остатки…",
    "get_sales_analytics":    "Считаю аналитику…",
}


log = logging.getLogger(__name__)


class _NoOpArgsFiller:
    """Drop-in for ArgsFiller used by PlanExecutor.

    The fine-tuned model already supplies args for every step; we don't
    want PlanExecutor to issue another LLM call per step. Returning {}
    makes PlanExecutor honor `step.args` as-is, then merge ParseHints
    over the top (numbers, quantifier resolution) via its existing logic.
    """

    async def fill(self, *args, **kwargs) -> dict[str, Any]:
        return {}


class Pipeline:
    """Main entry point: text in → structured result out."""

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
        role = user_context.role
        role_filtered = tools.for_role(role)
        filter_options = await self.provider.get_filter_options()
        categories = (filter_options or {}).get("categories", [])

        hints = parse_user_text(text, categories)
        if hints.triggers_reset:
            session_context.last_search = None
            session_context.visible_product_ids = []
            session_context.current_filters = {}

        # ── Semantic cache lookup ─────────────────────────────────────────
        # Same (role-filtered tool set, normalized query) → reuse stored plan.
        # On miss or low similarity, fall through to the LLM call.
        tools_signature = _tools_signature(role_filtered)
        cached_plan_id: int | None = None
        plan_steps: list[PlanStepV2] = []
        try:
            cache_result = await plan_cache.lookup(
                self.provider.db, user_context.user_id,
                text, tools_signature, categories,
            )
        except Exception:
            log.exception("[CACHE] lookup failed")
            cache_result = None

        if cache_result is not None and cache_result[1] >= _CACHE_TRUST_THRESHOLD:
            entry, sim = cache_result
            log.info("[CACHE] HIT sim=%.3f entry_id=%d", sim, entry.id)
            plan_steps = _plan_from_cache(entry.plan_json)
            cached_plan_id = entry.id

        # ── LLM fallback ──────────────────────────────────────────────────
        if not plan_steps:
            # Single-turn — model trained on system + user only, no prior turns.
            # filter_options carries fresh DB enums into each tool's schema.
            prompt_messages = [
                Message(role=Role.SYSTEM,
                        content=build_system_prompt(role_filtered, role, filter_options)),
                Message(role=Role.USER, content=text),
            ]

            log.info("[CHAT] role=%s model=%s text=%r", role, self.config.chat_model, text[:80])
            try:
                response = await asyncio.wait_for(
                    self.llm.chat(prompt_messages, format=None, temperature=0.0),
                    timeout=self.config.planner_schema_timeout,
                )
            except asyncio.TimeoutError:
                log.warning("[CHAT] LLM timeout")
                return AgentResult(
                    response="Подождите, обработка заняла больше обычного. Попробуйте упростить запрос.",
                    complexity=Complexity.SIMPLE,
                )
            except Exception:
                log.exception("[CHAT] LLM error")
                return AgentResult(
                    response="Извините, сейчас не получилось обработать запрос. Попробуйте ещё раз.",
                    complexity=Complexity.SIMPLE,
                )

            raw = (response.get("message") or {}).get("content", "") or ""
            plan_steps = self._parse_plan(raw)
            log.info("[CHAT] parsed %d steps from raw=%r", len(plan_steps), raw[:800])

        executor = PlanExecutor(role_filtered, _NoOpArgsFiller())
        _, tool_results, issues = await executor.execute(
            plan_steps,
            context=session_context,
            user_id=user_context.user_id,
            hints=hints,
            filter_options=filter_options,
            step_texts=[text],
            fallback_text=text,
        )

        action: dict[str, Any] | None = None
        for tr in reversed(tool_results):
            if isinstance(tr.result, dict) and "action" in tr.result:
                action = tr.result
                break

        # ── Cache write-back ──────────────────────────────────────────────
        # Two paths:
        #   - hit reused: bump hit_count + remember entry_id for negative-feedback
        #   - fresh plan succeeded: store it for future similar queries
        # Skip store on empty plans or any tool error — those aren't worth caching.
        session_context.last_cache_hit_id = None
        cache_eligible = bool(plan_steps) and not _has_tool_errors(tool_results)
        if cache_eligible:
            try:
                if cached_plan_id is not None:
                    await plan_cache.record_hit(self.provider.db, cached_plan_id)
                    session_context.last_cache_hit_id = cached_plan_id
                else:
                    plan_json = {"plan": _plan_to_template(plan_steps)}
                    new_id = await plan_cache.store(
                        self.provider.db, user_context.user_id,
                        text, plan_json, tools_signature, categories,
                    )
                    if new_id is not None:
                        session_context.last_cache_hit_id = new_id
                        log.info("[CACHE] STORE entry_id=%d steps=%d", new_id, len(plan_steps))
            except Exception:
                log.exception("[CACHE] write-back failed")

        # ── REPLY (template-based) ────────────────────────────────────────
        # Шаблонный ответ на основе primary action — без второго LLM call.
        # Экономит 5-15с на CPU. Если потребуется более естественные фразы —
        # вернуть _generate_reply (Git history).
        if not plan_steps:
            reply_text = self._template_smalltalk(text)
        else:
            primary_action = None
            primary_count = 0
            for tr in tool_results:
                if isinstance(tr.result, dict) and "action" in tr.result:
                    primary_action = tr.result.get("action")
                    primary_count = tr.result.get("count") or len(
                        tr.result.get("products") or tr.result.get("added") or []
                    )
                    break
            reply_text = self._template_reply(primary_action, primary_count, tool_results)

        result = AgentResult(
            response=reply_text,
            complexity=Complexity.COMPLEX if len(plan_steps) > 1 else Complexity.SIMPLE,
            tool_results=tool_results,
            action=action,
            validation_issues=issues,
        )

        validator = ValidatorAgent(self.provider)
        return await validator.validate(result)

    async def run_stream(
        self,
        text: str,
        tools: ToolRegistry,
        user_context: UserContext,
        session_context: SessionContext | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming variant of run(): yields events as work progresses.

        Event types:
          - {"type": "thinking", "step": str}
              ← human-readable status, emitted at each pipeline phase
          - {"type": "meta", "action": dict|None, "actions": list[dict]}
              ← after tools execute, before reply generation
          - {"type": "token", "content": str}
              ← each chunk of the assistant's text (may be 1 char or many)
          - {"type": "done", "final_text": str}
              ← reply complete; caller persists assistant message
          - {"type": "error", "message": str}
              ← on timeout/error in plan or reply LLM call
        """
        session_context = session_context or SessionContext()
        role = user_context.role
        role_filtered = tools.for_role(role)
        filter_options = await self.provider.get_filter_options()
        categories = (filter_options or {}).get("categories", [])

        yield {"type": "thinking", "step": "Анализирую запрос…"}

        hints = parse_user_text(text, categories)
        if hints.triggers_reset:
            session_context.last_search = None
            session_context.visible_product_ids = []
            session_context.current_filters = {}

        # ── Cache lookup (same as run()) ──────────────────────────────────
        tools_signature = _tools_signature(role_filtered)
        cached_plan_id: int | None = None
        plan_steps: list[PlanStepV2] = []
        try:
            cache_result = await plan_cache.lookup(
                self.provider.db, user_context.user_id,
                text, tools_signature, categories,
            )
        except Exception:
            log.exception("[CACHE] lookup failed")
            cache_result = None

        if cache_result is not None and cache_result[1] >= _CACHE_TRUST_THRESHOLD:
            entry, sim = cache_result
            log.info("[CACHE] HIT sim=%.3f entry_id=%d", sim, entry.id)
            plan_steps = _plan_from_cache(entry.plan_json)
            cached_plan_id = entry.id
            yield {"type": "thinking", "step": "Использую кэшированный план"}

        # ── LLM plan (cache miss) ─────────────────────────────────────────
        if not plan_steps:
            yield {"type": "thinking", "step": "Думаю над планом…"}
            prompt_messages = [
                Message(role=Role.SYSTEM,
                        content=build_system_prompt(role_filtered, role, filter_options)),
                Message(role=Role.USER, content=text),
            ]
            log.info("[STREAM] role=%s model=%s text=%r", role, self.config.chat_model, text[:80])
            try:
                response = await asyncio.wait_for(
                    self.llm.chat(prompt_messages, format=None, temperature=0.0),
                    timeout=self.config.planner_schema_timeout,
                )
            except asyncio.TimeoutError:
                log.warning("[STREAM] plan LLM timeout")
                yield {"type": "error", "message":
                       "Подождите, обработка заняла больше обычного. Попробуйте упростить запрос."}
                return
            except Exception:
                log.exception("[STREAM] plan LLM error")
                yield {"type": "error", "message":
                       "Извините, сейчас не получилось обработать запрос. Попробуйте ещё раз."}
                return
            raw = (response.get("message") or {}).get("content", "") or ""
            plan_steps = self._parse_plan(raw)
            log.info("[STREAM] parsed %d steps", len(plan_steps))

        # Emit one thinking step per planned tool call.
        for ps in plan_steps:
            label = _THINKING_LABELS.get(ps.tool)
            if label:
                yield {"type": "thinking", "step": label}

        # ── Tools execute ─────────────────────────────────────────────────
        executor = PlanExecutor(role_filtered, _NoOpArgsFiller())
        _, tool_results, _issues = await executor.execute(
            plan_steps,
            context=session_context,
            user_id=user_context.user_id,
            hints=hints,
            filter_options=filter_options,
            step_texts=[text],
            fallback_text=text,
        )

        action: dict[str, Any] | None = None
        for tr in reversed(tool_results):
            if isinstance(tr.result, dict) and "action" in tr.result:
                action = tr.result
                break
        actions = [
            tr.result for tr in tool_results
            if isinstance(tr.result, dict) and "action" in tr.result
        ]

        # ── Cache write-back ──────────────────────────────────────────────
        session_context.last_cache_hit_id = None
        cache_eligible = bool(plan_steps) and not _has_tool_errors(tool_results)
        if cache_eligible:
            try:
                if cached_plan_id is not None:
                    await plan_cache.record_hit(self.provider.db, cached_plan_id)
                    session_context.last_cache_hit_id = cached_plan_id
                else:
                    plan_json = {"plan": _plan_to_template(plan_steps)}
                    new_id = await plan_cache.store(
                        self.provider.db, user_context.user_id,
                        text, plan_json, tools_signature, categories,
                    )
                    if new_id is not None:
                        session_context.last_cache_hit_id = new_id
                        log.info("[CACHE] STORE entry_id=%d steps=%d", new_id, len(plan_steps))
            except Exception:
                log.exception("[CACHE] write-back failed")

        # ── Emit meta — фронт обновляет каталог/корзину сейчас ────────────
        yield {"type": "meta", "action": action, "actions": actions}

        # ── Reply: cache hit → шаблон одним токеном; miss → стрим LLM ─────
        primary_action = action.get("action") if action else None
        primary_count = 0
        if action:
            primary_count = action.get("count") or len(
                action.get("products") or action.get("added") or []
            )

        if not plan_steps:
            # Empty plan — conversational fallback
            text_out = self._template_smalltalk(text)
            yield {"type": "token", "content": text_out}
            yield {"type": "done", "final_text": text_out}
            return

        # Template-only reply — без второго LLM call.
        # На CPU LLM reply добавляет 10-15с overhead, что неприемлемо.
        # Шаблоны покрывают типовые actions (apply_filters/add_to_cart/...).
        text_out = self._template_reply(primary_action, primary_count, tool_results)
        yield {"type": "token", "content": text_out}
        yield {"type": "done", "final_text": text_out}

    @staticmethod
    def _template_smalltalk(user_text: str) -> str:
        low = user_text.lower()
        if any(w in low for w in ("привет", "здравств", "доброе утро", "добрый день", "добрый вечер")):
            return "Здравствуйте! Помогу подобрать мебель. Что интересует?"
        if any(w in low for w in ("спасибо", "благодар")):
            return "Пожалуйста! Если ещё что-то подобрать — пишите."
        if any(w in low for w in ("скидк", "акци", "купон", "промокод", "распродаж", "чёрная пятниц", "бонус", "кешбэк")):
            return "Сейчас система скидок не настроена. Могу помочь с подбором мебели по цене?"
        if any(w in low for w in ("оплат", "доставк", "заказ", "менеджер", "возврат")):
            return "По заказам и доставке — оформите заказ через сайт, менеджер свяжется."
        return "Я помогу подобрать мебель. Опишите что вы хотите."

    @staticmethod
    def _template_reply(action: str | None, count: int, tool_results: list) -> str:
        if action == "apply_filters":
            if count == 0:
                return "Не нашла подходящих товаров. Попробуйте изменить фильтры."
            return f"Нашла {count} {'товар' if count == 1 else 'товара' if count < 5 else 'товаров'} — они в каталоге справа."
        if action == "added_to_cart":
            # Подсчитываем сколько не добавили из-за лимита склада
            stock_failed = 0
            for tr in tool_results:
                r = tr.result if isinstance(tr.result, dict) else {}
                if r.get("action") != "added_to_cart":
                    continue
                for err in r.get("errors") or []:
                    msg = err.get("error", "") if isinstance(err, dict) else ""
                    if "склад" in msg.lower() or "наличи" in msg.lower():
                        stock_failed += 1
            base = f"Добавила {count} {'товар' if count == 1 else 'товаров'} в корзину."
            if stock_failed:
                base += f" {stock_failed} {'товар не добавлен' if stock_failed == 1 else 'товаров не добавлены'} — недостаточно на складе."
            return base
        if action == "added_to_favorites":
            return f"Сохранила {count} {'товар' if count == 1 else 'товаров'} в избранное."
        if action == "cart_cleared":
            return "Корзина очищена."
        if action == "favorites_cleared":
            return "Избранное очищено."
        if action == "removed_from_cart":
            return "Убрала из корзины."
        if action == "removed_from_favorites":
            return "Убрала из избранного."
        if action in ("stock_updated", "prices_updated"):
            return "Готово, изменения применены."
        if action == "sales_analytics":
            return "Аналитика готова."
        # No success action surfaced — surface a useful error instead of «Готово».
        if tool_results:
            for tr in tool_results:
                r = tr.result if isinstance(tr.result, dict) else {}
                err = (r.get("error") or "").lower()
                if not err:
                    continue
                if "каталог пуст" in err or "visible_product_ids" in err:
                    return "Каталог пустой — сначала покажите товары, потом смогу добавить или сохранить."
                if "product_ids is empty" in err or "нет товаров" in err:
                    return "Не вижу к чему применить — уточните «все / первые N» или покажите товары."
                if "не хватает прав" in err or "permission" in err or "forbidden" in err:
                    return "У вас нет прав для этого действия."
            return "Не получилось выполнить действие — уточните запрос."
        return "Готово."

    @staticmethod
    def _parse_plan(raw: str) -> list[PlanStepV2]:
        """Extract plan steps from the model's JSON response.

        Tolerates: bare `{...}` or wrapped in markdown ```json fences,
        and the rare bug where the model emits `"parameters"` instead of `"args"`.
        """
        if not raw:
            return []
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                return []
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError as e:
                log.warning("[CHAT] plan JSON parse failed: %r", e)
                return []
        if not isinstance(obj, dict):
            return []
        raw_steps = obj.get("plan") or []
        if not isinstance(raw_steps, list):
            return []
        steps: list[PlanStepV2] = []
        for i, s in enumerate(raw_steps):
            if not isinstance(s, dict):
                continue
            tool_name = s.get("tool")
            if not isinstance(tool_name, str) or not tool_name:
                continue
            args = s.get("args") if isinstance(s.get("args"), dict) else None
            if args is None and isinstance(s.get("parameters"), dict):
                args = s["parameters"]
            steps.append(PlanStepV2(step_id=f"step_{i + 1}", tool=tool_name, args=args or {}))
        return steps


def _tools_signature(tools: ToolRegistry) -> str:
    """Stable 16-hex-char key for the role-filtered tool set.

    SHA256 of sorted tool names, truncated to 16 chars — matches the
    `tools_signature String(16)` column on PlanCacheEntry. User and admin
    requests don't collide because admin tools change the input string;
    reordering tool registration doesn't invalidate cache (sorted).
    """
    import hashlib
    names = "|".join(sorted(t.name for t in tools.all()))
    return hashlib.sha256(names.encode("utf-8")).hexdigest()[:16]


# Args whose values must come from the CURRENT request, never from a cached
# plan. The semantic cache stores plan SKELETONS — tool sequences shared by
# many surface-form queries («диваны до 50k» and «столы до 70k» both store
# as `apply_filters(<dynamic>)`). On load these stay empty; PlanExecutor's
# `_merge_hints` injects the right values from the current text's ParseHints.
_DYNAMIC_ARGS: dict[str, set[str]] = {
    "apply_filters": {"category", "max_price", "min_price"},
    "add_to_cart": {"product_ids", "quantifier", "n", "quantity"},
    "remove_from_cart": {"product_ids", "quantifier", "n", "quantity"},
    "add_to_favorites": {"product_ids", "quantifier", "n", "quantity"},
    "remove_from_favorites": {"product_ids", "quantifier", "n", "quantity"},
}


def _strip_dynamic(args: dict[str, Any], tool: str) -> dict[str, Any]:
    """Remove fields that must come from the current request."""
    dyn = _DYNAMIC_ARGS.get(tool, set())
    if not dyn:
        return dict(args or {})
    return {k: v for k, v in (args or {}).items() if k not in dyn}


def _plan_to_template(plan_steps: list[PlanStepV2]) -> list[dict[str, Any]]:
    """Serialize plan as a cacheable skeleton (dynamic args stripped)."""
    return [
        {"step_id": s.step_id, "tool": s.tool, "args": _strip_dynamic(s.args, s.tool)}
        for s in plan_steps
    ]


def _plan_from_cache(plan_json: dict[str, Any]) -> list[PlanStepV2]:
    """Hydrate stored plan_json back into PlanStepV2 list.

    Also strips dynamic args defensively — older entries (written before the
    template change) may still carry stale category/prices; stripping at load
    time ensures _merge_hints always reads from the current request.
    """
    raw_steps = (plan_json or {}).get("plan") or []
    if not isinstance(raw_steps, list):
        return []
    steps: list[PlanStepV2] = []
    for i, s in enumerate(raw_steps):
        if not isinstance(s, dict) or not s.get("tool"):
            continue
        tool = s["tool"]
        steps.append(PlanStepV2(
            step_id=s.get("step_id") or f"step_{i + 1}",
            tool=tool,
            args=_strip_dynamic(s.get("args") or {}, tool),
        ))
    return steps


def _has_tool_errors(tool_results: list) -> bool:
    """True if any tool returned an error payload — disqualifies caching."""
    for tr in tool_results:
        r = tr.result if isinstance(tr.result, dict) else {}
        if r.get("error"):
            return True
    return False
