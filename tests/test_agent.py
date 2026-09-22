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
    _execute_tool_call,
)
from app.models import MenuItem, OrderStatus, PaymentStatus


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

        # Confirm payment
        pay = customer_confirm_payment(db, cust_phone, order_id)
        assert pay["status"] == "success"

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
