#!/usr/bin/env python3
"""나노 바나나(Google AI Studio) 일괄 입력용 텍스트 묶음 생성기.

API 없이 나노 바나나 채팅창에 직접 붙여 넣을 프롬프트 블록을 만든다.
배치가 크면 N개씩 나눠서 파일로 저장한다.

사용:
  python3 tools/nano_export.py scenes                     → docs/nano_prompts/scenes.txt
  python3 tools/nano_export.py portraits_npc portraits_hero
  python3 tools/nano_export.py battle_bg parallax markers
  python3 tools/nano_export.py all                        → icons 제외 전체
  python3 tools/nano_export.py --list                     → 사용 가능한 배치 목록

  --chunk 10    한 파일에 최대 N장 (기본 10장, 나노 바나나는 한 번에 너무 많으면 일부 건너뜀)
  --format md   마크다운 (기본: txt 순번 목록)
"""
import argparse
import csv
import glob
import textwrap
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "assets" / "prompts"
OUT    = ROOT / "docs" / "nano_prompts"

# 종류별 나노 바나나 지시문 앞부분
PREAMBLE = {
    "default": (
        "Please generate the following images. "
        "Create each image described below, using the exact style specified. "
        "For each image, the filename to save it as is shown in brackets."
    ),
    "scenes": (
        "Please generate {n} background images for a visual novel game set in Joseon Dynasty Korea (1861). "
        "Each image should be in 16:9 landscape orientation. "
        "Keep the lower quarter of the image calm and uncluttered — it will be covered by a dialogue box. "
        "Do NOT include any people, characters, or text in these backgrounds."
    ),
    "portraits_npc": (
        "Please generate {n} half-body portrait illustrations of Joseon Dynasty characters for a visual novel game. "
        "All portraits: 4:5 ratio, plain aged hanji paper background, half-length (waist up), "
        "three-quarter view, calm expression. No text, no frame."
    ),
    "portraits_hero": (
        "Please generate {n} protagonist portrait illustrations for a Joseon Dynasty RPG game. "
        "4:5 ratio. Half-length portrait, three-quarter view, hanji paper background."
    ),
    "portraits_companion": (
        "Please generate {n} companion character portrait illustrations for a Joseon Dynasty RPG. "
        "4:5 ratio. Half-length, three-quarter view, plain hanji background, dignified expression."
    ),
    "portraits_enemy": (
        "Please generate {n} enemy character portrait illustrations for a Joseon Dynasty RPG battle screen. "
        "4:5 ratio. Half-length, slightly menacing expression, hanji background."
    ),
    "battle_bg": (
        "Please generate {n} battle stage background images for a Joseon Dynasty RPG. "
        "16:9 landscape. Clear flat ground in the lower third for character sprites. No characters shown."
    ),
    "parallax": (
        "Please generate {n} seamless side-scrolling parallax layer images for a Joseon Dynasty game. "
        "8:3 ratio (wide horizontal strip). The left and right edges must tile seamlessly. "
        "Upper portion transparent-ready (sky above). No characters."
    ),
    "markers": (
        "Please generate {n} small icon/emblem images for map markers in a Joseon Dynasty game. "
        "Square 1:1 ratio. Bold readable silhouette at small size. Transparent or plain background."
    ),
    "minigames": (
        "Please generate {n} illustration images for minigame screens in a Joseon Dynasty game. "
        "Square 1:1 ratio. Flat frontal composition filling the frame."
    ),
    "minigames_heritage": (
        "Please generate {n} artifact illustration images for sliding puzzle minigames in a Joseon Dynasty game. "
        "Square 1:1 ratio. Frontal view of the artifact, filling most of the frame."
    ),
}

SUFFIX = {
    "default": (
        "\n\nFor ALL images above:\n"
        "- Style: Joseon-era Korean ink-and-wash painting (sumukchaesaek) on aged hanji mulberry paper\n"
        "- Colors: muted mineral pigments — malachite green, azurite blue, ochre, cinnabar red, ink black\n"
        "- Technique: confident brush strokes with dry-brush texture, soft paper grain\n"
        "- Do NOT include any text, signatures, watermarks, or modern elements\n"
        "- Strictly traditional Joseon period (1392–1897), no anachronisms"
    )
}

