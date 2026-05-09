from app.llm.providers.base import DataProvider
from app.llm.schemas import AgentResult, ToolResult, ValidationIssue


class ValidatorAgent:
    """Validates agent results by checking tool outputs for errors and inconsistencies."""

    def __init__(self, provider: DataProvider):
        self.provider = provider

    async def validate(self, result: AgentResult) -> AgentResult:
        issues: list[ValidationIssue] = []

        for tr in result.tool_results:
            tool_issues = self._validate_tool_result(tr)
            issues.extend(tool_issues)

        result.validation_issues = issues
        return result

    def _validate_tool_result(self, tr: ToolResult) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        # Check for explicit errors from any tool
        if tr.result.get("error"):
            issues.append(
                ValidationIssue(
                    field=tr.tool_name,
                    message=tr.result["error"],
                    severity="error",
                )
            )

        # Check empty search results
        if "products" in tr.result and tr.result.get("count", 0) == 0:
            issues.append(
                ValidationIssue(
                    field=tr.tool_name,
                    message="No results found",
                    severity="warning",
                )
            )

        return issues