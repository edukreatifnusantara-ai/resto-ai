import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, MenuItem, Recipe, Stock, Order, DiningTable, Reservation


DATABASE_URL = os.getenv("RESTO_DATABASE_URL", "sqlite:///./resto.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Buku Menu Warung Ndelik 2026 v3 (57 menu)
_MENU = [
    # Makanan Utama & Nasi
    ("Nasi Goreng Telur", 16000, "Nasi goreng spesial khas Warung Ndelik dengan telur"),
    ("Nasi Putih", 4000, "Nasi putih pulen"),
    ("Nasi Soto Ayam", 8000, "Nasi soto ayam segar khas Ndelik"),
    ("Nasi Tahu Tempe Penyet", 12000, "Nasi dengan tahu tempe penyet sambal khas"),
    ("Nasi Telur Penyet", 15000, "Nasi telur penyet sambal mantap"),
    ("Nasi Telur Oseng Ndelik", 15000, "Nasi dengan telur oseng bumbu spesial Ndelik"),
    ("Nasi Ayam Penyet", 16000, "Nasi ayam penyet gurih dengan sambal"),
    ("Nasi Ayam Kremes", 18000, "Nasi ayam goreng renyah dengan taburan kremes"),
    ("Nasi Goreng Ayam", 16000, "Nasi goreng dengan suwiran ayam"),
    ("Nasi Goreng Katsu", 18000, "Nasi goreng dengan topping chicken katsu"),
    ("Nasi Goreng Dadar / Ceplok", 19000, "Nasi goreng favorit bolo ndelik dengan telur dadar/ceplok"),
    ("Nasi Goreng Babat", 20000, "Nasi goreng gurih dengan potongan babat sapi"),
    ("Mie Goreng / Rebus", 16000, "Mie goreng atau rebus dengan sayur dan bumbu spesial"),
    ("Kwetiau Goreng / Rebus", 16000, "Kwetiau Ndelik goreng/rebus best seller"),
    ("Capcay", 15000, "Capcay aneka sayuran segar bergizi"),
    ("Ca Kangkung", 10000, "Tumis kangkung gurih sedap"),
    ("Nasi Babat Gongso", 20000, "Nasi babat sapi gongso bumbu manis gurih"),
    ("Nasi Sop Ayam", 20000, "Nasi sup ayam hangat dan segar"),
    ("Nasi Ayam Saus Padang", 20000, "Nasi ayam dengan siraman saus padang pedas manis"),
    ("Nasi Ayam Asam Manis", 20000, "Nasi ayam bumbu saus asam manis"),
    ("Nasi Bebek Bumbu Hitam Ndelik 1/4", 22000, "Nasi bebek bumbu hitam khas Madura porsi 1/4"),
    ("Nasi Bebek Bumbu Hitam Ndelik 1/2", 38000, "Nasi bebek bumbu hitam porsi 1/2 ekor best seller"),
    ("Nasi Garang Asem", 20000, "Nasi garang asem ayam belimbing wuluh segar"),
    ("Nasi Ayam Bumbu Hitam", 20000, "Nasi ayam dengan racikan bumbu hitam gurih pekat"),
    ("Steak Ayam Hot Plate", 23000, "Steak ayam lezat disajikan di atas hot plate"),
    ("Steak Sapi Hot Plate", 28000, "Steak daging sapi empuk di atas hot plate"),
    ("Nasi Ayam Sambal Gami", 20000, "Nasi ayam dengan sambal gami cobek bakar"),

    # Minuman
    ("Teh Es / Panas", 3000, "Teh manis segar dingin atau hangat"),
    ("Teh Jumbo Es / Panas", 5000, "Teh jumbo porsi besar es atau panas"),
    ("Jeruk Es / Panas", 5000, "Jeruk peras asli es atau hangat"),
    ("Es Sirup", 5000, "Es sirup manis segar"),
    ("Kopi Hitam", 5000, "Kopi hitam mantap"),
    ("Good Day Es / Panas", 5000, "Kopi Good Day aneka rasa es atau panas"),
    ("Air Mineral Besar (500ml)", 5000, "Air mineral kemasan 500ml"),
    ("Air Mineral Kecil (300ml)", 3000, "Air mineral kemasan 300ml"),
    ("Wedang Uwuh", 5000, "Wedang uwuh rempah tradisional penghangat badan"),
    ("Wedang Jahe", 6000, "Wedang jahe hangat alami"),
    ("Soda Gembira", 12000, "Minuman soda gembira susu sirup segar"),
    ("Es Susu", 7000, "Es susu segar manis"),
    ("Susu Jahe", 10000, "Susu jahe hangat berkhasiat"),
    ("Es Falooda Ndelik", 12000, "Es falooda khas Ndelik segar nikmat"),
    ("Es Teler Creamy", 12000, "Es teler creamy khas Ndelik kaya topping"),
    ("Es Cream Juara", 10000, "Es krim lembut manis juara"),

    # Snack
    ("Sosis", 5000, "Sosis goreng lezat"),
    ("Nugget", 5000, "Nugget ayam renyah"),
    ("Kentang", 7000, "Kentang goreng / french fries renyah"),
    ("Cireng", 5000, "Cireng kenyal gurih dengan cocolan bumbu"),
    ("Paket Snack", 20000, "Paket snack komplit untuk camilan rame-rame"),
    ("Tahu Bakso (1 Porsi)", 10000, "Tahu bakso gurih isi daging 1 porsi"),
    ("Galantin (1 Porsi)", 10000, "Galantin lezat 1 porsi"),
    ("Stick Keju (1 Porsi)", 10000, "Stick keju renyah gurih 1 porsi"),

    # Gorengan / Kerupuk
    ("Tempe Goreng", 1500, "Tempe goreng gurih renyah"),
    ("Sate Usus / Telur / Jeroan", 4000, "Sate tusuk usus, telur puyuh, atau jeroan"),
    ("Mendoan (1 Porsi @ 7pcs)", 10000, "Tempe mendoan hangat isi 7 pcs"),
    ("Bergedel", 3000, "Perkedel kentang gurih"),
    ("Rempeyek", 5000, "Rempeyek renyah gurih"),
    ("Kerupuk Terung", 1000, "Kerupuk terung renyah pelengkap makan"),
]


def _get_recipe_ingredients(menu_name: str) -> list[tuple[str, float]]:
    name_l = menu_name.lower()
    if "nasi goreng" in name_l:
        rec = [("nasi", 1.0), ("bumbu", 0.1)]
        if "babat" in name_l:
            rec.append(("babat", 1.0))
        elif "ayam" in name_l:
            rec.append(("ayam", 0.5))
        elif "katsu" in name_l:
            rec.append(("ayam", 0.5))
        else:
            rec.append(("telur", 1.0))
        return rec
    if "nasi bebek" in name_l:
        return [("nasi", 1.0), ("bebek", 1.0), ("bumbu_hitam", 0.2)]
    if "nasi ayam" in name_l or "garang asem" in name_l:
        return [("nasi", 1.0), ("ayam", 1.0), ("bumbu", 0.2)]
    if "nasi soto" in name_l or "sop ayam" in name_l:
        return [("nasi", 1.0), ("ayam", 0.5), ("kuah_sop", 1.0)]
    if "nasi babat" in name_l:
        return [("nasi", 1.0), ("babat", 1.0), ("bumbu", 0.2)]
    if "nasi telur" in name_l:
        return [("nasi", 1.0), ("telur", 1.0), ("sambal", 0.2)]
    if "nasi tahu tempe" in name_l:
        return [("nasi", 1.0), ("tempe", 1.0), ("sambal", 0.2)]
    if "nasi putih" in name_l:
        return [("nasi", 1.0)]
    if "steak sapi" in name_l:
        return [("daging_sapi", 1.0), ("saus_steak", 1.0)]
    if "steak ayam" in name_l:
        return [("ayam", 1.0), ("saus_steak", 1.0)]
    if "mie" in name_l:
        return [("mie", 1.0), ("sayur", 0.5), ("bumbu", 0.1)]
    if "kwetiau" in name_l:
        return [("kwetiau", 1.0), ("sayur", 0.5), ("bumbu", 0.1)]
    if "capcay" in name_l or "kangkung" in name_l:
        return [("sayur", 1.0), ("bumbu", 0.1)]
    if "teh" in name_l:
        return [("teh", 0.1), ("gula", 0.1)]
    if "jeruk" in name_l:
        return [("jeruk", 1.0), ("gula", 0.1)]
    if "kopi" in name_l or "good day" in name_l:
        return [("kopi", 1.0), ("gula", 0.1)]
    if "air mineral" in name_l:
        return [("air_mineral", 1.0)]
    if "wedang" in name_l or "jahe" in name_l:
        return [("jahe_rempah", 1.0)]
    if "soda gembira" in name_l:
        return [("soda", 1.0), ("susu", 1.0), ("sirup", 1.0)]
    if "susu" in name_l:
        return [("susu", 1.0)]
    if "falooda" in name_l or "teler" in name_l or "es cream" in name_l or "sirup" in name_l:
        return [("es_manis_buah", 1.0)]
    if "sosis" in name_l:
        return [("sosis", 1.0)]
    if "nugget" in name_l:
        return [("nugget", 1.0)]
    if "kentang" in name_l:
        return [("kentang", 1.0)]
    if "cireng" in name_l:
        return [("cireng", 1.0)]
    if "paket snack" in name_l:
        return [("kentang", 0.5), ("sosis", 0.5), ("nugget", 0.5)]
    if "tahu bakso" in name_l:
        return [("tahu_bakso", 1.0)]
    if "galantin" in name_l:
        return [("galantin", 1.0)]
    if "stick keju" in name_l:
        return [("stick_keju", 1.0)]
    if "tempe" in name_l or "mendoan" in name_l:
        return [("tempe", 1.0)]
    if "sate" in name_l:
        return [("sate_jeroan", 1.0)]
    if "bergedel" in name_l:
        return [("kentang", 1.0)]
    if "rempeyek" in name_l or "kerupuk" in name_l:
        return [("kerupuk", 1.0)]
    return [("bahan_utama", 1.0)]


def ensure_schema():
    """Apply additive migrations needed by the staging and production systems."""
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("orders")}
    migrations = {
        "stock_consumed": "ALTER TABLE orders ADD COLUMN stock_consumed BOOLEAN NOT NULL DEFAULT 0",
        "customer_phone": "ALTER TABLE orders ADD COLUMN customer_phone VARCHAR(32)",
        "source_message_id": "ALTER TABLE orders ADD COLUMN source_message_id VARCHAR(160)",
        "table_number": "ALTER TABLE orders ADD COLUMN table_number VARCHAR(50) DEFAULT 'Bawa Pulang / Takeaway'",
        "order_type": "ALTER TABLE orders ADD COLUMN order_type VARCHAR(30) NOT NULL DEFAULT 'DINE_IN'",
        "payment_method": "ALTER TABLE orders ADD COLUMN payment_method VARCHAR(30) NOT NULL DEFAULT 'QRIS'",
        "queue_number": "ALTER TABLE orders ADD COLUMN queue_number VARCHAR(20)",
    }
    missing = [name for name in migrations if name not in columns]
    reservation_columns = {column["name"] for column in inspect(engine).get_columns("reservations")}
    reservation_migrations = {
        "payment_order_id": "ALTER TABLE reservations ADD COLUMN payment_order_id INTEGER",
    }
    missing_reservation = [name for name in reservation_migrations if name not in reservation_columns]
    event_columns = {column["name"] for column in inspect(engine).get_columns("whatsapp_events")}
    event_migrations = {
        "claimed_at": "ALTER TABLE whatsapp_events ADD COLUMN claimed_at DATETIME",
        "response_body": "ALTER TABLE whatsapp_events ADD COLUMN response_body VARCHAR(4096)",
    }
    missing_event = [name for name in event_migrations if name not in event_columns]
    
    menu_columns = {column["name"] for column in inspect(engine).get_columns("menu_items")}
    menu_migrations = {
        "cost_price": "ALTER TABLE menu_items ADD COLUMN cost_price FLOAT NOT NULL DEFAULT 0.0",
        "discount_percent": "ALTER TABLE menu_items ADD COLUMN discount_percent FLOAT NOT NULL DEFAULT 0.0",
        "is_active": "ALTER TABLE menu_items ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
    }
    missing_menu = [name for name in menu_migrations if name not in menu_columns]

    if missing or missing_reservation or missing_event or missing_menu:
        with engine.begin() as connection:
            for name in missing:
                connection.execute(text(migrations[name]))
            for name in missing_reservation:
                connection.execute(text(reservation_migrations[name]))
            for name in missing_event:
                connection.execute(text(event_migrations[name]))
            for name in missing_menu:
                connection.execute(text(menu_migrations[name]))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_source_message_id "
                "ON orders(source_message_id)"
            ))