NANO_ICONS_NOTE = (
    "※ 아이콘 1,391건은 ComfyUI 일괄 생성을 권장합니다 (나노 바나나로는 시간이 너무 오래 걸립니다).\n"
    "   ComfyUI 명령: python3 tools/comfy_batch.py icons_weapon icons_armor ... --preset gtx3060\n"
)


def get_preamble(batch, n):
    text = PREAMBLE.get(batch, PREAMBLE["default"])
    return text.format(n=n)


def format_block(rows, batch, chunk_idx, total_chunks):
    lines = []
    pream = get_preamble(batch, len(rows))
    lines.append(pream)
    if total_chunks > 1:
        lines.append(f"(Batch {chunk_idx}/{total_chunks})")
    lines.append("")

    for i, r in enumerate(rows, 1):
        save_as = r["path"].replace("res://", "").split("/")[-1]
        lines.append(f"{i}. [{save_as}]  {r['name_kr']}")
        # prompt에서 공통 스타일 꼬리 제거 (공통으로 suffix에 적으므로)
        p = r["prompt"]
        for cut in ["Joseon-era Korean ink-and-wash painting", "sumukchaesaek"]:
            idx = p.find(cut)
            if idx > 10:
                p = p[:idx].rstrip(", ")
                break
        lines.append(f"   → {p}")
        if r.get("negative"):
            neg = r["negative"][:120]
            lines.append(f"   ✕ avoid: {neg}")
        lines.append("")

    lines.append(SUFFIX["default"])
    lines.append("")
    lines.append(f"Save each image with the filename shown in brackets [ ] above.")
    return "\n".join(lines)


def read_batch(batch):
    hits = sorted(PROMPTS.glob(f"{batch}.csv")) or sorted(PROMPTS.glob(f"{batch}*.csv"))
    rows = []
    for f in hits:
        if f.name.startswith("_"):
            continue
        rows += list(csv.DictReader(open(f, encoding="utf-8-sig")))
    return rows


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def list_batches():
    csvs = sorted(PROMPTS.glob("[!_]*.csv"))
    icons = [f for f in csvs if f.stem.startswith("icons")]
    others = [f for f in csvs if not f.stem.startswith("icons")]
    print("=== 나노 바나나 권장 배치 ===")
    for f in others:
        rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
        print(f"  {f.stem:<30} {len(rows):4}건")
    print()
    print("=== ComfyUI 권장 배치 (아이콘류 대량) ===")
    for f in icons:
        rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
        print(f"  {f.stem:<30} {len(rows):4}건")
    print()
    print(NANO_ICONS_NOTE)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("batches", nargs="*")
    ap.add_argument("--chunk", type=int, default=10, help="한 파일에 최대 N장 (기본 10)")
    ap.add_argument("--format", choices=["txt", "md"], default="txt")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list or not a.batches:
        list_batches()
        return

    OUT.mkdir(parents=True, exist_ok=True)
    NANO_BATCHES = ["scenes", "portraits_npc", "portraits_hero", "portraits_companion",
                    "portraits_enemy", "battle_bg", "parallax", "markers",
                    "minigames", "minigames_heritage", "sprites"]

    batches_to_run = []
    if "all" in a.batches:
        batches_to_run = NANO_BATCHES
    else:
        batches_to_run = a.batches

    total_files = 0
    for batch in batches_to_run:
        if batch.startswith("icons"):
            print(f"⚠  {batch}: 아이콘 대량 배치는 ComfyUI 사용 권장")
            print(f"   python3 tools/comfy_batch.py {batch} --preset gtx3060")
            continue
        rows = read_batch(batch)
        if not rows:
            print(f"✗ '{batch}' CSV 없음")
            continue
        parts = list(chunks(rows, a.chunk))
        for ci, part in enumerate(parts, 1):
            suffix = f"_part{ci}" if len(parts) > 1 else ""
            fname = f"{batch}{suffix}.txt"
            text = format_block(part, batch, ci, len(parts))
            (OUT / fname).write_text(text, encoding="utf-8")
            total_files += 1
            print(f"✓ {fname} ({len(part)}장{f', {len(parts)}개 파일 중 {ci}번' if len(parts)>1 else ''})")

    if total_files:
        print(f"\n저장 위치: docs/nano_prompts/ ({total_files}개 파일)")
        print("사용법: 파일을 열어 내용을 나노 바나나 채팅창에 붙여 넣습니다.")
        print("생성된 이미지는 assets/ 아래 path 열의 경로에 파일명을 맞춰 저장하세요.")
