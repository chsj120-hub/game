#!/usr/bin/env python3
"""실제 고도·하천 데이터 → 권역 17곳의 지형 마스크 + AI 지도 생성용 밑그림 (표준 라이브러리만 사용).

입력(공공 데이터, tools/fetch_geo.sh 로 받음 → data_src/geo_raw/, 저장소에는 올리지 않음)
  · SRTM 1″(약 30m) .hgt  — NASA/USGS, 퍼블릭 도메인. 남한 권역
  · GTOPO30 30″(약 0.9km) — USGS, 퍼블릭 도메인. SRTM 이 없는 북한 권역·보조
  · Natural Earth 10m 하천·호수 — 퍼블릭 도메인
투영: data/regions.json 의 regions[].geo_projection (tools/build_world.py 가 노드 실제 좌표로 계산) — 노드 px 와 1:1 로 맞음.

출력 (3840×2160)
  assets/maps/masks/map_nn_mask.png       게임용 마스크 R=지형(0–31 통행불가·32–95 수계·96–191 산악·192–255 평지/관로) · G=위험도 · B=나루·도하(≥128)
  assets/maps/guides/map_nn_relief.png    음영기복(회색) + 바다 평탄 + 하천 — AI 생성 구도 고정(ControlNet Lineart/Canny·img2img)
  assets/maps/guides/map_nn_height.png    고도(8bit, 바다 0) — ControlNet Depth 용
  assets/maps/guides/map_nn_layout.png    음영기복 + 노드 점·도로(1920×1080) — 배치 검토용(AI 입력 금지)
사용: python3 tools/gen_terrain.py [--regions MAP_01,MAP_02] [--scale 2] [--jobs 8]
  --scale N : 계산 해상도 = 3840/N (기본 2 → 1920×1080 으로 계산해 3840×2160 으로 보간 저장. 1 = 원해상도, 느림)
"""
import argparse
import array
import json
import math
import os
import struct
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_src" / "geo_raw"
OUT_MASK = ROOT / "assets" / "maps" / "masks"
OUT_GUIDE = ROOT / "assets" / "maps" / "guides"
W_OUT, H_OUT = 3840, 2160

# ---------------------------------------------------------------- 파라미터(지형 판정)
SEA_DEEP_PX = 40          # 해안에서 이 거리(출력 px) 이상 떨어진 바다 = 통행불가(심해)
MOUNTAIN_ELEV = 350.0     # m 이상 또는
MOUNTAIN_SLOPE = 14.0     # 경사(도) 이상 → 산악
CLIFF_SLOPE = 38.0        # 경사(도) 이상 → 절벽(통행불가)
ROAD_HALF_PX = 7          # 관로(도로 간선) 폭의 절반(출력 px)
RIVER_PX = {0: 11, 1: 10, 2: 9, 3: 8, 4: 7, 5: 6, 6: 5, 7: 4, 8: 4, 9: 3, 10: 3, 11: 3, 12: 2}  # scalerank → 폭(출력 px)


# ---------------------------------------------------------------- PNG (표준 라이브러리)
def write_png(path, w, h, rows, channels):
    """rows: bytes 행 목록. channels 1(회색)|3(RGB). 필터 Sub 로 압축률 개선."""
    ctype = {1: 0, 3: 2}[channels]
    raw = bytearray()
    for r in rows:
        raw.append(1)
        prev = bytes(channels) + r[:-channels] if channels else r
        raw += bytes((a - b) & 255 for a, b in zip(r, prev))
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


# ---------------------------------------------------------------- DEM
class SRTM:
    """SRTM1 .hgt 타일(3601×3601, 빅엔디언 int16, 공백 −32768). 지연 로딩."""
    def __init__(self, d):
        self.dir = d
        self.cache = {}

    def tile(self, la, lo):
        k = (la, lo)
        if k not in self.cache:
            p = self.dir / f"n{la:02d}e{lo:03d}.hgt"
            if p.exists():
                a = array.array("h")
                a.frombytes(p.read_bytes())
                if sys.byteorder == "little":
                    a.byteswap()
                self.cache[k] = a
            else:
                self.cache[k] = None
        return self.cache[k]

    def get(self, lat, lon):
        la, lo = math.floor(lat), math.floor(lon)
        t = self.tile(la, lo)
        if t is None:
            return None
        fx = (lon - lo) * 3600.0
        fy = (la + 1 - lat) * 3600.0
        x0, y0 = int(fx), int(fy)
        x0, y0 = min(x0, 3599), min(y0, 3599)
        dx, dy = fx - x0, fy - y0
        i = y0 * 3601 + x0
        v00, v10, v01, v11 = t[i], t[i + 1], t[i + 3601], t[i + 3602]
        if -32768 in (v00, v10, v01, v11):
            return None
        return (v00 * (1 - dx) + v10 * dx) * (1 - dy) + (v01 * (1 - dx) + v11 * dx) * dy


