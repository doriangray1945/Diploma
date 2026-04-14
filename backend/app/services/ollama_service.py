import json
import httpx
from typing import AsyncGenerator

from app.core.config import settings


SYSTEM_PROMPT = """Ты - AI-ассистент мебельного магазина "Nova Furnish". Твоя задача - помогать покупателям:
- Подбирать мебель по их запросам и предпочтениям
- Отвечать на вопросы о товарах
- Помогать с фильтрацией каталога
- Добавлять товары в корзину
- Оформлять заказы

У тебя есть доступ к следующим функциям (tools):
1. search_products - поиск товаров по запросу и фильтрам
2. get_product_details - получить детали конкретного товара
3. apply_filters - применить фильтры к каталогу
4. add_to_cart - добавить товар в корзину
5. get_cart - получить содержимое корзины
6. create_order - создать заказ

Отвечай на русском языке. Будь дружелюбным и полезным.
Если пользователь спрашивает о конкретном товаре, используй функции для получения информации.
Когда предлагаешь товары, упоминай их названия, цены и ключевые характеристики.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Поиск товаров в каталоге по запросу и фильтрам",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос (название, описание)"
                    },
                    "category": {
                        "type": "string",
                        "description": "Категория товара (Диваны, Кресла, Столы, Стулья, Шкафы, Кровати)"
                    },
                    "min_price": {
                        "type": "number",
                        "description": "Минимальная цена"
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Максимальная цена"
                    },
                    "color": {
                        "type": "string",
                        "description": "Цвет товара"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Получить подробную информацию о товаре по ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "ID товара"
                    }
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_filters",
            "description": "Применить фильтры к каталогу товаров на странице",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Категория товара"
                    },
                    "min_price": {
                        "type": "number",
                        "description": "Минимальная цена"
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Максимальная цена"
                    },
                    "color": {
                        "type": "string",
                        "description": "Цвет товара"
                    },
                    "in_stock": {
                        "type": "boolean",
                        "description": "Только в наличии"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Добавить товар в корзину пользователя",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "ID товара для добавления"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Количество (по умолчанию 1)"
                    }
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cart",
            "description": "Получить содержимое корзины пользователя",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Создать заказ из корзины. Запросить у пользователя адрес и телефон перед вызовом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Адрес доставки"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Телефон для связи"
                    }
                },
                "required": ["address", "phone"]
            }
        }
    }
]


class OllamaService:
    def __init__(self):
        self.base_url = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> dict:
        """Send a chat request to Ollama and get a response."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *messages
                ],
                "stream": False,
            }

            if tools:
                payload["tools"] = tools

            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            return response.json()

    async def chat_stream(
        self,
        messages: list[dict]
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Ollama."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *messages
                ],
                "stream": True,
            }

            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]


ollama_service = OllamaService()
