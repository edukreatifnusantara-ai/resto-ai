from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Order, OrderStatus, PaymentStatus, MenuItem
from app.midtrans import (
    create_qris_charge,
    verify_midtrans_signature,
)
from app.agent import customer_request_qris, customer_create_order

client = TestClient(app, headers={"X-RESTO-API-TOKEN": "test-token"})


def test_create_qris_charge_simulation():
    res = create_qris_charge(order_id=999, gross_amount=50000.0, customer_name="Budi", customer_phone="628111111111")
    assert res["status"] == "success"
    assert res["gross_amount"] == 50000
    assert "NDELIK-999-" in res["order_midtrans_id"]
    assert res["qr_image_path"] != ""
    assert res["mode"] == "simulation"


def test_midtrans_signature_verification():
    # In simulation mode (empty server key), signature verification passes
    assert verify_midtrans_signature("order-1", "200", "50000", "any-sig") is True


def test_midtrans_webhook_settlement_and_failure():
    db = SessionLocal()
    try:
        # Create a sample order in DRAFT status
        order = Order(
            items_json={"items": [{"name": "Nasi Bebek", "quantity": 1, "price": 35000}]},
            total=35000.0,
            state=OrderStatus.DRAFT,
            payment_state=PaymentStatus.PENDING,
            customer_phone="628199988877",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        order_id = order.id

        # Webhook call for settlement
        midtrans_payload = {
            "order_id": f"NDELIK-{order_id}-1727000000",
            "status_code": "200",
            "gross_amount": "35000.00",
            "signature_key": "dummy-signature",
            "transaction_status": "settlement",
            "fraud_status": "accept",
        }
        resp = client.post("/webhooks/midtrans", json=midtrans_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["order_id"] == order_id
        assert data["order_state"] == OrderStatus.PAID
        assert data["payment_state"] == PaymentStatus.SIMULATED_CONFIRMED

        # Check DB directly
        db.refresh(order)
        assert str(order.state) == OrderStatus.PAID
        assert str(order.payment_state) == PaymentStatus.SIMULATED_CONFIRMED

        # Test failure/expire webhook for a new order
        failed_order = Order(
            items_json={"items": []},
            total=20000.0,
            state=OrderStatus.DRAFT,
            payment_state=PaymentStatus.PENDING,
            customer_phone="628199988877",
        )
        db.add(failed_order)
        db.commit()
        db.refresh(failed_order)
        failed_id = int(getattr(failed_order, "id"))

        resp_failed = client.post("/webhooks/midtrans", json={
            "order_id": f"NDELIK-{failed_id}-1727000000",
            "status_code": "200",
            "gross_amount": "20000.00",
            "signature_key": "dummy-signature",
            "transaction_status": "expire",
        })
        assert resp_failed.status_code == 200
        db.refresh(failed_order)
        assert str(failed_order.payment_state) == PaymentStatus.FAILED
    finally:
        db.close()


def test_customer_request_qris_tool():
    db = SessionLocal()
    try:
        # Create an order
        order = Order(
            items_json={"items": []},
            total=45000.0,
            state=OrderStatus.DRAFT,
            payment_state=PaymentStatus.PENDING,
            customer_phone="628123456789",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        oid = int(getattr(order, "id"))

        res = customer_request_qris(db, "628123456789", oid)
        assert res["status"] == "success"
        assert res["order_id"] == oid
        assert res["qr_image_path"] != ""
        assert "45.000" in res["formatted_total"]
    finally:
        db.close()


def test_cash_order_creation_and_owner_confirmation():
    db = SessionLocal()
    try:
        from app.agent import owner_confirm_cash_payment
        # 1. Customer creates CASH order on Meja 3
        items = [{"menu_name": "Nasi Goreng Telur", "quantity": 2}]
        order_res = customer_create_order(
            db,
            customer_phone="628129999000",
            items=items,
            table_number="Meja 3",
            payment_method="CASH",
        )
        assert order_res["status"] == "success"
        assert order_res["payment_method"] == "CASH"
        assert order_res["table_number"] == "Meja 3"
        assert order_res["queue_number"] is None
        assert order_res["qr_image_path"] == ""
        oid = int(order_res["order_id"])

        # 2. Check Order state before payment
        order = db.query(Order).get(oid)
        assert order is not None
        assert str(order.payment_state) == PaymentStatus.PENDING
        assert order.queue_number is None

        # 3. Owner confirms CASH payment
        confirm_res = owner_confirm_cash_payment(db, oid)
        assert confirm_res["status"] == "success"
        assert confirm_res["queue_number"] is not None
        assert "A-" in confirm_res["queue_number"]

        # 4. Check Order state after payment
        db.refresh(order)
        assert order is not None
        assert str(order.payment_state) == PaymentStatus.SIMULATED_CONFIRMED
        assert str(order.state) == OrderStatus.PAID
        assert order.queue_number == confirm_res["queue_number"]
    finally:
        db.close()


def test_table_availability_and_reservation_flow():
    db = SessionLocal()
    try:
        from app.agent import customer_check_available_tables, customer_create_reservation
        # 1. Check available tables
        avail_res = customer_check_available_tables(db, reservation_date="2026-09-25")
        assert avail_res["status"] == "success"
        assert avail_res["available_count"] >= 10
        assert any(t["table_number"] == "Meja 1" for t in avail_res["available_tables"])

        # 2. An unpaid order cannot reserve a table.
        unpaid = customer_create_order(
            db,
            customer_phone="628133344455",
            items=[{"name": "Nasi Goreng", "quantity": 1}],
        )
        blocked = customer_create_reservation(
            db,
            customer_phone="628133344455",
            customer_name="Pak Ahmad",
            table_number="Meja 1",
            reservation_date="2026-09-25",
            reservation_time="19:00",
            guest_count=4,
            payment_order_id=unpaid["order_id"],
        )
        assert "belum lunas" in blocked["error"]

        # 3. The same reservation is confirmed only after the linked order is paid.
        paid_order = db.get(Order, unpaid["order_id"])
        assert paid_order is not None
        setattr(paid_order, "payment_state", PaymentStatus.SIMULATED_CONFIRMED)
        setattr(paid_order, "state", OrderStatus.PAID)
        db.commit()
        resv_res = customer_create_reservation(
            db,
            customer_phone="628133344455",
            customer_name="Pak Ahmad",
            table_number="Meja 1",
            reservation_date="2026-09-25",
            reservation_time="19:00",
            guest_count=4,
            notes="Dekat jendela jika bisa",
            payment_order_id=unpaid["order_id"],
        )
        assert resv_res["status"] == "success"
        assert resv_res["table_number"] == "Meja 1"
        assert resv_res["customer_name"] == "Pak Ahmad"

        # 4. A second paid customer still cannot take the same table and date.
        second_order = customer_create_order(
            db,
            customer_phone="628188899900",
            items=[{"name": "Nasi Goreng", "quantity": 1}],
        )
        second_paid_order = db.get(Order, second_order["order_id"])
        assert second_paid_order is not None
        setattr(second_paid_order, "payment_state", PaymentStatus.SIMULATED_CONFIRMED)
        setattr(second_paid_order, "state", OrderStatus.PAID)
        db.commit()
        resv_conflict = customer_create_reservation(
            db,
            customer_phone="628188899900",
            customer_name="Ibu Siti",
            table_number="Meja 1",
            reservation_date="2026-09-25",
            reservation_time="19:00",
            guest_count=2,
            payment_order_id=second_order["order_id"],
        )
        assert "error" in resv_conflict
        assert "sudah direservasi" in resv_conflict["error"]

        # 4. Check available tables again -> Meja 1 should now be booked
        avail_res_after = customer_check_available_tables(db, reservation_date="2026-09-25")
        assert any(t["table_number"] == "Meja 1" for t in avail_res_after["booked_tables"])
    finally:
        db.close()

