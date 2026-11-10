"""SQLite: один файл, без отдельного сервера базы данных."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_path = os.getenv("DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "app.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY,
    company_id     INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'owner',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- В базе лежит только sha256 от токена: утечка базы не даёт войти чужими сессиями.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

-- Склад и значения по умолчанию для новых маршрутных листов.
CREATE TABLE IF NOT EXISTS company_settings (
    company_id       INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    depot_label      TEXT,
    depot_lat        REAL,
    depot_lon        REAL,
    vehicles         INTEGER NOT NULL DEFAULT 2,
    service_min      INTEGER NOT NULL DEFAULT 5,
    return_to_depot  INTEGER NOT NULL DEFAULT 1
);

-- Маршрутный лист на день: точки и настройки (черновик) + построенный результат.
CREATE TABLE IF NOT EXISTS plans (
    id               INTEGER PRIMARY KEY,
    company_id       INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    plan_date        TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'draft',
    stops_json       TEXT NOT NULL DEFAULT '[]',
    stops_count      INTEGER NOT NULL DEFAULT 0,
    vehicles         INTEGER NOT NULL DEFAULT 2,
    service_min      INTEGER NOT NULL DEFAULT 5,
    return_to_depot  INTEGER NOT NULL DEFAULT 1,
    result_json      TEXT,
    routes_count     INTEGER NOT NULL DEFAULT 0,
    total_km         REAL NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS plans_company_date ON plans(company_id, plan_date DESC, id DESC);

-- Секретная ссылка водителя: одна на машину в листе, не меняется при пересчёте.
CREATE TABLE IF NOT EXISTS driver_links (
    token    TEXT PRIMARY KEY,
    plan_id  INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    vehicle  INTEGER NOT NULL,
    UNIQUE (plan_id, vehicle)
);

-- Отметки водителя. Ключ — координаты точки: при пересчёте отметка остаётся за точкой,
-- даже если точка ушла другой машине.
CREATE TABLE IF NOT EXISTS stop_statuses (
    plan_id     INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    stop_key    TEXT NOT NULL,
    status      TEXT NOT NULL,  -- done | failed
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (plan_id, stop_key)
);
"""

# Колонки, добавленные после первых версий: в старой базе их нужно дописать.
MIGRATIONS = [
    ("company_settings", "start_time", "TEXT NOT NULL DEFAULT '09:00'"),
    ("plans", "start_time", "TEXT NOT NULL DEFAULT '09:00'"),
]


def set_path(path: str) -> None:
    """Для тестов: работать с другой базой."""
    global _path
    _path = path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    Path(_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        with con:  # коммит при успехе, откат при ошибке
            yield con
    finally:
        con.close()


def init() -> None:
    with connect() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
