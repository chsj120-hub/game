#!/usr/bin/env python3
"""국가유산 448 반영 점검 보고서(엑셀) — import_heritage450.py 판정 + build_world 등급 배정 + economy 보상 비교.
출력: docs/국가유산450_반영_점검.xlsx   사용: python3 tools/report_heritage450.py (build_world·economy_sim 뒤)"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "db15"))
import xlsx_io  # noqa: E402
from common import DATA, ROOT, SRC, load, tier_curve  # noqa: E402

REP = json.loads((SRC / "heritage450" / "report.json").read_text(encoding="utf-8"))
OUT = ROOT / "docs" / "국가유산450_반영_점검.xlsx"
ORDER = ["요약", "파일내_중복", "노드_중복병합", "게임유산_중복", "좌표_충돌", "좌표_지명불일치", "바다위_보정", "템플릿_유산",
         "시대_고증주의", "권역_경계확인", "유산_배치"]


def main():
    her = load("01_heritage.json")["heritage"]
    nodes = {n["id"]: n for n in load("regions.json")["nodes"]}
    ov = load("00_overview.json")
    E = ov["economy"]
    imp = [h for h in her if h.get("source") == "heritage450"]
    rows = [["id", "게임 이름", "원 이름", "지정(게임)", "원 등급", "게임 등급", "분류", "계열", "노드", "노드 유형", "은닉", "보상", "권역"]]
    for h in imp:
        rows.append([h["id"], h["name"], h.get("orig_name", h["name"]), h["designation"], h["src_tier"], h["tier"], h["category"], h["faction"],
                     nodes[h["node"]]["name"], h["node_type"], h["hidden"], h["reward"], h["region"]])
    rew = [["등급", "원본 명성", "원본 엽전", "게임 기준 명성(기증·건축)", "게임 기준 엽전(매각·건축)", "반영 유산 수", "전체 유산 수"]]
    src = {3: (150, 300), 4: (200, 400), 5: (250, 500)}
    for t in range(1, 6):
        rew.append([t, src.get(t, ("", ""))[0], src.get(t, ("", ""))[1], round(tier_curve(E["heritage_rep"], t) * E["category_mult"]["architecture"]["rep"]),
                    round(tier_curve(E["heritage_money"], t) * E["category_mult"]["architecture"]["money"]),
                    sum(1 for h in imp if h["tier"] == t), sum(1 for h in her if h["tier"] == t)])
    rk = ov["rank"]
    rew += [["—"], ["신분 임계(재보정)", *[r["threshold"] for r in rk["table"]]],
            ["보정 기준", rk.get("calibration_basis", {}).get("basis", ""), "유산 등급 분포", str(Counter(h["tier"] for h in her))]]
    summary = REP["요약"] + [["반영 후 유산 수", len(her)], ["반영 후 노드 수", f"{len(nodes)} (은닉 {sum(1 for n in nodes.values() if n['hidden'])})"],
                           ["한 노드 여러 유산", sum(1 for n in nodes.values() if n.get("heritage_ids"))],
                           ["발견 조건 은닉지", sum(1 for n in nodes.values() if n.get("discover"))]]
    sheets = [("요약", summary)] + [(k, REP[k]) for k in ORDER[1:] if REP.get(k)] + [("등급_배정", rows), ("보상_비교", rew)]
    xlsx_io.write(OUT, sheets)
    got = xlsx_io.read(OUT)
    bad = [n for n, r in sheets if len(got.get(n[:31], [])) != len(r)]
    print(f"{OUT.relative_to(ROOT)} — 시트 {len(sheets)}개 · 반영 유산 {len(imp)} · 검증 {'✓' if not bad else bad}")


if __name__ == "__main__":
    main()
