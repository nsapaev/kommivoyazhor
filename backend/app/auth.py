"""Регистрация компании, вход, выход.

Пароли — scrypt из стандартной библиотеки. Сессия — случайный токен в httpOnly-cookie,
в базе хранится только его хеш.
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db

COOKIE = "session"
SESSION_TTL = 30 * 24 * 3600
# В продакшене за HTTPS включить: COOKIE_SECURE=1
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

MAX_FAILS = 10
FAIL_WINDOW = 15 * 60

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/api/auth")


# ---------- Пароли ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


# Хеш-заглушка: при входе с несуществующим email тратим столько же времени,
# чтобы по скорости ответа нельзя было узнать, зарегистрирован ли адрес.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# ---------- Сессии ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    with db.connect() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        con.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, int(time.time()) + SESSION_TTL),
        )
    response.set_cookie(
        COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/"
    )


class Me(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    company_id: int
    company_name: str


def _load_me(con: sqlite3.Connection, user_id: int) -> Me:
    row = con.execute(
        """SELECT u.id, u.name, u.email, u.role, c.id AS company_id, c.name AS company_name
           FROM users u JOIN companies c ON c.id = u.company_id WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    return Me(user_id=row["id"], name=row["name"], email=row["email"], role=row["role"],
              company_id=row["company_id"], company_name=row["company_name"])


def current_user(session: Optional[str] = Cookie(default=None)) -> Me:
    """Зависимость FastAPI: пускает только вошедших."""
    if not session:
        raise HTTPException(401, "Нужно войти")
    with db.connect() as con:
        row = con.execute(
            "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
            (_token_hash(session), int(time.time())),
        ).fetchone()
        if not row:
            raise HTTPException(401, "Сессия истекла, войдите снова")
        return _load_me(con, row["user_id"])


# ---------- Защита от подбора пароля ----------

_fails: Dict[str, Deque[float]] = defaultdict(deque)


def _too_many_fails(key: str) -> bool:
    q = _fails[key]
    now = time.monotonic()
    while q and now - q[0] > FAIL_WINDOW:
        q.popleft()
    return len(q) >= MAX_FAILS


# ---------- Эндпоинты ----------

class RegisterIn(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


def _clean_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Проверьте email")
    return email


@router.post("/register", response_model=Me)
def register(data: RegisterIn, response: Response):
    email = _clean_email(data.email)
    company, name = data.company.strip(), data.name.strip()
    if not company or not name:
        raise HTTPException(422, "Заполните название компании и имя")
    with db.connect() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(409, "Этот email уже зарегистрирован — войдите")
        company_id = con.execute("INSERT INTO companies (name) VALUES (?)", (company,)).lastrowid
        user_id = con.execute(
            "INSERT INTO users (company_id, email, name, password_hash, role) VALUES (?, ?, ?, ?, 'owner')",
            (company_id, email, name, hash_password(data.password)),
        ).lastrowid
        me = _load_me(con, user_id)
    _start_session(response, user_id)
    return me


@router.post("/login", response_model=Me)
def login(data: LoginIn, request: Request, response: Response):
    email = data.email.strip().lower()
    key = f"{email}|{request.client.host if request.client else ''}"
    if _too_many_fails(key):
        raise HTTPException(429, "Слишком много попыток. Попробуйте через 15 минут")

    with db.connect() as con:
        row = con.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    ok = verify_password(data.password, row["password_hash"] if row else _DUMMY_HASH) and row is not None
    if not ok:
        _fails[key].append(time.monotonic())
        raise HTTPException(401, "Неверный email или пароль")

    _fails.pop(key, None)
    _start_session(response, row["id"])
    with db.connect() as con:
        return _load_me(con, row["id"])


@router.post("/logout")
def logout(response: Response, session: Optional[str] = Cookie(default=None)):
    if session:
        with db.connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(session),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=Me)
def me(user: Me = Depends(current_user)):
    return user
