from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CoreConfig
from core.llm.ollama import OllamaProvider
from core.pipeline import Pipeline
from core.schemas import AgentResult, Message, Role, UserContext
from core.tools.base import ToolRegistry
from core.tools.catalog import GetProductDetailsTool, ApplyFiltersTool
from core.tools.cart import AddToCartTool, GetCartTool
from core.tools.order import CreateOrderTool, ModifyOrderTool
from core.tools.favorites import GetFavoritesTool, AddToFavoritesTool, RemoveFromFavoritesTool
from core.tools.admin import AddProductTool, UpdateProductTool, DeleteProductTool

from app.adapters.data_provider import PostgresDataProvider
from app.core.config import settings
from app.models import Product


def _build_config(available_filters: str) -> CoreConfig:
    return CoreConfig(
        ollama_base_url=settings.OLLAMA_HOST,
        chat_model=settings.OLLAMA_MODEL,
        language="русский",
        business_prompt=(
            'Ты — AI-ассистент мебельного магазина "Nova Furnish". '
            "Помогаешь покупателям подбирать мебель, оформлять заказы "
            "и отвечаешь на вопросы о товарах.\n\n"
            f"Доступные фильтры каталога:\n{available_filters}"
        ),
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
    registry.register(CreateOrderTool(provider))
    registry.register(ModifyOrderTool(provider))
    registry.register(GetFavoritesTool(provider))
    registry.register(AddToFavoritesTool(provider))
    registry.register(RemoveFromFavoritesTool(provider))

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
    db: AsyncSession,
) -> AgentResult:
    """Main entry point: process a user message through the core pipeline."""
    # Fetch available filter values from DB
    cat_result = await db.execute(select(Product.category).distinct())
    categories = sorted([r for r in cat_result.scalars().all() if r])

    price_result = await db.execute(
        select(func.min(Product.price), func.max(Product.price))
    )
    price_row = price_result.one()
    min_price, max_price = float(price_row[0] or 0), float(price_row[1] or 0)

    available_filters = (
        f"Категории: {', '.join(categories)}\n"
        f"Цены: от {min_price:.0f} до {max_price:.0f} руб."
    )

    config = _build_config(available_filters)
    llm = OllamaProvider(config)
    provider = PostgresDataProvider(db)
    tools = _build_tools(provider, role)

    pipeline = Pipeline(llm, provider, config)

    user_context = UserContext(
        user_id=user_id,
        role=role,
        history=[
            Message(role=Role(msg["role"]), content=msg["content"])
            for msg in history
        ],
    )

    return await pipeline.run(text, tools, user_context)
