"""Поиск адреса через Nominatim (OpenStreetMap). Бесплатно, ~1 запрос/сек."""
import asyncio
import os
import time
from typing import Dict, List

import httpx

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
COUNTRY = os.getenv("GEOCODE_COUNTRY", "uz")
# Ищем только внутри города: "запад,север,восток,юг". По умолчанию — Ташкент.
# Пустое значение — искать по всей стране.
VIEWBOX = os.getenv("GEOCODE_VIEWBOX", "69.10,41.42,69.45,41.20")
HEADERS = {"User-Agent": "route-planner-mvp/0.1"}

_cache: Dict[str, List[dict]] = {}
_lock = asyncio.Lock()
_last_call = 0.0


async def search(query: str, limit: int = 5) -> List[dict]:
    global _last_call
    key = query.strip().lower()
    if not key:
        return []
    if key in _cache:
        return _cache[key]

    async with _lock:  # соблюдаем лимит публичного Nominatim
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        params = {"q": query, "format": "jsonv2", "limit": limit, "accept-language": "ru"}
        if COUNTRY:
            params["countrycodes"] = COUNTRY
        if VIEWBOX:
            params["viewbox"] = VIEWBOX
            params["bounded"] = 1
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(f"{NOMINATIM_URL}/search", params=params)
        _last_call = time.monotonic()
        resp.raise_for_status()

    results = [
        {"label": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"])}
        for r in resp.json()
    ]
    _cache[key] = results
    return results
