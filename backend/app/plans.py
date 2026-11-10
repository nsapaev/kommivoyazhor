"""Склад и настройки компании, маршрутные листы (черновики и построенные маршруты).

Всё строго в рамках компании пользователя: чужой лист — 404, как будто его нет.
"""
import datetime as dt
import json
import sqlite3
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .auth import Me, current_user
from .driver import ensure_tokens, load_statuses
from .routing import HHMM, BuildError, BuildResult, MAX_STOPS, Place, build

router = APIRouter(prefix="/api")

DEFAULTS = {"vehicles": 2, "service_min": 5, "return_to_depot": True, "start_time": "09:00"}
PLAN_FIELDS = ("vehicles", "service_min", "return_to_depot", "start_time")


# ---------- Настройки компании ----------

class Settings(BaseModel):
    depot: Optional[Place] = None
    vehicles: int = Field(default=2, ge=1, le=5)
    service_min: int = Field(default=5, ge=0, le=120)
    return_to_depot: bool = True
    start_time: str = Field(default="09:00", pattern=HHMM)  # начало смены: от него считается время прибытия


class SettingsPatch(BaseModel):
    depot: Optional[Place] = None
    clear_depot: bool = False
    vehicles: Optional[int] = Field(default=None, ge=1, le=5)
    service_min: Optional[int] = Field(default=None, ge=0, le=120)
    return_to_depot: Optional[bool] = None
    start_time: Optional[str] = Field(default=None, pattern=HHMM)


def _load_settings(con: sqlite3.Connection, company_id: int) -> Settings:
    row = con.execute("SELECT * FROM company_settings WHERE company_id = ?", (company_id,)).fetchone()
    if not row:
        return Settings(**DEFAULTS)
    depot = (
        Place(lat=row["depot_lat"], lon=row["depot_lon"], label=row["depot_label"])
        if row["depot_lat"] is not None
        else None
    )
    return Settings(depot=depot, vehicles=row["vehicles"], service_min=row["service_min"],
                    return_to_depot=bool(row["return_to_depot"]), start_time=row["start_time"])


def _save_settings(con: sqlite3.Connection, company_id: int, s: Settings) -> None:
    con.execute(
        """INSERT INTO company_settings
               (company_id, depot_label, depot_lat, depot_lon, vehicles, service_min, return_to_depot, start_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(company_id) DO UPDATE SET
               depot_label = excluded.depot_label, depot_lat = excluded.depot_lat,
               depot_lon = excluded.depot_lon, vehicles = excluded.vehicles,
               service_min = excluded.service_min, return_to_depot = excluded.return_to_depot,
               start_time = excluded.start_time""",
        (company_id, s.depot.label if s.depot else None, s.depot.lat if s.depot else None,
         s.depot.lon if s.depot else None, s.vehicles, s.service_min, int(s.return_to_depot), s.start_time),
    )


@router.get("/company/settings", response_model=Settings)
def get_settings(me: Me = Depends(current_user)):
    with db.connect() as con:
        return _load_settings(con, me.company_id)


@router.patch("/company/settings", response_model=Settings)
def patch_settings(patch: SettingsPatch, me: Me = Depends(current_user)):
    with db.connect() as con:
        s = _load_settings(con, me.company_id)
        if patch.clear_depot:
            s.depot = None
        elif patch.depot is not None:
            s.depot = patch.depot
        for field in PLAN_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                setattr(s, field, value)
        _save_settings(con, me.company_id, s)
        return s


# ---------- Маршрутные листы ----------

class PlanSummary(BaseModel):
    id: int
    plan_date: str
    status: str  # draft | built
    stops_count: int
    routes_count: int
    total_km: float
    updated_at: str


class Plan(PlanSummary):
    stops: List[Place]
    vehicles: int
    service_min: int
    return_to_depot: bool
    start_time: str = "09:00"
    result: Optional[BuildResult] = None
    statuses: Dict[str, str] = {}  # отметки водителей: "lat,lon" точки → done | failed


class PlanCreate(BaseModel):
    plan_date: Optional[dt.date] = None  # дата клиента: у него свой часовой пояс
    stops: List[Place] = Field(default_factory=list, max_length=MAX_STOPS)
    from_plan_id: Optional[int] = None  # «Повторить»: взять точки и настройки из этого листа


class PlanPatch(BaseModel):
    plan_date: Optional[dt.date] = None
    stops: Optional[List[Place]] = Field(default=None, max_length=MAX_STOPS)
    vehicles: Optional[int] = Field(default=None, ge=1, le=5)
    service_min: Optional[int] = Field(default=None, ge=0, le=120)
    return_to_depot: Optional[bool] = None
    start_time: Optional[str] = Field(default=None, pattern=HHMM)


_SUMMARY_COLS = "id, plan_date, status, stops_count, routes_count, total_km, updated_at"


def _row_to_plan(row: sqlite3.Row, con: Optional[sqlite3.Connection] = None) -> Plan:
    return Plan(
        id=row["id"], plan_date=row["plan_date"], status=row["status"],
        stops_count=row["stops_count"], routes_count=row["routes_count"], total_km=row["total_km"],
        updated_at=row["updated_at"],
        stops=[Place(**p) for p in json.loads(row["stops_json"])],
        vehicles=row["vehicles"], service_min=row["service_min"], return_to_depot=bool(row["return_to_depot"]),
        start_time=row["start_time"],
        result=BuildResult.model_validate_json(row["result_json"]) if row["result_json"] else None,
        statuses=load_statuses(con, row["id"]) if con is not None else {},
    )


