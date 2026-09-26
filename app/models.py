from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False, default=0.0)
    description = Column(String(255))
    discount_percent = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, nullable=False, default=True)
    recipes = relationship("Recipe", back_populates="menu_item", cascade="all, delete-orphan")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    ingredient = Column(String(120), nullable=False)
    quantity = Column(Float, nullable=False)
    menu_item = relationship("MenuItem", back_populates="recipes")


class Stock(Base):
    __tablename__ = "stock"

    id = Column(Integer, primary_key=True)
    ingredient = Column(String(120), nullable=False, unique=True)
    quantity = Column(Float, default=0.0)
    min_threshold = Column(Float, default=0.0)

    def deduct(self, amount: float) -> bool:
        if amount < 0 or self.quantity < amount:
            return False
        self.quantity -= amount
        return True


class OrderStatus:
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    SENT_TO_KITCHEN = "SENT_TO_KITCHEN"
    PREPARING = "PREPARING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatus:
    PENDING = "PENDING"
    SIMULATED_CONFIRMED = "SIMULATED_CONFIRMED"
    FAILED = "FAILED"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    items_json = Column(JSON, nullable=False, default=dict)
    total = Column(Float, nullable=False)
    table_number = Column(String(50), nullable=True, default="Bawa Pulang / Takeaway")
    order_type = Column(String(30), nullable=False, default="DINE_IN")
    payment_method = Column(String(30), nullable=False, default="QRIS")
    queue_number = Column(String(20), nullable=True, default=None)
    state = Column(String(30), nullable=False, default=OrderStatus.DRAFT)
    payment_state = Column(String(30), nullable=False, default=PaymentStatus.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    stock_consumed = Column(Boolean, nullable=False, default=False)
    customer_phone = Column(String(32), nullable=True, index=True)
    source_message_id = Column(String(160), nullable=True, unique=True, index=True)

    @property
    def item_details(self):
        return self.items_json.get("items", [])

    @item_details.setter
    def item_details(self, value):
        if "items" not in self.items_json:
            self.items_json["items"] = value

    def calculate_total(self) -> float:
        total = sum(
            item.get("price", 0.0) * item.get("quantity", 1.0)
            for item in self.items_json.get("items", [])
        )
        return round(total, 2)

    def can_transition_to(self, new_state: str) -> bool:
        allowed = {
            OrderStatus.DRAFT: {OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED},
            OrderStatus.PENDING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
            OrderStatus.PAID: {OrderStatus.SENT_TO_KITCHEN},
            OrderStatus.SENT_TO_KITCHEN: {OrderStatus.PREPARING},
            OrderStatus.PREPARING: {OrderStatus.READY},
            OrderStatus.READY: {OrderStatus.COMPLETED},
            OrderStatus.COMPLETED: set(),
            OrderStatus.CANCELLED: set(),
        }
        if new_state not in allowed.get(self.state, set()):
            return False
        if new_state == OrderStatus.PAID:
            return self.payment_state == PaymentStatus.SIMULATED_CONFIRMED
        return True


class WhatsAppEvent(Base):
    __tablename__ = "whatsapp_events"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(160), unique=True, nullable=False)
    sender_phone = Column(String(32), nullable=False)
    message_type = Column(String(32), nullable=False)
    body = Column(String(4096), nullable=False, default="")
    claimed_at = Column(DateTime, nullable=True)
    response_body = Column(String(4096), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DiningTable(Base):
    __tablename__ = "dining_tables"

    id = Column(Integer, primary_key=True)
    table_number = Column(String(50), unique=True, nullable=False)
    capacity = Column(Integer, nullable=False, default=4)
    area = Column(String(100), nullable=False, default="Area Utama")
    is_active = Column(Boolean, nullable=False, default=True)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(32), nullable=False)
    table_number = Column(String(50), nullable=False)
    guest_count = Column(Integer, nullable=False, default=2)
    reservation_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    reservation_time = Column(String(20), nullable=False)  # HH:MM
    status = Column(String(30), nullable=False, default="CONFIRMED")  # CONFIRMED, COMPLETED, CANCELLED
    notes = Column(String(255), nullable=True, default="")
    payment_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

