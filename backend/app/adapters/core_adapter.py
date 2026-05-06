from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CoreConfig
from core.llm.ollama import OllamaProvider
from core.pipeline import Pipeline
from core.schemas import AgentResult, Message, Role, SessionContext, UserContext
from core.tools.admin_bulk import (
    GetSalesAnalyticsTool,
    UpdatePricesTool,
    UpdateStockTool,
)
from core.tools.base import ToolRegistry
from core.tools.cart import AddToCartTool, ClearCartTool, RemoveFromCartTool
from core.tools.catalog import ApplyFiltersTool
from core.tools.favorites import (
    AddToFavoritesTool,
    ClearFavoritesTool,
    RemoveFromFavoritesTool,
)

from app.adapters.data_provider import PostgresDataProvider
from app.core.config import settings


def _build_config() -> CoreConfig:
    return CoreConfig(
        ollama_base_url=settings.OLLAMA_HOST,
        chat_model=settings.OLLAMA_MODEL,
        language="русский",
        business_prompt='Ассистент мебельного магазина "Nova Furnish".',
    )


def _build_tools(
    provider: PostgresDataProvider, role: str
) -> ToolRegistry:
    """Build the tool registry visible to the chat LLM.

    User role (7 tools): catalog filtering + favorites + cart.
    Admin role (10 tools): user tools + bulk-stock/prices/analytics.

    Schemas are stable per fine-tune. Adding NEW tool semantics requires
    warm-start retrain; renaming fields/values does not (schema-grounded).
    """
    registry = ToolRegistry()

    # User tools — visible to all chat users
    registry.register(ApplyFiltersTool(provider))
    registry.register(AddToFavoritesTool(provider))
    registry.register(RemoveFromFavoritesTool(provider))
    registry.register(ClearFavoritesTool(provider))
    registry.register(AddToCartTool(provider))
    registry.register(RemoveFromCartTool(provider))
    registry.register(ClearCartTool(provider))

    # Admin tools — only for admin role; bulk operations + flexible analytics
    if role == "admin":
        registry.register(UpdateStockTool(provider))
        registry.register(UpdatePricesTool(provider))
        registry.register(GetSalesAnalyticsTool(provider))

    return registry


async def process_message(
    text: str,
    user_id: int,
    role: str,
    history: list[dict],
    session_context: SessionContext | None,
    db: AsyncSession,
) -> tuple[AgentResult, SessionContext]:
    """Process a user message through the core pipeline.

    Returns (result, updated_session_context) so the caller can persist
    the context changes back to the DB.
    """
    provider = PostgresDataProvider(db)
    config = _build_config()
    llm = OllamaProvider(config)
    tools = _build_tools(provider, role)
    pipeline = Pipeline(llm, provider, config)

    session_context = session_context or SessionContext()

    user_context = UserContext(
        user_id=user_id,
        role=role,
        history=[
            Message(role=Role(msg["role"]), content=msg["content"])
            for msg in history
        ],
    )

    result = await pipeline.run(text, tools, user_context, session_context)
    # session_context is mutated in-place by PlanExecutor.updates_context
    return result, session_context