class GTOPO30:
    """GTOPO30 GeoTIFF(무압축 int16, 바다 −9999). gt30e100n90: 경도 100–140 · 위도 40–90, gt30e100n40: 위도 −10–40."""
    def __init__(self, d):
        self.tiles = []
        for name in ("gt30e100n90.tif", "gt30e100n40.tif"):
            p = d / name
            if p.exists():
                self.tiles.append(self._read(p))

    @staticmethod
    def _read(p):
        b = p.read_bytes()
        bo = "<" if b[:2] == b"II" else ">"
        off = struct.unpack(bo + "I", b[4:8])[0]
        n = struct.unpack(bo + "H", b[off:off + 2])[0]
        tags = {}
        for i in range(n):
            tag, typ, cnt, val = struct.unpack(bo + "HHII", b[off + 2 + 12 * i: off + 14 + 12 * i])
            tags[tag] = (typ, cnt, val)
        w, h = tags[256][2], tags[257][2]
        so = tags[273]
        first = struct.unpack(bo + "I", b[so[2]:so[2] + 4])[0] if so[1] > 1 else so[2]
        ps = struct.unpack(bo + "3d", b[tags[33550][2]: tags[33550][2] + 24])
        tp = struct.unpack(bo + "6d", b[tags[33922][2]: tags[33922][2] + 48])
        a = array.array("h")
        a.frombytes(b[first: first + w * h * 2])   # 스트립이 연속 저장(GDAL 기본) — 첫 오프셋부터 전체 읽기
        if (bo == "<") != (sys.byteorder == "little"):
            a.byteswap()
        return {"w": w, "h": h, "lon0": tp[3], "lat0": tp[4], "dx": ps[0], "dy": ps[1], "a": a}

    def get(self, lat, lon):
        for t in self.tiles:
            fx = (lon - t["lon0"]) / t["dx"] - 0.5
            fy = (t["lat0"] - lat) / t["dy"] - 0.5
            if -0.51 <= fx <= t["w"] - 0.49 and -0.51 <= fy <= t["h"] - 0.49:
                fx = min(max(fx, 0.0), t["w"] - 1.001)   # 타일 경계(위도 40°) 반 픽셀 틈 메움
                fy = min(max(fy, 0.0), t["h"] - 1.001)
                x0, y0 = int(fx), int(fy)
                dx, dy = fx - x0, fy - y0
                a, w = t["a"], t["w"]
                i = y0 * w + x0
                v = [a[i], a[i + 1], a[i + w], a[i + w + 1]]
                if all(x == -9999 for x in v):
                    continue   # 타일 가장자리 무자료 행 → 다음 타일에서 재조회
                v = [0.0 if x == -9999 else float(x) for x in v]
                return (v[0] * (1 - dx) + v[1] * dx) * (1 - dy) + (v[2] * (1 - dx) + v[3] * dx) * dy
        return 0.0


# ---------------------------------------------------------------- 벡터(하천·호수)
def load_water(bbox):
    """Natural Earth 10m 하천(선)·호수(면) 중 bbox(lat0,lat1,lon0,lon1) 와 겹치는 것."""
    la0, la1, lo0, lo1 = bbox
    rivers, lakes = [], []
    rp = RAW / "ne_10m_rivers_lake_centerlines.geojson"
    if rp.exists():
        for f in json.loads(rp.read_text(encoding="utf-8"))["features"]:
            g = f["geometry"]
            if not g:
                continue
            lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
            sr = int(f["properties"].get("scalerank", 9) or 9)
            for ln in lines:
                if any(la0 <= y <= la1 and lo0 <= x <= lo1 for x, y in ln):
                    rivers.append((sr, ln))
    lp = RAW / "ne_10m_lakes.geojson"
    if lp.exists():
        for f in json.loads(lp.read_text(encoding="utf-8"))["features"]:
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                ring = poly[0]
                if any(la0 <= y <= la1 and lo0 <= x <= lo1 for x, y in ring):
                    lakes.append(ring)
    return rivers, lakes


