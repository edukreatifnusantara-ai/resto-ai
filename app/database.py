import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.models import Base, MenuItem, Recipe, Stock


DATABASE_URL = os.getenv("RESTO_DATABASE_URL", "sqlite:///./resto.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_MENU = [
    ("Nasi Goreng", 25000, "Nasi goreng spesial dengan telur"),
    ("Mie Goreng", 22000, "Mie goreng dengan ayam"),
    ("Sate Ayam", 30000, "Sate ayam dengan bumbu kacang"),
    ("Es Teh", 5000, "Es teh manis"),
    ("Air Mineral", 3000, "Air mineral bottled"),
]
_RECIPES = {
    "Nasi Goreng": [("nasi", 1.0), ("telur", 1.0), ("ayam", 0.2), ("sayur", 0.1)],
    "Mie Goreng": [("mie", 1.0), ("ayam", 0.2), ("bawang", 0.05)],
    "Sate Ayam": [("daging ayam", 2.0), ("bumbu kacang", 0.1)],
    "Es Teh": [("teh", 0.05), ("gula", 0.02)],
    "Air Mineral": [("air mineral", 1.0)],
}
_STOCK = [
    ("nasi", 50.0, 5.0),
    ("telur", 30.0, 3.0),
    ("ayam", 40.0, 5.0),
    ("sayur", 30.0, 5.0),
    ("mie", 50.0, 5.0),
    ("bawang", 20.0, 3.0),
    ("daging ayam", 40.0, 5.0),
    ("bumbu kacang", 20.0, 3.0),
    ("teh", 20.0, 3.0),
    ("gula", 20.0, 3.0),
    ("air mineral", 50.0, 5.0),
]


def ensure_schema():
    """Apply the small additive migration needed by the staging MVP."""
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("orders")}
    migrations = {
        "stock_consumed": "ALTER TABLE orders ADD COLUMN stock_consumed BOOLEAN NOT NULL DEFAULT 0",
        "customer_phone": "ALTER TABLE orders ADD COLUMN customer_phone VARCHAR(32)",
    }
    missing = [name for name in migrations if name not in columns]
    event_columns = {column["name"] for column in inspect(engine).get_columns("whatsapp_events")}
    event_migrations = {
        "claimed_at": "ALTER TABLE whatsapp_events ADD COLUMN claimed_at DATETIME",
    }
    missing_event = [name for name in event_migrations if name not in event_columns]
    if missing or missing_event:
        with engine.begin() as connection:
            for name in missing:
                connection.execute(text(migrations[name]))
            for name in missing_event:
                connection.execute(text(event_migrations[name]))


def init_db():
    """Create tables, apply additive migrations, and repair synthetic seed data."""
    ensure_schema()
    seed_db()


def seed_db():
    """Idempotently upsert synthetic menu, recipe, and stock fixtures."""
    session = SessionLocal()
    try:
        menu_ids = {}
        added_menu = 0
        for name, price, description in _MENU:
            item = session.query(MenuItem).filter(MenuItem.name == name).one_or_none()
            if item is None:
                item = MenuItem(name=name, price=price, description=description)
                session.add(item)
                session.flush()
                added_menu += 1
            menu_ids[name] = item.id

        added_recipes = 0
        for menu_name, recipe_rows in _RECIPES.items():
            menu_id = menu_ids[menu_name]
            for ingredient, quantity in recipe_rows:
                exists = session.query(Recipe).filter(
                    Recipe.menu_item_id == menu_id,
                    Recipe.ingredient == ingredient,
                ).one_or_none()
                if exists is None:
                    session.add(Recipe(menu_item_id=menu_id, ingredient=ingredient, quantity=quantity))
                    added_recipes += 1

        added_stock = 0
        for ingredient, quantity, threshold in _STOCK:
            item = session.query(Stock).filter(Stock.ingredient == ingredient).one_or_none()
            if item is None:
                session.add(Stock(ingredient=ingredient, quantity=quantity, min_threshold=threshold))
                added_stock += 1

        session.commit()
        if added_menu:
            print(f"Seeded {added_menu} menu items.")
        if added_recipes:
            print(f"Seeded {added_recipes} recipes.")
        if added_stock:
            print(f"Seeded {added_stock} stock items.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
