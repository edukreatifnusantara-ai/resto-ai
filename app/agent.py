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
)

logger = logging.getLogger(__name__)

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

    order = Order(
        items_json={"items": order_items, "notes": notes},
        total=round(float(total_amount), 2),
        state=OrderStatus.DRAFT,
        payment_state=PaymentStatus.PENDING,
        customer_phone=customer_phone,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "status": "success",
        "order_id": order.id,
        "total": float(order.total),
        "formatted_total": f"Rp{float(order.total):,.0f}".replace(",", "."),
        "items": order_items,
        "message": f"Pesanan #{order.id} berhasil dibuat dengan total Rp{float(order.total):,.0f}.".replace(",", "."),
        "next_step": f"Kirim 'BAYAR {order.id}' untuk konfirmasi pembayaran simulasi.",
    }


def customer_check_order(db: Session, customer_phone: str, order_id: int) -> dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id, Order.customer_phone == customer_phone).first()
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan untuk nomor ini."}
    return {
        "order_id": order.id,
        "state": order.state,
        "payment_state": order.payment_state,
        "total": f"Rp{float(order.total):,.0f}".replace(",", "."),
        "items": getattr(order, "items_json", {}).get("items", []),
    }


def customer_confirm_payment(db: Session, customer_phone: str, order_id: int) -> dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id, Order.customer_phone == customer_phone).first()
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan."}
    if getattr(order, "payment_state", "") == PaymentStatus.SIMULATED_CONFIRMED:
        return {"status": "already_paid", "message": f"Pesanan #{order_id} sudah terbayar sebelumnya."}

    setattr(order, "state", OrderStatus.PAID)
    setattr(order, "payment_state", PaymentStatus.SIMULATED_CONFIRMED)
    db.commit()
    return {
        "status": "success",
        "order_id": order.id,
        "message": f"Pembayaran untuk Pesanan #{order_id} berhasil dikonfirmasi (SIMULASI). Pesanan siap diproses dapur!",
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
                    "notes": {"type": "string", "description": "Catatan khusus pesanan, misal: pedas sedang, es sedikit"},
                },
                "required": ["items"],
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
            "description": "Mengonfirmasi pembayaran simulasi pesanan agar pesanan siap diteruskan ke dapur.",
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

    # Customer accessible tools (available to customer and owner)
    if func_name == "customer_get_menu":
        return customer_get_menu(db)
    elif func_name == "customer_create_order":
        return customer_create_order(db, sender, args.get("items", []), args.get("notes", ""))
    elif func_name == "customer_check_order":
        return customer_check_order(db, sender, int(args.get("order_id", 0)))
    elif func_name == "customer_confirm_payment":
        return customer_confirm_payment(db, sender, int(args.get("order_id", 0)))
    elif func_name == "customer_cancel_order":
        return customer_cancel_order(db, sender, int(args.get("order_id", 0)))

    return {"error": f"Fungsi '{func_name}' tidak diizinkan atau tidak ditemukan."}


def run_ai_agent(db: Session, sender: str, user_message: str) -> str:
    """Main entry point for two-way AI agent processing."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not found; cannot invoke AI agent.")
        return ""

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
            "- Melihat seluruh daftar menu & harga (owner_list_menu)\n\n"
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
            "- Membantu pelanggan memesan makanan & minuman. Jika pelanggan ingin memesan, pastikan rincian pesanan jelas lalu panggil fungsi customer_create_order.\n"
            "- Berikan nomor ID pesanan, rincian menu, dan total harga setelah pesanan berhasil dibuat.\n"
            "- Pandu pelanggan cara konfirmasi bayar (kirim BAYAR <id> atau minta tolong bayar di chat).\n"
            "- Jangan pernah membuka informasi rahasia omset resto, modal HPP, atau mengubah harga/menu untuk pelanggan umum.\n\n"
            "Gaya bicara: Ramah, santun, panggil pelanggan 'kak' atau 'kakak', gunakan bahasa Indonesia santai tapi sopan layaknya pelayan restoran profesional."
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

    for _ in range(max_tool_loops):
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
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
            return ""

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
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(tool_output, ensure_ascii=False),
            })

    if final_reply:
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": final_reply})

    return final_reply
