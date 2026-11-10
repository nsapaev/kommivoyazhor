import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import app


@pytest.fixture()
def client(tmp_path):
    db.set_path(str(tmp_path / "test.db"))
    auth._fails.clear()
    with TestClient(app) as c:
        yield c


def register(client, email="owner@shop.uz", password="secret123", company="Доставка Плюс"):
    return client.post(
        "/api/auth/register",
        json={"company": company, "name": "Алишер", "email": email, "password": password},
    )


def test_register_logs_in_and_me_works(client):
    r = register(client)
    assert r.status_code == 200
    assert r.json()["company_name"] == "Доставка Плюс"
    assert "session" in r.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@shop.uz"


def test_password_is_not_stored_in_plain_text(client):
    register(client)
    with db.connect() as con:
        stored = con.execute("SELECT password_hash FROM users").fetchone()[0]
    assert "secret123" not in stored and stored.startswith("scrypt$")


def test_duplicate_email_rejected(client):
    register(client)
    r = register(client, email="OWNER@shop.uz ")
    assert r.status_code == 409


def test_short_password_and_bad_email_rejected(client):
    assert register(client, password="123").status_code == 422
    assert register(client, email="not-an-email").status_code == 422


def test_login_logout(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    assert client.post("/api/auth/login", json={"email": "owner@shop.uz", "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": " Owner@Shop.uz", "password": "secret123"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_old_session_dead_after_logout(client):
    register(client)
    token = client.cookies.get("session")
    client.post("/api/auth/logout")
    client.cookies.set("session", token)
    assert client.get("/api/auth/me").status_code == 401


def test_api_requires_login(client):
    assert client.get("/api/plans").status_code == 401
    assert client.post("/api/plans", json={}).status_code == 401
    assert client.get("/api/company/settings").status_code == 401
    assert client.get("/api/geocode", params={"q": "Чиланзар"}).status_code == 401


def test_brute_force_blocked(client):
    register(client)
    client.post("/api/auth/logout")
    for _ in range(auth.MAX_FAILS):
        client.post("/api/auth/login", json={"email": "owner@shop.uz", "password": "nope-nope"})
    r = client.post("/api/auth/login", json={"email": "owner@shop.uz", "password": "secret123"})
    assert r.status_code == 429
