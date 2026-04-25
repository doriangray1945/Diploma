from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.providers.base import DataProvider


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    # Declarative contract: which SessionContext keys this tool updates after success.
    # Format: {"<session_field>": "<dot.path.in_result[*].x>"}
    # Example: {"visible_product_ids": "result.products[*].id"}
    updates_context: dict[str, str] = {}
    # Minimum user role required to invoke this tool. "user" = any authenticated
    # user; "admin" = catalog management. ToolRegistry.for_role(role) filters
    # the planner's view so non-admins can't see admin tools in schema/prompt.
    role: str = "user"

    def __init__(self, provider: DataProvider):
        self.provider = provider

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]: ...

    def to_ollama_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def param_schema(
        self,
        filter_options: dict[str, Any] | None = None,
        session_context: Any | None = None,
    ) -> dict[str, Any]:
        """JSON Schema for this tool's args used by Schema Router constrained decoding.

        Override in subclasses to inject dynamic enums (categories from DB,
        product_ids from session) or value constraints (patterns, ranges).
        Default returns the static `parameters` dict.
        """
        return self.parameters

    def few_shot(self) -> list[dict[str, Any]]:
        """Few-shot examples for this tool. Each: {"user": str, "args": dict}.

        Rendered into the planner system prompt by build_system_prompt.
        Default is empty — tool authors add examples in their own subclass.
        """
        return []

    def skeleton_examples(self) -> list[str]:
        """Short user phrases that should trigger this tool at the skeleton
        (tool-selection) stage. Rendered into build_planner_skeleton_prompt as
        '"<phrase>" → <tool.name>'. Teaches the model intent → tool mapping
        without args. Default empty — tools opt in by overriding."""
        return []


def flatten_ids(raw: Any) -> list[int]:
    """Normalize product_ids from LLM — handles nested lists from $ref resolution.

    LLM may produce ["$context.visible_product_ids"] which resolves to [[1,2,3]].
    This flattens it to [1, 2, 3] and coerces to int.
    """
    if not raw:
        return []
    result: list[int] = []
    for item in raw:
        if isinstance(item, list):
            result.extend(int(x) for x in item)
        else:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
    return result


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def for_role(self, role: str) -> "ToolRegistry":
        """Return a new registry containing only tools accessible to `role`.

        Role hierarchy: "admin" sees everything; "user" sees only role="user".
        """
        filtered = ToolRegistry()
        for tool in self._tools.values():
            if role == "admin" or tool.role == "user":
                filtered.register(tool)
        return filtered

    def to_ollama_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_ollama_schema() for tool in self._tools.values()]

    async def execute(
        self, name: str, user_id: int = 0, **kwargs: Any
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}"}
        try:
            print(f"[TOOL] {name}(user_id={user_id}, {kwargs})")
            result = await tool.execute(user_id=user_id, **kwargs)
            print(f"[TOOL] {name} -> {str(result)[:200]}")
            return result
        except Exception as e:
            print(f"[TOOL] {name} ERROR: {repr(e)}")
            return {"error": f"Tool execution error ({name}): {str(e)}"}
