"""Распределение точек по машинам и порядок объезда (OR-Tools VRP).

Узел 0 — склад, узлы 1..n — точки доставки.
Цель: минимум суммарного времени + равномерная загрузка машин
(штраф за самый длинный маршрут, чтобы одна машина не везла всё).

Окна времени («с 10 до 12»): раньше начала окна приехать нельзя — машина ждёт;
опоздать можно, но за каждую секунду опоздания большой штраф. Так маршрут
строится всегда, даже если все окна выполнить невозможно, а опоздания видны в результате.
"""
from typing import List, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# (начало, конец) в секундах от начала смены; None — без ограничения
Window = Optional[Tuple[Optional[int], Optional[int]]]

LATE_PENALTY = 500  # секунда опоздания «стоит» как 500 секунд в дороге


def solve(
    durations: List[List[float]],
    vehicles: int,
    service_sec: int = 300,
    return_to_depot: bool = True,
    time_limit_sec: int = 0,
    windows: Optional[List[Window]] = None,
) -> List[List[int]]:
    """Возвращает список маршрутов: для каждой машины — индексы точек (без склада)."""
    n = len(durations)
    if n <= 1:
        return [[] for _ in range(vehicles)]
    vehicles = max(1, min(vehicles, n - 1))
    windows = windows or [None] * n
    has_windows = any(w for w in windows[1:])

    # Целые секунды; без возврата на склад дорога «назад» бесплатна.
    matrix = [
        [0 if (j == 0 and not return_to_depot) else int(round(durations[i][j])) for j in range(n)]
        for i in range(n)
    ]

    manager = pywrapcp.RoutingIndexManager(n, vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index, to_index):
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        return matrix[i][j] + (service_sec if i != 0 else 0)

    cb = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(cb)

    latest_open = max((w[0] or 0 for w in windows if w), default=0)
    horizon = sum(max(row) for row in matrix) + service_sec * n + latest_open + 1
    # Ожидание (slack) разрешено, только если есть окна — иначе поведение как раньше.
    routing.AddDimension(cb, horizon if has_windows else 0, horizon, True, "Time")
    time = routing.GetDimensionOrDie("Time")
    time.SetGlobalSpanCostCoefficient(100)

    if has_windows:
        for v in range(vehicles):
            time.CumulVar(routing.Start(v)).SetRange(0, 0)  # все выезжают к началу смены
        for node in range(1, n):
            w = windows[node]
            if not w:
                continue
            lo, hi = w
            idx = manager.NodeToIndex(node)
            if lo:
                time.CumulVar(idx).SetMin(min(lo, horizon))
            if hi is not None:
                time.SetCumulVarSoftUpperBound(idx, max(0, hi), LATE_PENALTY)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = time_limit_sec or min(10, 1 + n // 10)

    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise RuntimeError("Не удалось построить маршрут")

    routes = []
    for v in range(vehicles):
        idx = routing.Start(v)
        route = []
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node != 0:
                route.append(node)
            idx = solution.Value(routing.NextVar(idx))
        routes.append(route)
    return routes


def timeline(
    path: List[int], durations: List[List[float]], service_sec: int, windows: List[Window]
) -> Tuple[List[int], int]:
    """Время прибытия на каждую точку пути (сек от начала смены) и время окончания работы.

    path: [0, точки…] и, если машина возвращается, ещё 0 в конце.
    Приехал раньше окна — ждёт начала окна.
    """
    t, arrivals = 0, []
    for a, b in zip(path, path[1:]):
        t += (service_sec if a != 0 else 0) + durations[a][b]
        if b != 0:
            w = windows[b]
            if w and w[0]:
                t = max(t, w[0])
            arrivals.append(int(t))
    finish = t if path[-1] == 0 and len(path) > 1 else t + service_sec
    return arrivals, int(finish)
