# Nova Furnish — мебельный магазин с AI-ассистентом

Интернет-магазин мебели с интегрированным AI-чатом на собственной LoRA-дообученной модели `furniture-3b-v5` (база — `qwen2.5-3b-instruct`). Ассистент понимает естественные русские запросы и переводит их в действия в каталоге: поиск с фильтрами, добавление в корзину/избранное, очистка, а на админ-сессии — массовое изменение цен/остатков и аналитика продаж.

## Технологический стек

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Zustand + Recharts + `@google/model-viewer` (для 3D/AR)
- **Backend:** FastAPI + SQLAlchemy 2 async + asyncpg + Pydantic v2
- **БД:** PostgreSQL (ParadeDB образ) + pgvector (семантический кэш планов)
- **Файлы:** MinIO (S3-совместимое хранилище изображений и 3D-моделей)
- **AI:** Ollama + кастомная LoRA-fine-tuned модель `furniture-3b-v5` (Q8_0 GGUF, ~3.3 GB)
- **Эмбеддинги:** `bge-m3` через Ollama (для cache lookup)
- **Аутентификация:** JWT (HS256)

## Быстрый старт

### Предварительные требования

1. **Docker и Docker Compose** — для backend, frontend, Postgres, MinIO
2. **Ollama** — для AI-ассистента (устанавливается на хост-машину)

### Установка Ollama и моделей

```bash
# Linux/macOS
curl -fsSL https://ollama.com/install.sh | sh

# Windows — установщик: https://ollama.com/download

# Запуск Ollama-демона
ollama serve

# Эмбеддинги для cache lookup
ollama pull bge-m3
```

Затем собрать кастомную модель из готового GGUF:

```bash
cd dataset/model_v5
ollama create furniture-3b-v5 -f Modelfile
```

(GGUF и Modelfile уже лежат в `dataset/model_v5/`.)

### Запуск проекта

```bash
docker compose up -d

# Приложение доступно:
# Frontend:    https://localhost:5173   (vite в режиме HTTPS, см. секцию AR)
# Backend API: http://localhost:8000
# Swagger UI:  http://localhost:8000/docs
# MinIO:       http://localhost:9001    (login: minioadmin / minioadmin123)
```

Дефолтный админ создаётся при первом старте: `admin@admin.com` / `admin12345`.

## Структура проекта

```
Diploma/
├── backend/
│   └── app/
│       ├── adapters/         # backend ↔ LLM-pipeline (DataProvider impl)
│       ├── api/routes/       # FastAPI endpoints (auth, products, cart, favorites, orders, admin/, chat)
│       ├── core/             # Конфигурация, JWT, инициализация БД
│       ├── llm/
│       │   ├── agents/       # SchemaPlanner, PlanExecutor, ArgsFiller
│       │   ├── clients/      # Ollama HTTP-клиент
│       │   ├── providers/    # PostgresDataProvider
│       │   ├── tools/        # Tool-функции (catalog, cart, favorites, admin_bulk, analytics)
│       │   ├── pipeline.py   # Полный chat pipeline + семантический cache
│       │   └── parsing.py    # Регекс-парсер цен/количеств/квантификаторов
│       ├── models/           # SQLAlchemy ORM
│       ├── schemas/          # Pydantic
│       └── services/         # MinIO, products, chat_sessions
├── frontend/
│   └── src/
│       ├── api/              # axios клиент + SSE-парсер
│       ├── components/       # Chat (с ThinkingBlock), ProductCard, Admin, Catalog, ...
│       ├── pages/            # Каталог, товар, корзина, оформление, история, admin/*
│       ├── stores/           # Zustand (auth, cart, favorites, chat, products)
│       ├── lib/              # Утилиты (errors.ts)
│       └── types/            # TypeScript типы
├── dataset/                  # Pipeline дообучения (LoRA через unsloth)
│   ├── model_v1..v5/         # Чекпоинты моделей (v5 — продакшен)
│   ├── seeds.json            # Канонический интент-каталог
│   ├── train.jsonl, eval.jsonl  # Сгенерированный SFT-датасет
│   ├── generator.py          # Генерация train/eval через GPT-4o-mini из seeds
│   ├── validator.py          # Валидация train.jsonl против tool_schemas
│   ├── tool_schemas.py       # Канонические enum (категории/цвета/материалы)
│   ├── colab_finetune.ipynb  # Тренировочный ноутбук для Colab/Kaggle
│   └── concept_mappings.md   # Reference для GPT-4 промпта
└── docker-compose.yml
```

## Функциональность

### Пользователь

