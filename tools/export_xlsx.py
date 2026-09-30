#!/usr/bin/env python3
"""게임 데이터셋 전체(data/*.json)를 엑셀 한 파일로 내보내고, 다시 읽어 모든 시트·행이 빠짐없이 들어갔는지 검증한다.

출력: docs/데이터셋_전체.xlsx
  목차        시트별 원본 파일·키·행/열 수·신규(노랑) 행 수·검증 결과
  NN_키       표 형태 데이터(행 = 레코드, 열 = 필드). 중첩 값(목록·사전)은 JSON 문자열로 한 칸에
  00_개요     00_overview.json 을 '경로 | 값' 으로 펼침
  기타_설정   각 파일의 표가 아닌 설정 블록을 '파일 | 경로 | 값' 으로 펼침
  노랑 행 = 이번 개편으로 추가·교체된 행(generated = craft_trade / content2, 고을 1등급 유산)
사용: python3 tools/export_xlsx.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "db15"))
import xlsx_io  # noqa: E402
from common import DATA, ROOT  # noqa: E402

OUT = ROOT / "docs" / "데이터셋_전체.xlsx"
NEW_TAGS = {"craft_trade", "content2"}
CELL_MAX = 32000


def cell(v):
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    elif v is None:
        s = ""
    else:
        return v
    return s if len(s) <= CELL_MAX else s[:CELL_MAX] + "…(잘림)"


def is_new(row, key):
    return row.get("generated") in NEW_TAGS or (key == "heritage" and row.get("node_type") == "town")


def flatten(obj, prefix=""):
    """설정 블록 → [(경로, 값)] (스칼라·스칼라 목록은 한 칸, 표 목록은 JSON 한 칸)"""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict) and v:
                out += flatten(v, p)
            else:
                out.append((p, cell(v)))
    else:
        out.append((prefix, cell(obj)))
    return out


def table_rows(rows):
    cols = []
    for r in rows:
        for k in r:
            if k not in cols and k != "_sheet":
                cols.append(k)
    return [cols] + [[cell(r.get(c, "")) for c in cols] for r in rows]


def build():
    sheets, marks, toc, expect = [], {}, [], {}
    extra = [["파일", "경로", "값"]]
    for f in sorted(DATA.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        no = f.stem.split("_")[0]
        if f.stem == "00_overview":
            rows = [["경로", "값"]] + [list(x) for x in flatten(doc)]
            sheets.append(("00_개요", rows))
            toc.append(["00_개요", f.name, "(전체 펼침)", len(rows) - 1, 2, 0, "00_개요"])
            expect["00_개요"] = len(rows) - 1
            continue
        for key, v in doc.items():
            if isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
                name = f"{no}_{key}"[:31] if no.isdigit() else f"{f.stem}_{key}"[:31]
                rows = table_rows(v)
                new = [i for i, r in enumerate(v, 1) if is_new(r, key) or f.stem == "23_tutorial"]   # 23 = 신규 시트
                if new:
                    marks[name] = {"changed": {(i, c) for i in new for c in range(len(rows[0]))}}
                sheets.append((name, rows))
                toc.append([name, f.name, key, len(v), len(rows[0]), len(new), name])
                expect[name] = len(v)
            elif key == "_schema":
                extra.append([f.name, "_schema", v])
            else:
                for p, val in flatten(v, key):
                    extra.append([f.name, p, val])
    sheets.append(("기타_설정", extra))
    toc.append(["기타_설정", "(각 파일)", "표가 아닌 설정 블록", len(extra) - 1, 3, 0, "기타_설정"])
    expect["기타_설정"] = len(extra) - 1
    return sheets, marks, toc, expect


def verify(path, expect, sheets):
    got = xlsx_io.read(path)
    res = {}
    for name, rows in sheets:
        g = got.get(name[:31])
        if g is None:
            res[name] = "✗ 시트 없음"
            continue
        n = len(g) - 1
        ids_ok = True
        if rows and rows[0] and rows[0][0] == "id":   # id 열 전체 일치
            ids_ok = [r[0] for r in g[1:]] == [r[0] for r in rows[1:]]
        res[name] = "✓" if n == expect[name] and ids_ok else f"✗ 행 {n}/{expect[name]}{'' if ids_ok else ' · id 불일치'}"
    return res


def main():
    sheets, marks, toc, expect = build()
    head = [["시트", "원본 파일", "키", "행 수", "열 수", "신규·교체 행(노랑)", "검증(다시 읽기)"]]
    body = [r[:6] + ["(확인 중)"] for r in toc]
    all_sheets = [("목차", head + body)] + sheets
    OUT.parent.mkdir(exist_ok=True)
    xlsx_io.write(OUT, all_sheets, marks=marks)
    res = verify(OUT, expect, sheets)
    body = [r[:6] + [res[r[0]]] for r in toc]
    all_sheets[0] = ("목차", head + body + [[], ["합계", f"{len(sheets)}개 시트", "", sum(r[3] for r in toc), "", sum(r[5] for r in toc),
                                               "전부 ✓" if all(v == "✓" for v in res.values()) else "✗ 있음"]])
    xlsx_io.write(OUT, all_sheets, marks=marks)
    res2 = verify(OUT, expect, sheets)
    bad = {k: v for k, v in res2.items() if v != "✓"}
    print(f"{OUT.relative_to(ROOT)} — 시트 {len(sheets) + 1}개(목차 포함) · 레코드 {sum(r[3] for r in toc):,}행 · 신규·교체 {sum(r[5] for r in toc)}행")
    for r in toc:
        print(f"  {res2[r[0]]} {r[0]:<24} {r[3]:>5}행 × {r[4]:>2}열  (신규 {r[5]})  ← {r[1]}:{r[2]}")
    print("검증: 모든 시트·행·id 일치" if not bad else f"검증 실패: {bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
