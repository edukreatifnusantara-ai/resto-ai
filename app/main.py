import os
import secrets
from datetime import datetime
from math import isfinite
from threading import Lock

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update
from sqlalchemy.orm import Session
from typing import List

from app.database import init_db, SessionLocal
from app.models import (
    Base, MenuItem, Recipe, Stock, Order,
    OrderStatus, PaymentStatus,
    Order as OrderModel,
)
from app.database import engine


app = FastAPI(title="Resto AI MVP", version="0.1.0")
_stock_lock = Lock()


@app.middleware("http")
async def require_runtime_token(request: Request, call_next):
    # Health is intentionally public for local process supervision. All data
    # and mutation endpoints require the staging token.
    if request.url.path == "/":
        return await call_next(request)
    expected = os.getenv("RESTO_API_TOKEN")
    supplied = request.headers.get("X-RESTO-API-TOKEN", "")
    if not expected:
        return JSONResponse(
            {"detail": "RESTO_API_TOKEN belum dikonfigurasi"}, status_code=503
        )
    if not supplied or not secrets.compare_digest(supplied, expected):
        return JSONResponse({"detail": "Token runtime tidak valid"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
def startup_database():
    init_db()


@app.get("/", response_description="Staging health check")
def health_check():
    return {
        "service": "resto-ai-mvp",
        "status": "ok",
        "environment": "DATA DUMMY / SIMULASI",
    }


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def transition_order(order: OrderModel, new_state: str) -> None:
    if not order.can_transition_to(new_state):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid order transition: {order.state} -> {new_state}",
        )
    order.state = new_state


# --- Menu endpoints ---

@app.get("/menu", response_description="List menu items")
def list_menu(db: Session = Depends(get_db)):
    items = db.query(MenuItem).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "price": item.price,
            "description": item.description,
        }
        for item in items
    ]


class MenuItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    price: float = Field(..., gt=0, le=1_000_000_000)
    description: str = ""

    @field_validator("price")
    @classmethod
    def price_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("price harus berupa angka finite")
        return value


@app.post("/menu", response_description="Add a menu item (owner)")
def add_menu_item(payload: MenuItemCreate, db: Session = Depends(get_db)):
    existing = db.query(MenuItem).filter(MenuItem.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Menu item name already exists")
    item = MenuItem(name=payload.name, price=payload.price, description=payload.description)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "name": item.name, "price": item.price}


# Pydantic models for API contracts

class OrderItem(BaseModel):
    menu_item_id: int = Field(..., ge=1, description="Menu item ID")
    quantity: int = Field(default=1, ge=1, le=1000, description="Quantity ordered")


class OrderCreate(BaseModel):
    items: List[OrderItem] = Field(
        ..., min_length=1, max_length=50, description="Order items with menu_item_id and quantity"
    )


# --- Order endpoints ---

@app.post("/orders/", response_description="Create a new order (DRAFT)")
def create_order(order_create: OrderCreate, db: Session = Depends(get_db)):
    """Create a new order. items: [{"menu_item_id": int, "quantity": int}]"""
    # Validate all menu items exist and calculate total
    total = 0.0
    order_items = []
    for item_data in order_create.items:
        mi = db.query(MenuItem).get(item_data.menu_item_id)
        if mi is None:
            raise HTTPException(status_code=400, detail=f"Menu item {item_data.menu_item_id} not found")
        if not db.query(Recipe).filter(Recipe.menu_item_id == mi.id).count():
            raise HTTPException(
                status_code=400,
                detail=f"Menu item {mi.name} belum memiliki resep stok",
            )
        total += mi.price * item_data.quantity
        order_items.append({
            "menu_item_id": mi.id,
            "name": mi.name,
            "price": mi.price,
            "quantity": item_data.quantity,
        })

    order = OrderModel(
        items_json={"items": order_items},
        total=round(total, 2),
        state=OrderStatus.DRAFT,
        payment_state=PaymentStatus.PENDING,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "items": order_items,
        "total": order.total,
        "state": order.state,
        "payment_state": order.payment_state,
    }


