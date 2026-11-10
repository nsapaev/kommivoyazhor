"""Импорт точек из Excel (.xlsx) или CSV, а также из текста, вставленного из таблицы.

Колонки узнаём по заголовкам (по-русски, по-узбекски латиницей или по-английски).
Нет заголовков — каждая строка считается адресом.
"""
import csv
import datetime as dt
import io
import re
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .auth import Me, current_user
from .routing import MAX_STOPS

router = APIRouter(prefix="/api")

MAX_BYTES = 2 * 1024 * 1024

# Поле → слова, с которых может начинаться заголовок колонки (в нижнем регистре).
COLUMNS = {
    "address": ["адрес", "address", "manzil", "улица"],
    "name": ["клиент", "имя", "название", "получатель", "магазин", "name", "client", "mijoz", "nomi"],
    "phone": ["телефон", "тел", "phone", "tel"],
    "comment": ["комментарий", "коммент", "примечание", "заметка", "comment", "note", "izoh"],
    "window": ["окно", "время доставки", "интервал", "время", "window", "vaqt"],
    "tw_from": ["с", "от", "время с", "с (время)", "from", "dan"],
    "tw_to": ["до", "по", "время до", "до (время)", "to", "gacha"],
    "lat": ["широта", "lat", "latitude"],
    "lon": ["долгота", "lon", "lng", "longitude"],
}


class ImportRow(BaseModel):
    address: str = ""
    name: str = ""
    phone: str = ""
    comment: str = ""
    tw_from: Optional[str] = None
    tw_to: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class ImportResult(BaseModel):
    rows: List[ImportRow]
    skipped: int = 0  # строки без адреса и координат
    truncated: bool = False  # строк больше лимита — взяли первые


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _match(header: str) -> Optional[str]:
    h = _norm(header).lower().rstrip(":.")
    if not h:
        return None
    # Сначала точные совпадения («с», «до» — короткие, только целиком), затем начало слова.
    for field, words in COLUMNS.items():
        if h in words:
            return field
    for field, words in COLUMNS.items():
        if any(len(w) > 2 and h.startswith(w) for w in words):
            return field
    return None


