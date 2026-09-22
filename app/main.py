import os
import secrets
from datetime import datetime, timedelta
from math import isfinite
from threading import Lock
from dotenv import load_dotenv

load_dotenv("/home/edukreativ-vps/resto-ai/.env.runtime")
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Any

from app.database import init_db, SessionLocal
from app.agent import run_ai_agent, is_owner
from app.models import (
    Base, MenuItem, Recipe, Stock, Order,
    OrderStatus, PaymentStatus, WhatsAppEvent,
    Order as OrderModel,
)
from app.database import engine
from app.whatsapp import (
    MetaWhatsAppClient,
    WhatsAppConfigurationError,
    WhatsAppDeliveryError,
    extract_messages,
    verify_signature,
    verify_subscription,
)


app = FastAPI(title="Resto AI MVP", version="0.1.0")
_stock_lock = Lock()


@app.middleware("http")
async def require_runtime_token(request: Request, call_next):
    # Health is intentionally public for local process supervision. All data
    # and mutation endpoints require the staging token.
    # Meta calls the webhook without the internal API token. It is protected
    # independently by the verify token and X-Hub-Signature-256.
    if request.url.path in {"/", "/webhooks/whatsapp", "/api/chat", "/webhooks/midtrans"}:
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
            "price": float(item.price),
            "cost_price": float(getattr(item, "cost_price", round(float(item.price) * 0.70, 2))),
            "margin_profit": round(float(item.price) * 0.30, 2),
            "description": item.description,
            "discount_percent": float(getattr(item, "discount_percent", 0.0)),
            "is_active": bool(getattr(item, "is_active", True)),
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
    customer_phone: str | None = Field(default=None, min_length=1, max_length=32)
    source_message_id: str | None = Field(default=None, min_length=1, max_length=160)


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
        customer_phone=order_create.customer_phone,
        source_message_id=order_create.source_message_id,
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


def _chatbot_help() -> str:
    return (
        "Perintah Resto-AI (SIMULASI):\\n"
        "MENU — lihat menu\\n"
        "PESAN <id_menu> <jumlah> — buat order\\n"
        "BAYAR <id_order> — konfirmasi pembayaran simulasi\\n"
        "STATUS <id_order> — lihat status order\\n"
        "BATAL <id_order> — batalkan order"
    )


def _chatbot_menu(db: Session) -> str:
    items = db.query(MenuItem).order_by(MenuItem.id).all()
    if not items:
        return "Menu belum tersedia."
    lines = ["Menu Resto-AI (DATA DUMMY / SIMULASI):"]
    for item in items:
        lines.append(f"{item.id}. {item.name} — Rp{item.price:,.0f}".replace(",", "."))
    lines.append("\\nPesan dengan format: PESAN <id_menu> <jumlah>")
    return "\\n".join(lines)


def _owned_order(db: Session, sender: str, order_id: int) -> OrderModel | None:
    return (
        db.query(OrderModel)
        .filter(OrderModel.id == order_id, OrderModel.customer_phone == sender)
        .one_or_none()
    )