# ---------------------------------------------------------------- 래스터 도구
def dist_transform(src, w, h):
    """src[i] True 인 픽셀에서의 거리(체스보드·대각 1.4 근사, 2 패스)."""
    INF = 1e9
    d = array.array("f", [0.0 if s else INF for s in src])
    for y in range(h):
        row = y * w
        for x in range(w):
            i = row + x
            v = d[i]
            if v == 0.0:
                continue
            if x > 0 and d[i - 1] + 1 < v:
                v = d[i - 1] + 1
            if y > 0:
                j = i - w
                if d[j] + 1 < v:
                    v = d[j] + 1
                if x > 0 and d[j - 1] + 1.414 < v:
                    v = d[j - 1] + 1.414
                if x < w - 1 and d[j + 1] + 1.414 < v:
                    v = d[j + 1] + 1.414
            d[i] = v
    for y in range(h - 1, -1, -1):
        row = y * w
        for x in range(w - 1, -1, -1):
            i = row + x
            v = d[i]
            if v == 0.0:
                continue
            if x < w - 1 and d[i + 1] + 1 < v:
                v = d[i + 1] + 1
            if y < h - 1:
                j = i + w
                if d[j] + 1 < v:
                    v = d[j] + 1
                if x < w - 1 and d[j + 1] + 1.414 < v:
                    v = d[j + 1] + 1.414
                if x > 0 and d[j - 1] + 1.414 < v:
                    v = d[j - 1] + 1.414
            d[i] = v
    return d


def draw_line(buf, w, h, p0, p1, half, val):
    """굵은 선분(원형 브러시)을 buf 에 val 로."""
    (x0, y0), (x1, y1) = p0, p1
    L = max(1, int(math.hypot(x1 - x0, y1 - y0)))
    r = max(0, int(math.ceil(half)))
    r2 = half * half
    for k in range(L + 1):
        t = k / L
        cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        ix, iy = int(cx), int(cy)
        for yy in range(iy - r, iy + r + 1):
            if 0 <= yy < h:
                for xx in range(ix - r, ix + r + 1):
                    if 0 <= xx < w and (xx - cx) ** 2 + (yy - cy) ** 2 <= r2 + 0.25:
                        buf[yy * w + xx] = val


def fill_poly(buf, w, h, pts, val):
    ys = [p[1] for p in pts]
    for y in range(max(0, int(min(ys))), min(h - 1, int(max(ys))) + 1):
        xs = []
        for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
            if (ya <= y < yb) or (yb <= y < ya):
                xs.append(xa + (y - ya) * (xb - xa) / (yb - ya))
        xs.sort()
        for a, b in zip(xs[::2], xs[1::2]):
            for x in range(max(0, int(a)), min(w - 1, int(b)) + 1):
                buf[y * w + x] = val


