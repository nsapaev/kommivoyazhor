"""Построение маршрутов: матрица OSRM → OR-Tools → ссылки, время прибытия и линии для карты."""
import asyncio
import logging
import os
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from . import links, osrm
from .links import LinkPart
from .solver import Window, solve, timeline

log = logging.getLogger("routes")

MAX_STOPS = int(os.getenv("MAX_STOPS", "100"))
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class Place(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=40)
    comment: str = Field(default="", max_length=300)
    tw_from: Optional[str] = Field(default=None, pattern=HHMM)  # окно доставки «с»
    tw_to: Optional[str] = Field(default=None, pattern=HHMM)  # окно доставки «до»

    @field_validator("tw_from", "tw_to", mode="before")
    @classmethod
    def _empty_time(cls, v):
        return v or None

    @model_validator(mode="after")
    def _window_order(self):
        if self.tw_from and self.tw_to and self.tw_from > self.tw_to:
            raise ValueError("Время «с» позже, чем «до»")
        return self


class Route(BaseModel):
    vehicle: int
    stops: List[Place]
    distance_km: float
    duration_min: int
    link: str  # весь маршрут одной ссылкой (если точек больше лимита — только начало)
    parts: List[LinkPart] = []  # ссылки по частям; в старых расчётах может не быть
    geometry: Optional[List[List[float]]] = None
    etas: List[str] = []  # «≈ ЧЧ:ММ» прибытия на каждую точку
    finish: Optional[str] = None  # когда машина закончит (вернётся на склад)
    driver_token: Optional[str] = None  # ссылка для водителя /d/<token>


class BuildResult(BaseModel):
    depot: Place  # снимок склада на момент расчёта — история не «поедет», если склад сменят
    routes: List[Route]
    approximate: bool  # True — OSRM недоступен, расчёт по прямой
    start_time: str = "09:00"


class BuildError(Exception):
    pass


def _windows(places: List[Place], start_min: int) -> List[Window]:
    """Окна в секундах от начала смены."""
    out: List[Window] = [None]
    for p in places[1:]:
        if not (p.tw_from or p.tw_to):
            out.append(None)
            continue
        lo = max(0, to_min(p.tw_from) - start_min) * 60 if p.tw_from else None
        hi = (to_min(p.tw_to) - start_min) * 60 if p.tw_to else None
        out.append((lo, hi))
    return out


async def build(
    depot: Place, stops: List[Place], vehicles: int, service_min: int, return_to_depot: bool,
    start_time: str = "09:00",
) -> BuildResult:
    if not stops:
        raise BuildError("Добавьте хотя бы одну точку")
    if len(stops) > MAX_STOPS:
        raise BuildError(f"Не больше {MAX_STOPS} точек за раз")

    places = [depot] + stops
    points = [(p.lat, p.lon) for p in places]

    approximate = False
    try:
        durations, distances = await osrm.table(points)
    except Exception as e:
        log.warning("OSRM недоступен (%s), считаю по прямой", e)
        durations, distances = osrm.fallback_matrix(points)
        approximate = True

    service_sec = service_min * 60
    start_min = to_min(start_time)
    windows = _windows(places, start_min)
    try:
        order = await asyncio.to_thread(solve, durations, vehicles, service_sec, return_to_depot, 0, windows)
    except RuntimeError as e:
        raise BuildError(str(e))

    routes = []
    for nodes in order:
        if not nodes:
            continue
        path = [0] + nodes + ([0] if return_to_depot else [])
        dist = sum(distances[a][b] for a, b in zip(path, path[1:]))
        arrivals, finish = timeline(path, durations, service_sec, windows)
        route_points = [points[i] for i in path]
        routes.append(
            Route(
                vehicle=len(routes) + 1,  # без пропусков: если машине не досталось точек — «Машина 1, 2», а не «1, 3»
                stops=[places[i] for i in nodes],
                distance_km=round(dist / 1000, 1),
                duration_min=round(finish / 60),
                link=links.yandex_maps(route_points[: links.MAX_POINTS]),
                parts=links.yandex_maps_parts(route_points, return_to_depot),
                etas=[to_hhmm(start_min + round(t / 60)) for t in arrivals],
                finish=to_hhmm(start_min + round(finish / 60)),
            )
        )

    if not approximate:
        geoms = await asyncio.gather(
            *(osrm.geometry([points[0]] + [(s.lat, s.lon) for s in r.stops] + ([points[0]] if return_to_depot else []))
              for r in routes)
        )
        for r, g in zip(routes, geoms):
            r.geometry = [list(p) for p in g] if g else None

    return BuildResult(depot=depot, routes=routes, approximate=approximate, start_time=start_time)
