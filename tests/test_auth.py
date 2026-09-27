"""Unit tests for Web UI Password Protection ('juara') and JUARA MANAGEMENT ENTERPRISE branding.
"""

from fastapi.testclient import TestClient
from app.main import app
from app.auth import AUTH_COOKIE_NAME, DEFAULT_WEB_PASSWORD

client_anon = TestClient(app)  # No auth headers
client_authed = TestClient(app, headers={"X-RESTO-API-TOKEN": "test-token"})


def test_unauthenticated_dashboard_redirects_to_login():
    response = client_anon.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert "/login?next=/dashboard" in response.headers["location"]


def test_unauthenticated_dapur_redirects_to_login():
    response = client_anon.get("/dapur", follow_redirects=False)
    assert response.status_code == 303
    assert "/login?next=/dapur" in response.headers["location"]


def test_login_screen_renders_branding():
    response = client_anon.get("/login")
    assert response.status_code == 200
    assert "JUARA MANAGEMENT ENTERPRISE" in response.text
    assert "Warung Ndelik" in response.text
    assert "Password Akses Sistem" in response.text


def test_login_with_wrong_password_fails():
    response = client_anon.post(
        "/login",
        data={"password": "wrong-password", "next": "/dashboard"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401
    assert "Password salah" in response.text
    assert "JUARA MANAGEMENT ENTERPRISE" in response.text


def test_login_with_correct_password_succeeds_and_sets_cookie():
    response = client_anon.post(
        "/login",
        data={"password": "juara", "next": "/dashboard"},
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert AUTH_COOKIE_NAME in response.headers.get("set-cookie", "")

    # Extract session cookie
    cookie_header = response.headers["set-cookie"]
    session_val = [c.split(";")[0] for c in cookie_header.split(",") if AUTH_COOKIE_NAME in c][0].split("=")[1]

    # Test accessing /dashboard with this session cookie
    dash_resp = client_anon.get("/dashboard", cookies={AUTH_COOKIE_NAME: session_val})
    assert dash_resp.status_code == 200
    assert "WARUNG NDELIK" in dash_resp.text
    assert "JUARA MANAGEMENT ENTERPRISE" in dash_resp.text


def test_logout_clears_cookie():
    response = client_anon.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert AUTH_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_internal_api_token_bypasses_login():
    response = client_authed.get("/dashboard")
    assert response.status_code == 200