def handle_whatsapp_text(
    db: Session,
    sender: str,
    body: str,
    source_message_id: str | None = None,
) -> str | dict[str, Any]:
    """Handle incoming WhatsApp messages with two-way AI agent and deterministic fallbacks."""
    text = " ".join(body.strip().split())
    if not text:
        return "Halo, ini Resto-AI.\\n\\n" + _chatbot_help()

    # If sender is Owner, prioritize AI Agent controller
    if is_owner(sender):
        ai_reply = run_ai_agent(db, sender, text)
        if isinstance(ai_reply, dict) and ai_reply.get("reply"):
            return ai_reply
        elif isinstance(ai_reply, str) and ai_reply:
            return ai_reply

    upper = text.upper()
    if upper in {"MENU", "DAFTAR MENU"}:
        return _chatbot_menu(db)

    parts = text.split()
    command = parts[0].upper()
    if command in {"PESAN", "ORDER"} and len(parts) in {2, 3} and parts[1].isdigit() and (len(parts) == 2 or parts[2].isdigit()):
        menu_id = int(parts[1])
        quantity = int(parts[2]) if len(parts) == 3 else 1
        if quantity < 1 or quantity > 1000:
            return "Jumlah harus antara 1 sampai 1000."
        if source_message_id:
            existing = db.query(OrderModel).filter(
                OrderModel.source_message_id == source_message_id,
                OrderModel.customer_phone == sender,
            ).one_or_none()
            if existing is not None:
                return (
                    f"Order #{existing.id} dibuat dengan status {existing.state}.\\n"
                    f"Total: Rp{existing.total:,.0f}".replace(",", ".")
                    + f"\\nBalas BAYAR {existing.id} untuk pembayaran SIMULASI."
                )
        try:
            result = create_order(
                OrderCreate(
                    items=[OrderItem(menu_item_id=menu_id, quantity=quantity)],
                    customer_phone=sender,
                    source_message_id=source_message_id,
                ),
                db,
            )
        except HTTPException as exc:
            return f"Order belum dapat dibuat: {exc.detail}"
        return (
            f"Order #{result['id']} dibuat dengan status DRAFT.\\n"
            f"Total: Rp{result['total']:,.0f}".replace(",", ".")
            + f"\\nBalas BAYAR {result['id']} untuk pembayaran SIMULASI."
        )

    if command in {"STATUS", "CEK"} and len(parts) == 2 and parts[1].isdigit():
        order = _owned_order(db, sender, int(parts[1]))
        if order is None:
            return "Order tidak ditemukan."
        return (
            f"Order #{order.id}\\n"
            f"Status: {order.state}\\n"
            f"Pembayaran: {order.payment_state}\\n"
            f"Total: Rp{order.total:,.0f}".replace(",", ".")
        )

    if command == "BATAL" and len(parts) == 2 and parts[1].isdigit():
        order_id = int(parts[1])
        order = _owned_order(db, sender, order_id)
        if order is None:
            return "Order tidak ditemukan."
        try:
            cancel_order(order_id, db)
        except HTTPException as exc:
            return f"Order tidak dapat dibatalkan: {exc.detail}"
        return f"Order #{order_id} berhasil dibatalkan."

    if command == "BAYAR" and len(parts) == 2 and parts[1].isdigit():
        order_id = int(parts[1])
        order = _owned_order(db, sender, order_id)
        if order is None:
            return "Order tidak ditemukan."
        try:
            if order.state == OrderStatus.DRAFT:
                request_payment(order_id, db)
            result = simulate_payment(order_id, db)
        except HTTPException as exc:
            return f"Pembayaran tidak dapat diproses: {exc.detail}"
        return (
            f"Order #{order_id} berstatus PAID.\\n"
            "Pembayaran ini SIMULASI dan bukan settlement nyata."
            if result.get("payment_state") == PaymentStatus.SIMULATED_CONFIRMED
            else f"Order #{order_id}: {result}"
        )

    # For any conversational customer messages, run AI Agent
    ai_reply = run_ai_agent(db, sender, text)
    if isinstance(ai_reply, dict) and ai_reply.get("reply"):
        return ai_reply
    elif isinstance(ai_reply, str) and ai_reply:
        return ai_reply

    if upper in {"HALO", "HI", "HAI", "HELP", "BANTUAN", "MULAI"}:
        return "Halo, ini Resto-AI.\\n\\n" + _chatbot_help()

    return "Perintah belum dikenali.\\n\\n" + _chatbot_help()


def _claim_whatsapp_event(db: Session, message: dict[str, str]) -> tuple[WhatsAppEvent, bool]:
    """Claim one webhook event exactly once, with stale-claim recovery."""
    now = datetime.utcnow()
    event = db.query(WhatsAppEvent).filter(
        WhatsAppEvent.message_id == message["message_id"]
    ).one_or_none()
    if event is None:
        event = WhatsAppEvent(
            message_id=message["message_id"],
            sender_phone=message["sender"],
            message_type=message["message_type"],
            body=message["body"],
            claimed_at=now,
        )
        db.add(event)
        try:
            db.commit()
            return event, True
        except IntegrityError:
            db.rollback()
            event = db.query(WhatsAppEvent).filter(
                WhatsAppEvent.message_id == message["message_id"]
            ).one()

    if event.processed_at is not None:
        return event, False
    stale_before = now - timedelta(minutes=5)
    claim = db.execute(
        update(WhatsAppEvent)
        .where(
            WhatsAppEvent.id == event.id,
            WhatsAppEvent.processed_at.is_(None),
            or_(WhatsAppEvent.claimed_at.is_(None), WhatsAppEvent.claimed_at < stale_before),
        )
        .values(claimed_at=now)
    )
    db.commit()
    if claim.rowcount != 1:
        return event, False
    db.refresh(event)
    return event, True


