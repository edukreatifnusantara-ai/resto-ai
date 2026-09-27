import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.models import Order, OrderStatus, PaymentStatus
from app.midtrans import send_whatsapp_bridge_message

logger = logging.getLogger("resto_ai.kitchen")

WIB = timezone(timedelta(hours=7))


def get_wib_now() -> datetime:
    return datetime.now(WIB)


def get_kitchen_destinations() -> list[str]:
    """Retrieve list of kitchen phone numbers or group JIDs."""
    raw = os.getenv("KITCHEN_PHONE_NUMBERS", "").strip()
    if not raw:
        # Fallback to owner phone numbers so notifications are never lost
        raw = os.getenv("OWNER_PHONE_NUMBERS", "").strip()
    destinations = [p.strip() for p in raw.split(",") if p.strip()]
    return destinations


def format_kitchen_ticket(order: Order) -> str:
    """Format an order ticket specifically designed for kitchen staff via WhatsApp."""
    items_data = order.items_json.get("items", []) if order.items_json else []
    notes = order.items_json.get("notes", "") if order.items_json else ""
    
    # Calculate WIB order time
    created_dt = order.created_at
    if created_dt:
        if created_dt.tzinfo is None:
            # Assume UTC in db, convert to WIB
            created_dt = created_dt.replace(tzinfo=timezone.utc).astimezone(WIB)
        else:
            created_dt = created_dt.astimezone(WIB)
        time_str = created_dt.strftime("%H:%M")
    else:
        time_str = get_wib_now().strftime("%H:%M")

    q_num = order.queue_number or f"#{order.id}"
    tbl_num = order.table_number or "Bawa Pulang / Takeaway"
    pay_method = order.payment_method or "QRIS"

    lines = [
        "🍳 *TIKET ORDERAN MASUK — DAPUR*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"No. Antrean: *{q_num}*",
        f"Lokasi / Meja: *{tbl_num}*",
        f"Waktu Masuk: *{time_str} WIB*",
        f"ID Pesanan: #{order.id} ({pay_method} - LUNAS)",
        "━━━━━━━━━━━━━━━━━━━━━",
        "*DAFTAR MENU YANG DIMASAK:*",
    ]

    for idx, it in enumerate(items_data, 1):
        name = it.get("name") or it.get("menu_name") or f"Item #{idx}"
        qty = it.get("quantity", 1)
        lines.append(f"  {idx}. *{name}*  x*{qty}*")

    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    if notes and notes.strip():
        lines.append(f"⚠️ *Catatan Khusus:* _{notes.strip()}_")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")

    lines.append("Status: *Menunggu Dimasak*")
    lines.append("🖥️ Layar Dapur Web: http://103.89.5.220:18081/dapur")

    return "\n".join(lines)


def notify_kitchen_order(db: Session, order: Order) -> int:
    """Send formatted kitchen order ticket to all configured kitchen channels."""
    destinations = get_kitchen_destinations()
    if not destinations:
        logger.warning(f"No kitchen or owner phone numbers configured for Order #{order.id}")
        return 0

    ticket_msg = format_kitchen_ticket(order)
    sent_count = 0
    for dest in destinations:
        success = send_whatsapp_bridge_message(dest, ticket_msg)
        if success:
            sent_count += 1
            logger.info(f"Kitchen ticket for Order #{order.id} sent to {dest}")
        else:
            logger.warning(f"Failed to send kitchen ticket for Order #{order.id} to {dest}")

    return sent_count