# ---------------------------------------------------------------- 권역 1곳
def build_region(args):
    rid, scale = args
    reg = json.loads((ROOT / "data" / "regions.json").read_text(encoding="utf-8"))
    R = next(r for r in reg["regions"] if r["id"] == rid)
    pr = R["geo_projection"]
    w, h = W_OUT // scale, H_OUT // scale
    kmpp = pr["km_per_px"] * scale                     # 계산 격자 1칸 = km
    srtm, gt = SRTM(RAW / "srtm"), GTOPO30(RAW / "gtopo30")

    def lonlat(px, py):   # 계산 격자 → 경위도
        X, Y = (px + 0.5) * scale, (py + 0.5) * scale
        lon = pr["lon_c"] + (X - W_OUT / 2) * pr["km_per_px"] / pr["kx"]
        lat = pr["lat_c"] - (Y - H_OUT / 2) * pr["km_per_px"] / pr["ky"]
        return lat, lon

    def to_px(lat, lon):  # 경위도 → 계산 격자
        X = W_OUT / 2 + (lon - pr["lon_c"]) * pr["kx"] / pr["km_per_px"]
        Y = H_OUT / 2 - (lat - pr["lat_c"]) * pr["ky"] / pr["km_per_px"]
        return X / scale, Y / scale

    # 1) 고도(SRTM 우선, 없으면 GTOPO30). 바다 = 고도 ≤ 0
    elev = array.array("f", bytes(4 * w * h))
    src_srtm = 0
    for y in range(h):
        for x in range(w):
            lat, lon = lonlat(x, y)
            v = srtm.get(lat, lon)
            if v is None:
                v = gt.get(lat, lon)
            else:
                src_srtm += 1
            elev[y * w + x] = v
    sea = [e <= 0.5 for e in elev]
    # 2) 하천·호수
    la_a, lo_a = lonlat(0, h - 1)
    la_b, lo_b = lonlat(w - 1, 0)
    rivers, lakes = load_water((la_a - 0.2, la_b + 0.2, lo_a - 0.2, lo_b + 0.2))
    water = bytearray(w * h)          # 1 = 하천·호수
    for sr, ln in rivers:
        half = RIVER_PX.get(sr, 2) / 2 / scale * (1.0 if pr["km_per_px"] < 0.08 else 0.8)
        pts = [to_px(y, x) for x, y in ln]
        for a, b in zip(pts, pts[1:]):
            draw_line(water, w, h, a, b, max(0.6, half), 1)
    for ring in lakes:
        fill_poly(water, w, h, [to_px(y, x) for x, y in ring], 1)
    # 3) 경사(도)·음영기복
    slope = array.array("f", bytes(4 * w * h))
    shade = bytearray(w * h)
    cell = kmpp * 1000.0
    az1, az2 = math.radians(315), math.radians(15)
    alt = math.radians(42)
    for y in range(h):
        ym, yp = max(0, y - 1), min(h - 1, y + 1)
        for x in range(w):
            xm, xp = max(0, x - 1), min(w - 1, x + 1)
            dzdx = (elev[y * w + xp] - elev[y * w + xm]) / ((xp - xm) * cell)
            dzdy = (elev[yp * w + x] - elev[ym * w + x]) / ((yp - ym) * cell)
            s = math.atan(math.hypot(dzdx, dzdy))
            slope[y * w + x] = math.degrees(s)
            asp = math.atan2(dzdy, -dzdx)
            v1 = math.sin(alt) * math.cos(s) + math.cos(alt) * math.sin(s) * math.cos(az1 - asp)
            v2 = math.sin(alt) * math.cos(s) + math.cos(alt) * math.sin(s) * math.cos(az2 - asp)
            shade[y * w + x] = max(0, min(255, int(255 * (0.7 * v1 + 0.3 * v2))))
    # 4) 해안 거리 · 노드/도로
    d_land = dist_transform([not s for s in sea], w, h)    # 바다 픽셀의 육지까지 거리
    nodes = [n for n in reg["nodes"] if n["region"] == rid]
    npos = {n["id"]: (n["pos"][0] / scale, n["pos"][1] / scale) for n in nodes}
    road = bytearray(w * h)
    for e in reg["edges"]:
        if e["a"] in npos and e["b"] in npos and e["kind"] == "road":
            draw_line(road, w, h, npos[e["a"]], npos[e["b"]], ROAD_HALF_PX / scale, 1)
    near_node = dist_transform([False] * (w * h) if not nodes else _points(npos.values(), w, h), w, h)
    ferry = [npos[n["id"]] for n in nodes if "ferry" in n["facilities"] or n["type"] == "wreck"]
    hazard = [npos[n["id"]] for n in nodes if n["type"] == "hazard"]
    # 5) 마스크
    R_, G_, B_ = bytearray(w * h), bytearray(w * h), bytearray(w * h)
    far_px = 900 / scale
    for i in range(w * h):
        e, sl = elev[i], slope[i]
        if sea[i]:
            r = 12 if d_land[i] * scale > SEA_DEEP_PX else 60
        elif water[i]:
            r = 70
        elif sl >= CLIFF_SLOPE:
            r = 24
        elif road[i]:
            r = 240
        elif e >= MOUNTAIN_ELEV or sl >= MOUNTAIN_SLOPE:
            r = 96 + min(95, int(max(e - MOUNTAIN_ELEV, 0) / 1800 * 70 + sl / CLIFF_SLOPE * 25))
        else:
            r = 250 - min(50, int(sl / MOUNTAIN_SLOPE * 30 + e / MOUNTAIN_ELEV * 20))
        R_[i] = r
        g = 0.0 if sea[i] else min(1.0, max(e, 0) / 1600) * 150 + min(1.0, sl / 30) * 40
        g += min(1.0, near_node[i] / far_px) * 65
        if road[i]:
            g *= 0.4
        G_[i] = max(0, min(255, int(g)))
    for (hx, hy) in hazard:
        _stamp(G_, w, h, hx, hy, 260 / scale, 90)
    for (fx, fy) in ferry:   # 나루: 노드 주변 물 픽셀
        rr = int(90 / scale)
        for yy in range(max(0, int(fy) - rr), min(h, int(fy) + rr + 1)):
            for xx in range(max(0, int(fx) - rr), min(w, int(fx) + rr + 1)):
                j = yy * w + xx
                if (sea[j] or water[j]) and (xx - fx) ** 2 + (yy - fy) ** 2 <= rr * rr:
                    B_[j] = 220
    for i in range(w * h):   # 도로가 물을 건너는 곳 = 도하 지점
        if road[i] and (water[i] or sea[i]):
            B_[i] = max(B_[i], 160)
    # 6) 출력(보간 확대)
    stem = rid.lower()
    up = scale
    def rows_gray(buf):
        for Y in range(H_OUT):
            fy = (Y + 0.5) / up - 0.5
            y0 = max(0, min(h - 1, int(math.floor(fy))))
            y1 = min(h - 1, y0 + 1)
            ty = max(0.0, min(1.0, fy - y0))
            r0, r1 = y0 * w, y1 * w
            out = bytearray(W_OUT)
            for X in range(W_OUT):
                fx = (X + 0.5) / up - 0.5
                x0 = max(0, min(w - 1, int(math.floor(fx))))
                x1 = min(w - 1, x0 + 1)
                tx = max(0.0, min(1.0, fx - x0))
                a = buf[r0 + x0] * (1 - tx) + buf[r0 + x1] * tx
                b = buf[r1 + x0] * (1 - tx) + buf[r1 + x1] * tx
                out[X] = int(a * (1 - ty) + b * ty)
            yield bytes(out)
    relief = bytearray(w * h)
    hgt = bytearray(w * h)
    emax = max(max(elev), 1.0)
    for i in range(w * h):
        if sea[i]:
            relief[i] = 236 - min(30, int(d_land[i] * scale / 8))   # 연안은 밝게, 먼바다는 약간 어둡게
            hgt[i] = 0
        else:
            v = 70 + shade[i] * 0.72
            if water[i]:
                v = 120
            relief[i] = max(0, min(255, int(v)))
            hgt[i] = max(1, min(255, int(1 + 254 * (max(elev[i], 0) / emax) ** 0.6)))
    write_png(OUT_GUIDE / f"{stem}_relief.png", W_OUT, H_OUT, list(rows_gray(relief)), 1)
    write_png(OUT_GUIDE / f"{stem}_height.png", W_OUT, H_OUT, list(rows_gray(hgt)), 1)
    mrows = []
    for Y in range(H_OUT):
        y = min(h - 1, Y // up)
        r0 = y * w
        row = bytearray(W_OUT * 3)
        for X in range(W_OUT):
            j = r0 + min(w - 1, X // up)
            row[3 * X], row[3 * X + 1], row[3 * X + 2] = R_[j], G_[j], B_[j]
        mrows.append(bytes(row))
    write_png(OUT_MASK / f"{stem}_mask.png", W_OUT, H_OUT, mrows, 3)
    # 배치 검토용(1920×1080): 음영 + 도로 + 노드 점
    lw, lh = W_OUT // 2, H_OUT // 2
    lay = bytearray(lw * lh * 3)
    for Y in range(lh):
        y = min(h - 1, int((Y + 0.5) * 2 / up))
        for X in range(lw):
            x = min(w - 1, int((X + 0.5) * 2 / up))
            v = relief[y * w + x]
            k = 3 * (Y * lw + X)
            if sea[y * w + x] or water[y * w + x]:
                lay[k:k + 3] = bytes((int(v * 0.75), int(v * 0.85), v))
            elif road[y * w + x]:
                lay[k:k + 3] = bytes((200, 60, 40))
            else:
                lay[k:k + 3] = bytes((v, v, v))
    col = {"city": (220, 30, 30), "town": (240, 140, 20), "station": (30, 110, 220), "temple": (130, 40, 170), "fort": (20, 20, 20)}
    for n in nodes:
        cx, cy = n["pos"][0] / 2, n["pos"][1] / 2
        c = (60, 160, 60) if n["hidden"] else col.get(n["type"], (230, 200, 30))
        rr = 9 if n["type"] == "city" else 6
        for yy in range(int(cy) - rr, int(cy) + rr + 1):
            for xx in range(int(cx) - rr, int(cx) + rr + 1):
                if 0 <= xx < lw and 0 <= yy < lh and (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                    k = 3 * (yy * lw + xx)
                    lay[k:k + 3] = bytes(c)
    write_png(OUT_GUIDE / f"{stem}_layout.png", lw, lh, [bytes(lay[3 * Y * lw: 3 * (Y + 1) * lw]) for Y in range(lh)], 3)
    # 노드 검증: 실제 좌표가 바다에 떨어진 노드(침몰선 제외)
    wet = []
    for n in nodes:
        la, lo = n["geo"]
        v = srtm.get(la, lo)
        v = gt.get(la, lo) if v is None else v
        if v <= 0.5 and n["type"] != "wreck":
            wet.append(n["name"])
    land = sum(1 for s in sea if not s) / (w * h)
    return {"id": rid, "srtm_share": round(src_srtm / (w * h), 3), "land": round(land, 3), "max_elev": round(max(elev)),
            "rivers": len(rivers), "lakes": len(lakes), "nodes_at_sea": wet,
            "mask_hist": {k: sum(1 for v in R_ if lo_ <= v <= hi_) / (w * h) for k, (lo_, hi_) in
                          {"impassable": (0, 31), "water": (32, 95), "mountain": (96, 191), "plain_road": (192, 255)}.items()}}


def _points(pts, w, h):
    src = [False] * (w * h)
    for x, y in pts:
        ix, iy = int(x), int(y)
        if 0 <= ix < w and 0 <= iy < h:
            src[iy * w + ix] = True
    return src


def _stamp(buf, w, h, cx, cy, rad, add):
    r = int(rad)
    for yy in range(max(0, int(cy) - r), min(h, int(cy) + r + 1)):
        for xx in range(max(0, int(cx) - r), min(w, int(cx) + r + 1)):
            d = math.hypot(xx - cx, yy - cy)
            if d <= rad:
                j = yy * w + xx
                buf[j] = min(255, buf[j] + int(add * (1 - d / rad)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default="")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    a = ap.parse_args()
    reg = json.loads((ROOT / "data" / "regions.json").read_text(encoding="utf-8"))
    ids = [x for x in a.regions.split(",") if x] or [r["id"] for r in reg["regions"] if "geo_projection" in r]
    miss = [p for p in ("srtm", "gtopo30") if not (RAW / p).exists()]
    if miss:
        sys.exit(f"원천 데이터 없음: {miss} — 먼저 bash tools/fetch_geo.sh")
    with Pool(a.jobs) as pool:
        res = pool.map(build_region, [(i, a.scale) for i in ids])
    rep = {r["id"]: r for r in res}
    old = {}
    rp = OUT_GUIDE / "terrain_report.json"
    if rp.exists():
        old = json.loads(rp.read_text(encoding="utf-8"))
    old.update(rep)
    rp.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        h = r["mask_hist"]
        print(f"{r['id']}: SRTM {r['srtm_share']*100:3.0f}% · 육지 {r['land']*100:3.0f}% · 최고 {r['max_elev']}m · 하천 {r['rivers']} · "
              f"통행불가 {h['impassable']*100:4.1f}% 수계 {h['water']*100:4.1f}% 산악 {h['mountain']*100:4.1f}% 평지 {h['plain_road']*100:4.1f}%"
              + (f" · ⚠ 바다 위 노드: {', '.join(r['nodes_at_sea'])}" if r["nodes_at_sea"] else ""))


if __name__ == "__main__":
    main()
