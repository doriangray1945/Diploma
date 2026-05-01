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

## AR-режим на iPhone

На странице товара появляется блок «3D-модель»: на десктопе — вращающаяся 3D-модель, на iPhone Safari — кнопка **«Просмотр в AR»**, которая открывает нативный iOS Quick Look. С iPhone 12 Pro и выше (LiDAR) AR работает с точным определением плоскостей и окклюзии.

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
3. Залогиниться → каталог → открыть товар, у которого есть 3D-модель (например, первые товары имеют тестовые модели).
4. Прокрутить до блока «3D-модель» → тапнуть кнопку **«Просмотр в AR»** в правом нижнем углу.
5. iOS Quick Look откроется во весь экран → навести камеру на пол → виртуальный объект встанет в комнате.

### Замечания

- Файлы 3D-моделей лежат в `frontend/public/models/`. Привязка к товарам — через `/admin/products/X/edit` (поля «Модель GLB» и «Модель USDZ»).
- Apple AR Quick Look поддерживает только формат **USDZ** на iOS. Для десктопного 3D-просмотра используется **GLB** (через `<model-viewer>`). Если у товара заполнен только USDZ — на десктопе не будет 3D, но AR на iPhone работает.
- При смене Wi-Fi сети IP ноута меняется — сертификат нужно перевыпустить (`mkcert localhost новый-IP` в `frontend/.cert/`).

## Лицензия

MIT
