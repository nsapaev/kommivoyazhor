"""Страница водителя: открывается по секретной ссылке, без входа и регистрации.

Водитель видит свои точки по порядку и отмечает «Доставлено» / «Не получилось»,
владелец видит эти отметки в своём маршрутном листе.
"""
import secrets
import sqlite3
from typing import Dict, Iterable, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db
from .routing import BuildResult, Place

router = APIRouter(prefix="/api/driver")

Status = Literal["done", "failed"]


def stop_key(p: Place) -> str:
    return f"{p.lat:.6f},{p.lon:.6f}"


def ensure_tokens(con: sqlite3.Connection, plan_id: int, vehicles: Iterable[int]) -> Dict[int, str]:
    """Ссылка на машину создаётся один раз и переживает пересчёты — водителю не нужно слать новую."""
    have = {r["vehicle"]: r["token"] for r in con.execute(
        "SELECT vehicle, token FROM driver_links WHERE plan_id = ?", (plan_id,))}
    for v in vehicles:
        if v not in have:
            have[v] = secrets.token_urlsafe(12)
            con.execute("INSERT INTO driver_links (token, plan_id, vehicle) VALUES (?, ?, ?)", (have[v], plan_id, v))
    return have


def load_statuses(con: sqlite3.Connection, plan_id: int) -> Dict[str, str]:
    return {r["stop_key"]: r["status"] for r in con.execute(
        "SELECT stop_key, status FROM stop_statuses WHERE plan_id = ?", (plan_id,))}


class DriverStop(Place):
    eta: Optional[str] = None
    status: Optional[Status] = None


class DriverView(BaseModel):
    company: str
    plan_date: str
    vehicle: int
    ready: bool  # False — маршрут сейчас меняют, загляните позже
    empty: bool = False  # маршрут построен, но этой машине точек не досталось
    depot: Optional[Place] = None
    return_to_depot: bool = True
    start_time: Optional[str] = None
    finish: Optional[str] = None
    stops: List[DriverStop] = []


def _view(con: sqlite3.Connection, token: str) -> tuple[DriverView, int]:
    row = con.execute(
        """SELECT l.vehicle, p.id AS plan_id, p.plan_date, p.result_json, p.return_to_depot, c.name AS company
             FROM driver_links l JOIN plans p ON p.id = l.plan_id JOIN companies c ON c.id = p.company_id
            WHERE l.token = ?""",
        (token,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Ссылка не найдена — попросите у диспетчера новую")
    view = DriverView(company=row["company"], plan_date=row["plan_date"], vehicle=row["vehicle"], ready=False)
    if not row["result_json"]:
        return view, row["plan_id"]
    result = BuildResult.model_validate_json(row["result_json"])
    route = next((r for r in result.routes if r.vehicle == row["vehicle"]), None)
    if route is None:
        view.empty = True
        return view, row["plan_id"]
    statuses = load_statuses(con, row["plan_id"])
    view.ready = True
    view.depot = result.depot
    view.return_to_depot = bool(row["return_to_depot"])
    view.start_time = result.start_time
    view.finish = route.finish
    view.stops = [
        DriverStop(**s.model_dump(), eta=route.etas[i] if i < len(route.etas) else None,
                   status=statuses.get(stop_key(s)))
        for i, s in enumerate(route.stops)
    ]
    return view, row["plan_id"]


@router.get("/{token}", response_model=DriverView)
def get_route(token: str):
    with db.connect() as con:
        return _view(con, token)[0]


class StatusIn(BaseModel):
    status: Optional[Status] = None  # None — снять отметку


@router.put("/{token}/stops/{index}", response_model=DriverView)
def set_status(token: str, index: int, data: StatusIn):
    with db.connect() as con:
        view, plan_id = _view(con, token)
        if not view.ready:
            raise HTTPException(409, "Маршрут сейчас меняют — обновите страницу через минуту")
        if not 0 <= index < len(view.stops):
            raise HTTPException(404, "Точка не найдена — обновите страницу")
        key = stop_key(view.stops[index])
        if data.status is None:
            con.execute("DELETE FROM stop_statuses WHERE plan_id = ? AND stop_key = ?", (plan_id, key))
        else:
            con.execute(
                """INSERT INTO stop_statuses (plan_id, stop_key, status) VALUES (?, ?, ?)
                   ON CONFLICT(plan_id, stop_key) DO UPDATE SET status = excluded.status,
                                                                updated_at = datetime('now')""",
                (plan_id, key, data.status),
            )
        return _view(con, token)[0]
