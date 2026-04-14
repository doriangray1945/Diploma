import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker, engine, Base
from app.models import Product

FURNITURE_DATA = [
    # Диваны
    {
        "name": "Red Wood",
        "description": "Диван с подставкой из красного дерева, 100 x 180, с механизмом трансформации. Идеально подходит для гостиной. Мягкие подушки и прочный каркас обеспечивают комфорт и долговечность.",
        "price": 89990.00,
        "old_price": 99990.00,
        "category": "Диваны",
        "subcategory": "Прямые диваны",
        "images": ["/images/sofa-red-wood-1.jpg", "/images/sofa-red-wood-2.jpg"],
        "dimensions": "180x100x85",
        "materials": "Красное дерево, велюр",
        "color": "Жёлтый",
        "in_stock": True,
        "stock_quantity": 5,
        "rating": 4.8,
        "reviews_count": 24,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Comfort Plus",
        "description": "Угловой диван с просторным спальным местом. Качественная обивка из экокожи, механизм еврокнижка. Вместительный ящик для белья.",
        "price": 129990.00,
        "category": "Диваны",
        "subcategory": "Угловые диваны",
        "images": ["/images/sofa-comfort-1.jpg"],
        "dimensions": "250x180x90",
        "materials": "Экокожа, ДСП, поролон",
        "color": "Серый",
        "in_stock": True,
        "stock_quantity": 3,
        "rating": 4.6,
        "reviews_count": 18,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Milano",
        "description": "Элегантный диван в итальянском стиле. Натуральная кожа, хромированные ножки. Минималистичный дизайн для современного интерьера.",
        "price": 189990.00,
        "old_price": 219990.00,
        "category": "Диваны",
        "subcategory": "Прямые диваны",
        "images": ["/images/sofa-milano-1.jpg"],
        "dimensions": "220x95x80",
        "materials": "Натуральная кожа, хром, дуб",
        "color": "Белый",
        "in_stock": True,
        "stock_quantity": 2,
        "rating": 4.9,
        "reviews_count": 12,
        "is_popular": False,
        "is_new": True
    },
    {
        "name": "Scandia",
        "description": "Компактный диван в скандинавском стиле. Светлая обивка, деревянные ножки. Идеален для небольших пространств.",
        "price": 54990.00,
        "category": "Диваны",
        "subcategory": "Прямые диваны",
        "images": ["/images/sofa-scandia-1.jpg"],
        "dimensions": "160x85x75",
        "materials": "Рогожка, берёза",
        "color": "Бежевый",
        "in_stock": True,
        "stock_quantity": 8,
        "rating": 4.5,
        "reviews_count": 31,
        "is_popular": True,
        "is_new": False
    },

    # Кресла
    {
        "name": "Lounge Master",
        "description": "Кресло для отдыха с высокой спинкой и подголовником. Механизм реклайнер. Идеально для чтения и просмотра фильмов.",
        "price": 45990.00,
        "category": "Кресла",
        "subcategory": "Кресла-реклайнеры",
        "images": ["/images/chair-lounge-1.jpg"],
        "dimensions": "85x90x110",
        "materials": "Велюр, металл, пенополиуретан",
        "color": "Синий",
        "in_stock": True,
        "stock_quantity": 6,
        "rating": 4.7,
        "reviews_count": 15,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Egg Chair",
        "description": "Дизайнерское кресло-яйцо. Культовая модель для стильного интерьера. Поворотное основание.",
        "price": 79990.00,
        "category": "Кресла",
        "subcategory": "Дизайнерские кресла",
        "images": ["/images/chair-egg-1.jpg"],
        "dimensions": "80x75x110",
        "materials": "Кашемир, алюминий",
        "color": "Красный",
        "in_stock": True,
        "stock_quantity": 2,
        "rating": 4.9,
        "reviews_count": 8,
        "is_popular": False,
        "is_new": True
    },
    {
        "name": "Nordic Comfort",
        "description": "Мягкое кресло в скандинавском стиле. Широкое сиденье, деревянные ножки. Универсальный дизайн.",
        "price": 32990.00,
        "category": "Кресла",
        "subcategory": "Мягкие кресла",
        "images": ["/images/chair-nordic-1.jpg"],
        "dimensions": "75x80x85",
        "materials": "Рогожка, дуб",
        "color": "Зелёный",
        "in_stock": True,
        "stock_quantity": 10,
        "rating": 4.4,
        "reviews_count": 22,
        "is_popular": True,
        "is_new": False
    },

    # Столы
    {
        "name": "Oak Dining",
        "description": "Обеденный стол из массива дуба. Классический дизайн, прочная конструкция. Вместимость до 8 человек.",
        "price": 67990.00,
        "category": "Столы",
        "subcategory": "Обеденные столы",
        "images": ["/images/table-oak-1.jpg"],
        "dimensions": "180x90x75",
        "materials": "Массив дуба",
        "color": "Коричневый",
        "in_stock": True,
        "stock_quantity": 4,
        "rating": 4.8,
        "reviews_count": 19,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Glass Modern",
        "description": "Современный журнальный столик со стеклянной столешницей. Металлический каркас золотого цвета.",
        "price": 24990.00,
        "category": "Столы",
        "subcategory": "Журнальные столы",
        "images": ["/images/table-glass-1.jpg"],
        "dimensions": "100x60x45",
        "materials": "Закалённое стекло, металл",
        "color": "Прозрачный",
        "in_stock": True,
        "stock_quantity": 7,
        "rating": 4.3,
        "reviews_count": 14,
        "is_popular": False,
        "is_new": True
    },
    {
        "name": "Work Station",
        "description": "Письменный стол для домашнего офиса. Встроенные ящики, кабель-менеджмент. Просторная рабочая поверхность.",
        "price": 34990.00,
        "category": "Столы",
        "subcategory": "Письменные столы",
        "images": ["/images/table-work-1.jpg"],
        "dimensions": "140x70x75",
        "materials": "МДФ, металл",
        "color": "Белый",
        "in_stock": True,
        "stock_quantity": 9,
        "rating": 4.6,
        "reviews_count": 27,
        "is_popular": True,
        "is_new": False
    },

    # Шкафы
    {
        "name": "Wardrobe Premium",
        "description": "Вместительный шкаф-купе с зеркальными дверями. Система хранения включает штанги, полки и ящики.",
        "price": 89990.00,
        "category": "Шкафы",
        "subcategory": "Шкафы-купе",
        "images": ["/images/wardrobe-premium-1.jpg"],
        "dimensions": "240x60x220",
        "materials": "ЛДСП, зеркало, алюминий",
        "color": "Венге",
        "in_stock": True,
        "stock_quantity": 3,
        "rating": 4.7,
        "reviews_count": 11,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Книжный Классик",
        "description": "Книжный шкаф в классическом стиле. Открытые полки и закрытые секции. Резные элементы декора.",
        "price": 54990.00,
        "category": "Шкафы",
        "subcategory": "Книжные шкафы",
        "images": ["/images/bookcase-classic-1.jpg"],
        "dimensions": "120x40x200",
        "materials": "Массив сосны, МДФ",
        "color": "Орех",
        "in_stock": True,
        "stock_quantity": 5,
        "rating": 4.5,
        "reviews_count": 9,
        "is_popular": False,
        "is_new": False
    },

    # Кровати
    {
        "name": "Dream King",
        "description": "Двуспальная кровать с мягким изголовьем. Ортопедическое основание в комплекте. Подъёмный механизм для хранения.",
        "price": 79990.00,
        "old_price": 89990.00,
        "category": "Кровати",
        "subcategory": "Двуспальные кровати",
        "images": ["/images/bed-dream-1.jpg"],
        "dimensions": "180x200",
        "materials": "Велюр, ДСП, металл",
        "color": "Серый",
        "in_stock": True,
        "stock_quantity": 4,
        "rating": 4.9,
        "reviews_count": 32,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Loft Single",
        "description": "Односпальная кровать в стиле лофт. Металлический каркас, минималистичный дизайн.",
        "price": 24990.00,
        "category": "Кровати",
        "subcategory": "Односпальные кровати",
        "images": ["/images/bed-loft-1.jpg"],
        "dimensions": "90x200",
        "materials": "Металл, ЛДСП",
        "color": "Чёрный",
        "in_stock": True,
        "stock_quantity": 12,
        "rating": 4.4,
        "reviews_count": 17,
        "is_popular": False,
        "is_new": True
    },
    {
        "name": "Princess",
        "description": "Детская кровать для девочки. Нежный дизайн с балдахином. Безопасные материалы.",
        "price": 34990.00,
        "category": "Кровати",
        "subcategory": "Детские кровати",
        "images": ["/images/bed-princess-1.jpg"],
        "dimensions": "90x180",
        "materials": "МДФ, текстиль",
        "color": "Розовый",
        "in_stock": True,
        "stock_quantity": 6,
        "rating": 4.8,
        "reviews_count": 14,
        "is_popular": True,
        "is_new": False
    },

    # Стулья
    {
        "name": "Dining Elegance",
        "description": "Обеденный стул с мягким сиденьем. Деревянные ножки, обивка из велюра. Продаётся комплектом из 2 шт.",
        "price": 14990.00,
        "category": "Стулья",
        "subcategory": "Обеденные стулья",
        "images": ["/images/chair-dining-1.jpg"],
        "dimensions": "45x50x90",
        "materials": "Велюр, бук",
        "color": "Изумрудный",
        "in_stock": True,
        "stock_quantity": 20,
        "rating": 4.6,
        "reviews_count": 28,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Office Pro",
        "description": "Эргономичное офисное кресло. Поддержка поясницы, регулируемые подлокотники. Сетчатая спинка.",
        "price": 29990.00,
        "category": "Стулья",
        "subcategory": "Офисные кресла",
        "images": ["/images/chair-office-1.jpg"],
        "dimensions": "65x65x120",
        "materials": "Сетка, пластик, металл",
        "color": "Чёрный",
        "in_stock": True,
        "stock_quantity": 15,
        "rating": 4.7,
        "reviews_count": 45,
        "is_popular": True,
        "is_new": False
    },
    {
        "name": "Bar Stool Modern",
        "description": "Барный стул с регулировкой высоты. Хромированная ножка, кожаное сиденье.",
        "price": 9990.00,
        "category": "Стулья",
        "subcategory": "Барные стулья",
        "images": ["/images/stool-bar-1.jpg"],
        "dimensions": "40x40x85",
        "materials": "Экокожа, хром",
        "color": "Белый",
        "in_stock": True,
        "stock_quantity": 18,
        "rating": 4.3,
        "reviews_count": 21,
        "is_popular": False,
        "is_new": True
    },
]


async def seed_database():
    """Seed the database with initial furniture data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # Check if products already exist
        result = await session.execute(select(Product).limit(1))
        if result.scalar_one_or_none():
            print("Database already has products. Skipping seed.")
            return

        # Add products
        for product_data in FURNITURE_DATA:
            product = Product(**product_data)
            session.add(product)

        await session.commit()
        print(f"Successfully seeded {len(FURNITURE_DATA)} products!")


if __name__ == "__main__":
    asyncio.run(seed_database())
