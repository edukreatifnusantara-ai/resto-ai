from datetime import datetime, timedelta
import json

from app.database import SessionLocal
from app.agent import (
    is_owner,
    owner_add_menu,
    owner_update_price,
    owner_set_discount,
    owner_set_menu_status,
    owner_get_report,
    owner_update_stock,
    customer_get_menu,
    customer_create_order,
    customer_check_order,
    customer_confirm_payment,
    customer_cancel_order,
    get_customer_session,
    run_ai_agent,
    cleanup_expired_sessions,
    _CUSTOMER_SESSIONS,
    _execute_tool_call,
)
from app.models import CustomerProfile, MenuItem, Order, OrderStatus, PaymentStatus


def test_is_owner():
    assert is_owner("628131344159") is True
    assert is_owner("+628131344159@s.whatsapp.net") is True
    assert is_owner("628999999999") is False


def test_owner_menu_management():
    db = SessionLocal()
    try:
        # 1. Add menu
        res_add = owner_add_menu(db, name="Bebek Goreng", price=35000, description="Bebek goreng kremes")
        assert res_add["status"] == "success"
        item_id = res_add["item"]["id"]

        # 2. Update price
        res_price = owner_update_price(db, name_or_id="Bebek Goreng", new_price=38000)
        assert res_price["status"] == "success"
        assert res_price["new_price"] == 38000.0

        # 3. Set discount
        res_disc = owner_set_discount(db, name_or_id="Bebek Goreng", discount_percent=15)
        assert res_disc["status"] == "success"
        assert res_disc["effective_price"] == 38000.0 * 0.85

        # 4. Set status
        res_stat = owner_set_menu_status(db, name_or_id="Bebek Goreng", is_active=False)
        assert res_stat["status"] == "success"

        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        assert item is not None
        assert item.is_active is False
    finally:
        db.close()


def test_owner_report_and_stock():
    db = SessionLocal()
    try:
        rep = owner_get_report(db)
        assert "total_orders_today" in rep
        assert "total_revenue_today" in rep

        res_stock = owner_update_stock(db, ingredient="telur", add_quantity=10)
        assert res_stock["status"] == "success"
    finally:
        db.close()


def test_customer_ordering_and_security_boundary():
    db = SessionLocal()
    try:
        # Customer menu should only show active items
        menu = customer_get_menu(db)
        names = [m["name"] for m in menu]
        assert "Bebek Goreng" not in names  # because deactivated earlier

        # Create order
        cust_phone = "628777111222"
        res_order = customer_create_order(
            db,
            customer_phone=cust_phone,
            items=[{"name": "Nasi Goreng", "quantity": 1}],
            notes="pedas manis",
        )
        assert res_order["status"] == "success"
        order_id = res_order["order_id"]

        # Check order
        chk = customer_check_order(db, cust_phone, order_id)
        assert chk["state"] == OrderStatus.DRAFT

        # A customer statement cannot mark payment as paid; verification is external.
        pay = customer_confirm_payment(db, cust_phone, order_id)
        assert pay["status"] == "pending_verification"
        paid_state = db.get(Order, order_id)
        assert paid_state is not None
        assert getattr(paid_state, "payment_state") == PaymentStatus.PENDING

        # Security boundary: non-owner calling owner tool via dispatcher
        sec_res = _execute_tool_call(
            db,
            sender=cust_phone,
            is_owner_role=False,
            func_name="owner_update_price",
            args={"name_or_id": "Nasi Goreng", "new_price": 1000},
        )
        assert "error" in sec_res
    finally:
        db.close()


def test_customer_order_stores_name_and_passes_it_to_qris(monkeypatch):
    import app.midtrans as midtrans

    db = SessionLocal()
    phone = "628777123456"
    captured = {}

    def fake_qris_charge(**kwargs):
        captured.update(kwargs)
        return {"qr_image_path": "", "mode": "simulation"}

    monkeypatch.setattr(midtrans, "create_qris_charge", fake_qris_charge)
    try:
        result = customer_create_order(
            db,
            customer_phone=phone,
            customer_name="Budi",
            items=[{"name": "Nasi Goreng Telur", "quantity": 1}],
            table_number="Meja 2",
        )

        assert result["status"] == "success"
        profile = db.query(CustomerProfile).filter_by(phone=phone).one()
        assert profile.name == "Budi"
        assert profile.last_table == "Meja 2"
        assert profile.last_order_type == "DINE_IN"
        assert captured["customer_name"] == "Budi"
    finally:
        _CUSTOMER_SESSIONS.pop(phone, None)
        db.close()