@app.get("/orders/{order_id}", response_description="Get order by ID")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    items = order.items_json.get("items", []) if order.items_json else []
    return {
        "id": order.id,
        "items": items,
        "total": order.total,
        "state": order.state,
        "payment_state": order.payment_state,
        "created_at": order.created_at,
        "completed_at": order.completed_at,
    }


# Payment state transitions

@app.post("/orders/{order_id}/request-payment", response_description="Move draft order to payment pending")
def request_payment(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.state == OrderStatus.PENDING_PAYMENT:
        return {"id": order.id, "state": order.state}
    transition_order(order, OrderStatus.PENDING_PAYMENT)
    db.commit()
    return {"id": order.id, "state": order.state}


@app.post("/orders/{order_id}/pay", response_description="Simulate payment confirmation")
def simulate_payment(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_state == PaymentStatus.SIMULATED_CONFIRMED:
        return {"message": "Payment already confirmed", "payment_state": order.payment_state}
    if order.payment_state == PaymentStatus.FAILED:
        raise HTTPException(status_code=400, detail="Payment already failed; create a new order")
    result = db.execute(
        update(OrderModel)
        .where(
            OrderModel.id == order_id,
            OrderModel.state == OrderStatus.PENDING_PAYMENT,
            OrderModel.payment_state == PaymentStatus.PENDING,
        )
        .values(state=OrderStatus.PAID, payment_state=PaymentStatus.SIMULATED_CONFIRMED)
    )
    if result.rowcount != 1:
        db.rollback()
        current = db.query(OrderModel).get(order_id)
        if current and current.payment_state == PaymentStatus.SIMULATED_CONFIRMED:
            return {"message": "Payment already confirmed", "payment_state": current.payment_state}
        raise HTTPException(status_code=409, detail="Order berubah; pembayaran tidak diproses")
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "state": order.state,
        "payment_state": order.payment_state,
        "message": "Payment simulated confirmed (non-settlement)",
    }


@app.post("/orders/{order_id}/payment-failed", response_description="Simulate failed payment")
def simulate_payment_failed(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_state == PaymentStatus.FAILED:
        return {"message": "Payment already failed", "payment_state": order.payment_state}
    if order.payment_state == PaymentStatus.SIMULATED_CONFIRMED:
        raise HTTPException(status_code=400, detail="Payment sudah dikonfirmasi")
    if order.state != OrderStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=400, detail=f"Order must be PENDING_PAYMENT, current: {order.state}")
    order.payment_state = PaymentStatus.FAILED
    db.commit()
    return {"id": order.id, "state": order.state, "payment_state": order.payment_state}


@app.post("/orders/{order_id}/cancel", response_description="Cancel an order")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    result = db.execute(
        update(OrderModel)
        .where(
            OrderModel.id == order_id,
            OrderModel.state.in_([OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT]),
        )
        .values(state=OrderStatus.CANCELLED)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Order sudah masuk proses pembayaran/operasional dan tidak dapat dibatalkan",
        )
    db.commit()
    db.refresh(order)
    return {"id": order.id, "state": order.state, "message": "Order cancelled"}


# Kitchen transition endpoints


def deduct_order_stock(db: Session, order: OrderModel) -> None:
    """Preflight and deduct stock atomically within this process."""
    with _stock_lock:
        db.refresh(order)
        if order.stock_consumed:
            raise HTTPException(status_code=409, detail="Order sudah dikirim ke dapur")
        if order.state != OrderStatus.PAID or order.payment_state != PaymentStatus.SIMULATED_CONFIRMED:
            raise HTTPException(status_code=409, detail=f"Order tidak siap dikirim: {order.state}")
        requirements = {}
        items = order.items_json.get("items", [])
        for item in items:
            mi_id = item["menu_item_id"]
            mi = db.query(MenuItem).get(mi_id)
            if mi is None:
                raise HTTPException(status_code=400, detail=f"Menu item {mi_id} not found")
            recipes = db.query(Recipe).filter(Recipe.menu_item_id == mi_id).all()
            if not recipes:
                raise HTTPException(status_code=400, detail=f"Menu item {mi.name} belum memiliki resep stok")
            for rec in recipes:
                requirements[rec.ingredient] = requirements.get(rec.ingredient, 0.0) + (
                    rec.quantity * item["quantity"]
                )

        try:
            for ingredient, quantity_needed in requirements.items():
                result = db.execute(
                    update(Stock)
                    .where(Stock.ingredient == ingredient, Stock.quantity >= quantity_needed)
                    .values(quantity=Stock.quantity - quantity_needed)
                )
                if result.rowcount != 1:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient or changed stock for {ingredient}",
                    )
            transition_order(order, OrderStatus.SENT_TO_KITCHEN)
            order.stock_consumed = True
            db.commit()
        except Exception:
            db.rollback()
            raise