# Meta WhatsApp webhook verification is protected by Meta's verify token.
@app.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if not os.getenv("WHATSAPP_VERIFY_TOKEN"):
        raise HTTPException(status_code=503, detail="WHATSAPP_VERIFY_TOKEN belum dikonfigurasi")
    if not challenge or not verify_subscription(mode, verify_token):
        raise HTTPException(status_code=403, detail="Verifikasi webhook WhatsApp gagal")
    return PlainTextResponse(challenge)


@app.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    if not verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Signature webhook WhatsApp tidak valid")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Payload webhook bukan JSON valid") from exc

    processed = 0
    duplicates = 0
    ignored = 0
    client = MetaWhatsAppClient()
    for message in extract_messages(payload):
        event, claimed = _claim_whatsapp_event(db, message)
        if not claimed:
            duplicates += 1
            continue

        if event.response_body:
            reply_text = str(event.response_body)
        elif message["message_type"] == "text":
            reply_res = handle_whatsapp_text(
                db,
                message["sender"],
                message["body"],
                source_message_id=message["message_id"],
            )
            reply_text = reply_res.get("reply", "") if isinstance(reply_res, dict) else str(reply_res)
            event.response_body = reply_text
            db.commit()
        else:
            reply_text = "Saat ini Resto-AI hanya menerima pesan teks. Balas MENU untuk mulai."
            event.response_body = reply_text
            db.commit()
            ignored += 1
        try:
            client.send_text(message["sender"], reply_text)
        except WhatsAppConfigurationError as exc:
            event.claimed_at = datetime.utcnow() - timedelta(minutes=6)
            db.commit()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except WhatsAppDeliveryError as exc:
            event.claimed_at = datetime.utcnow() - timedelta(minutes=6)
            db.commit()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        event.processed_at = datetime.utcnow()
        db.commit()
        processed += 1

    return {"status": "ok", "processed": processed, "duplicates": duplicates, "ignored": ignored}


