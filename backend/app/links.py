"""Ссылки для водителя в Яндекс Картах. Бесплатно, без API-ключа."""
from typing import List, Tuple

from pydantic import BaseModel

Point = Tuple[float, float]

# Сколько точек Яндекс Карты прокладывают по одной ссылке: старт + 18 промежуточных + финиш.
# Проверено вручную (ноябрь 2026): остальные промежуточные точки молча пропускаются.
MAX_POINTS = 20


class LinkPart(BaseModel):
    title: str  # «Часть 1: склад → точка 19»
    link: str


def yandex_maps(points: List[Point]) -> str:
    """Маршрут в Яндекс Картах (на телефоне откроется в приложении)."""
    rtext = "~".join(f"{lat:.6f},{lon:.6f}" for lat, lon in points)
    return f"https://yandex.ru/maps/?rtext={rtext}&rtt=auto"


def yandex_maps_parts(points: List[Point], returns_to_depot: bool) -> List[LinkPart]:
    """Длинный маршрут — на части, каждая следующая начинается там, где закончилась прошлая.

    points: склад, точки 1..n, и снова склад, если машина возвращается.
    """
    last = len(points) - 1

    def name(i: int) -> str:
        if i == 0 or (returns_to_depot and i == last):
            return "склад"
        return f"точка {i}"

    if len(points) <= MAX_POINTS:
        return [LinkPart(title="Весь маршрут", link=yandex_maps(points))]

    parts, start, n = [], 0, 1
    while start < last:
        end = min(start + MAX_POINTS - 1, last)
        parts.append(LinkPart(title=f"Часть {n}: {name(start)} → {name(end)}", link=yandex_maps(points[start:end + 1])))
        start, n = end, n + 1
    return parts
