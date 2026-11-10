import pytest
from fastapi.testclient import TestClient

from app import auth, db, osrm
from app.main import app

DEPOT = {"lat": 41.3111, "lon": 69.2797, "label": "Склад"}
STOPS = [
    {"lat": 41.285, "lon": 69.204, "label": "Чиланзар"},
    {"lat": 41.366, "lon": 69.288, "label": "Юнусабад"},
    {"lat": 41.327, "lon": 69.335, "label": "Мирзо-Улугбек"},
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db.set_path(str(tmp_path / "test.db"))
    auth._fails.clear()

    async def offline(_points):  # без сети: сработает расчёт по прямой
        raise RuntimeError("offline")

    monkeypatch.setattr(osrm, "table", offline)
    with TestClient(app) as c:
        yield c


def signup(client, email="a@shop.uz", company="Альфа"):
    r = client.post("/api/auth/register",
                    json={"company": company, "name": "Тест", "email": email, "password": "secret123"})
    assert r.status_code == 200


def test_settings_defaults_and_depot(client):
    signup(client)
    s = client.get("/api/company/settings").json()
    assert s == {"depot": None, "vehicles": 2, "service_min": 5, "return_to_depot": True, "start_time": "09:00"}

    s = client.patch("/api/company/settings", json={"depot": DEPOT}).json()
    assert s["depot"]["label"] == "Склад"
    assert client.get("/api/company/settings").json()["depot"]["lat"] == DEPOT["lat"]

    assert client.patch("/api/company/settings", json={"clear_depot": True}).json()["depot"] is None


def test_plan_lifecycle(client):
    signup(client)
    client.patch("/api/company/settings", json={"depot": DEPOT})

    plan = client.post("/api/plans", json={"plan_date": "2026-11-11"}).json()
    assert plan["status"] == "draft" and plan["stops"] == [] and plan["plan_date"] == "2026-11-11"

    plan = client.patch(f"/api/plans/{plan['id']}", json={"stops": STOPS}).json()
    assert plan["stops_count"] == 3

    built = client.post(f"/api/plans/{plan['id']}/build").json()
    assert built["status"] == "built"
    assert built["result"]["approximate"] is True
    assert built["result"]["depot"]["label"] == "Склад"
    assert sum(len(r["stops"]) for r in built["result"]["routes"]) == 3
    assert built["total_km"] > 0

    # После перезагрузки страницы всё на месте
    again = client.get(f"/api/plans/{plan['id']}").json()
    assert again["result"] == built["result"]

    # Правка точек сбрасывает построенный маршрут
    edited = client.patch(f"/api/plans/{plan['id']}", json={"stops": STOPS[:2]}).json()
    assert edited["status"] == "draft" and edited["result"] is None and edited["total_km"] == 0

    summaries = client.get("/api/plans").json()
    assert [p["id"] for p in summaries] == [plan["id"]]

    assert client.delete(f"/api/plans/{plan['id']}").status_code == 200
    assert client.get("/api/plans").json() == []


def test_build_needs_depot_and_stops(client):
    signup(client)
    plan = client.post("/api/plans", json={"stops": STOPS}).json()
    assert client.post(f"/api/plans/{plan['id']}/build").status_code == 422  # нет склада

    client.patch("/api/company/settings", json={"depot": DEPOT})
    empty = client.post("/api/plans", json={}).json()
    assert client.post(f"/api/plans/{empty['id']}/build").status_code == 422  # нет точек


def test_repeat_copies_stops_and_settings(client):
    signup(client)
    src = client.post("/api/plans", json={"plan_date": "2026-11-03", "stops": STOPS}).json()
    client.patch(f"/api/plans/{src['id']}", json={"vehicles": 4, "service_min": 10})

    copy = client.post("/api/plans", json={"plan_date": "2026-11-10", "from_plan_id": src["id"]}).json()
    assert copy["id"] != src["id"]
    assert [{k: x[k] for k in ("lat", "lon", "label")} for x in copy["stops"]] == STOPS and copy["vehicles"] == 4 and copy["service_min"] == 10
    assert copy["status"] == "draft" and copy["plan_date"] == "2026-11-10"

    # Список — сначала новые даты
    assert [p["plan_date"] for p in client.get("/api/plans").json()] == ["2026-11-10", "2026-11-03"]


def test_last_settings_become_defaults(client):
    signup(client)
    p = client.post("/api/plans", json={}).json()
    client.patch(f"/api/plans/{p['id']}", json={"vehicles": 3, "return_to_depot": False})
    fresh = client.post("/api/plans", json={}).json()
    assert fresh["vehicles"] == 3 and fresh["return_to_depot"] is False


def test_companies_do_not_see_each_other(client):
    signup(client, "a@shop.uz", "Альфа")
    client.patch("/api/company/settings", json={"depot": DEPOT})
    plan = client.post("/api/plans", json={"stops": STOPS}).json()
    client.post("/api/auth/logout")

    signup(client, "b@shop.uz", "Бета")
    assert client.get("/api/plans").json() == []
    assert client.get("/api/company/settings").json()["depot"] is None
    assert client.get(f"/api/plans/{plan['id']}").status_code == 404
    assert client.patch(f"/api/plans/{plan['id']}", json={"stops": []}).status_code == 404
    assert client.post(f"/api/plans/{plan['id']}/build").status_code == 404
    assert client.delete(f"/api/plans/{plan['id']}").status_code == 404
    assert client.post("/api/plans", json={"from_plan_id": plan["id"]}).status_code == 404