def get_kitchen_active_orders(db: Session) -> list[dict[str, Any]]:
    """Retrieve active orders for the Kitchen Display System (KDS)."""
    # Active orders: PAID, SENT_TO_KITCHEN, PREPARING, READY, or completed within last 3 hours
    active_states = [
        OrderStatus.PAID,
        OrderStatus.SENT_TO_KITCHEN,
        OrderStatus.PREPARING,
        OrderStatus.READY,
    ]

    orders = (
        db.query(Order)
        .filter(
            or_(
                Order.state.in_(active_states),
                Order.state == OrderStatus.COMPLETED
            )
        )
        .order_by(desc(Order.created_at))
        .limit(60)
        .all()
    )

    now_wib = get_wib_now()
    results = []

    for ord_obj in orders:
        created_dt = ord_obj.created_at
        if created_dt:
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc).astimezone(WIB)
            else:
                created_dt = created_dt.astimezone(WIB)
            time_str = created_dt.strftime("%H:%M")
            elapsed_minutes = int((now_wib - created_dt).total_seconds() / 60)
        else:
            time_str = now_wib.strftime("%H:%M")
            elapsed_minutes = 0

        # Only include COMPLETED orders if within last 180 minutes
        if ord_obj.state == OrderStatus.COMPLETED and elapsed_minutes > 180:
            continue

        items_data = ord_obj.items_json.get("items", []) if ord_obj.items_json else []
        notes = ord_obj.items_json.get("notes", "") if ord_obj.items_json else ""

        results.append({
            "id": ord_obj.id,
            "queue_number": ord_obj.queue_number or f"#{ord_obj.id}",
            "table_number": ord_obj.table_number or "Bawa Pulang / Takeaway",
            "state": ord_obj.state,
            "payment_state": ord_obj.payment_state,
            "payment_method": ord_obj.payment_method or "QRIS",
            "total": float(ord_obj.total or 0.0),
            "formatted_total": f"Rp{float(ord_obj.total or 0.0):,.0f}".replace(",", "."),
            "customer_phone": ord_obj.customer_phone or "-",
            "order_time": time_str,
            "elapsed_minutes": max(0, elapsed_minutes),
            "items": [
                {
                    "name": it.get("name") or it.get("menu_name") or "Menu",
                    "quantity": it.get("quantity", 1),
                    "price": it.get("price", 0.0),
                }
                for it in items_data
            ],
            "total_items_qty": sum(it.get("quantity", 1) for it in items_data),
            "notes": notes,
        })

    return results


def update_kitchen_order_status(db: Session, order_id: int, new_status: str) -> dict[str, Any]:
    """Transition order status from kitchen display and alert customer when ready."""
    order = db.query(Order).get(order_id)
    if not order:
        return {"error": f"Pesanan #{order_id} tidak ditemukan."}

    valid_transitions = {
        OrderStatus.PAID: [OrderStatus.SENT_TO_KITCHEN, OrderStatus.PREPARING],
        OrderStatus.SENT_TO_KITCHEN: [OrderStatus.PREPARING, OrderStatus.READY],
        OrderStatus.PREPARING: [OrderStatus.READY, OrderStatus.COMPLETED],
        OrderStatus.READY: [OrderStatus.COMPLETED],
    }

    allowed = valid_transitions.get(order.state, [])
    # Also allow direct PREPARING, READY, COMPLETED if logical
    if new_status not in allowed and new_status not in [OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.COMPLETED]:
        return {"error": f"Transisi dari {order.state} ke {new_status} tidak valid."}

    prev_state = order.state
    order.state = new_status

    if new_status == OrderStatus.COMPLETED:
        order.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(order)

    # When food is READY, automatically notify customer via WhatsApp
    cust_notified = False
    if new_status == OrderStatus.READY and order.customer_phone:
        q_num = order.queue_number or f"#{order.id}"
        tbl = order.table_number or "Bawa Pulang / Takeaway"
        cust_msg = (
            f"🔔 *PESANAN SELESAI DIMASAK & SIAP DISAJIKAN!*\n\n"
            f"Halo Kak! Pesanan #{order.id} (*No. Antrean: {q_num}*) untuk *{tbl}* "
            f"sudah selesai dimasak di dapur dan siap disajikan.\n\n"
            f"Staf kami sedang mengantarkan hidangan ke lokasi Anda. "
            f"Selamat menikmati kelezatan khas Warung Ndelik!"
        )
        cust_notified = send_whatsapp_bridge_message(order.customer_phone, cust_msg)

    return {
        "status": "success",
        "order_id": order.id,
        "previous_state": prev_state,
        "current_state": order.state,
        "customer_notified": cust_notified,
        "message": f"Status Pesanan #{order.id} berhasil diubah ke {new_status}.",
    }