def _get_plan_row(con: sqlite3.Connection, plan_id: int, company_id: int) -> sqlite3.Row:
    row = con.execute("SELECT * FROM plans WHERE id = ? AND company_id = ?", (plan_id, company_id)).fetchone()
    if not row:
        raise HTTPException(404, "Маршрутный лист не найден")
    return row


@router.get("/plans", response_model=List[PlanSummary])
def list_plans(me: Me = Depends(current_user)):
    with db.connect() as con:
        rows = con.execute(
            f"SELECT {_SUMMARY_COLS} FROM plans WHERE company_id = ? ORDER BY plan_date DESC, id DESC LIMIT 100",
            (me.company_id,),
        ).fetchall()
    return [PlanSummary(**dict(r)) for r in rows]


@router.post("/plans", response_model=Plan)
def create_plan(data: PlanCreate, me: Me = Depends(current_user)):
    with db.connect() as con:
        s = _load_settings(con, me.company_id)
        stops, vehicles, service_min, ret, start = (
            data.stops, s.vehicles, s.service_min, s.return_to_depot, s.start_time)
        if data.from_plan_id is not None:
            src = _row_to_plan(_get_plan_row(con, data.from_plan_id, me.company_id))
            stops, vehicles, service_min, ret, start = (
                src.stops, src.vehicles, src.service_min, src.return_to_depot, src.start_time)
        plan_id = con.execute(
            """INSERT INTO plans (company_id, created_by, plan_date, stops_json, stops_count,
                                  vehicles, service_min, return_to_depot, start_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (me.company_id, me.user_id, (data.plan_date or dt.date.today()).isoformat(),
             json.dumps([p.model_dump() for p in stops], ensure_ascii=False), len(stops),
             vehicles, service_min, int(ret), start),
        ).lastrowid
        return _row_to_plan(_get_plan_row(con, plan_id, me.company_id), con)


@router.get("/plans/{plan_id}", response_model=Plan)
def get_plan(plan_id: int, me: Me = Depends(current_user)):
    with db.connect() as con:
        return _row_to_plan(_get_plan_row(con, plan_id, me.company_id), con)


@router.patch("/plans/{plan_id}", response_model=Plan)
def patch_plan(plan_id: int, patch: PlanPatch, me: Me = Depends(current_user)):
    """Любая правка исходных данных сбрасывает построенный маршрут: он больше не соответствует точкам."""
    with db.connect() as con:
        _get_plan_row(con, plan_id, me.company_id)
        sets, args = [], []
        if patch.plan_date is not None:
            sets.append("plan_date = ?")
            args.append(patch.plan_date.isoformat())
        if patch.stops is not None:
            sets += ["stops_json = ?", "stops_count = ?"]
            args += [json.dumps([p.model_dump() for p in patch.stops], ensure_ascii=False), len(patch.stops)]
        for field in PLAN_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                sets.append(f"{field} = ?")
                args.append(value if isinstance(value, str) else int(value))
        if patch.model_fields_set - {"plan_date"}:
            sets += ["status = 'draft'", "result_json = NULL", "routes_count = 0", "total_km = 0"]
        if sets:
            sets.append("updated_at = datetime('now')")
            con.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id = ?", (*args, plan_id))

        # Последние выбранные настройки становятся значениями по умолчанию для новых листов.
        if set(PLAN_FIELDS) & patch.model_fields_set:
            s = _load_settings(con, me.company_id)
            for field in PLAN_FIELDS:
                value = getattr(patch, field)
                if value is not None:
                    setattr(s, field, value)
            _save_settings(con, me.company_id, s)

        return _row_to_plan(_get_plan_row(con, plan_id, me.company_id), con)


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, me: Me = Depends(current_user)):
    with db.connect() as con:
        _get_plan_row(con, plan_id, me.company_id)
        con.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    return {"ok": True}


@router.post("/plans/{plan_id}/build", response_model=Plan)
async def build_plan(plan_id: int, me: Me = Depends(current_user)):
    with db.connect() as con:
        plan = _row_to_plan(_get_plan_row(con, plan_id, me.company_id))
        depot = _load_settings(con, me.company_id).depot
    if depot is None:
        raise HTTPException(422, "Сначала укажите склад")

    try:
        result = await build(depot, plan.stops, plan.vehicles, plan.service_min, plan.return_to_depot,
                             plan.start_time)
    except BuildError as e:
        raise HTTPException(422, str(e))

    with db.connect() as con:
        # Пока считали, точки могли поменять — тогда результат уже не про этот лист.
        current = _row_to_plan(_get_plan_row(con, plan_id, me.company_id))
        if (current.stops, current.vehicles, current.service_min, current.return_to_depot, current.start_time) != (
            plan.stops, plan.vehicles, plan.service_min, plan.return_to_depot, plan.start_time
        ):
            raise HTTPException(409, "Точки изменились во время расчёта — постройте ещё раз")
        tokens = ensure_tokens(con, plan_id, (r.vehicle for r in result.routes))
        for r in result.routes:
            r.driver_token = tokens[r.vehicle]
        con.execute(
            """UPDATE plans SET status = 'built', result_json = ?, routes_count = ?, total_km = ?,
                                updated_at = datetime('now') WHERE id = ?""",
            (result.model_dump_json(), len(result.routes),
             round(sum(r.distance_km for r in result.routes), 1), plan_id),
        )
        return _row_to_plan(_get_plan_row(con, plan_id, me.company_id), con)


@router.get("/plans/{plan_id}/statuses", response_model=Dict[str, str])
def plan_statuses(plan_id: int, me: Me = Depends(current_user)):
    """Лёгкий запрос для обновления отметок водителей без перезагрузки всего листа."""
    with db.connect() as con:
        _get_plan_row(con, plan_id, me.company_id)
        return load_statuses(con, plan_id)
