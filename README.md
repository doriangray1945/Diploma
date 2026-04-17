# Nova Furnish - Мебельный магазин с AI-ассистентом

Интернет-магазин мебели с интегрированным AI-чатом на базе Ollama (qwen2.5:3b), который помогает пользователям подбирать товары, управлять фильтрами каталога и оформлять заказы через естественный диалог.

## Технологический стек

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL + pgvector
- **AI:** Ollama + qwen2.5:3b
- **State Management:** Zustand
- **Аутентификация:** JWT tokens

## Быстрый старт

### Предварительные требования

1. **Docker и Docker Compose** - для запуска всех сервисов
2. **Ollama** - для AI-ассистента (устанавливается на хост-машину)

### Установка Ollama

```bash
# Linux/macOS
curl -fsSL https://ollama.com/install.sh | sh

# Windows - скачайте установщик с https://ollama.com/download

# Запуск Ollama
ollama serve

# Загрузка модели
ollama pull qwen2.5:3b
```

### Запуск проекта

```bash
# Клонировать репозиторий
cd /path/to/Diploma

# Запуск всех сервисов через Docker Compose
docker-compose up -d

# Приложение будет доступно:
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# Swagger UI: http://localhost:8000/docs
```

### Запуск без Docker (для разработки)

**Backend:**
```bash
cd backend

# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate  # Windows

# Установить зависимости
pip install -r requirements.txt

# Запустить PostgreSQL (требуется установленный PostgreSQL)
# Создать базу данных furniture_store

# Запустить seed данных
python seed_data.py

# Запустить сервер
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend

# Установить зависимости
npm install

# Запустить dev сервер
npm run dev
```

## Структура проекта

```
Diploma/
├── backend/
│   ├── app/
│   │   ├── adapters/       # Связка backend ↔ core (DataProvider impl)
│   │   ├── api/routes/     # API endpoints
│   │   ├── core/           # Конфигурация, безопасность, БД
│   │   ├── models/         # SQLAlchemy модели
│   │   └── schemas/        # Pydantic схемы
│   └── seed_data.py        # Начальные данные
├── core/                   # Универсальное ядро AI-агентов
│   ├── agents/             # SchemaPlanner, PlanExecutor, Validator, Base
│   ├── llm/                # Ollama-клиент и LLMProvider Protocol
│   ├── prompts/            # JSON Schema и system prompt для Schema Router
│   ├── providers/          # DataProvider Protocol
│   └── tools/              # Tool-функции для LLM
├── frontend/
│   ├── src/
│   │   ├── api/            # API клиент
│   │   ├── components/     # React компоненты
│   │   ├── pages/          # Страницы
│   │   ├── stores/         # Zustand stores
│   │   └── types/          # TypeScript типы
│   └── ...
└── docker-compose.yml
```

## Функциональность

### Основные возможности

- **Каталог товаров** - просмотр, поиск, фильтрация
- **Страница товара** - детальная информация, характеристики
- **Избранное** - сохранение понравившихся товаров
- **Корзина** - добавление, изменение количества, удаление
- **Оформление заказов** - с адресом и контактными данными
- **История заказов** - просмотр всех заказов пользователя

### AI-ассистент (Chat)

AI-чат на базе Ollama позволяет:

- **Поиск товаров**: "Покажи диваны до 100000 рублей"
- **Фильтрация**: "Найди серые кресла"
- **Рекомендации**: "Подбери мебель для гостиной"
- **Добавление в корзину**: "Добавь этот стол в корзину"
- **Информация о товаре**: "Расскажи подробнее о диване Red Wood"
- **Оформление заказа**: "Хочу оформить заказ"

## API Endpoints

### Аутентификация
- `POST /api/auth/register` - Регистрация
- `POST /api/auth/login` - Вход
- `GET /api/auth/me` - Текущий пользователь

### Товары
- `GET /api/products` - Список с фильтрацией
- `GET /api/products/{id}` - Детали товара
- `GET /api/products/categories` - Категории

### Корзина
- `GET /api/cart` - Содержимое корзины
- `POST /api/cart/items` - Добавить товар
- `PUT /api/cart/items/{id}` - Изменить количество
- `DELETE /api/cart/items/{id}` - Удалить товар

### Заказы
- `GET /api/orders` - Список заказов
- `POST /api/orders` - Создать заказ
- `GET /api/orders/{id}` - Детали заказа

### Избранное
- `GET /api/favorites` - Список избранного
- `POST /api/favorites/{product_id}` - Добавить
- `DELETE /api/favorites/{product_id}` - Удалить

### Чат
- `POST /api/chat/message` - Отправить сообщение AI
- `GET /api/chat/history` - История чата

## Переменные окружения

**Backend (.env):**
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/furniture_store
SECRET_KEY=your-secret-key
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

## Тестовые данные

При первом запуске автоматически создаются тестовые товары:
- 4 дивана
- 3 кресла
- 3 стола
- 2 шкафа
- 3 кровати
- 3 стула

## Скриншоты

Интерфейс соответствует предоставленному дизайну:
- AI-чат в верхней части каталога
- Карточки товаров с кнопками избранного
- Фильтры: Популярное, Новое, расширенные фильтры

## Лицензия

MIT