@app.post("/orders/{order_id}/send-to-kitchen", response_description="Send order to kitchen (deducts stock)")
def send_to_kitchen(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_state != PaymentStatus.SIMULATED_CONFIRMED:
        raise HTTPException(status_code=400, detail="Order must be PAID before sending to kitchen")
    if order.state != OrderStatus.PAID:
        raise HTTPException(status_code=409, detail=f"Order sudah berubah state: {order.state}")

    deduct_order_stock(db, order)
    return {
        "id": order.id,
        "state": order.state,
        "message": "Order sent to kitchen; stock deducted",
    }


@app.post("/orders/{order_id}/prepare", response_description="Start food preparation")
def start_prepare(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    transition_order(order, OrderStatus.PREPARING)
    db.commit()
    return {"id": order.id, "state": order.state}


@app.post("/orders/{order_id}/ready", response_description="Mark order ready for pickup/delivery")
def mark_ready(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    transition_order(order, OrderStatus.READY)
    db.commit()
    return {"id": order.id, "state": order.state}


@app.post("/orders/{order_id}/complete", response_description="Mark ready order completed")
def complete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    transition_order(order, OrderStatus.COMPLETED)
    order.completed_at = datetime.utcnow()
    db.commit()
    return {
        "id": order.id,
        "state": order.state,
        "completed_at": order.completed_at,
    }


# --- Report endpoints ---

@app.get("/reports/sales", response_description="Sales summary report")
def sales_report(db: Session = Depends(get_db)):
    from sqlalchemy import func
    from app.models import Order as OrderModel
    # Sum of totals for completed orders
    result = db.query(func.sum(OrderModel.total)).filter(OrderModel.state == OrderStatus.COMPLETED).scalar()
    total_sales = round(float(result) if result else 0.0, 2)
    count = db.query(OrderModel).filter(OrderModel.state == OrderStatus.COMPLETED).count()
    return {
        "total_sales": total_sales,
        "completed_orders": count,
        "report_type": "sales",
    }


@app.get("/reports/finance", response_description="Simulated finance report")
def finance_report(db: Session = Depends(get_db)):
    from sqlalchemy import func

    paid_total = db.query(func.sum(OrderModel.total)).filter(
        OrderModel.payment_state == PaymentStatus.SIMULATED_CONFIRMED,
        OrderModel.state != OrderStatus.CANCELLED,
    ).scalar()
    return {
        "report_type": "finance",
        "status": "SIMULASI — bukan settlement nyata",
        "simulated_paid_total": round(float(paid_total) if paid_total else 0.0, 2),
    }


@app.get("/reports/stock", response_description="Current stock levels report")
def stock_report(db: Session = Depends(get_db)):
    stocks = db.query(Stock).all()
    return {
        "report_type": "stock",
        "stocks": [
            {
                "ingredient": s.ingredient,
                "quantity": s.quantity,
                "min_threshold": s.min_threshold,
            }
            for s in stocks
        ],
    }