def test_customer_forgets_recent_dining_preference_after_six_hours():
    db = SessionLocal()
    phone = "628777654321"
    try:
        db.add(CustomerProfile(
            phone=phone,
            name="Sari",
            visit_count=3,
            last_table="Meja 3",
            last_order_type="DINE_IN",
            last_seen=datetime.utcnow() - timedelta(hours=7),
        ))
        db.commit()
        _CUSTOMER_SESSIONS.pop(phone, None)

        session = get_customer_session(phone, db)

        assert session.customer_name == "Sari"
        assert session.table_number is None
        assert session.order_type is None
        assert session.dining_preference_known is False
        profile = db.query(CustomerProfile).filter_by(phone=phone).one()
        assert profile.visit_count == 4
        assert profile.last_table is None
        assert profile.last_order_type is None
    finally:
        _CUSTOMER_SESSIONS.pop(phone, None)
        db.close()


def test_returning_customer_prompt_uses_one_honorific(monkeypatch):
    import urllib.request

    db = SessionLocal()
    phone = "628777999888"
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "Selamat datang kembali, Kak Budi.", "tool_calls": []}}]
            }).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OWNER_PHONE_NUMBERS", "628131344159")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    try:
        db.add(CustomerProfile(
            phone=phone,
            name="Kak Budi",
            visit_count=4,
            last_seen=datetime.utcnow(),
        ))
        db.commit()
        _CUSTOMER_SESSIONS.pop(phone, None)

        result = run_ai_agent(db, phone, "Halo")
        prompt = captured["payload"]["messages"][0]["content"]

        assert result["reply"] == "Selamat datang kembali, Kak Budi."
        assert "Nama Pelanggan: Kak Budi" in prompt
        assert "Kak Kak Budi" not in prompt
    finally:
        _CUSTOMER_SESSIONS.pop(phone, None)
        db.close()


def test_customer_message_remembers_table_before_order(monkeypatch):
    import urllib.request

    db = SessionLocal()
    phone = "628777456789"
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "Baik, saya catat.", "tool_calls": []}}]
            }).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OWNER_PHONE_NUMBERS", "628131344159")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    try:
        result = run_ai_agent(db, phone, "Atas nama Budi untuk makan di meja 4, ya")
        session = _CUSTOMER_SESSIONS[phone]
        profile = db.query(CustomerProfile).filter_by(phone=phone).one()
        prompt = captured["payload"]["messages"][0]["content"]

        assert result["reply"] == "Baik, saya catat."
        assert session.dining_preference_known is True
        assert session.table_number == "Meja 4"
        assert session.order_type == "DINE_IN"
        assert profile.name == "Budi"
        assert profile.last_table == "Meja 4"
        assert profile.last_order_type == "DINE_IN"
        assert "SUDAH DIKETAHUI (Meja 4)" in prompt
    finally:
        _CUSTOMER_SESSIONS.pop(phone, None)
        db.close()


def test_customer_order_uses_remembered_table_when_tool_omits_it(monkeypatch):
    import app.midtrans as midtrans

    db = SessionLocal()
    phone = "628777987654"
    monkeypatch.setattr(
        midtrans,
        "create_qris_charge",
        lambda **kwargs: {"qr_image_path": "", "mode": "simulation"},
    )
    try:
        session = get_customer_session(phone, db)
        session.table_number = "Meja 5"
        session.order_type = "DINE_IN"
        session.dining_preference_known = True

        result = _execute_tool_call(
            db,
            sender=phone,
            is_owner_role=False,
            func_name="customer_create_order",
            args={"items": [{"menu_name": "Nasi Goreng Telur", "quantity": 1}]},
        )

        assert result["status"] == "success"
        order = db.get(Order, result["order_id"])
        assert order is not None
        assert order.table_number == "Meja 5"
        assert order.order_type == "DINE_IN"
    finally:
        _CUSTOMER_SESSIONS.pop(phone, None)
        db.close()


def test_expired_customer_session_is_removed_automatically():
    db = SessionLocal()
    phone = "628777222333"
    try:
        session = get_customer_session(phone, db)
        session.history.append({"role": "user", "content": "pesanan lama"})
        session.last_activity = datetime.utcnow() - timedelta(hours=6, seconds=1)

        removed = cleanup_expired_sessions()

        assert removed >= 1
        assert phone not in _CUSTOMER_SESSIONS
    finally:
        _CUSTOMER_SESSIONS.pop(phone, None)
        db.close()
