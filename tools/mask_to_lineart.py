#!/usr/bin/env python3
"""마스크맵(RGB 24-bit) → ControlNet 용 선화(lineart) PNG 일괄 변환.

GTX 3060 기준: ControlNet Canny/Lineart 입력으로 사용.
마스크의 채널별 색상 경계를 Canny 엣지로 추출해 흑백 선화를 만든다.
외부 패키지: pillow (pip install pillow) 만 필요.

사용:
  python3 tools/mask_to_lineart.py                      # 전체 17권역
  python3 tools/mask_to_lineart.py --ids MAP_02 MAP_08  # 특정 권역만
  python3 tools/mask_to_lineart.py --preview            # 미리보기(저장하지 않음)
"""
import argparse
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASKS  = ROOT / "assets" / "maps" / "masks"
GUIDES = ROOT / "assets" / "maps" / "guides"
OUT    = ROOT / "assets" / "maps" / "lineart"


# ---------------------------------------------------------------- 경량 PNG 읽기/쓰기 (pillow 없으면 폴백)
def _read_png_raw(path):
    """pillow 없이 24-bit RGB PNG 를 (w, h, pixels[y][x] = (r,g,b)) 로 읽는다."""
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', "PNG 아님"
    w = struct.unpack('>I', data[16:20])[0]
    h = struct.unpack('>I', data[20:24])[0]
    bit, ctype = data[24], data[25]
    assert bit == 8 and ctype == 2, f"24-bit RGB PNG 만 지원 (bit={bit} ctype={ctype})"
    idat = b""
    i = 8
    while i < len(data) - 4:
        length = struct.unpack('>I', data[i:i+4])[0]
        chunk  = data[i+4:i+8]
        if chunk == b'IDAT':
            idat += data[i+8:i+8+length]
        i += 12 + length
    raw = zlib.decompress(idat)
    stride = w * 3 + 1
    pixels = []
    for y in range(h):
        row_data = raw[y * stride + 1:(y + 1) * stride]
        row = [(row_data[x*3], row_data[x*3+1], row_data[x*3+2]) for x in range(w)]
        pixels.append(row)
    return w, h, pixels


def _write_png_gray(path, w, h, gray):
    """gray: list[list[int 0-255]] → 8-bit greyscale PNG 저장"""
    raw = b""
    for row in gray:
        raw += b'\x00' + bytes(row)
    compressed = zlib.compress(raw, 6)
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    path.write_bytes(data)


# ---------------------------------------------------------------- PIL 우선 사용
try:
    from PIL import Image, ImageFilter, ImageDraw
    USE_PIL = True
except ImportError:
    USE_PIL = False


