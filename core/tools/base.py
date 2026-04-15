from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.providers.base import DataProvider


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

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


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

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