- **Каталог** — категории, цвета, материалы, ценовые диапазоны, табы «Популярное / Новое»
- **Карточка товара** — варианты по цвету, характеристики, отзывы, 3D-модель, AR на iOS
- **Корзина** — изменение количества, проверка остатков, корректный пересчёт
- **Избранное** — на уровне вариантов (отдельные цвета — отдельные товары в избранном)
- **Оформление заказа** — адрес, контакты, история заказов
- **Отзывы** — оставлять можно только если есть завершённый заказ на этот товар

### AI-чат

Streaming SSE (`/api/chat/message/stream`) с thinking-блоком в UI («Подумал за N с»). Модель сама планирует последовательность tool-вызовов и исполняет их через PlanExecutor.

Поддерживаемые сценарии:

- **Поиск с фильтрами**: «покажи зелёные кресла до 30000»
- **Количественные операторы**: «положи первые 2 в корзину», «добавь все в корзину по 3 шт»
- **Очистка**: «очисти корзину», «убери из избранного»
- **Контекст между ходами**: «не то» / «отмени» корректно прерывает, без побочных действий
- **Out-of-domain**: «какая сегодня погода» → честный ответ без вызовов tools
- **Админ-операции** (только для admin-сессии):
  - аналитика: «выручка за месяц», «топ-5 товаров», «аналитика за неделю»
  - массовые изменения цен: «подними цены на стулья на 10%»
  - изменение остатков: «установи остатки 50 на все диваны»

### Семантический кэш планов

После успешного выполнения плана его «скелет» (структура без числовых аргументов) индексируется через `bge-m3` эмбеддинг в pgvector. На следующий схожий запрос план достаётся из кэша за ~500 мс вместо ~10–15 с холодного LLM-вызова. Числовые значения (цены, количества) подставляются заново через регекс-парсер; квантификатор «все» подставляется по умолчанию, если пользователь не указал явный.

## API Endpoints

### Аутентификация
- `POST /api/auth/register` — регистрация
- `POST /api/auth/login` — вход
- `GET /api/auth/me` — текущий пользователь

### Товары
- `GET /api/products` — список с фильтрацией
- `GET /api/products/{id}` — детали
- `GET /api/products/categories` — категории
- `GET /api/products/filter-options` — все доступные фильтры с enum
- `GET /api/products/{id}/reviews` — отзывы товара
- `GET /api/products/{id}/reviews/eligibility` — можно ли оставить отзыв

### Корзина
- `GET /api/cart` — содержимое
- `POST /api/cart/items` — добавить
- `PATCH /api/cart/items/{id}` — изменить количество
- `DELETE /api/cart/items/{id}` — удалить
- `DELETE /api/cart` — очистить

### Избранное (по вариантам, не товарам)
- `GET /api/favorites` — список
- `POST /api/favorites/{variant_id}` — добавить
- `DELETE /api/favorites/{variant_id}` — удалить

### Заказы
- `GET /api/orders` — мои заказы
- `POST /api/orders` — оформить (из текущей корзины)
- `GET /api/orders/{id}` — детали

### Чат
- `POST /api/chat/message` — синхронный ответ (для не-стримящих клиентов)
- `POST /api/chat/message/stream` — SSE: события `thinking` → `meta` → `token` → `done`
- `GET /api/chat/history` — история
- `DELETE /api/chat/history` — очистить

### Админ
- `GET /api/admin/users`, `GET /api/admin/users/{id}` — управление пользователями
- `GET/POST/PATCH/DELETE /api/admin/products[...]` — CRUD товаров и вариантов
- `POST /api/admin/products/bulk/prices` — массовое изменение цен
- `POST /api/admin/products/bulk/stock` — массовое изменение остатков
- `POST /api/admin/products/images/upload` — загрузка картинок в MinIO
- `GET /api/admin/orders`, `PATCH /api/admin/orders/{id}/status` — управление заказами
- `GET /api/admin/categories` — CRUD категорий
- `GET /api/admin/stats/{overview|inventory|low-stock|top-products|revenue-by-day|category-breakdown|query}` — аналитика

## Переменные окружения

