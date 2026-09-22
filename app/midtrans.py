import base64
import hashlib
import hmac
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import qrcode
import requests

logger = logging.getLogger("resto-ai.midtrans")

QRIS_CACHE_DIR = Path("/home/edukreativ-vps/resto-ai/qris_cache")
QRIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_midtrans_config() -> dict[str, Any]:
    server_key = os.getenv("MIDTRANS_SERVER_KEY", "").strip()
    client_key = os.getenv("MIDTRANS_CLIENT_KEY", "").strip()
    is_prod = os.getenv("MIDTRANS_IS_PRODUCTION", "false").lower() in {"true", "1", "yes"}
    base_url = "https://api.midtrans.com/v2" if is_prod else "https://api.sandbox.midtrans.com/v2"
    return {
        "server_key": server_key,
        "client_key": client_key,
        "is_production": is_prod,
        "base_url": base_url,
    }


def generate_qris_image(qr_string: str, order_id: int) -> str:
    """Generate QR code PNG locally from raw QRIS string."""
    file_path = QRIS_CACHE_DIR / f"qris_order_{order_id}.png"
    img = qrcode.make(qr_string)
    img.save(str(file_path))
    return str(file_path)


def create_qris_charge(
    order_id: int,
    gross_amount: float,
    customer_name: str = "",
    customer_phone: str = "",
) -> dict[str, Any]:
    """Create a dynamic QRIS transaction via Midtrans Core API, or fallback to mock simulation."""
    config = get_midtrans_config()
    server_key = config["server_key"]
    order_midtrans_id = f"NDELIK-{order_id}-{int(time.time())}"
    amount_int = int(round(gross_amount))

    if server_key:
        try:
            url = f"{config['base_url']}/charge"
            auth_header = base64.b64encode(f"{server_key}:".encode()).decode()
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            payload = {
                "payment_type": "qris",
                "transaction_details": {
                    "order_id": order_midtrans_id,
                    "gross_amount": amount_int,
                },
                "qris": {
                    "acquirer": "gopay",
                },
                "customer_details": {
                    "first_name": customer_name or "Pelanggan",
                    "phone": customer_phone or "",
                },
            }

            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code in {200, 201}:
                data = resp.json()
                qr_string = data.get("qr_string", "")
                qr_url = None
                for action in data.get("actions", []):
                    if action.get("name") == "generate-qr-code":
                        qr_url = action.get("url")
                        break

                img_path = ""
                if qr_string:
                    img_path = generate_qris_image(qr_string, order_id)
                elif qr_url:
                    img_resp = requests.get(qr_url, timeout=10)
                    if img_resp.status_code == 200:
                        img_path = str(QRIS_CACHE_DIR / f"qris_order_{order_id}.png")
                        with open(img_path, "wb") as f:
                            f.write(img_resp.content)

                return {
                    "status": "success",
                    "mode": "live" if config["is_production"] else "sandbox",
                    "order_midtrans_id": order_midtrans_id,
                    "transaction_id": data.get("transaction_id"),
                    "gross_amount": amount_int,
                    "qr_string": qr_string,
                    "qr_image_path": img_path,
                    "qr_image_url": qr_url,
                }
            else:
                logger.error(f"Midtrans charge API error ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.exception(f"Midtrans request failed: {e}")

    # Fallback / Simulation mode when key is absent or request fails
    mock_qr_string = (
        f"00020101021226680016ID.WARUNGNDELIK011893600999000000000052045812"
        f"5303360540{amount_int:06d}5802ID5913WARUNG NDELIK6006KUDUS62070703A016304"
    )
    img_path = generate_qris_image(mock_qr_string, order_id)
    return {
        "status": "success",
        "mode": "simulation",
        "order_midtrans_id": order_midtrans_id,
        "transaction_id": f"sim-{uuid.uuid4().hex[:12]}",
        "gross_amount": amount_int,
        "qr_string": mock_qr_string,
        "qr_image_path": img_path,
        "qr_image_url": None,
    }


def verify_midtrans_signature(
    order_id: str,
    status_code: str,
    gross_amount: str,
    signature_key: str,
) -> bool:
    """Verify Midtrans webhook notification signature."""
    config = get_midtrans_config()
    server_key = config["server_key"]
    if not server_key:
        return True  # Simulation mode

    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    expected = hashlib.sha512(raw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, signature_key)


def send_whatsapp_bridge_message(to: str, message: str, image_path: str = "") -> bool:
    """Send outbound WhatsApp message via local bridge HTTP server."""
    try:
        bridge_port = int(os.getenv("BRIDGE_PORT", "18082"))
        payload: dict[str, Any] = {"to": to, "message": message}
        if image_path and os.path.exists(image_path):
            payload["image_path"] = image_path
        resp = requests.post(f"http://127.0.0.1:{bridge_port}/send", json=payload, timeout=5)
        return resp.status_code == 200
    except Exception as exc:
        logger.warning(f"Could not reach WhatsApp bridge: {exc}")
        return False

