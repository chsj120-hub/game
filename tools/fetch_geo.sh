#!/usr/bin/env bash
# gen_terrain.py 원자료 내려받기 (모두 퍼블릭 도메인). 결과: data_src/geo_raw/ (git 제외)
set -euo pipefail
cd "$(dirname "$0")/.."
RAW=data_src/geo_raw; TMP=$(mktemp -d); mkdir -p "$RAW/srtm" "$RAW/gtopo30"
sparse() { git clone -q --depth 1 --filter=blob:none --sparse "$1" "$TMP/$2"; git -C "$TMP/$2" sparse-checkout set --no-cone "$3"; }
sparse https://github.com/jwayj/newNewGraphhopper.git srtm '/map-matching/files/*.hgt'          # SRTM1 남한 30m
sparse https://github.com/ThornboroughA/SillaGame.git gtopo '/GIS_Data/GTPO30_NortheastAsia/*.tif' # GTOPO30 ~0.9km
sparse https://github.com/nvkelso/natural-earth-vector.git ne '/geojson/ne_10m_rivers_lake_centerlines.geojson
/geojson/ne_10m_lakes.geojson'
cp "$TMP"/srtm/map-matching/files/*.hgt "$RAW/srtm/"
cp "$TMP"/gtopo/GIS_Data/GTPO30_NortheastAsia/gt30e100n{40,90}.tif "$RAW/gtopo30/"
cp "$TMP"/ne/geojson/ne_10m_*.geojson "$RAW/"
rm -rf "$TMP"; echo "OK → $RAW"
