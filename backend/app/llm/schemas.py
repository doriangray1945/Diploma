from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Complexity(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class Message(BaseModel):
    role: Role
    content: str
    tool_calls: list[ToolCall] | None = None


class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class PlanStep(BaseModel):
    description: str
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    field: str
    message: str
    severity: str = "warning"  # "warning" | "error"


class AgentResult(BaseModel):
    response: str
    complexity: Complexity = Complexity.SIMPLE
    tool_results: list[ToolResult] = Field(default_factory=list)
    action: dict[str, Any] | None = None
    plan_steps: list[PlanStep] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)


class UserContext(BaseModel):
    user_id: int
    role: str = "user"  # "user" | "admin"
    history: list[Message] = Field(default_factory=list)


class PlanStepV2(BaseModel):
    """A single executable step in a structured plan."""
    step_id: str  # e.g. "step_1"
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    """Per-user dialogue state. Resolves anaphora ('их', 'это') via $context.* refs."""
    last_search: dict[str, Any] | None = None
    visible_product_ids: list[int] = Field(default_factory=list)
    current_filters: dict[str, Any] = Field(default_factory=dict)
    open_product_id: int | None = None
    cart_summary: dict[str, Any] | None = None
    favorites_summary: dict[str, Any] | None = None
    # Plan cache entry id used by the LAST turn's plan. Read by chat.py on
    # the next turn to attribute negative feedback («не то»/«отмени») to
    # the entry that produced the bad plan. Set by pipeline after a
    # successful cache hit OR after a fresh store; cleared otherwise.
    last_cache_hit_id: int | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        """Compact dict for embedding into the system prompt.

        Strips bulky product lists from last_search to save LLM tokens.
        The model only needs IDs (available via visible_product_ids).
        """
        d: dict[str, Any] = {}
        if self.last_search:
            # Keep only compact info — no full product objects
            d["last_search"] = {
                "filters": self.last_search.get("filters"),
                "product_ids": [
                    p["id"] for p in self.last_search.get("products", [])
                    if isinstance(p, dict) and "id" in p
                ],
                "count": len(self.last_search.get("products", [])),
            }
        if self.visible_product_ids:
            d["visible_product_ids"] = self.visible_product_ids
        if self.current_filters:
            d["current_filters"] = self.current_filters
        if self.open_product_id is not None:
            d["open_product_id"] = self.open_product_id
        if self.cart_summary:
            d["cart_summary"] = self.cart_summary
        if self.favorites_summary:
            d["favorites_summary"] = self.favorites_summary
        return d
