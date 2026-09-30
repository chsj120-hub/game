#!/usr/bin/env python3
"""데이터 파이프라인 한 번에 실행 — 순서·의존 관계를 지키고, 단계별 시간과 결과를 요약한다.

  python3 tools/run_pipeline.py            전체(빌드 → 보정 → 검증 → 시뮬 → 내보내기)
  python3 tools/run_pipeline.py --fast     시뮬레이션(전투·DB-15 밸런스) 생략 — 시나리오·데이터 문구만 고쳤을 때
  python3 tools/run_pipeline.py --terrain  노드 좌표가 바뀌었을 때 지형 마스크·밑그림도 재생성(약 3분)
  python3 tools/run_pipeline.py --from build_world   특정 단계부터
실패하면 그 단계에서 멈추고 마지막 출력 20줄을 보여 준다. 병렬 시뮬 코어 수: 환경 변수 SIM_JOBS (기본 = CPU 수).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (이름, 인자, 종류)  종류: build 데이터 생성 · check 검증 · sim 시뮬 · out 내보내기
STEPS = [
    ("import_heritage450", [], "build"),       # 국가유산 448 원본 → import.json (좌표·중복 검증)
    ("build_world", [], "build"),              # 월드·유산·보상 아이템
    ("craft_trade_update", [], "build"),       # 무역·제작 개편
    ("content_expand", [], "build"),           # 이벤트·적·장비·탈것 + data_src/scenarios/*.json 시나리오
    ("gen_systematic", [], "build"),           # 4·5등급 세트·모작·포획구
    ("db15/audit_fix", [], "build"),           # DB-15 원본 점검(동료 병합 전제)
    ("db15/merge_companions", [], "build"),    # 동료·스킬 병합
    ("gen_story", [], "build"),                # 대화·서사 초안 + data_src/story/edits 병합 → 24_story (레시피·전설 퀘스트, 미니게임 변형)
    ("economy_sim", ["--write", "--players", "300"], "build"),   # 신분 임계·도 명성 요건 재보정(데이터에 기록)
    ("validate_data", [], "check"),
    ("balance_sim", ["--trials", "150"], "sim"),
    ("db15/balance_check", ["--trials", "200"], "sim"),
    ("travel_sim", [], "check"),
    ("trade_sim", [], "check"),
    ("gen_asset_manifest", [], "out"),
    ("export_xlsx", [], "out"),
    ("story_tool", ["export"], "out"),         # docs/대화_서사.xlsx (대사·선택지 한 줄씩 — 고친 뒤 story_tool import)
    ("report_heritage450", [], "out"),
    ("db15/audit_fix", [], "out"),             # 점검 문구(신분 임계 인용)를 방금 보정한 값으로 갱신
]
TERRAIN = ("gen_terrain", ["--jobs", "8"], "out")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="전투·DB-15 밸런스 시뮬 생략")
    ap.add_argument("--terrain", action="store_true", help="지형 마스크·밑그림 재생성 포함")
    ap.add_argument("--from", dest="start", help="이 단계부터 실행")
    a = ap.parse_args()
    steps = STEPS + ([TERRAIN] if a.terrain else [])
    if a.start:
        names = [s[0] for s in steps]
        if a.start not in names:
            sys.exit(f"단계 이름: {', '.join(names)}")
        steps = steps[names.index(a.start):]
    total, rows = time.time(), []
    for name, args, kind in steps:
        if a.fast and kind == "sim":
            rows.append((name, "생략", 0.0))
            continue
        t0 = time.time()
        r = subprocess.run([sys.executable, str(ROOT / "tools" / f"{name}.py"), *args], cwd=ROOT, capture_output=True, text=True)
        dt = time.time() - t0
        out = (r.stdout + r.stderr).strip().splitlines()
        tail = next((x for x in reversed(out) if x.strip()), "")
        rows.append((name, "OK" if r.returncode == 0 else f"실패({r.returncode})", dt))
        print(f"  {'✓' if r.returncode == 0 else '✗'} {name:<22} {dt:6.1f}s  {tail[:90]}", flush=True)
        if r.returncode != 0:
            print("\n".join(out[-20:]))
            sys.exit(f"\n✗ {name} 에서 멈춤 — 위 메시지를 확인하세요.")
    print(f"\n전체 {time.time() - total:.1f}s · {sum(1 for r in rows if r[1] == 'OK')}단계 OK" + (" · 시뮬 생략(--fast)" if a.fast else ""))


if __name__ == "__main__":
    main()
