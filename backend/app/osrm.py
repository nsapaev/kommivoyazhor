"""Клиент OSRM: матрица времени/расстояний и геометрия маршрута.

Если OSRM недоступен, считаем по прямой с поправкой на дороги —
так интерфейс продолжает работать, но ответ помечается предупреждением.
"""
import math
import os
from typing import List, Optional, Tuple

import httpx

OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
TIMEOUT = float(os.getenv("OSRM_TIMEOUT", "15"))

# Координаты везде храним как (lat, lon); OSRM ждёт lon,lat.
Point = Tuple[float, float]


def _coords(points: List[Point]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)


def _haversine_m(a: Point, b: Point) -> float:
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def fallback_matrix(points: List[Point]) -> Tuple[List[List[float]], List[List[float]]]:
    """Грубая оценка: расстояние по прямой × 1.3, средняя скорость 30 км/ч."""
    n = len(points)
    dist = [[_haversine_m(points[i], points[j]) * 1.3 for j in range(n)] for i in range(n)]
    dur = [[d / (30 / 3.6) for d in row] for row in dist]
    return dur, dist


async def table(points: List[Point]) -> Tuple[List[List[float]], List[List[float]]]:
    """Возвращает (durations_sec, distances_m) — квадратные матрицы n×n."""
    url = f"{OSRM_URL}/table/v1/driving/{_coords(points)}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params={"annotations": "duration,distance"})
        resp.raise_for_status()
        data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data.get("message", "OSRM error"))
    # Недостижимые пары OSRM отдаёт как null — заменяем большим числом.
    big = 10 ** 7
    dur = [[big if v is None else v for v in row] for row in data["durations"]]
    dist = [[big if v is None else v for v in row] for row in data["distances"]]
    return dur, dist


async def geometry(points: List[Point]) -> Optional[List[Point]]:
    """Линия маршрута по дорогам для отрисовки на карте. None — если не вышло."""
    if len(points) < 2:
        return None
    url = f"{OSRM_URL}/route/v1/driving/{_coords(points)}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params={"overview": "full", "geometries": "geojson"})
            resp.raise_for_status()
            data = resp.json()
        coords = data["routes"][0]["geometry"]["coordinates"]
        return [(lat, lon) for lon, lat in coords]
    except Exception:
        return None
