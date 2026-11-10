from app.solver import solve, timeline
from tests.test_plans import DEPOT, STOPS, client, signup  # noqa: F401 — фикстура


def build_plan(client, stops=STOPS, vehicles=1):
    signup(client)
    client.patch("/api/company/settings", json={"depot": DEPOT})
    plan = client.post("/api/plans", json={"plan_date": "2026-11-11", "stops": stops}).json()
    client.patch(f"/api/plans/{plan['id']}", json={"vehicles": vehicles})
    return client.post(f"/api/plans/{plan['id']}/build").json()


def test_driver_page_and_statuses(client):
    built = build_plan(client)
    route = built["result"]["routes"][0]
    assert len(route["etas"]) == 3 and route["finish"]
    token = route["driver_token"]

    # Страница водителя открывается без входа
    client.post("/api/auth/logout")
    view = client.get(f"/api/driver/{token}").json()
    assert view["ready"] and view["company"] == "Альфа" and len(view["stops"]) == 3
    assert view["stops"][0]["eta"] == route["etas"][0]

    view = client.put(f"/api/driver/{token}/stops/1", json={"status": "done"}).json()
    assert view["stops"][1]["status"] == "done"
    view = client.put(f"/api/driver/{token}/stops/2", json={"status": "failed"}).json()
    view = client.put(f"/api/driver/{token}/stops/2", json={"status": None}).json()
    assert view["stops"][2]["status"] is None
    assert client.put(f"/api/driver/{token}/stops/9", json={"status": "done"}).status_code == 404
    assert client.get("/api/driver/nope").status_code == 404

    # Владелец видит отметку; ссылка водителя не меняется при пересчёте, отметка остаётся
    client.post("/api/auth/login", json={"email": "a@shop.uz", "password": "secret123"})
    plan = client.get(f"/api/plans/{built['id']}").json()
    assert list(plan["statuses"].values()) == ["done"]
    rebuilt = client.post(f"/api/plans/{built['id']}/build").json()
    assert rebuilt["result"]["routes"][0]["driver_token"] == token
    assert client.get(f"/api/plans/{built['id']}/statuses").json() == plan["statuses"]

    # Пока лист меняют — водителю «маршрут меняют»
    client.patch(f"/api/plans/{built['id']}", json={"service_min": 7})
    assert client.get(f"/api/driver/{token}").json()["ready"] is False


def test_time_window_respected(client):
    # Мирзо-Улугбек строго к 15:00, остальные без окна: должен ждать и приехать не раньше 15:00
    stops = [dict(s) for s in STOPS]
    stops[2].update(tw_from="15:00", tw_to="16:00", phone="+998 90 000 00 00", comment="домофон 12")
    built = build_plan(client, stops)
    route = built["result"]["routes"][0]
    i = [s["label"] for s in route["stops"]].index("Мирзо-Улугбек")
    assert "15:00" <= route["etas"][i] <= "16:00"
    assert route["stops"][i]["comment"] == "домофон 12"


def test_bad_window_rejected(client):
    signup(client)
    plan = client.post("/api/plans", json={"plan_date": "2026-11-11"}).json()
    bad = dict(STOPS[0], tw_from="14:00", tw_to="12:00")
    assert client.patch(f"/api/plans/{plan['id']}", json={"stops": [bad]}).status_code == 422
    empty = dict(STOPS[0], tw_from="", tw_to="")
    assert client.patch(f"/api/plans/{plan['id']}", json={"stops": [empty]}).status_code == 200


def test_solver_orders_by_windows():
    # Точки на прямой; окна заставляют ехать сначала к дальней (3), потом к ближней (1)
    dur = [[abs(i - j) * 60.0 for j in range(4)] for i in range(4)]
    windows = [None, (3600, 4000), None, (0, 300)]
    route = solve(dur, 1, service_sec=0, time_limit_sec=1, windows=windows)[0]
    assert route.index(3) < route.index(1)
    arrivals, finish = timeline([0] + route + [0], dur, 0, windows)
    assert arrivals[route.index(1)] >= 3600 and finish >= arrivals[-1]


def test_driver_link_for_vehicle_without_stops(client):
    built = build_plan(client, STOPS[:1], vehicles=1)
    token = built["result"]["routes"][0]["driver_token"]
    from app import db
    with db.connect() as con:  # ссылка на машину 2, которой в этом листе ничего не досталось
        con.execute("INSERT INTO driver_links (token, plan_id, vehicle) VALUES ('t2', ?, 2)", (built["id"],))
    view = client.get("/api/driver/t2").json()
    assert view["ready"] is False and view["empty"] is True
    assert client.get(f"/api/driver/{token}").json()["empty"] is False
