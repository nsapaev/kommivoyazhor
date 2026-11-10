from app.links import yandex_maps
from app.osrm import fallback_matrix
from app.solver import solve


def line_matrix(n):
    """Точки на прямой: время = расстояние между индексами × 60 сек."""
    return [[abs(i - j) * 60.0 for j in range(n)] for i in range(n)]


def test_single_vehicle_visits_all_in_order():
    routes = solve(line_matrix(6), vehicles=1, service_sec=0, time_limit_sec=1)
    assert len(routes) == 1
    assert sorted(routes[0]) == [1, 2, 3, 4, 5]
    assert routes[0] in ([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])


def test_work_split_between_vehicles():
    routes = solve(line_matrix(9), vehicles=2, service_sec=300, time_limit_sec=1)
    assert sorted(i for r in routes for i in r) == list(range(1, 9))
    assert all(r for r in routes), "обе машины должны работать"


def test_more_vehicles_than_stops():
    routes = solve(line_matrix(3), vehicles=5, service_sec=0, time_limit_sec=1)
    assert sorted(i for r in routes for i in r) == [1, 2]


def test_fallback_matrix_symmetric():
    dur, dist = fallback_matrix([(55.75, 37.62), (55.76, 37.64)])
    assert dist[0][0] == 0 and dist[0][1] == dist[1][0] > 0
    assert dur[0][1] > 0


def test_yandex_link():
    link = yandex_maps([(55.75, 37.62), (55.76, 37.64)])
    assert link == "https://yandex.ru/maps/?rtext=55.750000,37.620000~55.760000,37.640000&rtt=auto"


def _pts(n):
    return [(41.0 + i / 1000, 69.0) for i in range(n)]


def test_short_route_single_link():
    from app.links import yandex_maps_parts
    parts = yandex_maps_parts(_pts(20), returns_to_depot=False)
    assert len(parts) == 1 and parts[0].title == "Весь маршрут"


def test_long_route_split_into_chained_parts():
    from app.links import MAX_POINTS, yandex_maps_parts
    # склад + 38 точек + возврат на склад = 40 точек
    pts = _pts(39) + [_pts(1)[0]]
    parts = yandex_maps_parts(pts, returns_to_depot=True)
    assert [p.title for p in parts] == [
        "Часть 1: склад → точка 19",
        "Часть 2: точка 19 → точка 38",
        "Часть 3: точка 38 → склад",
    ]
    for p in parts:
        n = p.link.split("rtext=")[1].split("&")[0].count("~") + 1
        assert 2 <= n <= MAX_POINTS
    # каждая часть начинается там, где закончилась предыдущая
    for a, b in zip(parts, parts[1:]):
        assert a.link.split("rtext=")[1].split("&")[0].split("~")[-1] == b.link.split("rtext=")[1].split("&")[0].split("~")[0]
