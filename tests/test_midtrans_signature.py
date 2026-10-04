import pytest

from app.midtrans import verify_midtrans_signature


def test_verify_midtrans_signature_fails_closed_without_server_key(monkeypatch):
    """Empty MIDTRANS_SERVER_KEY must reject webhook payloads, not accept them."""
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "")
    assert verify_midtrans_signature("order-1", "200", "50000", "any-sig") is False


def test_verify_midtrans_signature_accepts_valid_sha512(monkeypatch):
    import hashlib

    server_key = "test-server-key"
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", server_key)
    order_id = "NDELIK-1-1727000000"
    status_code = "200"
    gross_amount = "35000.00"
    expected = hashlib.sha512(
        f"{order_id}{status_code}{gross_amount}{server_key}".encode("utf-8")
    ).hexdigest()
    assert verify_midtrans_signature(order_id, status_code, gross_amount, expected) is True


def test_verify_midtrans_signature_rejects_wrong_signature(monkeypatch):
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "test-server-key")
    assert (
        verify_midtrans_signature("order-1", "200", "50000.00", "tampered-signature")
        is False
    )


@pytest.mark.parametrize("server_key", ["", "   ", None])
def test_verify_midtrans_signature_never_accepts_blank_or_missing_key(
    monkeypatch, server_key
):
    if server_key is None:
        monkeypatch.delenv("MIDTRANS_SERVER_KEY", raising=False)
    else:
        monkeypatch.setenv("MIDTRANS_SERVER_KEY", server_key)
    assert verify_midtrans_signature("order-1", "200", "50000.00", "dummy-signature") is False
