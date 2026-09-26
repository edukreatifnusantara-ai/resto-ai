# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false
"""AI Agent integration for Resto-AI.

Supports two-way interaction:
1. Outward (Customer): Warm, natural ordering, menu exploration, order tracking, and simulated payments.
2. Inward (Owner Authority): Adding menus, changing prices, setting discounts, updating stock, and getting sales reports.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, date
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    MenuItem,
    Order,
    OrderStatus,
    PaymentStatus,
    Stock,
    DiningTable,
    Reservation,
)

logger = logging.getLogger(__name__)


_EMOJI_OR_EMOTICON = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]"
    r"|(?<!\w)(?::|;|=|8|x|X)[-^']?[)(DPpOo/\\\\]|(?<!\w)<3(?!\w)|(?<!\w)[xX][dD](?!\w)"
)


def _natural_customer_reply(text: str) -> str:
    """Keep customer-facing AI replies conversational and free of emojis/emoticons."""
    text = _EMOJI_OR_EMOTICON.sub("", text or "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Conversation memory per sender phone (last 10 turns)
_CONVERSATION_HISTORY: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=10))


def get_owner_phones() -> set[str]:
    """Retrieve configured owner phone numbers."""
    raw = os.getenv("OWNER_PHONE_NUMBERS", "628131344159")
    phones = set()
    for p in re.split(r"[,\s;]+", raw.strip()):
        cleaned = re.sub(r"\D", "", p)
        if cleaned:
            phones.add(cleaned)
    return phones


def is_owner(sender: str) -> bool:
    """Check if the sender is an authorized owner."""
    cleaned = re.sub(r"\D", "", sender)
    owners = get_owner_phones()
    return cleaned in owners


def _find_menu_item(db: Session, identifier: Any) -> MenuItem | None:
    if identifier is None:
        return None
    raw_str = str(identifier).strip()
    if raw_str.isdigit():
        item = db.query(MenuItem).filter(MenuItem.id == int(raw_str)).first()
        if item:
            return item

    clean_q = raw_str.lower()
    # 1. Exact match first
    item = db.query(MenuItem).filter(MenuItem.name.ilike(clean_q)).first()
    if item:
        return item

    # 2. Substring match
    items = db.query(MenuItem).all()
    for it in items:
        it_name = str(getattr(it, "name", "")).lower()
        if clean_q in it_name or it_name in clean_q:
            return it

    # 3. Smart token overlap matching
    q_tokens = set(re.findall(r"\w+", clean_q))
    q_meaningful = q_tokens - {"porsi", "satu", "dua", "tiga", "bungkus", "pesan", "mau", "dong", "ya", "kak"}
    if not q_meaningful:
        q_meaningful = q_tokens

    best_item = None
    best_score = 0
    for it in items:
        it_tokens = set(re.findall(r"\w+", str(getattr(it, "name", "")).lower()))
        common = q_meaningful.intersection(it_tokens)
        score = len(common)
        if score > best_score and len(common) >= max(1, len(q_meaningful) * 0.4):
            best_score = score
            best_item = it

    return best_item


# =====================================================================
# OWNER TOOLS
# =====================================================================

def owner_add_menu(db: Session, name: str, price: float, description: str = "") -> dict[str, Any]:
    existing = db.query(MenuItem).filter(MenuItem.name.ilike(name.strip())).first()
    if existing:
        return {"error": f"Menu '{name}' sudah ada di database."}
    price_val = float(price)
    cost_val = round(price_val * 0.70, 2)
    item = MenuItem(
        name=name.strip(),
        price=price_val,
        cost_price=cost_val,
        description=description.strip(),
        discount_percent=0.0,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "status": "success",
        "message": f"Menu '{item.name}' berhasil ditambahkan dengan harga Rp{float(item.price):,.0f} (Modal HPP: Rp{cost_val:,.0f}, Margin 30%: Rp{price_val - cost_val:,.0f}).".replace(",", "."),
        "item": {
            "id": item.id,
            "name": item.name,
            "price": float(item.price),
            "cost_price": cost_val,
            "description": item.description,
        },
    }


def owner_update_price(db: Session, name_or_id: str, new_price: float) -> dict[str, Any]:
    item = _find_menu_item(db, name_or_id)
    if not item:
        return {"error": f"Menu '{name_or_id}' tidak ditemukan."}
    old_price = float(item.price)
    new_price_val = float(new_price)
    cost_val = round(new_price_val * 0.70, 2)
    setattr(item, "price", new_price_val)
    setattr(item, "cost_price", cost_val)
    db.commit()
    return {
        "status": "success",
        "message": f"Harga '{item.name}' diubah dari Rp{old_price:,.0f} menjadi Rp{new_price_val:,.0f} (Modal HPP 70%: Rp{cost_val:,.0f}, Margin 30%: Rp{new_price_val - cost_val:,.0f}).".replace(",", "."),
        "item_id": item.id,
        "name": item.name,
        "new_price": new_price_val,
        "cost_price": cost_val,
    }


def owner_set_discount(db: Session, name_or_id: str, discount_percent: float) -> dict[str, Any]:
    discount = max(0.0, min(100.0, float(discount_percent)))
    if name_or_id.strip().lower() in {"all", "semua"}:
        items = db.query(MenuItem).filter(MenuItem.is_active == True).all()
        for it in items:
            setattr(it, "discount_percent", discount)
        db.commit()
        return {
            "status": "success",
            "message": f"Diskon {discount:.0f}% diterapkan ke semua menu aktif ({len(items)} menu).",
        }

    item = _find_menu_item(db, name_or_id)
    if not item:
        return {"error": f"Menu '{name_or_id}' tidak ditemukan."}
    setattr(item, "discount_percent", discount)
    db.commit()
    effective_price = float(item.price) * (1.0 - discount / 100.0)
    return {
        "status": "success",
        "message": f"Diskon menu '{item.name}' diatur ke {discount:.0f}%. Harga promo: Rp{effective_price:,.0f} (Normal: Rp{float(item.price):,.0f}).".replace(",", "."),
        "name": item.name,
        "discount_percent": discount,
        "effective_price": effective_price,
    }


def owner_set_menu_status(db: Session, name_or_id: str, is_active: bool) -> dict[str, Any]:
    item = _find_menu_item(db, name_or_id)
    if not item:
        return {"error": f"Menu '{name_or_id}' tidak ditemukan."}
    setattr(item, "is_active", bool(is_active))
    db.commit()
    status_str = "AKTIF (Tersedia)" if is_active else "NONAKTIF (Habis/Disembunyikan)"
    return {
        "status": "success",
        "message": f"Status menu '{item.name}' berhasil diubah menjadi {status_str}.",
    }


def owner_get_report(db: Session) -> dict[str, Any]:
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_orders = db.query(Order).filter(Order.created_at >= today_start).all()
    all_orders = db.query(Order).all()

    total_sales = sum(float(getattr(o, "total", 0.0)) for o in today_orders if getattr(o, "payment_state", "") == PaymentStatus.SIMULATED_CONFIRMED)
    paid_count = sum(1 for o in today_orders if getattr(o, "payment_state", "") == PaymentStatus.SIMULATED_CONFIRMED)
    draft_count = sum(1 for o in today_orders if getattr(o, "state", "") == OrderStatus.DRAFT)
    kitchen_count = sum(1 for o in today_orders if getattr(o, "state", "") in {OrderStatus.SENT_TO_KITCHEN, OrderStatus.PREPARING})

    cogs_70 = total_sales * 0.70
    profit_30 = total_sales * 0.30

    all_sales = sum(float(getattr(o, "total", 0.0)) for o in all_orders if getattr(o, "payment_state", "") == PaymentStatus.SIMULATED_CONFIRMED)
    all_cogs_70 = all_sales * 0.70
    all_profit_30 = all_sales * 0.30

    sold_items_map: dict[str, int] = {}
    for o in today_orders:
        if getattr(o, "payment_state", "") == PaymentStatus.SIMULATED_CONFIRMED:
            items_list = o.items_json.get("items", []) if isinstance(o.items_json, dict) else []
            for itm in items_list:
                name = str(itm.get("name", "Unknown"))
                qty = int(itm.get("quantity", 1))
                sold_items_map[name] = sold_items_map.get(name, 0) + qty
    top_items = [f"{k} ({v} porsi)" for k, v in sorted(sold_items_map.items(), key=lambda x: x[1], reverse=True)[:5]]

    # Stock alert
    low_stocks = db.query(Stock).filter(Stock.quantity <= Stock.min_threshold).all()
    stock_alerts = [f"{s.ingredient}: sisa {float(s.quantity):.1f} (min: {float(s.min_threshold):.1f})" for s in low_stocks]

    return {
        "today_date": str(date.today()),
        "total_orders_today": len(today_orders),
        "paid_orders": paid_count,
        "draft_orders": draft_count,
        "orders_in_kitchen": kitchen_count,
        "total_revenue_today": f"Rp{total_sales:,.0f}".replace(",", "."),
        "cost_of_goods_sold_70pct": f"Rp{cogs_70:,.0f}".replace(",", "."),
        "estimated_net_profit_30pct": f"Rp{profit_30:,.0f}".replace(",", "."),
        "cost_percent": 70.0,
        "profit_margin_percent": 30.0,
        "top_selling_items_today": top_items if top_items else "Belum ada pesanan terjual hari ini.",
        "all_time_revenue": f"Rp{all_sales:,.0f}".replace(",", "."),
        "all_time_estimated_net_profit_30pct": f"Rp{all_profit_30:,.0f}".replace(",", "."),
        "low_stock_warnings": stock_alerts if stock_alerts else "Semua stok bahan aman.",
    }


def owner_update_stock(db: Session, ingredient: str, add_quantity: float) -> dict[str, Any]:
    ing_clean = ingredient.strip().lower()
    stock = db.query(Stock).filter(Stock.ingredient.ilike(ing_clean)).first()
    if not stock:
        # Create new stock entry if not exists
        stock = Stock(ingredient=ing_clean, quantity=float(add_quantity), min_threshold=5.0)
        db.add(stock)
    else:
        setattr(stock, "quantity", float(stock.quantity) + float(add_quantity))
    db.commit()
    db.refresh(stock)
    return {
        "status": "success",
        "message": f"Stok bahan '{stock.ingredient}' sekarang berjumlah {float(stock.quantity):.1f} (ditambah {float(add_quantity):.1f}).",
    }


def owner_list_menu(db: Session) -> list[dict[str, Any]]:
    items = db.query(MenuItem).all()
    res = []
    for it in items:
        disc = float(getattr(it, "discount_percent", 0.0))
        eff_price = float(it.price) * (1.0 - disc / 100.0)
        cost_val = float(getattr(it, "cost_price", round(float(it.price) * 0.70, 2)))
        margin = eff_price - cost_val
        res.append({
            "id": it.id,
            "name": it.name,
            "original_price": float(it.price),
            "cost_price": cost_val,
            "margin_profit": round(margin, 2),
            "discount_percent": disc,
            "effective_price": eff_price,
            "is_active": bool(getattr(it, "is_active", True)),
            "description": it.description or "",
        })
    return res


# =====================================================================
# CUSTOMER TOOLS
# =====================================================================

def customer_get_menu(db: Session) -> list[dict[str, Any]]:
    items = db.query(MenuItem).filter(MenuItem.is_active == True).all()
    res = []
    for it in items:
        disc = float(getattr(it, "discount_percent", 0.0))
        eff_price = float(it.price) * (1.0 - disc / 100.0)
        res.append({
            "id": it.id,
            "name": it.name,
            "price": float(it.price),
            "discount_percent": disc,
            "effective_price": eff_price,
            "description": it.description or "",
        })
    return res


def customer_create_order(
    db: Session,
    customer_phone: str,
    items: list[dict[str, Any]],
    table_number: str = "Bawa Pulang / Takeaway",
    payment_method: str = "QRIS",
    order_type: str = "DINE_IN",
    notes: str = "",
) -> dict[str, Any]:
    if not items:
        return {"error": "Pesanan tidak boleh kosong."}

    order_items = []
    total_amount = 0.0

    for it in items:
        identifier = it.get("menu_name") or it.get("menu_id") or it.get("name")
        qty = int(it.get("quantity", 1))
        if qty < 1:
            qty = 1

        menu_item = _find_menu_item(db, identifier)
        if not menu_item or not getattr(menu_item, "is_active", True):
            return {"error": f"Menu '{identifier}' tidak ditemukan atau sedang tidak tersedia."}

        disc = float(getattr(menu_item, "discount_percent", 0.0))
        eff_price = float(menu_item.price) * (1.0 - disc / 100.0)
        subtotal = eff_price * qty
        total_amount += subtotal

        order_items.append({
            "menu_item_id": menu_item.id,
            "name": menu_item.name,
            "quantity": qty,
            "price": eff_price,
            "subtotal": subtotal,
        })

    clean_table = table_number.strip() if table_number else "Bawa Pulang / Takeaway"
    pay_method = payment_method.strip().upper() if payment_method else "QRIS"
    if pay_method not in {"CASH", "QRIS"}:
        pay_method = "QRIS"

    order = Order(
        items_json={"items": order_items, "notes": notes},
        total=round(float(total_amount), 2),
        table_number=clean_table,
        order_type=order_type,
        payment_method=pay_method,
        state=OrderStatus.DRAFT,
        payment_state=PaymentStatus.PENDING,
        customer_phone=customer_phone,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    from app.midtrans import send_whatsapp_bridge_message

    if pay_method == "CASH":
        # Alert owner/cashier via WhatsApp
        owner_alert = (
            "*PESANAN BARU — PEMBAYARAN TUNAI*\n"
            f"ID Pesanan: #{order.id}\n"
            f"Lokasi/Meja: {clean_table}\n"
            f"Pelanggan: {customer_phone}\n"
            f"Total tagihan: Rp{float(order.total):,.0f}\n"
            f"Menu: {', '.join(it['name'] + ' x' + str(it['quantity']) for it in order_items)}\n"
            f"Mohon konfirmasi setelah pembayaran tunai untuk Pesanan #{order.id} diterima."
        ).replace(",", ".")
        for op in os.getenv("OWNER_PHONE_NUMBERS", "").split(","):
            if op.strip():
                send_whatsapp_bridge_message(op.strip(), owner_alert)

        return {
            "status": "success",
            "order_id": order.id,
            "table_number": clean_table,
            "payment_method": "CASH",
            "total": float(order.total),
            "formatted_total": f"Rp{float(order.total):,.0f}".replace(",", "."),
            "items": order_items,
            "qr_image_path": "",
            "queue_number": None,
            "message": f"Pesanan #{order.id} untuk {clean_table} berhasil dicatat dengan metode Bayar Tunai (Cash). Total: Rp{float(order.total):,.0f}.".replace(",", "."),
            "next_step": f"Silakan lakukan pembayaran tunai sebesar Rp{float(order.total):,.0f} di kasir Warung Ndelik dengan menunjukkan ID Pesanan #{order.id}. Nomor antrean pesanan akan otomatis terbit begitu kasir mengonfirmasi pembayaran.".replace(",", "."),
        }

    # Otherwise QRIS
    from app.midtrans import create_qris_charge
    qris_info = create_qris_charge(
        order_id=order.id,
        gross_amount=float(order.total),
        customer_name="Pelanggan",
        customer_phone=customer_phone,
    )

    return {
        "status": "success",
        "order_id": order.id,
        "table_number": clean_table,
        "payment_method": "QRIS",
        "total": float(order.total),
        "formatted_total": f"Rp{float(order.total):,.0f}".replace(",", "."),
        "items": order_items,
        "qr_image_path": qris_info.get("qr_image_path", ""),
        "qris_mode": qris_info.get("mode", "simulation"),
        "queue_number": None,
        "message": f"Pesanan #{order.id} untuk {clean_table} berhasil dibuat dengan total Rp{float(order.total):,.0f}.".replace(",", "."),
        "next_step": "Gambar kode QRIS pembayaran otomatis telah dikirimkan ke chat. Pelanggan cukup scan/screenshot QRIS tersebut di aplikasi mobile banking / e-wallet. Nomor antrean akan otomatis terbit begitu pembayaran QRIS berhasil.",
    }


def customer_request_qris(db: Session, customer_phone: str, order_id: int) -> dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id, Order.customer_phone == customer_phone).first()
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan untuk nomor ini."}
    if order.payment_state == PaymentStatus.SIMULATED_CONFIRMED:
        return {"status": "already_paid", "message": f"Pesanan #{order_id} sudah lunas terbayar."}

    from app.midtrans import create_qris_charge
    qris_info = create_qris_charge(
        order_id=order.id,
        gross_amount=float(order.total),
        customer_name="Pelanggan",
        customer_phone=customer_phone,
    )
    return {
        "status": "success",
        "order_id": order.id,
        "total": float(order.total),
        "formatted_total": f"Rp{float(order.total):,.0f}".replace(",", "."),
        "qr_image_path": qris_info.get("qr_image_path", ""),
        "message": f"Berikut gambar barcode QRIS untuk Pesanan #{order.id} sebesar Rp{float(order.total):,.0f}.".replace(",", "."),
    }



def customer_check_order(db: Session, customer_phone: str, order_id: int) -> dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id, Order.customer_phone == customer_phone).first()
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan untuk nomor ini."}
    return {
        "order_id": order.id,
        "table_number": getattr(order, "table_number", "Bawa Pulang / Takeaway"),
        "payment_method": getattr(order, "payment_method", "QRIS"),
        "queue_number": getattr(order, "queue_number", "Belum terbit (menunggu pembayaran lunas)"),
        "state": order.state,
        "payment_state": order.payment_state,
        "total": f"Rp{float(order.total):,.0f}".replace(",", "."),
        "items": getattr(order, "items_json", {}).get("items", []),
    }


def customer_confirm_payment(db: Session, customer_phone: str, order_id: int) -> dict[str, Any]:
    """Report the current payment state; customer chat cannot mark an order as paid."""
    order = db.query(Order).filter(Order.id == order_id, Order.customer_phone == customer_phone).first()
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan."}
    if getattr(order, "payment_state", "") == PaymentStatus.SIMULATED_CONFIRMED:
        return {
            "status": "already_paid",
            "message": f"Pesanan #{order_id} sudah lunas dan dapat diproses.",
        }
    return {
        "status": "pending_verification",
        "message": (
            f"Pembayaran Pesanan #{order_id} masih menunggu verifikasi. "
            "Pesanan dan reservasi akan dilayani setelah pembayaran lunas terkonfirmasi."
        ),
    }


def customer_check_available_tables(
    db: Session,
    reservation_date: str = "",
    reservation_time: str = "",
) -> dict[str, Any]:
    """Check table availability for dining or reservation."""
    from datetime import datetime, timedelta
    if not reservation_date:
        reservation_date = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")

    all_tables = db.query(DiningTable).filter(DiningTable.is_active == True).all()
    reservations = db.query(Reservation).filter(
        Reservation.reservation_date == reservation_date,
        Reservation.status.in_(["CONFIRMED", "PENDING"]),
    ).all()

    booked_tables = {r.table_number: r for r in reservations}

    available = []
    occupied = []
    for tbl in all_tables:
        t_info = {
            "table_number": tbl.table_number,
            "capacity": f"{tbl.capacity} orang",
            "area": tbl.area,
        }
        if tbl.table_number in booked_tables:
            res_info = booked_tables[tbl.table_number]
            t_info["booked_by"] = res_info.customer_name
            t_info["booked_time"] = res_info.reservation_time
            occupied.append(t_info)
        else:
            available.append(t_info)

    return {
        "status": "success",
        "date": reservation_date,
        "available_tables": available,
        "booked_tables": occupied,
        "available_count": len(available),
        "total_count": len(all_tables),
        "message": f"Tersedia {len(available)} meja kosong dari total {len(all_tables)} meja pada tanggal {reservation_date}.",
    }


def customer_create_reservation(
    db: Session,
    customer_phone: str,
    customer_name: str,
    table_number: str,
    reservation_date: str,
    reservation_time: str,
    guest_count: int = 2,
    notes: str = "",
    payment_order_id: int | None = None,
) -> dict[str, Any]:
    """Confirm a table reservation only after its linked order is paid in full."""
    if not payment_order_id:
        return {
            "error": (
                "Reservasi belum dapat dikonfirmasi karena pembayaran belum terhubung. "
                "Silakan buat pesanan terlebih dahulu, lakukan pembayaran sampai lunas, "
                "lalu kirim nomor pesanan yang sudah dibayar."
            )
        }

    paid_order = db.query(Order).filter(
        Order.id == int(payment_order_id),
        Order.customer_phone == customer_phone,
    ).first()
    if not paid_order:
        return {"error": "Pesanan pembayaran tidak ditemukan untuk nomor WhatsApp ini."}
    if paid_order.payment_state != PaymentStatus.SIMULATED_CONFIRMED:
        return {
            "error": (
                f"Reservasi belum dapat dikonfirmasi karena Pesanan #{paid_order.id} belum lunas. "
                "Reservasi akan dilayani setelah pembayaran terverifikasi."
            )
        }

    from datetime import datetime, timedelta
    if not reservation_date:
        reservation_date = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")

    tbl = db.query(DiningTable).filter(DiningTable.table_number.ilike(table_number.strip())).first()
    if not tbl:
        return {"error": f"Meja '{table_number}' tidak ditemukan di Warung Ndelik. Silakan cek meja yang tersedia."}

    matched_tbl_number = tbl.table_number

    existing = db.query(Reservation).filter(
        Reservation.table_number == matched_tbl_number,
        Reservation.reservation_date == reservation_date,
        Reservation.status.in_(["CONFIRMED", "PENDING"]),
    ).first()

    if existing:
        return {
            "error": f"{matched_tbl_number} sudah direservasi oleh pelanggan lain pada tanggal {reservation_date} pukul {existing.reservation_time} WIB. Silakan pilih meja lain yang masih kosong."
        }

    resv = Reservation(
        customer_name=customer_name or "Pelanggan",
        customer_phone=customer_phone,
        table_number=matched_tbl_number,
        guest_count=guest_count,
        reservation_date=reservation_date,
        reservation_time=reservation_time,
        status="CONFIRMED",
        notes=notes or "",
        payment_order_id=paid_order.id,
    )
    db.add(resv)
    db.commit()
    db.refresh(resv)

    from app.midtrans import send_whatsapp_bridge_message
    owner_msg = (
        "*RESERVASI MEJA DIKONFIRMASI*\n"
        f"Nama: {customer_name}\n"
        f"No. WhatsApp: {customer_phone}\n"
        f"Meja: {matched_tbl_number} ({tbl.area}, kapasitas {tbl.capacity} orang)\n"
        f"Tanggal: {reservation_date}\n"
        f"Jam: {reservation_time} WIB\n"
        f"Jumlah tamu: {guest_count} orang\n"
        f"Pesanan lunas: #{paid_order.id}\n"
        f"Catatan: {notes or '-'}"
    )
    for op in os.getenv("OWNER_PHONE_NUMBERS", "").split(","):
        if op.strip():
            send_whatsapp_bridge_message(op.strip(), owner_msg)

    return {
        "status": "success",
        "reservation_id": resv.id,
        "customer_name": customer_name,
        "table_number": matched_tbl_number,
        "reservation_date": reservation_date,
        "reservation_time": reservation_time,
        "guest_count": guest_count,
        "area": tbl.area,
        "payment_order_id": paid_order.id,
        "message": (
            f"Reservasi {matched_tbl_number} untuk {customer_name} pada {reservation_date}, "
            f"pukul {reservation_time} WIB sudah dikonfirmasi. Pembayaran Pesanan #{paid_order.id} telah lunas."
        ),
    }


def owner_confirm_cash_payment(
    db: Session,
    order_id: int,
) -> dict[str, Any]:
    """Owner/cashier confirms cash payment for an order, assigning queue number and notifying customer."""
    order = db.query(Order).get(order_id)
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan."}

    curr_pay_state = str(getattr(order, "payment_state", ""))
    if curr_pay_state == PaymentStatus.SIMULATED_CONFIRMED:
        curr_q = getattr(order, "queue_number", "-")
        return {"status": "already_paid", "message": f"Pesanan #{order_id} sudah lunas sebelumnya dengan Nomor Antrean: {curr_q}."}

    from app.database import assign_order_queue
    from app.midtrans import send_whatsapp_bridge_message

    setattr(order, "payment_state", PaymentStatus.SIMULATED_CONFIRMED)
    setattr(order, "state", OrderStatus.PAID)
    queue_number = assign_order_queue(db, order)
    db.commit()

    tbl_num = getattr(order, "table_number", "Bawa Pulang / Takeaway")
    cust_phone = getattr(order, "customer_phone", "")

    if cust_phone:
        cust_msg = (
            f"Pembayaran tunai untuk Pesanan #{order.id} ({tbl_num}) sebesar "
            f"Rp{float(order.total):,.0f} sudah kami terima.\n"
            f"*Nomor antrean: {queue_number}*\n"
            f"Pesanan sedang disiapkan dan akan diantarkan ke {tbl_num}. Terima kasih sudah memesan di Warung Ndelik."
        ).replace(",", ".")
        send_whatsapp_bridge_message(cust_phone, cust_msg)

    return {
        "status": "success",
        "order_id": order.id,
        "table_number": tbl_num,
        "queue_number": queue_number,
        "total": float(order.total),
        "formatted_total": f"Rp{float(order.total):,.0f}".replace(",", "."),
        "message": f"Pesanan #{order.id} ({tbl_num}) berhasil dikonfirmasi LUNAS (CASH). Nomor Antrean: {queue_number}. Notifikasi telah dikirim ke pelanggan via WhatsApp.",
    }


def customer_cancel_order(db: Session, customer_phone: str, order_id: int) -> dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id, Order.customer_phone == customer_phone).first()
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan."}
    if getattr(order, "state", "") in {OrderStatus.PAID, OrderStatus.SENT_TO_KITCHEN, OrderStatus.PREPARING, OrderStatus.COMPLETED}:
        return {"error": f"Pesanan #{order_id} tidak dapat dibatalkan karena sudah dalam status {order.state}."}
    setattr(order, "state", OrderStatus.CANCELLED)
    db.commit()
    return {
        "status": "success",
        "message": f"Pesanan #{order_id} berhasil dibatalkan.",
    }


# =====================================================================
# TOOL SPECIFICATIONS FOR LLM (OPENAI SCHEMA)
# =====================================================================

OWNER_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "owner_add_menu",
            "description": "Menambahkan menu makanan atau minuman baru ke sistem resto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nama menu, misal: Nasi Bakar Cumi"},
                    "price": {"type": "number", "description": "Harga menu dalam Rupiah, misal: 28000"},
                    "description": {"type": "string", "description": "Deskripsi menu"},
                },
                "required": ["name", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_update_price",
            "description": "Mengubah harga menu makanan atau minuman yang sudah ada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_id": {"type": "string", "description": "Nama menu atau ID menu"},
                    "new_price": {"type": "number", "description": "Harga baru dalam Rupiah"},
                },
                "required": ["name_or_id", "new_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_set_discount",
            "description": "Memberikan diskon persen pada menu tertentu atau semua menu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_id": {"type": "string", "description": "Nama menu, ID menu, atau 'all' untuk semua menu"},
                    "discount_percent": {"type": "number", "description": "Besar diskon dalam persen (0 - 100)"},
                },
                "required": ["name_or_id", "discount_percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_set_menu_status",
            "description": "Mengubah status aktif/nonaktif menu (misal jika menu habis atau tersedia kembali).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_id": {"type": "string", "description": "Nama menu atau ID menu"},
                    "is_active": {"type": "boolean", "description": "true jika tersedia, false jika habis/dinonaktifkan"},
                },
                "required": ["name_or_id", "is_active"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_get_report",
            "description": "Melihat laporan penjualan resto hari ini, omset, jumlah pesanan, dan peringatan stok bahan yang menipis.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_update_stock",
            "description": "Menambah stok bahan mentah di gudang / dapur resto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredient": {"type": "string", "description": "Nama bahan baku, misal: ayam, telur, beras"},
                    "add_quantity": {"type": "number", "description": "Jumlah yang ditambahkan"},
                },
                "required": ["ingredient", "add_quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_list_menu",
            "description": "Melihat seluruh daftar menu resto beserta harga asli, diskon, dan status aktifnya.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "owner_confirm_cash_payment",
            "description": "Mengonfirmasi bahwa pelanggan telah membayar tunai (CASH) di kasir untuk pesanan tertentu. Otomatis menerbitkan nomor antrean pesanan dan memberi tahu pelanggan via WhatsApp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Nomor ID pesanan yang dibayar cash di kasir"},
                },
                "required": ["order_id"],
            },
        },
    },
]

CUSTOMER_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "customer_get_menu",
            "description": "Melihat daftar menu makanan dan minuman yang tersedia untuk pelanggan beserta harga dan promo diskon.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_create_order",
            "description": "Membuat pesanan makanan atau minuman baru untuk pelanggan ke sistem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Daftar item yang dipesan",
                        "items": {
                            "type": "object",
                            "properties": {
                                "menu_name": {"type": "string", "description": "Nama atau ID menu yang dipesan"},
                                "quantity": {"type": "integer", "description": "Jumlah porsi yang dipesan"},
                            },
                            "required": ["menu_name", "quantity"],
                        },
                    },
                    "table_number": {
                        "type": "string",
                        "description": "Nomor meja makan (misal: Meja 1, Meja 5, Lesehan 2) atau 'Bawa Pulang / Takeaway' jika pesanan dibungkus",
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["QRIS", "CASH"],
                        "description": "Metode pembayaran: 'QRIS' untuk bayar otomatis via barcode QRIS, atau 'CASH' untuk bayar tunai di kasir",
                    },
                    "notes": {"type": "string", "description": "Catatan khusus pesanan, misal: pedas sedang, es sedikit"},
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_check_available_tables",
            "description": "Mengecek daftar meja di Warung Ndelik yang masih kosong dan tersedia untuk ditempati atau direservasi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_date": {"type": "string", "description": "Tanggal yang dicek format YYYY-MM-DD (kosongkan jika untuk hari ini)"},
                    "reservation_time": {"type": "string", "description": "Jam yang dicek format HH:MM (misal: 19:00)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_create_reservation",
            "description": "Mengonfirmasi reservasi meja hanya untuk pelanggan yang sudah melunasi pesanan terkait.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Nama pelanggan yang memesan reservasi"},
                    "table_number": {"type": "string", "description": "Nomor meja yang dipilih (misal: Meja 3, Lesehan 1, Ruang VIP)"},
                    "reservation_date": {"type": "string", "description": "Tanggal reservasi format YYYY-MM-DD (misal: 2026-09-22)"},
                    "reservation_time": {"type": "string", "description": "Jam reservasi format HH:MM (misal: 19:00)"},
                    "guest_count": {"type": "integer", "description": "Jumlah tamu/orang"},
                    "notes": {"type": "string", "description": "Catatan tambahan untuk resto"},
                    "payment_order_id": {"type": "integer", "description": "Nomor pesanan milik pelanggan yang sudah berstatus lunas"},
                },
                "required": ["customer_name", "table_number", "reservation_date", "reservation_time", "payment_order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_check_order",
            "description": "Mengecek rincian dan status pesanan pelanggan berdasarkan ID pesanan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Nomor ID pesanan"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_confirm_payment",
            "description": "Mengecek apakah pembayaran pesanan sudah terverifikasi. Fungsi ini tidak dapat menandai pembayaran sebagai lunas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Nomor ID pesanan yang ingin dibayar"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_request_qris",
            "description": "Mengirimkan gambar kode QRIS dinamis untuk pembayaran pesanan pelanggan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Nomor ID pesanan yang ingin dibayar via QRIS"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_cancel_order",
            "description": "Membatalkan pesanan yang belum diproses dapur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "Nomor ID pesanan yang ingin dibatalkan"},
                },
                "required": ["order_id"],
            },
        },
    },
]


def _execute_tool_call(db: Session, sender: str, is_owner_role: bool, func_name: str, args: dict[str, Any]) -> Any:
    """Safely route and execute tool calls with strict role boundaries."""
    if is_owner_role:
        if func_name == "owner_add_menu":
            return owner_add_menu(db, args.get("name", ""), args.get("price", 0), args.get("description", ""))
        elif func_name == "owner_update_price":
            return owner_update_price(db, str(args.get("name_or_id", "")), args.get("new_price", 0))
        elif func_name == "owner_set_discount":
            return owner_set_discount(db, str(args.get("name_or_id", "")), args.get("discount_percent", 0))
        elif func_name == "owner_set_menu_status":
            return owner_set_menu_status(db, str(args.get("name_or_id", "")), bool(args.get("is_active", True)))
        elif func_name == "owner_get_report":
            return owner_get_report(db)
        elif func_name == "owner_update_stock":
            return owner_update_stock(db, args.get("ingredient", ""), args.get("add_quantity", 0))
        elif func_name == "owner_list_menu":
            return owner_list_menu(db)
        elif func_name == "owner_confirm_cash_payment":
            return owner_confirm_cash_payment(db, int(args.get("order_id", 0)))

    # Customer accessible tools (available to customer and owner)
    if func_name == "customer_get_menu":
        return customer_get_menu(db)
    elif func_name == "customer_create_order":
        return customer_create_order(
            db,
            sender,
            args.get("items", []),
            table_number=args.get("table_number", "Bawa Pulang / Takeaway"),
            payment_method=args.get("payment_method", "QRIS"),
            notes=args.get("notes", ""),
        )
    elif func_name == "customer_check_order":
        return customer_check_order(db, sender, int(args.get("order_id", 0)))
    elif func_name == "customer_request_qris":
        return customer_request_qris(db, sender, int(args.get("order_id", 0)))
    elif func_name == "customer_confirm_payment":
        return customer_confirm_payment(db, sender, int(args.get("order_id", 0)))
    elif func_name == "customer_cancel_order":
        return customer_cancel_order(db, sender, int(args.get("order_id", 0)))
    elif func_name == "customer_check_available_tables":
        return customer_check_available_tables(db, args.get("reservation_date", ""), args.get("reservation_time", ""))
    elif func_name == "customer_create_reservation":
        return customer_create_reservation(
            db,
            sender,
            customer_name=args.get("customer_name", "Pelanggan"),
            table_number=args.get("table_number", ""),
            reservation_date=args.get("reservation_date", ""),
            reservation_time=args.get("reservation_time", ""),
            guest_count=int(args.get("guest_count", 2)),
            notes=args.get("notes", ""),
            payment_order_id=int(args["payment_order_id"]) if args.get("payment_order_id") else None,
        )


    return {"error": f"Fungsi '{func_name}' tidak diizinkan atau tidak ditemukan."}


def run_ai_agent(db: Session, sender: str, user_message: str) -> dict[str, Any]:
    """Main entry point for two-way AI agent processing."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not found; cannot invoke AI agent.")
        return {"reply": "", "image_path": ""}

    is_owner_user = is_owner(sender)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if is_owner_user:
        system_prompt = (
            "Kamu adalah AI Agent Asisten Resto-AI yang bertindak sebagai pengendali resto internal untuk Owner (Bapak/Bos).\n"
            "Restoran: Warung Ndelik.\n"
            "Aturan Keuangan Resto:\n"
            "- Harga modal (HPP) seluruh menu dipukul rata 70% dari harga jual.\n"
            "- Margin keuntungan bersih dipukul rata 30% dari harga jual.\n"
            "- Saat Owner meminta laporan penjualan / keuangan, selalu sampaikan secara transparan: Total Omset (Penjualan), Estimasi Modal HPP (70%), dan Estimasi Keuntungan Bersih (30%).\n\n"
            "Tugasmu membantu Owner mengelola restoran melalui WhatsApp:\n"
            "- Menambah menu baru (owner_add_menu)\n"
            "- Mengubah harga menu (owner_update_price)\n"
            "- Mengatur diskon/promo (owner_set_discount)\n"
            "- Mengubah status menu habis/tersedia (owner_set_menu_status)\n"
            "- Melihat laporan penjualan harian, omset, modal HPP, margin laba & peringatan stok menipis (owner_get_report)\n"
            "- Menambah stok bahan mentah (owner_update_stock)\n"
            "- Melihat seluruh daftar menu & harga (owner_list_menu)\n"
            "- Mengonfirmasi pembayaran tunai / cash dari kasir (owner_confirm_cash_payment), yang otomatis menerbitkan nomor antrean pesanan dan mengabari pelanggan.\n\n"
            "Gaya bicara: Hormat, sopan, natural, panggil 'Bos' atau 'Bapak'. Berikan konfirmasi jelas setiap ada perubahan data."
        )
        tools = OWNER_TOOLS_SCHEMA
    else:
        system_prompt = (
            "Kamu adalah AI Agent pelayan restoran Warung Ndelik yang ramah, sopan, dan hangat melayani pelanggan via WhatsApp.\n"
            "Tugasmu:\n"
            "- Menjawab pertanyaan seputar menu makanan dan minuman khas Warung Ndelik secara ramah dan menggugah selera.\n"
            "- Jika pelanggan menanyakan menu atau ingin tahu apa saja yang dijual, gunakan fungsi customer_get_menu.\n"
            "- Menu favorit / best seller kami antara lain: Nasi Bebek Ndelik 1/2 (Bumbu Hitam), Nasi Goreng Ceplok, Kwetiau Ndelik, dan Nasi Garang Asem.\n"
            "- Saat pelanggan memesan:\n"
            "  * Tanyakan atau pastikan apakah makan di tempat (makan di meja berapa) atau dibawa pulang / dibungkus.\n"
            "  * Tanyakan atau pastikan metode pembayaran: QRIS otomatis (scan barcode) atau Bayar Tunai (Cash di kasir).\n"
            "  * Panggil customer_create_order dengan mengisi table_number dan payment_method ('QRIS' atau 'CASH').\n"
            "- Nomor Antrean (Queue Number) hanya diterbitkan otomatis SETELAH pembayaran lunas (setelah scan QRIS berhasil, atau setelah bayar cash diterima di kasir).\n"
            "- Jika pelanggan memilih QRIS, beri tahu bahwa barcode QRIS otomatis dikirimkan ke chat dan nomor antrean terbit saat pembayaran terverifikasi.\n"
            "- Jika pelanggan memilih CASH, beri tahu ID pesanan dan arahkan untuk membayar tunai di kasir. Nomor antrean terbit setelah kasir mengonfirmasi.\n"
            "- Reservasi Meja & Info Meja Kosong:\n"
            "  * Jika pelanggan ingin melihat meja yang tersedia, gunakan customer_check_available_tables dan sampaikan hasilnya secara ringkas.\n"
            "  * Reservasi hanya boleh dikonfirmasi apabila pelanggan memiliki pesanan terkait yang sudah LUNAS dan terverifikasi. Minta nomor pesanan lunas tersebut, lalu panggil customer_create_reservation dengan payment_order_id.\n"
            "  * Jangan pernah menyatakan meja dipesan, diamankan, atau reservasi berhasil sebelum fungsi customer_create_reservation mengembalikan konfirmasi sukses. Jika pembayaran belum lunas, jelaskan dengan singkat bahwa reservasi akan dilayani setelah pembayaran terverifikasi.\n"
            "- Jangan pernah membuka informasi rahasia omset resto, modal HPP, atau mengubah harga/menu untuk pelanggan umum.\n\n"
            "Gaya bicara: Berbahasa Indonesia yang hangat, sopan, dan alami seperti staf Warung Ndelik yang benar-benar sedang membantu pelanggan. Sesuaikan jawaban dengan pertanyaan dan percakapan sebelumnya; jangan memakai kalimat template berulang atau gaya chatbot. Jangan gunakan emoji maupun emotikon. Gunakan daftar hanya ketika menyampaikan menu, pilihan, atau langkah yang memang perlu dirapikan."
        )
        tools = CUSTOMER_TOOLS_SCHEMA

    history = _CONVERSATION_HISTORY[sender]

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append(dict(h))
    messages.append({"role": "user", "content": user_message})

    # Call OpenAI Chat Completion with tools
    max_tool_loops = 3
    final_reply = ""
    last_image_path = ""

    for _ in range(max_tool_loops):
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.55,
        }

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.error("Error communicating with OpenAI API: %s", exc)
            return {"reply": "", "image_path": ""}

        choice = result["choices"][0]
        msg = choice.get("message", {})
        messages.append(msg)

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            final_reply = msg.get("content", "") or ""
            break

        for tc in tool_calls:
            call_id = tc.get("id")
            func = tc.get("function", {})
            f_name = func.get("name", "")
            try:
                f_args = json.loads(func.get("arguments", "{}"))
            except Exception:
                f_args = {}

            tool_output = _execute_tool_call(db, sender, is_owner_user, f_name, f_args)
            if isinstance(tool_output, dict) and tool_output.get("qr_image_path"):
                last_image_path = tool_output.get("qr_image_path")

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(tool_output, ensure_ascii=False),
            })

    if not is_owner_user:
        final_reply = _natural_customer_reply(final_reply)

    if final_reply:
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": final_reply})

    return {
        "reply": final_reply,
        "image_path": last_image_path,
    }

