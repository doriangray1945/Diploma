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