def parse_time(v: Any) -> Optional[str]:
    """10 · 10:00 · 10.30 · 9:5 · время из Excel → «ЧЧ:ММ»."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        v = v.time()
    if isinstance(v, dt.time):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 0 <= v < 1:  # Excel хранит время как долю суток
            m = round(v * 24 * 60)
            return f"{m // 60 % 24:02d}:{m % 60:02d}"
        if 0 <= v <= 23 and float(v).is_integer():
            return f"{int(v):02d}:00"
        return None
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{1,2}))?", _norm(v))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def parse_window(v: Any) -> tuple[Optional[str], Optional[str]]:
    """«10:00-12:00», «с 10 до 12», «до 14», «после 15»."""
    s = _norm(v).lower()
    if not s:
        return None, None
    times = re.findall(r"\d{1,2}(?:[:.]\d{2})?", s)
    if len(times) >= 2:
        return parse_time(times[0]), parse_time(times[1])
    if len(times) == 1:
        t = parse_time(times[0])
        if re.search(r"\b(до|по|gacha|to)\b", s):
            return None, t
        return t, None
    return None, None


def _number(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def rows_to_points(table: List[List[Any]]) -> ImportResult:
    table = [r for r in table if any(_norm(c) for c in r)]
    if not table:
        return ImportResult(rows=[])

    header = [_match(c) for c in table[0]]
    if "address" in header or ("lat" in header and "lon" in header):
        cols = {f: i for i, f in reversed(list(enumerate(header))) if f}  # первая колонка с таким полем
        body = table[1:]
    else:
        # Без заголовков: первая непустая колонка — адрес.
        cols, body = {"address": 0}, table

    def cell(r: List[Any], field: str) -> Any:
        i = cols.get(field)
        return r[i] if i is not None and i < len(r) else None

    rows, skipped = [], 0
    for r in body:
        row = ImportRow(
            address=_norm(cell(r, "address")),
            name=_norm(cell(r, "name")),
            phone=_norm(cell(r, "phone"))[:40],
            comment=_norm(cell(r, "comment"))[:300],
            lat=_number(cell(r, "lat")),
            lon=_number(cell(r, "lon")),
        )
        if not (-90 <= (row.lat or 0) <= 90 and -180 <= (row.lon or 0) <= 180) or (row.lat is None) != (row.lon is None):
            row.lat = row.lon = None
        if "window" in cols:
            row.tw_from, row.tw_to = parse_window(cell(r, "window"))
        if "tw_from" in cols:
            row.tw_from = parse_time(cell(r, "tw_from")) or row.tw_from
        if "tw_to" in cols:
            row.tw_to = parse_time(cell(r, "tw_to")) or row.tw_to
        if row.tw_from and row.tw_to and row.tw_from > row.tw_to:
            row.tw_from, row.tw_to = row.tw_to, row.tw_from
        if not row.address and row.lat is None:
            skipped += 1
            continue
        rows.append(row)

    return ImportResult(rows=rows[:MAX_STOPS], skipped=skipped, truncated=len(rows) > MAX_STOPS)


def _read_xlsx(data: bytes) -> List[List[Any]]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(422, "Не получилось открыть файл Excel. Сохраните его как .xlsx или CSV")
    ws = wb.worksheets[0]
    rows = [list(r) for _, r in zip(range(MAX_STOPS * 3 + 1), ws.iter_rows(values_only=True))]
    wb.close()
    return rows


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(422, "Не получилось прочитать файл: сохраните его в кодировке UTF-8")


def _read_text(text: str, from_file: bool) -> List[List[Any]]:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    sample = "\n".join(lines[:20])
    # Табуляция — вставка из Excel/Google Таблиц; «;» — CSV из русского Excel.
    for delim in ("\t", ";"):
        if delim in sample:
            return list(csv.reader(lines, delimiter=delim))
    # Запятая — разделитель, только если это CSV-файл с узнаваемыми заголовками;
    # иначе это просто адреса («Ташкент, улица …») по одному на строку.
    if from_file and "," in lines[0]:
        rows = list(csv.reader(lines))
        if any(_match(c) == "address" for c in rows[0]):
            return rows
    return [[l] for l in lines]


@router.post("/import", response_model=ImportResult)
async def import_points(request: Request, kind: str = "file", _: Me = Depends(current_user)):
    """Тело запроса — сам файл (или вставленный текст при kind=text)."""
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Файл больше 2 МБ — разбейте его на части")
    if kind == "file" and data[:2] == b"PK":  # .xlsx — это zip
        table = _read_xlsx(data)
    elif kind == "file" and data[:4] == b"\xd0\xcf\x11\xe0":
        raise HTTPException(422, "Старый формат .xls не поддерживается — сохраните файл как .xlsx или CSV")
    else:
        table = _read_text(_decode(data), from_file=kind == "file")
    result = rows_to_points(table)
    if not result.rows:
        raise HTTPException(422, "В файле не нашлось адресов. Нужна колонка «Адрес» или адрес в каждой строке")
    return result


def template_csv() -> str:
    rows = [
        ["Адрес", "Клиент", "Телефон", "С", "До", "Комментарий"],
        ["Ташкент, улица Амира Темура 1", "Магазин «Ромашка»", "+998 90 123 45 67", "10:00", "12:00", "Въезд со двора"],
        ["Ташкент, Чиланзар, улица Бунёдкор 15", "Ахмад", "+998 93 765 43 21", "", "14:00", ""],
    ]
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(rows)
    return "﻿" + buf.getvalue()  # BOM — чтобы Excel открыл кириллицу правильно


@router.get("/import/template.csv")
def import_template():
    from fastapi.responses import Response

    return Response(
        template_csv().encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tochki.csv"'},
    )

