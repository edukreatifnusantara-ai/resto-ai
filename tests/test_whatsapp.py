import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Order, WhatsAppEvent


client = TestClient(app)


def signed_payload(message_id="wamid.test-1", sender="628120000000", text="MENU"):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "id": message_id,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": f"sha256={signature}"}


def test_whatsapp_subscription_verification():
    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "challenge-123",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-123"


def test_whatsapp_rejects_bad_signature():
    body, _ = signed_payload()
    response = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    assert response.status_code == 401


def test_whatsapp_menu_event_is_idempotent():
    body, headers = signed_payload(message_id="wamid.menu-1", text="MENU")
    first = client.post("/webhooks/whatsapp", content=body, headers=headers)
    second = client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"status": "ok", "processed": 1, "duplicates": 0, "ignored": 0}
    assert second.status_code == 200
    assert second.json() == {"status": "ok", "processed": 0, "duplicates": 1, "ignored": 0}
    db = SessionLocal()
    try:
        assert db.query(WhatsAppEvent).filter_by(message_id="wamid.menu-1").count() == 1
    finally:
        db.close()


def test_whatsapp_customer_order_and_simulated_payment():
    sender = "628121111111"
    order_body, order_headers = signed_payload(
        message_id="wamid.order-1", sender=sender, text="PESAN 1 2"
    )
    order_response = client.post(
        "/webhooks/whatsapp", content=order_body, headers=order_headers
    )
    assert order_response.status_code == 200

    db = SessionLocal()
    try:
        order = db.query(Order).filter_by(customer_phone=sender).one()
        order_id = order.id
        assert order.state == "DRAFT"
    finally:
        db.close()

    payment_body, payment_headers = signed_payload(
        message_id="wamid.payment-1", sender=sender, text=f"BAYAR {order_id}"
    )
    payment_response = client.post(
        "/webhooks/whatsapp", content=payment_body, headers=payment_headers
    )
    assert payment_response.status_code == 200

    db = SessionLocal()
    try:
        order = db.get(Order, order_id)
        assert order.customer_phone == sender
        assert order.state == "PAID"
        assert order.payment_state == "SIMULATED_CONFIRMED"
    finally:
        db.close()


def test_whatsapp_cannot_read_another_customer_order():
    sender = "628122222222"
    owner_body, owner_headers = signed_payload(
        message_id="wamid.owner-order", sender=sender, text="PESAN 1"
    )
    assert client.post(
        "/webhooks/whatsapp", content=owner_body, headers=owner_headers
    ).status_code == 200
    db = SessionLocal()
    try:
        order_id = db.query(Order).filter_by(customer_phone=sender).one().id
    finally:
        db.close()

    other_body, other_headers = signed_payload(
        message_id="wamid.other-status", sender="628133333333", text=f"STATUS {order_id}"
    )
    response = client.post(
        "/webhooks/whatsapp", content=other_body, headers=other_headers
    )
    assert response.status_code == 200


def test_meta_client_builds_signed_api_request(monkeypatch):
    import app.whatsapp as whatsapp

    monkeypatch.setenv("WHATSAPP_DRY_RUN", "false")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v-test")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"messages":[{"id":"wamid.out"}]}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(whatsapp, "urlopen", fake_urlopen)
    result = whatsapp.MetaWhatsAppClient().send_text("628120000000", "Halo")

    assert result["messages"][0]["id"] == "wamid.out"
    assert captured["url"].endswith("/v-test/phone-id/messages")
    assert captured["headers"]["Authorization"] == "Bearer access-token"
    assert captured["body"]["to"] == "628120000000"
    assert captured["body"]["text"]["body"] == "Halo"


def test_webhook_delivery_retry_does_not_duplicate_order(monkeypatch):
    import app.whatsapp as whatsapp

    sender = "628144444444"
    body, headers = signed_payload(
        message_id="wamid.retry-order", sender=sender, text="PESAN 1"
    )

    def fail_delivery(self, recipient, reply):
        raise whatsapp.WhatsAppDeliveryError("temporary failure")

    monkeypatch.setattr(whatsapp.MetaWhatsAppClient, "send_text", fail_delivery)
    first = client.post("/webhooks/whatsapp", content=body, headers=headers)
    assert first.status_code == 502

    db = SessionLocal()
    try:
        event = db.query(WhatsAppEvent).filter_by(message_id="wamid.retry-order").one()
        order_count = db.query(Order).filter_by(source_message_id="wamid.retry-order").count()
        db.commit()
    finally:
        db.close()
    assert order_count == 1

    monkeypatch.setattr(whatsapp.MetaWhatsAppClient, "send_text", lambda self, recipient, reply: {"dry_run": True})
    second = client.post("/webhooks/whatsapp", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["processed"] == 1

    db = SessionLocal()
    try:
        assert db.query(Order).filter_by(source_message_id="wamid.retry-order").count() == 1
        assert db.query(WhatsAppEvent).filter_by(message_id="wamid.retry-order").one().processed_at is not None
    finally:
        db.close()


def test_unsigned_webhook_is_rejected_without_app_secret(monkeypatch):
    import app.whatsapp as whatsapp

    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    monkeypatch.setenv("WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS", "true")
    assert whatsapp.verify_signature(b"{}", None) is False