def mask_to_lineart(mask_path: Path, out_path: Path, *, blur=2, edge_strength=1.5,
                    add_grid=True, preview=False):
    """
    마스크 → 선화 변환 (흑배경, 흰 선).
    채널 경계(통행불가/수계/산악/평지) 사이 에지를 추출.
    add_grid: 1/8 격자선(대동여지도 목판 사각형 격자 재현)
    """
    GUIDE = GUIDES / mask_path.name.replace("_mask.png", "_relief.png")

    if USE_PIL:
        img = Image.open(mask_path).convert("RGB")
        w, h = img.size
        r, g, b = img.split()
        # 채널 R 기준 경계 강조: 수계(32~95 → 파란색)와 산악(96~191 → 녹색) 경계
        import array

        def channel_edge(ch, lo, hi):
            """ch 에서 lo~hi 범위를 255, 나머지 0으로 이진화 후 윤곽"""
            mask_img = ch.point(lambda p: 255 if lo <= p <= hi else 0)
            return mask_img.filter(ImageFilter.FIND_EDGES)

        water_edge  = channel_edge(r, 32, 95)
        mtn_edge    = channel_edge(r, 96, 191)
        road_edge   = channel_edge(r, 192, 255)

        from PIL import ImageChops, ImageEnhance
        combined = ImageChops.lighter(ImageChops.lighter(water_edge, mtn_edge), road_edge)
        combined = ImageEnhance.Contrast(combined).enhance(edge_strength)
        combined = combined.filter(ImageFilter.GaussianBlur(radius=max(0.5, blur - 1)))
        gray = combined.convert("L")

        # 대동여지도 목판 격자 추가 (10리 = 200px 기준)
        if add_grid:
            grid = Image.new("L", (w, h), 0)
            draw = ImageDraw.Draw(grid)
            grid_px = max(100, w // 38)  # 38칸 ≈ 대동여지도 1:1 비율
            for x in range(0, w, grid_px):
                draw.line([(x, 0), (x, h)], fill=60, width=1)
            for y in range(0, h, grid_px):
                draw.line([(0, y), (w, y)], fill=60, width=1)
            gray = ImageChops.lighter(gray, grid)

        # relief 밑그림이 있으면 희미하게 합성
        if GUIDE.exists():
            relief = Image.open(GUIDE).convert("L").resize((w, h), Image.LANCZOS)
            relief = ImageEnhance.Brightness(relief).enhance(0.18)
            gray = ImageChops.lighter(gray, relief)

        if preview:
            gray.show(title=mask_path.stem)
            return
        out_path.parent.mkdir(parents=True, exist_ok=True)
        gray.save(out_path, "PNG", optimize=True)
    else:
        # PIL 없을 때 간이 구현
        print(f"  pillow 없음 — 간이 변환 사용 (pip install pillow 로 품질 향상 가능)")
        w, h, pixels = _read_png_raw(mask_path)
        gray = []
        for y in range(h):
            row = []
            for x in range(w):
                r_val = pixels[y][x][0]
                # 채널 경계 검출 (이웃 픽셀과 비교)
                diffs = []
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = max(0, min(h-1, y+dy)), max(0, min(w-1, x+dx))
                    # 같은 채널 범위에 있으면 0, 다른 범위면 255
                    def bucket(v):
                        if v < 32: return 0
                        if v < 96: return 1
                        if v < 192: return 2
                        return 3
                    diffs.append(0 if bucket(r_val) == bucket(pixels[ny][nx][0]) else 255)
                v = min(255, int(sum(diffs) * edge_strength))
                row.append(v)
            gray.append(row)
        if not preview:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            _write_png_gray(out_path, w, h, gray)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", nargs="*", help="권역 id 필터 (예: MAP_02 MAP_08)")
    ap.add_argument("--blur", type=float, default=2.0, help="엣지 흐리기 (클수록 부드러움, 기본 2)")
    ap.add_argument("--strength", type=float, default=1.5, help="엣지 강도 (기본 1.5)")
    ap.add_argument("--no-grid", action="store_true", help="격자선 제외")
    ap.add_argument("--preview", action="store_true", help="미리보기만 (저장 안 함, pillow 필요)")
    a = ap.parse_args()

    masks = sorted(MASKS.glob("map_*_mask.png"))
    if a.ids:
        keep = {f"map_{i.lower().replace('map_','')}_mask.png" for i in a.ids}
        masks = [m for m in masks if m.name in keep]
    if not masks:
        print("마스크 파일 없음:", MASKS)
        return

    try:
        import pip  # noqa
    except ImportError:
        pass

    ok = 0
    for mask in masks:
        rid = mask.stem.replace("_mask", "")         # map_01
        out = OUT / f"{rid}_lineart.png"
        print(f"  {'미리보기' if a.preview else '변환'}: {mask.name} → {out.name if not a.preview else '화면'}")
        try:
            mask_to_lineart(mask, out, blur=a.blur, edge_strength=a.strength,
                            add_grid=not a.no_grid, preview=a.preview)
            ok += 1
        except Exception as e:
            print(f"  ✗ {e}")
    if not a.preview:
        print(f"\n완료: {ok}/{len(masks)}장 → {OUT.relative_to(ROOT)}/")
        print("다음: python3 tools/comfy_batch.py maps --use-lineart")


if __name__ == "__main__":
    main()