@app.post("/webhooks/midtrans", response_description="Midtrans payment notification webhook")
async def midtrans_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    order_midtrans_id = str(payload.get("order_id", ""))
    status_code = str(payload.get("status_code", ""))
    gross_amount = str(payload.get("gross_amount", ""))
    signature_key = str(payload.get("signature_key", ""))
    transaction_status = str(payload.get("transaction_status", ""))
    fraud_status = str(payload.get("fraud_status", ""))

    from app.midtrans import verify_midtrans_signature, send_whatsapp_bridge_message
    if not verify_midtrans_signature(order_midtrans_id, status_code, gross_amount, signature_key):
        raise HTTPException(status_code=403, detail="Invalid Midtrans signature")

    parts = order_midtrans_id.split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        internal_order_id = int(parts[1])
    else:
        try:
            internal_order_id = int(order_midtrans_id)
        except ValueError:
            return {"status": "ignored", "reason": "Unrecognized order_id format"}

    order = db.query(OrderModel).get(internal_order_id)
    if not order:
        return {"status": "ignored", "reason": f"Order #{internal_order_id} not found"}

    is_paid = False
    if transaction_status in {"capture", "settlement"}:
        if fraud_status in {"accept", ""} or not fraud_status:
            is_paid = True

    if is_paid:
        curr_pay_state = str(getattr(order, "payment_state", ""))
        curr_state = str(getattr(order, "state", ""))
        if curr_pay_state != PaymentStatus.SIMULATED_CONFIRMED:
            setattr(order, "payment_state", PaymentStatus.SIMULATED_CONFIRMED)
            if curr_state in {OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT}:
                setattr(order, "state", OrderStatus.PAID)
            db.commit()

            cust_phone = str(getattr(order, "customer_phone", ""))
            total_val = float(getattr(order, "total", 0.0))

            # 1. Notify Customer via WhatsApp Bridge
            cust_msg = (
                f"Halo kak! Pembayaran untuk Pesanan #{order.id} sebesar "
                f"Rp{total_val:,.0f} telah BERHASIL kami terima melalui QRIS.\n"
                f"Pesanan sekarang sedang disiapkan di dapur. Terima kasih telah memesan di Warung Ndelik!"
            ).replace(",", ".")
            send_whatsapp_bridge_message(cust_phone, cust_msg)

            # 2. Notify Owner via WhatsApp Bridge
            owner_msg = (
                f"🔔 *NOTIFIKASI PEMBAYARAN QRIS MASUK*\n"
                f"Pesanan #{order.id} senilai Rp{total_val:,.0f} dari {cust_phone} "
                f"telah LUNAS melalui QRIS Midtrans (Settlement)."
            ).replace(",", ".")
            for op in os.getenv("OWNER_PHONE_NUMBERS", "").split(","):
                if op.strip():
                    send_whatsapp_bridge_message(op.strip(), owner_msg)
    elif transaction_status in {"cancel", "deny", "expire"}:
        setattr(order, "payment_state", PaymentStatus.FAILED)
        db.commit()

    return {
        "status": "ok",
        "order_id": internal_order_id,
        "transaction_status": transaction_status,
        "payment_state": order.payment_state,
        "order_state": order.state,
    }



class DirectChatMessage(BaseModel):
    sender: str
    body: str
    message_id: str | None = None


@app.post("/api/chat", response_description="Direct customer chatbot message")
def direct_chat(payload: DirectChatMessage, db: Session = Depends(get_db)):
    reply = handle_whatsapp_text(
        db,
        sender=payload.sender,
        body=payload.body,
        source_message_id=payload.message_id,
    )
    if isinstance(reply, dict):
        return reply
    return {"reply": str(reply)}


# Payment state transitions

@app.post("/orders/{order_id}/request-payment", response_description="Move draft order to payment pending")
def request_payment(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderModel).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.state == OrderStatus.PENDING_PAYMENT:
        return {"id": order.id, "state": order.state}
    result = db.execute(
        update(OrderModel)
        .where(OrderModel.id == order_id, OrderModel.state == OrderStatus.DRAFT)
        .values(state=OrderStatus.PENDING_PAYMENT)
    )
    if result.rowcount != 1:
        db.rollback()
        current = db.query(OrderModel).get(order_id)
        if current and current.state == OrderStatus.PENDING_PAYMENT:
            return {"id": current.id, "state": current.state}
        raise HTTPException(status_code=409, detail="Order tidak lagi berstatus DRAFT")
    db.commit()
    db.refresh(order)
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
    result = db.execute(
        update(OrderModel)
        .where(
            OrderModel.id == order_id,
            OrderModel.state == OrderStatus.PENDING_PAYMENT,
            OrderModel.payment_state == PaymentStatus.PENDING,
        )
        .values(payment_state=PaymentStatus.FAILED)
    )
    if result.rowcount != 1:
        db.rollback()
        current = db.query(OrderModel).get(order_id)
        if current and current.payment_state == PaymentStatus.FAILED:
            return {"message": "Payment already failed", "payment_state": current.payment_state}
        raise HTTPException(status_code=409, detail="Order berubah; kegagalan pembayaran tidak diproses")
    db.commit()
    db.refresh(order)
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
        claim = db.execute(
            update(OrderModel)
            .where(
                OrderModel.id == order.id,
                OrderModel.state == OrderStatus.PAID,
                OrderModel.payment_state == PaymentStatus.SIMULATED_CONFIRMED,
                OrderModel.stock_consumed.is_(False),
            )
            .values(stock_consumed=True)
        )
        if claim.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Order sedang/ sudah diproses ke dapur")
        db.refresh(order)
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