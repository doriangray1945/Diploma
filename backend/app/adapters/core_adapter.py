from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CoreConfig
from core.llm.ollama import OllamaProvider
from core.pipeline import Pipeline
from core.schemas import AgentResult, Message, Role, SessionContext, UserContext
from core.tools.base import ToolRegistry
from core.tools.catalog import GetProductDetailsTool, ApplyFiltersTool
from core.tools.cart import AddToCartTool, GetCartTool, ClearCartTool
from core.tools.order import CreateOrderTool, ModifyOrderTool
from core.tools.favorites import GetFavoritesTool, AddToFavoritesTool, RemoveFromFavoritesTool, ClearFavoritesTool
from core.tools.admin import AddProductTool, UpdateProductTool, DeleteProductTool

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
    registry = ToolRegistry()

    # User tools — always available
    registry.register(ApplyFiltersTool(provider))
    registry.register(GetProductDetailsTool(provider))
    registry.register(AddToCartTool(provider))
    registry.register(GetCartTool(provider))
    registry.register(ClearCartTool(provider))
    registry.register(CreateOrderTool(provider))
    registry.register(ModifyOrderTool(provider))
    registry.register(GetFavoritesTool(provider))
    registry.register(AddToFavoritesTool(provider))
    registry.register(RemoveFromFavoritesTool(provider))
    registry.register(ClearFavoritesTool(provider))

    # Admin tools — only for admin role
    if role == "admin":
        registry.register(AddProductTool(provider))
        registry.register(UpdateProductTool(provider))
        registry.register(DeleteProductTool(provider))

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

    # Fetch filter options via cached DataProvider method (avoids raw SQL each time)
    filter_opts = await provider.get_filter_options()
    categories = filter_opts["categories"]
    colors = filter_opts.get("colors", [])
    price_range = filter_opts.get("price_range", {})

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
