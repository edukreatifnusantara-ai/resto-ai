from fastapi.testclient import TestClient
from app.database import SessionLocal, assign_order_queue
from app.main import app
from app.models import Order, OrderStatus, PaymentStatus
from app.kitchen import (
    format_kitchen_ticket,
    get_kitchen_active_orders,
    update_kitchen_order_status,
)

client = TestClient(app, headers={"X-RESTO-API-TOKEN": "test-token"})


def test_kitchen_kds_html_endpoint():
    response = client.get("/dapur")
    assert response.status_code == 200
    assert "Layar Dapur (KDS)" in response.text
    assert "Warung Ndelik" in response.text
    assert "Perlu Dimasak" in response.text

    # Alias /kds
    response_kds = client.get("/kds")
    assert response_kds.status_code == 200


def test_kitchen_active_orders_api_and_transitions():
    db = SessionLocal()
    try:
        # Create a test paid order
        order = Order(
            items_json={
                "items": [
                    {"name": "Nasi Bebek Bumbu Hitam", "quantity": 2, "price": 25000.0},
                    {"name": "Es Teh Jumbo", "quantity": 2, "price": 5000.0},
                ],
                "notes": "Bebek paha semua, sambal banyak",
            },
            total=60000.0,
            table_number="Meja 5",
            order_type="DINE_IN",
            payment_method="QRIS",
            state=OrderStatus.PAID,
            payment_state=PaymentStatus.SIMULATED_CONFIRMED,
            customer_phone="628123456789",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        assign_order_queue(db, order)
        db.commit()
        db.refresh(order)

        order_id = int(getattr(order, "id"))
        q_num = str(getattr(order, "queue_number"))

        # 1. Test format_kitchen_ticket
        ticket = format_kitchen_ticket(order)
        assert "TIKET ORDERAN MASUK — DAPUR" in ticket
        assert q_num in ticket
        assert "Meja 5" in ticket
        assert "Nasi Bebek Bumbu Hitam" in ticket
        assert "x*2*" in ticket
        assert "Bebek paha semua, sambal banyak" in ticket

        # 2. Test GET /api/kitchen/orders
        response = client.get("/api/kitchen/orders")
        assert response.status_code == 200
        orders_list = response.json()
        target = next((o for o in orders_list if o["id"] == order_id), None)
        assert target is not None
        assert target["table_number"] == "Meja 5"
        assert target["queue_number"] == q_num
        assert len(target["items"]) == 2

        # 3. Test POST /api/kitchen/orders/{id}/status -> PREPARING
        res_prep = client.post(f"/api/kitchen/orders/{order_id}/status", json={"status": "PREPARING"})
        assert res_prep.status_code == 200
        assert res_prep.json()["current_state"] == "PREPARING"

        # 4. Test POST /api/kitchen/orders/{id}/status -> READY
        res_ready = client.post(f"/api/kitchen/orders/{order_id}/status", json={"status": "READY"})
        assert res_ready.status_code == 200
        assert res_ready.json()["current_state"] == "READY"

        # 5. Test POST /api/kitchen/orders/{id}/status -> COMPLETED
        res_done = client.post(f"/api/kitchen/orders/{order_id}/status", json={"status": "COMPLETED"})
        assert res_done.status_code == 200
        assert res_done.json()["current_state"] == "COMPLETED"

    finally:
        db.close()