def get_kitchen_kds_html() -> str:
    """Render full Kitchen Display System (KDS) single-page HTML interface."""
    return """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Layar Dapur (KDS) — Warung Ndelik</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    @keyframes pulse-ring {
      0% { transform: scale(0.95); opacity: 0.8; }
      50% { transform: scale(1.05); opacity: 0.4; }
      100% { transform: scale(0.95); opacity: 0.8; }
    }
    .pulse-amber { animation: pulse-ring 2s infinite; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen pb-12 antialiased">

  <!-- TOP HEADER -->
  <header class="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-4 py-3 sm:px-6">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <span class="p-2 bg-amber-500/20 text-amber-400 rounded-xl border border-amber-500/30 text-xl">🍳</span>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-lg font-bold text-white tracking-tight">Layar Dapur (KDS)</h1>
            <span class="px-2 py-0.5 text-[10px] font-bold bg-amber-500 text-slate-950 rounded-full uppercase">Warung Ndelik</span>
          </div>
          <p class="text-xs text-slate-400">Kitchen Display System — Antrean Pesanan Realtime</p>
        </div>
      </div>

      <!-- Controls & Live Indicator -->
      <div class="flex items-center gap-3">
        <!-- Sound Toggle -->
        <button id="btn-sound" onclick="toggleSound()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">
          <span id="sound-icon">🔔</span>
          <span id="sound-text">Suara: Aktif</span>
        </button>

        <!-- Live Clock -->
        <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span id="live-clock" class="mono text-xs font-bold text-emerald-400">--:-- WIB</span>
        </div>

        <!-- Dashboard Link -->
        <a href="/dashboard" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition">
          📊 Dashboard
        </a>
      </div>
    </div>

    <!-- STATS SUMMARY COUNTERS -->
    <div class="max-w-7xl mx-auto mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-800/80">
      <div onclick="setFilter('NEED_COOK')" class="cursor-pointer bg-slate-800/60 hover:bg-slate-800 p-2.5 rounded-xl border border-amber-500/30 flex items-center justify-between transition">
        <div>
          <p class="text-[11px] font-medium text-amber-300">Perlu Dimasak</p>
          <p id="count-need-cook" class="mono text-2xl font-black text-amber-400">0</p>
        </div>
        <span class="text-2xl opacity-60">⏳</span>
      </div>

      <div onclick="setFilter('PREPARING')" class="cursor-pointer bg-slate-800/60 hover:bg-slate-800 p-2.5 rounded-xl border border-sky-500/30 flex items-center justify-between transition">
        <div>
          <p class="text-[11px] font-medium text-sky-300">Sedang Dimasak</p>
          <p id="count-cooking" class="mono text-2xl font-black text-sky-400">0</p>
        </div>
        <span class="text-2xl opacity-60">🔥</span>
      </div>

      <div onclick="setFilter('READY')" class="cursor-pointer bg-slate-800/60 hover:bg-slate-800 p-2.5 rounded-xl border border-emerald-500/30 flex items-center justify-between transition">
        <div>
          <p class="text-[11px] font-medium text-emerald-300">Siap Saji</p>
          <p id="count-ready" class="mono text-2xl font-black text-emerald-400">0</p>
        </div>
        <span class="text-2xl opacity-60">🛎️</span>
      </div>

      <div onclick="setFilter('COMPLETED')" class="cursor-pointer bg-slate-800/60 hover:bg-slate-800 p-2.5 rounded-xl border border-slate-700 flex items-center justify-between transition">
        <div>
          <p class="text-[11px] font-medium text-slate-400">Selesai Hari Ini</p>
          <p id="count-completed" class="mono text-2xl font-black text-slate-300">0</p>
        </div>
        <span class="text-2xl opacity-60">✅</span>
      </div>
    </div>

    <!-- FILTER TABS -->
    <div class="max-w-7xl mx-auto mt-3 flex items-center gap-2 overflow-x-auto pb-1">
      <button onclick="setFilter('ALL')" id="tab-ALL" class="tab-btn px-3.5 py-1.5 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition">Semua Aktif</button>
      <button onclick="setFilter('NEED_COOK')" id="tab-NEED_COOK" class="tab-btn px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-400 hover:text-white transition">Perlu Dimasak</button>
      <button onclick="setFilter('PREPARING')" id="tab-PREPARING" class="tab-btn px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-400 hover:text-white transition">Sedang Dimasak</button>
      <button onclick="setFilter('READY')" id="tab-READY" class="tab-btn px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-400 hover:text-white transition">Siap Saji</button>
      <button onclick="setFilter('COMPLETED')" id="tab-COMPLETED" class="tab-btn px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-400 hover:text-white transition">Riwayat Selesai</button>
    </div>
  </header>

  <!-- MAIN ORDER CARDS GRID -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 mt-6">
    <!-- Empty State -->
    <div id="empty-state" class="hidden text-center py-20 bg-slate-900/40 rounded-3xl border border-slate-800">
      <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-800 flex items-center justify-center text-3xl">☕</div>
      <h3 class="text-lg font-bold text-white mb-1">Dapur Santai, Belum Ada Antrean</h3>
      <p class="text-sm text-slate-400 max-w-sm mx-auto">Pesanan lunas dari WhatsApp (QRIS / Kasir Tunai) akan otomatis muncul di sini dan membunyikan bel dapur.</p>
    </div>

    <!-- Cards Container -->
    <div id="orders-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <!-- Injected via JavaScript -->
    </div>
  </main>

  <script>
    let activeFilter = 'ALL';
    let soundEnabled = true;
    let knownOrderIds = new Set();
    let isInitialLoad = true;

    // Web Audio Chime generator
    function playKitchenBell() {
      if (!soundEnabled) return;
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const now = audioCtx.currentTime;
        
        // Tone 1: High crisp ding (880Hz)
        const osc1 = audioCtx.createOscillator();
        const gain1 = audioCtx.createGain();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(880, now);
        gain1.gain.setValueAtTime(0.3, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.8);
        osc1.connect(gain1);
        gain1.connect(audioCtx.destination);
        osc1.start(now);
        osc1.stop(now + 0.8);

        // Tone 2: Warm bell resonance (1320Hz)
        const osc2 = audioCtx.createOscillator();
        const gain2 = audioCtx.createGain();
        osc2.type = 'triangle';
        osc2.frequency.setValueAtTime(1320, now + 0.12);
        gain2.gain.setValueAtTime(0.25, now + 0.12);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 1.2);
        osc2.connect(gain2);
        gain2.connect(audioCtx.destination);
        osc2.start(now + 0.12);
        osc2.stop(now + 1.2);
      } catch (e) {
        console.log('Audio chime error:', e);
      }
    }

    function toggleSound() {
      soundEnabled = !soundEnabled;
      document.getElementById('sound-icon').textContent = soundEnabled ? '🔔' : '🔕';
      document.getElementById('sound-text').textContent = soundEnabled ? 'Suara: Aktif' : 'Suara: Mati';
      if (soundEnabled) playKitchenBell();
    }

    function updateClock() {
      const now = new Date();
      const h = String(now.getHours()).padStart(2, '0');
      const m = String(now.getMinutes()).padStart(2, '0');
      const s = String(now.getSeconds()).padStart(2, '0');
      const el = document.getElementById('live-clock');
      if (el) el.textContent = `${h}:${m}:${s} WIB`;
    }
    setInterval(updateClock, 1000);
    updateClock();

    function setFilter(filter) {
      activeFilter = filter;
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.className = 'tab-btn px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-400 hover:text-white transition';
      });
      const activeBtn = document.getElementById('tab-' + filter);
      if (activeBtn) {
        activeBtn.className = 'tab-btn px-3.5 py-1.5 text-xs font-bold rounded-lg bg-amber-500 text-slate-950 transition';
      }
      fetchOrders();
    }

    async function fetchOrders() {
      try {
        const res = await fetch('/api/kitchen/orders');
        if (!res.ok) return;
        const orders = await res.json();
        renderOrders(orders);
      } catch (err) {
        console.error('Failed to load kitchen orders:', err);
      }
    }

    function renderOrders(orders) {
      const grid = document.getElementById('orders-grid');
      const emptyState = document.getElementById('empty-state');

      // Calculate Counters
      let needCook = 0, cooking = 0, ready = 0, completed = 0;
      let hasNewOrder = false;

      orders.forEach(o => {
        if (o.state === 'PAID' || o.state === 'SENT_TO_KITCHEN') needCook++;
        else if (o.state === 'PREPARING') cooking++;
        else if (o.state === 'READY') ready++;
        else if (o.state === 'COMPLETED') completed++;

        if (!knownOrderIds.has(o.id) && (o.state === 'PAID' || o.state === 'SENT_TO_KITCHEN')) {
          if (!isInitialLoad) hasNewOrder = true;
          knownOrderIds.add(o.id);
        }
      });

      isInitialLoad = false;
      if (hasNewOrder) playKitchenBell();

      document.getElementById('count-need-cook').textContent = needCook;
      document.getElementById('count-cooking').textContent = cooking;
      document.getElementById('count-ready').textContent = ready;
      document.getElementById('count-completed').textContent = completed;

      // Filter orders based on active filter
      const filtered = orders.filter(o => {
        if (activeFilter === 'ALL') return o.state !== 'COMPLETED';
        if (activeFilter === 'NEED_COOK') return o.state === 'PAID' || o.state === 'SENT_TO_KITCHEN';
        if (activeFilter === 'PREPARING') return o.state === 'PREPARING';
        if (activeFilter === 'READY') return o.state === 'READY';
        if (activeFilter === 'COMPLETED') return o.state === 'COMPLETED';
        return true;
      });

      if (filtered.length === 0) {
        grid.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
      }
      emptyState.classList.add('hidden');

      grid.innerHTML = filtered.map(order => {
        const isNeedCook = order.state === 'PAID' || order.state === 'SENT_TO_KITCHEN';
        const isCooking = order.state === 'PREPARING';
        const isReady = order.state === 'READY';
        const isDone = order.state === 'COMPLETED';

        let borderColor = 'border-slate-800';
        let statusBadge = '<span class="px-2.5 py-1 text-xs font-bold rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30">⏳ Perlu Dimasak</span>';
        let actionBtn = `<button onclick="updateOrderStatus(${order.id}, 'PREPARING')" class="w-full py-2.5 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm shadow-lg shadow-amber-500/20 transition flex items-center justify-center gap-2"><span>🔥</span> Mulai Masak</button>`;

        if (isCooking) {
          borderColor = 'border-sky-500/40 bg-sky-950/20';
          statusBadge = '<span class="px-2.5 py-1 text-xs font-bold rounded-lg bg-sky-500/20 text-sky-300 border border-sky-500/30">🔥 Sedang Dimasak</span>';
          actionBtn = `<button onclick="updateOrderStatus(${order.id}, 'READY')" class="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition flex items-center justify-center gap-2"><span>🛎️</span> Selesai & Siap Saji</button>`;
        } else if (isReady) {
          borderColor = 'border-emerald-500/40 bg-emerald-950/20';
          statusBadge = '<span class="px-2.5 py-1 text-xs font-bold rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">🛎️ Siap Saji</span>';
          actionBtn = `<button onclick="updateOrderStatus(${order.id}, 'COMPLETED')" class="w-full py-2.5 px-4 rounded-xl bg-slate-700 hover:bg-slate-600 text-white font-semibold text-sm transition flex items-center justify-center gap-2"><span>✅</span> Tandai Selesai Diantar</button>`;
        } else if (isDone) {
          borderColor = 'border-slate-800 opacity-60';
          statusBadge = '<span class="px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-800 text-slate-400">Selesai</span>';
          actionBtn = `<div class="text-center text-xs text-slate-500 py-1 font-medium">Pesanan Selesai Dilayani</div>`;
        }

        // Time elapsed warning
        const elapsed = order.elapsed_minutes;
        let elapsedClass = 'text-slate-400';
        if (elapsed >= 20 && !isDone) elapsedClass = 'text-rose-400 font-bold';
        else if (elapsed >= 10 && !isDone) elapsedClass = 'text-amber-400 font-semibold';

        const itemsHtml = order.items.map(it => `
          <li class="flex items-start justify-between py-2 border-b border-slate-800/60 last:border-none group">
            <label class="flex items-start gap-2.5 cursor-pointer">
              <input type="checkbox" class="mt-1 w-4 h-4 rounded border-slate-700 bg-slate-800 text-amber-500 focus:ring-0">
              <span class="text-sm font-medium text-slate-200 group-hover:text-white">${it.name}</span>
            </label>
            <span class="mono text-sm font-black text-amber-400 px-2 py-0.5 bg-amber-500/10 rounded-md">x${it.quantity}</span>
          </li>
        `).join('');

        const notesHtml = order.notes && order.notes.trim() ? `
          <div class="mt-3 p-2.5 rounded-xl bg-amber-950/40 border border-amber-500/30 text-xs text-amber-200">
            <span class="font-bold text-amber-400">⚠️ Catatan:</span> ${order.notes}
          </div>
        ` : '';

        return `
          <div class="bg-slate-900 rounded-2xl border ${borderColor} p-4 shadow-xl flex flex-col justify-between transition hover:border-slate-700">
            <div>
              <!-- CARD HEADER -->
              <div class="flex items-start justify-between gap-2 mb-3">
                <div>
                  <div class="flex items-baseline gap-2">
                    <span class="mono text-3xl font-black text-white tracking-tight">${order.queue_number}</span>
                    <span class="text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">${order.table_number}</span>
                  </div>
                  <p class="text-xs ${elapsedClass} mt-0.5">Masuk: ${order.order_time} (${elapsed} mnt lalu)</p>
                </div>
                <div>${statusBadge}</div>
              </div>

              <!-- ITEMS LIST -->
              <div class="bg-slate-950/60 rounded-xl p-3 border border-slate-800/80 mb-3">
                <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Rincian Menu (${order.total_items_qty} porsi):</div>
                <ul class="divide-y divide-slate-800/40">${itemsHtml}</ul>
              </div>

              ${notesHtml}
            </div>

            <!-- ACTION FOOTER -->
            <div class="mt-4 pt-3 border-t border-slate-800">
              ${actionBtn}
            </div>
          </div>
        `;
      }).join('');
    }

    async function updateOrderStatus(orderId, newStatus) {
      try {
        const res = await fetch(`/api/kitchen/orders/${orderId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus })
        });
        if (res.ok) {
          fetchOrders();
        } else {
          const err = await res.json();
          alert('Gagal update status: ' + (err.detail || err.error || 'Unknown error'));
        }
      } catch (e) {
        alert('Kesalahan jaringan: ' + e.message);
      }
    }

    // Auto Poll every 4 seconds
    setInterval(fetchOrders, 4000);
    fetchOrders();
  </script>
</body>
</html>
"""
