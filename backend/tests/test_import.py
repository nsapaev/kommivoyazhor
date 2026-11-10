import io

from openpyxl import Workbook

from app.importer import parse_time, parse_window
from tests.test_plans import client, signup  # noqa: F401 — фикстура


def test_parse_time_and_window():
    assert parse_time("10") == "10:00" and parse_time("9.30") == "09:30" and parse_time(0.5) == "12:00"
    assert parse_time("25:00") is None
    assert parse_window("10:00-12:00") == ("10:00", "12:00")
    assert parse_window("с 10 до 12") == ("10:00", "12:00")
    assert parse_window("до 14") == (None, "14:00")
    assert parse_window("после 15") == ("15:00", None)


def test_import_csv_with_headers(client):
    signup(client)
    csv = "Адрес;Клиент;Телефон;Окно;Комментарий\nулица Навои 1;Ромашка;+998 90 1;10:00-12:00;двор\n;;;;\n"
    r = client.post("/api/import", content=csv.encode("cp1251")).json()
    assert r["rows"] == [{"address": "улица Навои 1", "name": "Ромашка", "phone": "+998 90 1",
                          "comment": "двор", "tw_from": "10:00", "tw_to": "12:00", "lat": None, "lon": None}]


def test_import_plain_addresses_keep_commas(client):
    signup(client)
    text = "Ташкент, улица Амира Темура 1\nТашкент, Чиланзар, улица Бунёдкор 15\n"
    r = client.post("/api/import?kind=text", content=text.encode()).json()
    assert [x["address"] for x in r["rows"]] == ["Ташкент, улица Амира Темура 1", "Ташкент, Чиланзар, улица Бунёдкор 15"]


def test_import_xlsx(client):
    import datetime as dt

    signup(client)
    wb = Workbook()
    ws = wb.active
    ws.append(["Клиент", "Адрес", "С", "До", "Широта", "Долгота"])
    ws.append(["Ахмад", "Чиланзар 5", dt.time(9, 0), "13", 41.28, 69.2])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/import", content=buf.getvalue()).json()
    row = r["rows"][0]
    assert (row["name"], row["address"], row["tw_from"], row["tw_to"], row["lat"]) == ("Ахмад", "Чиланзар 5", "09:00", "13:00", 41.28)


def test_import_requires_login_and_rejects_empty(client):
    assert client.post("/api/import", content=b"x").status_code == 401
    signup(client)
    assert client.post("/api/import", content=b"\n\n").status_code == 422