DEFAULT_TABLES = [
    ("Meja 1", 4, "Area Utama"),
    ("Meja 2", 4, "Area Utama"),
    ("Meja 3", 4, "Area Utama"),
    ("Meja 4", 6, "Area Utama"),
    ("Meja 5", 6, "Area Utama"),
    ("Meja 6", 2, "Area Semi Outdoor"),
    ("Meja 7", 2, "Area Semi Outdoor"),
    ("Lesehan 1", 8, "Area Gazebo Lesehan"),
    ("Lesehan 2", 8, "Area Gazebo Lesehan"),
    ("Ruang VIP", 12, "Area VIP / AC"),
]


def seed_tables(session: Session):
    """Seed default dining tables for Warung Ndelik."""
    for tbl_num, cap, area in DEFAULT_TABLES:
        exists = session.query(DiningTable).filter(DiningTable.table_number == tbl_num).one_or_none()
        if exists is None:
            session.add(DiningTable(
                table_number=tbl_num,
                capacity=cap,
                area=area,
                is_active=True,
            ))
    session.flush()


def get_next_queue_number(session: Session) -> str:
    """Generate sequential queue number for today, formatted as A-01, A-02, etc."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = session.query(Order).filter(
        Order.queue_number.isnot(None),
        Order.created_at >= today_start,
    ).count()
    return f"A-{count + 1:02d}"


def assign_order_queue(session: Session, order: Order) -> str:
    """Assign a queue number if not already assigned."""
    existing_q = getattr(order, "queue_number", None)
    if existing_q:
        return str(existing_q)
    q_num = get_next_queue_number(session)
    setattr(order, "queue_number", q_num)
    session.commit()
    return q_num


def init_db():
    """Create tables, apply additive migrations, and seed Warung Ndelik menu & tables."""
    ensure_schema()
    seed_db()


def seed_db():
    """Idempotently upsert Warung Ndelik menu items, recipes, stocks, and tables."""
    session = SessionLocal()
    try:
        seed_tables(session)
        ingredients_needed = set()
        menu_map = {}

        for name, price, description in _MENU:
            cost_price = round(price * 0.70, 2)
            item = session.query(MenuItem).filter(MenuItem.name == name).one_or_none()
            if item is None:
                item = MenuItem(
                    name=name,
                    price=price,
                    cost_price=cost_price,
                    description=description,
                    discount_percent=0.0,
                    is_active=True,
                )
                session.add(item)
                session.flush()
            else:
                setattr(item, "price", price)
                setattr(item, "cost_price", cost_price)
                setattr(item, "description", description)
                session.flush()

            menu_map[name] = item.id
            recipe_rows = _get_recipe_ingredients(name)
            for ingredient, qty in recipe_rows:
                ingredients_needed.add(ingredient)
                exists = session.query(Recipe).filter(
                    Recipe.menu_item_id == item.id,
                    Recipe.ingredient == ingredient,
                ).one_or_none()
                if exists is None:
                    session.add(Recipe(menu_item_id=item.id, ingredient=ingredient, quantity=qty))

        for ingredient in ingredients_needed:
            stk = session.query(Stock).filter(Stock.ingredient == ingredient).one_or_none()
            if stk is None:
                session.add(Stock(ingredient=ingredient, quantity=50.0, min_threshold=10.0))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_menu_to_warung_ndelik():
    """Full clean reset: remove old placeholder menus and seed 57 Warung Ndelik items."""
    ensure_schema()
    session = SessionLocal()
    try:
        session.query(Recipe).delete()
        session.query(MenuItem).delete()
        session.commit()
        seed_db()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
