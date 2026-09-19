from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Stock


client = TestClient(app, headers={"X-RESTO-API-TOKEN": "test-token"})


def test_list_menu():
    response = client.get("/menu")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5
    assert "Nasi Goreng" in [item["name"] for item in data]


def test_add_menu_item_owner():
    response = client.post(
        "/menu",
        json={"name": "Bakso", "price": 15000, "description": "Bakso sapi special"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Bakso"


def create_order(quantity=1):
    response = client.post(
        "/orders/", json={"items": [{"menu_item_id": 1, "quantity": quantity}]}
    )
    assert response.status_code == 200, response.text
    order_id = response.json()["id"]
    assert client.post(f"/orders/{order_id}/request-payment").status_code == 200
    return order_id


def pay(order_id):
    response = client.post(f"/orders/{order_id}/pay")
    assert response.status_code == 200, response.text


def test_create_order_and_total():
    response = client.post("/orders/", json={"items": [{"menu_item_id": 1, "quantity": 2}]})
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "DRAFT"
    assert data["payment_state"] == "PENDING"
    assert data["total"] == 50000.0
    assert client.post(f"/orders/{data['id']}/request-payment").json()["state"] == "PENDING_PAYMENT"


def test_create_order_invalid_item():
    response = client.post("/orders/", json={"items": [{"menu_item_id": 999, "quantity": 1}]})
    assert response.status_code == 400


def test_nonfinite_price_rejected():
    response = client.post(
        "/menu", json={"name": "Menu Infinity", "price": "Infinity", "description": "dummy"}
    )
    assert response.status_code == 422


def test_order_input_validation():
    assert client.post("/orders/", json={"items": []}).status_code == 422
    assert client.post("/orders/", json={"items": [{"menu_item_id": 1, "quantity": 0}]}).status_code == 422
    assert client.post("/orders/", json={"items": [{"menu_item_id": 1, "quantity": -1}]}).status_code == 422


def test_simulated_payment_and_idempotency():
    order_id = create_order()
    pay(order_id)
    response = client.post(f"/orders/{order_id}/pay")
    assert response.status_code == 200
    assert response.json()["message"] == "Payment already confirmed"


def test_simulate_payment_no_order():
    assert client.post("/orders/9999/pay").status_code == 404


def test_simulated_payment_failed():
    order_id = create_order()
    response = client.post(f"/orders/{order_id}/payment-failed")
    assert response.status_code == 200
    assert response.json()["payment_state"] == "FAILED"
    assert client.post(f"/orders/{order_id}/pay").status_code == 400


def test_send_to_kitchen_requires_payment():
    order_id = create_order()
    assert client.post(f"/orders/{order_id}/send-to-kitchen").status_code == 400


def test_kitchen_transitions_and_stock():
    order_id = create_order()
    pay(order_id)
    response = client.post(f"/orders/{order_id}/send-to-kitchen")
    assert response.status_code == 200
    assert response.json()["state"] == "SENT_TO_KITCHEN"
    assert client.post(f"/orders/{order_id}/send-to-kitchen").status_code == 409
    assert client.post(f"/orders/{order_id}/prepare").json()["state"] == "PREPARING"
    assert client.post(f"/orders/{order_id}/ready").json()["state"] == "READY"
    assert client.post(f"/orders/{order_id}/complete").json()["state"] == "COMPLETED"

    stock = client.get("/reports/stock").json()["stocks"]
    nasi = next(item for item in stock if item["ingredient"] == "nasi")
    assert nasi["quantity"] < 50.0


def test_insufficient_stock_does_not_advance_order():
    db = SessionLocal()
    stock_item = db.query(Stock).filter(Stock.ingredient == "nasi").first()
    stock_item.quantity = 0.01
    db.commit()
    db.close()

    order_id = create_order()
    pay(order_id)
    response = client.post(f"/orders/{order_id}/send-to-kitchen")
    assert response.status_code == 400
    assert client.get(f"/orders/{order_id}").json()["state"] == "PAID"


def test_runtime_token_required():
    assert TestClient(app).get("/menu").status_code == 401


def test_menu_without_recipe_rejected():
    response = client.post(
        "/menu", json={"name": "Menu Tanpa Resep", "price": 10000, "description": "dummy"}
    )
    assert response.status_code == 200
    order = client.post("/orders/", json={"items": [{"menu_item_id": response.json()["id"]}]})
    assert order.status_code == 400


def test_paid_order_cannot_be_cancelled():
    order_id = create_order()
    pay(order_id)
    assert client.post(f"/orders/{order_id}/cancel").status_code == 409


def test_reports_are_available():
    assert client.get("/reports/sales").status_code == 200
    finance = client.get("/reports/finance")
    assert finance.status_code == 200
    assert finance.json()["status"].startswith("SIMULASI")