Основная конфигурация — в `docker-compose.yml`. Для разработки backend локально:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/furniture_store
SECRET_KEY=your-secret-key
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=furniture-3b-v5
MINIO_ENDPOINT=http://localhost:9000
MINIO_PUBLIC_ENDPOINT=/minio
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=furniture-images
ADMIN_EMAIL=admin@admin.com
ADMIN_PASSWORD=admin12345
```

Для `dataset/generator.py` (опционально, нужен только если планируешь регенерировать обучающий датасет):

```env
OPENAI_API_KEY=sk-...
```

## Тестовые данные

При первом старте бэкенд автоматически сидит каталог: по 18–19 товаров в каждой из 6 категорий (диваны, кресла, столы, стулья, шкафы, кровати), у каждого — несколько вариантов по цвету.

## AR-режим на iPhone

На странице товара есть блок «3D-модель»: на десктопе — вращающаяся 3D-модель, на iPhone Safari — кнопка **«Просмотр в AR»**, открывающая нативный iOS Quick Look. С iPhone 12 Pro и выше (LiDAR) AR работает с точным определением плоскостей и окклюзии.

Для AR Quick Look iOS требует HTTPS, поэтому нужна одноразовая настройка локального сертификата через `mkcert`. Интернет не нужен — только общая Wi-Fi сеть между ноутом и iPhone.

### 1. Однократная настройка на ноуте (Linux/Arch)

```bash
# Установить mkcert и зависимость для NSS (Firefox/Chrome trust store)
sudo pacman -S mkcert nss

# Установить локальный CA в систему — добавит mkcert root в доверенные браузеров
mkcert -install

# Узнать IP ноута в твоей Wi-Fi сети (пример: 192.168.1.42)
ip -4 addr | grep inet | grep -v 127.0.0.1

# Сгенерировать сертификат для нужных хостов
cd frontend
mkdir -p .cert && cd .cert
mkcert localhost 127.0.0.1 ::1 192.168.1.42   # подставить твой IP

# Перезапустить frontend — vite автоматически подхватит .cert/
docker compose restart frontend
```

После рестарта `https://localhost:5173` должен открываться без warning'а в браузере на ноуте.

### 2. Однократная настройка на iPhone

iPhone должен доверять CA, который выпустил сертификат. Этого достаточно сделать один раз.

```bash
# На ноуте посмотреть путь к корневому CA (в нём лежит rootCA.pem)
mkcert -CAROOT
# Например: /home/dianakanaeva/.local/share/mkcert

# Скопировать rootCA.pem в публичную папку frontend временно
cp $(mkcert -CAROOT)/rootCA.pem frontend/public/
```

Дальше — на iPhone:

1. iPhone подключить к **той же Wi-Fi сети**, что и ноут.
2. Открыть в Safari: `http://192.168.1.42:5173/rootCA.pem` (без https — пока сертификат не доверен). Появится сообщение «Профиль конфигурации загружен».
3. Открыть **Настройки** → сверху появится строка «Загруженный профиль» → тап → **Установить** (потребуется код-пароль iPhone).
4. **Настройки → Основные → Об этом устройстве → Сертификаты доверия** → найти `mkcert development CA ...` → включить переключатель.
5. **Удалить** `frontend/public/rootCA.pem` — нельзя оставлять CA публично доступным:
   ```bash
   rm frontend/public/rootCA.pem
   ```

### 3. Использование

1. Запустить стек: `docker compose up -d`.
2. На iPhone Safari: `https://192.168.1.42:5173`.
3. Залогиниться → каталог → открыть товар, у которого есть 3D-модель.
4. Прокрутить до блока «3D-модель» → тапнуть кнопку **«Просмотр в AR»** в правом нижнем углу.
5. iOS Quick Look откроется во весь экран → навести камеру на пол → виртуальный объект встанет в комнате.

### Замечания

- Файлы 3D-моделей лежат в MinIO под `models/`. Привязка к товарам — через `/admin/products/X/edit` (поля «Модель GLB» и «Модель USDZ»).
- Apple AR Quick Look поддерживает только формат **USDZ** на iOS. Для десктопного 3D-просмотра используется **GLB** (через `<model-viewer>`). Если у товара заполнен только USDZ — на десктопе не будет 3D, но AR на iPhone работает.
- При смене Wi-Fi сети IP ноута меняется — сертификат нужно перевыпустить (`mkcert localhost новый-IP` в `frontend/.cert/`).

## Дообучение модели (опционально)

Текущий продакшен — `dataset/model_v5/`. Если потребуется обучить новую версию:

```bash
cd dataset

# 1. Дополнить или поправить seeds.json (канонические интенты)
# 2. Сгенерировать train/eval через GPT-4o-mini
python generator.py --seeds seeds.json --out-train train.jsonl --out-eval eval.jsonl

# 3. Валидировать сгенерированный датасет
python validator.py --jsonl train.jsonl --report

# 4. Запустить colab_finetune.ipynb в Kaggle/Colab (потребуется GPU)
#    Результат — qwen2.5-3b-furniture-q8_0.gguf + Modelfile
# 5. Создать модель в локальной Ollama
ollama create furniture-3b-v6 -f model_v6/Modelfile

# 6. Переключить backend на новую версию (OLLAMA_MODEL в docker-compose.yml)
```