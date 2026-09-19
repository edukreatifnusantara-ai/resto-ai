"""Meta WhatsApp Cloud API integration for the staging chatbot."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest
from urllib.request import urlopen


class WhatsAppConfigurationError(RuntimeError):
    """Raised when the Meta adapter is not configured."""


class WhatsAppDeliveryError(RuntimeError):
    """Raised when Meta rejects an outbound message."""


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 header.

    A configured app secret is mandatory. This prevents an accidental
    publicly reachable deployment from accepting unsigned commands.
    """
    app_secret = os.getenv("WHATSAPP_APP_SECRET")
    if not app_secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    supplied = signature_header.removeprefix("sha256=")
    expected = hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(supplied, expected)


def verify_subscription(mode: str | None, verify_token: str | None) -> bool:
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN")
    return bool(
        expected
        and mode == "subscribe"
        and verify_token
        and hmac.compare_digest(verify_token, expected)
    )


def extract_messages(payload: dict) -> list[dict[str, str]]:
    """Extract text messages from Meta's webhook envelope."""
    messages: list[dict[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                sender = str(message.get("from", "")).strip()
                message_id = str(message.get("id", "")).strip()
                message_type = str(message.get("type", "")).strip()
                body = ""
                if message_type == "text":
                    body = str(message.get("text", {}).get("body", "")).strip()
                if sender and message_id:
                    messages.append(
                        {
                            "sender": sender,
                            "message_id": message_id,
                            "message_type": message_type,
                            "body": body,
                        }
                    )
    return messages


class MetaWhatsAppClient:
    """Small standard-library client for Meta's Cloud API."""

    def __init__(self) -> None:
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.graph_api_version = os.getenv("WHATSAPP_GRAPH_API_VERSION")
        self.dry_run = _truthy("WHATSAPP_DRY_RUN")

    def send_text(self, recipient: str, body: str) -> dict:
        if self.dry_run:
            return {
                "dry_run": True,
                "to": recipient,
                "body": body,
            }
        missing = [
            name
            for name, value in (
                ("WHATSAPP_ACCESS_TOKEN", self.access_token),
                ("WHATSAPP_PHONE_NUMBER_ID", self.phone_number_id),
                ("WHATSAPP_GRAPH_API_VERSION", self.graph_api_version),
            )
            if not value
        ]
        if missing:
            raise WhatsAppConfigurationError(
                "Konfigurasi Meta WhatsApp belum lengkap: " + ", ".join(missing)
            )

        url = (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{self.phone_number_id}/messages"
        )
        payload = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": body},
            }
        ).encode("utf-8")
        request = URLRequest(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise WhatsAppDeliveryError("Pesan WhatsApp gagal dikirim ke Meta") from exc
