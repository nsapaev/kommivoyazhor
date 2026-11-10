#!/usr/bin/env bash
# Скачивает карту региона из Geofabrik и готовит её для OSRM (один раз,
# потом — раз в месяц-два, чтобы обновить дороги).
#
#   ./scripts/prepare_osrm.sh                    # Узбекистан (Ташкент)
#   ./scripts/prepare_osrm.sh asia/kazakhstan    # другая страна
#
# Список стран: https://download.geofabrik.de/asia.html
set -euo pipefail

REGION="${1:-asia/uzbekistan}"
IMAGE="ghcr.io/project-osrm/osrm-backend:v5.27.1"
DIR="$(cd "$(dirname "$0")/.." && pwd)/osrm-data"

mkdir -p "$DIR"
echo "Скачиваю $REGION…"
curl -fL -o "$DIR/region.osm.pbf" "https://download.geofabrik.de/${REGION}-latest.osm.pbf"

echo "Готовлю граф дорог (для Узбекистана ~5–15 минут, 2–4 ГБ памяти)…"
docker run --rm -t -v "$DIR:/data" "$IMAGE" osrm-extract -p /opt/car.lua /data/region.osm.pbf
docker run --rm -t -v "$DIR:/data" "$IMAGE" osrm-partition /data/region.osrm
docker run --rm -t -v "$DIR:/data" "$IMAGE" osrm-customize /data/region.osrm

echo "Готово. Запуск: docker compose up -d --build"
