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

    def to_json_schema(self, filter_options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Industry-standard function-calling JSON Schema entry.

        `filter_options` carries current DB catalog state (categories, colors,
        materials). Tools that expose enum-constrained catalog fields override
        `_build_parameters` to inject these values dynamically — adding a new
        category in DB shows up in the next request's prompt without retrain.
        API enums (quantifier, operation, period, ...) stay static — that's
        the contract, not data.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._build_parameters(filter_options or {}),
        }

    def _build_parameters(self, filter_options: dict[str, Any]) -> dict[str, Any]:
        """Override in subclasses with enum-constrained catalog fields.
        Default returns the static `parameters` dict."""
        return self.parameters


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
