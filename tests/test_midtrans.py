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
