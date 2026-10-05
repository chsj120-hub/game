#!/usr/bin/env python3
"""ComfyUI 일괄 생성기 — assets/prompts/*.csv 를 읽어 ComfyUI(로컬 API)로 이미지를 만들고 CSV의 path 위치에 바로 저장한다.

추가 설치 없음(파이썬 3.8+ 표준 라이브러리만 사용). 쉬운 설명은 docs/AI_에셋_제작_가이드.txt 참고.

자주 쓰는 명령
  python3 tools/comfy_batch.py --check                         연결·모델 확인 + 추천 프리셋 안내
  python3 tools/comfy_batch.py --preset mini16                 맥 미니 메모리별 추천 설정(mini8 / mini16 / standard)
  python3 tools/comfy_batch.py --set ckpt=sd_xl_base_1.0.safetensors   설정 저장(tools/comfy_config.json)
  python3 tools/comfy_batch.py maps --ids MAP_08 --test 4      스타일 시험: 시드 4개 → assets/_drafts/
  python3 tools/comfy_batch.py maps                            본 생성(이미 있는 파일은 건너뜀)
  python3 tools/comfy_batch.py icons_weapon icons_armor --limit 5
  python3 tools/comfy_batch.py all                             sprites 를 뺀 전체
"""
import argparse
import csv
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "assets" / "prompts"
GUIDES = ROOT / "assets" / "maps" / "guides"
LINEART = ROOT / "assets" / "maps" / "lineart"
DRAFTS = ROOT / "assets" / "_drafts"
CONFIG = Path(__file__).resolve().parent / "comfy_config.json"
LOG = PROMPTS / "_generated_log.csv"

DEFAULTS = {
    "server": "auto",                 # auto = 8000(ComfyUI Desktop) → 8188(일반 설치) 순서로 찾음
    "ckpt": "sd_xl_base_1.0.safetensors",
    "controlnet": "controlnet-union-sdxl-promax.safetensors",
    "upscaler": "RealESRGAN_x4plus.pth",   # 없으면 "" → 단순 확대(lanczos)
    "lora": "", "lora_strength": 0.8,
    "steps": 30, "cfg": 6.0, "sampler": "dpmpp_2m", "scheduler": "karras", "seed": 1861,
    "style_weight": 1.15,             # 공통 화풍 문구 가중치(1.0 = 그대로)
    "map_edge_strength": 0.8,         # 지도: 음영 밑그림 윤곽(canny) 고정 강도
    "map_depth_strength": 0.5,        # 지도: 고도(depth) 고정 강도
    "canny_low": 0.15, "canny_high": 0.45,
    "low_memory": False,              # True = 작은 해상도로 생성(GTX 1060 6GB 등)
}

# 컴퓨터별 추천 묶음 (--preset 이름) — 맥 미니 M1/M2 기준으로 조정
PRESETS = {
    "mini8":    {"low_memory": True, "steps": 22, "map_depth_strength": 0.0},   # 맥 미니 메모리 8GB: 작은 해상도·depth 끔
    "mini16":   {"low_memory": True, "steps": 25, "map_depth_strength": 0.5},   # 맥 미니 메모리 16GB 이상
    "standard": {"low_memory": False, "steps": 30, "map_depth_strength": 0.5},  # 메모리 32GB 이상(M1 Max·M2 Pro 등)
    "gtx3060":  {"low_memory": False, "steps": 30, "map_depth_strength": 0.6,  # GTX 3060 12GB VRAM CUDA
                 "sampler": "dpmpp_2m", "scheduler": "karras", "cfg": 7.0},
    "rtx4060":  {"low_memory": False, "steps": 30, "map_depth_strength": 0.6,  # RTX 4060 8GB VRAM CUDA
                 "sampler": "dpmpp_2m", "scheduler": "karras", "cfg": 7.0},
}

# kind → (생성 폭, 높이), (저메모리 폭, 높이), (최종 폭, 높이)  — 모두 최종 비율과 정확히 같음
SIZES = {
    "region_map": ((1536, 864), (1024, 576), (3840, 2160)),
    "overworld":  ((840, 1200), (560, 800), (1400, 2000)),
    "parallax":   ((1536, 576), (1024, 384), (1920, 720)),
    "battle_bg":  ((1536, 576), (1024, 384), (1920, 720)),
    "portrait":   ((896, 1120), (768, 960), (512, 640)),
    "icon":       ((1024, 1024), (768, 768), (256, 256)),
    "marker":     ((1024, 1024), (768, 768), (64, 64)),
    "minigame":   ((1024, 1024), (768, 768), (1024, 1024)),
    "takbon":     ((1280, 800), (896, 560), (1600, 1000)),
}
SKIP_KINDS = {"sprite": "8프레임 보행 시트는 AI 한 번으로 일관되게 나오지 않아 제외합니다(가이드 7단계 참고)."}
STYLE_KEY = "Joseon-era Korean ink-and-wash painting (sumukchaesaek) on aged hanji mulberry paper"
EXTRA_NEG = "hangul text, chinese characters, letters, calligraphy text, frame, border"


# ---------------------------------------------------------------- 설정
def load_cfg():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def save_cfg(cfg):
    CONFIG.write_text(json.dumps({k: cfg[k] for k in DEFAULTS}, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_value(v):
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return v


# ---------------------------------------------------------------- 서버 통신
class Comfy:
    def __init__(self, server):
        self.base = self._find(server)
        self.client = uuid.uuid4().hex

    @staticmethod
    def _find(server):
        cands = [server] if server != "auto" else ["http://127.0.0.1:8000", "http://127.0.0.1:8188"]
        for c in cands:
            try:
                urllib.request.urlopen(c.rstrip("/") + "/system_stats", timeout=3).read()
                return c.rstrip("/")
            except Exception:
                continue
        sys.exit("✗ ComfyUI 에 연결하지 못했습니다. ComfyUI 를 먼저 켜 두세요.\n"
                 f"  찾아본 주소: {', '.join(cands)}\n"
                 "  주소가 다르면: python3 tools/comfy_batch.py --set server=http://127.0.0.1:포트번호")

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return r.read()

    def get_json(self, path):
        return json.loads(self.get(path))

    def options(self, node, field):
        try:
            info = self.get_json(f"/object_info/{node}")[node]["input"]["required"][field]
            opts = info[0] if isinstance(info[0], list) else info[1].get("options", [])
            return list(opts)
        except Exception:
            return []

    def upload(self, path, name):
        bnd = uuid.uuid4().hex
        body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
                f"--{bnd}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                f"Content-Type: image/png\r\n\r\n").encode() + Path(path).read_bytes() + f"\r\n--{bnd}--\r\n".encode()
        req = urllib.request.Request(self.base + "/upload/image", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            res = json.loads(r.read())
        return (res.get("subfolder") + "/" if res.get("subfolder") else "") + res["name"]

    def run(self, graph, timeout=3600):
        data = json.dumps({"prompt": graph, "client_id": self.client}).encode()
        req = urllib.request.Request(self.base + "/prompt", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                pid = json.loads(r.read())["prompt_id"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(explain_error(e.read().decode("utf-8", "replace")))
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(2)
            h = self.get_json(f"/history/{pid}")
            if pid not in h:
                continue
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                msgs = [m[1].get("exception_message", "") for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError("ComfyUI 실행 오류: " + " / ".join(msgs)[:600])
            for out in h[pid].get("outputs", {}).values():
                for im in out.get("images", []):
                    q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": im.get("type", "output")})
                    return self.get("/view?" + q)
            if st.get("completed"):
                raise RuntimeError("완료됐지만 결과 이미지가 없습니다.")
        raise RuntimeError("시간 초과")


def explain_error(txt):
    hint = ""
    if "ckpt_name" in txt:
        hint = " → 모델 파일 이름이 다릅니다. --check 로 목록을 보고 --set ckpt=파일이름 으로 맞추세요."
    elif "control_net_name" in txt:
        hint = " → ControlNet 파일 이름이 다릅니다. --set controlnet=파일이름"
    elif "model_name" in txt:
        hint = " → 확대 모델 파일이 없습니다. --set upscaler= (빈칸) 으로 끄거나 파일을 넣으세요."
    elif "lora_name" in txt:
        hint = " → LoRA 파일 이름이 다릅니다. --set lora=파일이름 (끄려면 --set lora=)"
    return "ComfyUI 가 작업을 거부했습니다: " + txt[:500] + hint


# ---------------------------------------------------------------- 프롬프트 손질
HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3400-\u9fff]+")


def clean_prompt(p, cfg):
    p = re.sub(r"\s--\w+(\s+[^\s-][^\s]*)?", "", p)          # Midjourney 꼬리(--ar 16:9 --style raw) 제거
    p = HANGUL.sub("", p)                                       # SDXL 은 한글·한자를 못 읽고 글자 얼룩을 그림 → 제거
    p = re.sub(r"(?<=[\s,(])[/·《》\-]+(?=[\s,)])", " ", p)       # 한글이 빠지고 남은 기호
    p = re.sub(r"\(\s*[,\s]*\)", "", p)                         # 비어 버린 괄호
    p = re.sub(r",\s*\d+:\d+\s*(?=,|$)", "", p)                    # "16:9" 같은 비율 표기(크기로 대신 지정)
    p = re.sub(r"\s*,\s*(,\s*)+", ", ", p)
    p = re.sub(r"\s{2,}", " ", p).strip(" ,")
    p = re.sub(r"^(portrait of|museum-quality illustration of)\s*,", r"\1", p)
    p = p.replace("(", "\\(").replace(")", "\\)")             # ComfyUI 에서 ( ) 는 가중치 기호 → 글자 그대로 쓰도록 이스케이프
    w = float(cfg["style_weight"])
    key = STYLE_KEY.replace("(", "\\(").replace(")", "\\)")
    if abs(w - 1.0) > 1e-3 and key in p:
        p = p.replace(key, f"({key}:{w:.2f})", 1)
    return p


# ---------------------------------------------------------------- 워크플로(ComfyUI 기본 노드만 사용)
def build_graph(cfg, pos, neg, gen, out, seed, guide=None, prefix="daedong"):
    g = {}
    nid = [0]

    def node(cls, **inputs):
        nid[0] += 1
        g[str(nid[0])] = {"class_type": cls, "inputs": inputs}
        return [str(nid[0]), 0]

    ck = node("CheckpointLoaderSimple", ckpt_name=cfg["ckpt"])
    model, clip, vae = ck, [ck[0], 1], [ck[0], 2]
    if cfg.get("lora"):
        lo = node("LoraLoader", model=model, clip=clip, lora_name=cfg["lora"],
                  strength_model=float(cfg["lora_strength"]), strength_clip=float(cfg["lora_strength"]))
        model, clip = lo, [lo[0], 1]
    p = node("CLIPTextEncode", text=pos, clip=clip)
    n = node("CLIPTextEncode", text=neg, clip=clip)
    if guide:
        cn = node("ControlNetLoader", control_net_name=cfg["controlnet"])
        relief = node("ImageScale", image=node("LoadImage", image=guide["relief"]), upscale_method="area",
                      width=gen[0], height=gen[1], crop="disabled")
        edge = node("Canny", image=relief, low_threshold=float(cfg["canny_low"]), high_threshold=float(cfg["canny_high"]))
        a = node("ControlNetApplyAdvanced", positive=p, negative=n,
                 control_net=node("SetUnionControlNetType", control_net=cn, type="canny/lineart/anime_lineart/mlsd"),
                 image=edge, strength=float(cfg["map_edge_strength"]), start_percent=0.0, end_percent=0.85)
        p, n = a, [a[0], 1]
        if guide.get("height") and float(cfg["map_depth_strength"]) > 0:
            depth = node("ImageScale", image=node("LoadImage", image=guide["height"]), upscale_method="area",
                         width=gen[0], height=gen[1], crop="disabled")
            b = node("ControlNetApplyAdvanced", positive=p, negative=n,
                     control_net=node("SetUnionControlNetType", control_net=cn, type="depth"),
                     image=depth, strength=float(cfg["map_depth_strength"]), start_percent=0.0, end_percent=0.7)
            p, n = b, [b[0], 1]
    lat = node("EmptyLatentImage", width=gen[0], height=gen[1], batch_size=1)
    s = node("KSampler", model=model, seed=int(seed), steps=int(cfg["steps"]), cfg=float(cfg["cfg"]), sampler_name=cfg["sampler"],
             scheduler=cfg["scheduler"], positive=p, negative=n, latent_image=lat, denoise=1.0)
    img = node("VAEDecode", samples=s, vae=vae)
    if out[0] > gen[0] * 1.3 and cfg.get("upscaler"):
        img = node("ImageUpscaleWithModel", upscale_model=node("UpscaleModelLoader", model_name=cfg["upscaler"]), image=img)
    if tuple(out) != tuple(gen) or (out[0] > gen[0] * 1.3 and cfg.get("upscaler")):
        img = node("ImageScale", image=img, upscale_method="lanczos" if out[0] >= gen[0] else "area",
                   width=out[0], height=out[1], crop="disabled")
    node("SaveImage", images=img, filename_prefix=prefix)
    return g


# ---------------------------------------------------------------- 실행
def read_rows(batches):
    files = sorted(PROMPTS.glob("*.csv")) if batches == ["all"] else []
    for b in batches:
        if b == "all":
            continue
        hit = sorted(PROMPTS.glob(f"{b}.csv")) or sorted(PROMPTS.glob(f"{b}*.csv"))
        if not hit:
            sys.exit(f"✗ 배치 '{b}' 가 없습니다. 목록: " + ", ".join(p.stem for p in sorted(PROMPTS.glob('[!_]*.csv'))))
        files += hit
    rows = []
    for f in dict.fromkeys(files):
        if f.name.startswith("_"):
            continue
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                r["_batch"] = f.stem
                rows.append(r)
    return rows


def size_for(row, cfg):
    key = "takbon" if row["id"].startswith("takbon_") else row["kind"]
    gen, low, out = SIZES[key]
    return (low if cfg["low_memory"] else gen), out


def check(cfg):
    c = Comfy(cfg["server"])
    print(f"✓ ComfyUI 연결: {c.base}")
    stats = c.get_json("/system_stats")
    mem = 0
    for d in stats.get("devices", []):
        mem = max(mem, d.get("vram_total", 0) / 2**30)
        print(f"  장치: {d.get('name')} · 메모리 {d.get('vram_total', 0) / 2**30:.1f} GB")
    if mem:
        rec = "mini8" if mem < 12 else ("gtx3060" if cfg.get("server","").startswith("http://127.0.0.1") and mem < 14 else "mini16" if mem < 28 else "standard")
        cur = next((k for k, v in PRESETS.items() if all(cfg.get(x) == y for x, y in v.items())), None)
        print(f"  추천 설정: {rec}" + ("  (적용됨)" if cur == rec else f"  → python3 tools/comfy_batch.py --preset {rec}"))
    ok = True
    for label, node, field, key in (("기본 모델", "CheckpointLoaderSimple", "ckpt_name", "ckpt"),
                                    ("ControlNet", "ControlNetLoader", "control_net_name", "controlnet"),
                                    ("확대 모델", "UpscaleModelLoader", "model_name", "upscaler"),
                                    ("LoRA", "LoraLoader", "lora_name", "lora")):
        opts = c.options(node, field)
        want = cfg.get(key)
        mark = "✓" if (not want or want in opts) else "✗"
        if mark == "✗" and key in ("ckpt", "controlnet"):
            ok = False
        print(f"  {mark} {label}: 설정값 '{want or '(사용 안 함)'}'")
        print(f"      폴더에 있는 파일: {', '.join(opts) if opts else '(없음)'}")
    for node in ("Canny", "SetUnionControlNetType", "ImageUpscaleWithModel"):
        try:
            c.get_json(f"/object_info/{node}")[node]
            print(f"  ✓ 노드 {node}")
        except Exception:
            ok = False
            print(f"  ✗ 노드 {node} 없음 → ComfyUI 를 최신으로 업데이트하세요.")
    print("준비 완료!" if ok else "✗ 위 표시(✗)를 먼저 해결하세요.")


def main():
    ap = argparse.ArgumentParser(description="assets/prompts/*.csv → ComfyUI 일괄 생성")
    ap.add_argument("batches", nargs="*", help="배치 이름(maps, parallax, icons_weapon, icons … 앞부분만 써도 됨) 또는 all")
    ap.add_argument("--ids", nargs="*", help="특정 id만 (예: MAP_08 MAP_17)")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만")
    ap.add_argument("--test", type=int, default=0, help="스타일 시험: 시드 N개씩 assets/_drafts/ 에 저장")
    ap.add_argument("--seed", type=int, help="이번 실행에만 쓸 시드")
    ap.add_argument("--overwrite", action="store_true", help="이미 있는 파일도 다시 생성")
    ap.add_argument("--use-lineart", action="store_true", help="지도: guides/ 대신 lineart/ 선화를 ControlNet 입력으로 사용")
    ap.add_argument("--dry-run", action="store_true", help="생성하지 않고 할 일과 프롬프트만 출력")
    ap.add_argument("--check", action="store_true", help="연결·모델 파일 점검")
    ap.add_argument("--set", nargs="*", metavar="키=값", help="설정 저장 (예: --set cfg=6.5 seed=42 low_memory=true)")
    ap.add_argument("--show", action="store_true", help="현재 설정 보기")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="컴퓨터별 추천 설정 저장: mini8 / mini16 / standard")
    a = ap.parse_args()

    cfg = load_cfg()
    if a.preset:
        cfg.update(PRESETS[a.preset])
        save_cfg(cfg)
        print(f"✓ 추천 설정 '{a.preset}' 적용:", ", ".join(f"{k}={v}" for k, v in PRESETS[a.preset].items()))
    if a.set:
        for kv in a.set:
            k, _, v = kv.partition("=")
            if k not in DEFAULTS:
                sys.exit(f"✗ 모르는 설정 '{k}'. 가능: {', '.join(DEFAULTS)}")
            cfg[k] = parse_value(v) if v != "" else ""
        save_cfg(cfg)
        print("✓ 저장:", CONFIG)
    if a.show or a.set:
        print(json.dumps(cfg, ensure_ascii=False, indent=1))
    if a.check:
        return check(cfg)
    if not a.batches:
        if not (a.set or a.show):
            ap.print_help()
        return

    rows = read_rows(a.batches)
    if a.ids:
        rows = [r for r in rows if r["id"] in a.ids]
    todo, skipped = [], {}
    for r in rows:
        if r["kind"] in SKIP_KINDS:
            skipped[r["kind"]] = skipped.get(r["kind"], 0) + 1
            continue
        todo.append(r)
    for k, n in skipped.items():
        print(f"· {k} {n}건 건너뜀: {SKIP_KINDS[k]}")
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        return print("할 일이 없습니다.")

    seeds = [a.seed if a.seed is not None else int(cfg["seed"])]
    if a.test:
        seeds = seeds + [random.randint(1, 2**31) for _ in range(a.test - 1)]
    jobs = []
    for r in todo:
        for sd in seeds:
            if a.test:
                dest = DRAFTS / r["_batch"] / f"{r['id']}_seed{sd}.png"
            else:
                dest = ROOT / r["path"].replace("res://", "")
            if dest.exists() and not a.overwrite:
                continue
            jobs.append((r, sd, dest))
    done_before = len(todo) * len(seeds) - len(jobs)
    print(f"생성 {len(jobs)}건" + (f" (이미 있어 건너뜀 {done_before}건 — 다시 만들려면 --overwrite)" if done_before else ""))
    if a.dry_run:
        for r, sd, dest in jobs[:20]:
            gen, out = size_for(r, cfg)
            print(f"\n[{r['id']}] {gen[0]}x{gen[1]} → {out[0]}x{out[1]} · seed {sd} → {dest.relative_to(ROOT)}")
            print("  +", clean_prompt(r["prompt"], cfg))
            print("  -", r.get("negative", "") + ", " + EXTRA_NEG)
        return

    c = Comfy(cfg["server"])
    print(f"ComfyUI: {c.base} · 모델 {cfg['ckpt']}" + (" · 저메모리" if cfg["low_memory"] else ""))
    uploaded, t_all, fails = {}, time.time(), []
    new_log = not LOG.exists()
    logf = open(LOG, "a", encoding="utf-8-sig", newline="")
    log = csv.writer(logf)
    if new_log:
        log.writerow(["time", "id", "path", "seed", "ckpt", "lora", "steps", "cfg", "seconds"])
    try:
        for i, (r, sd, dest) in enumerate(jobs, 1):
            gen, out = size_for(r, cfg)
            guide = None
            if r["kind"] == "region_map":
                rid = r["id"].lower()
                # --use-lineart: 마스크→선화를 Canny 입력으로 (좌표 일치)
                # 기본: gen_terrain 이 만든 음영 밑그림(relief/height)을 ControlNet 입력으로
                if a.use_lineart:
                    la = LINEART / f"{rid}_lineart.png"
                    if not la.exists():
                        print(f"  ! {la.name} 없음 → 먼저: python3 tools/mask_to_lineart.py --ids {r['id']}")
                    else:
                        if la not in uploaded:
                            print(f"  선화 올리는 중: {la.name}")
                            uploaded[la] = c.upload(la, f"daedong_{la.name}")
                        guide = {"relief": uploaded[la]}  # height 없이 선화만 사용
                else:
                    rel, hei = GUIDES / f"{rid}_relief.png", GUIDES / f"{rid}_height.png"
                    if not rel.exists():
                        print(f"  ! {rel.name} 없음 → 밑그림 없이 생성(마스크와 어긋남). 먼저 python3 tools/gen_terrain.py")
                    else:
                        for p in (rel, hei):
                            if p.exists() and p not in uploaded:
                                print(f"  밑그림 올리는 중: {p.name}")
                                uploaded[p] = c.upload(p, f"daedong_{p.name}")
                        guide = {"relief": uploaded[rel], "height": uploaded.get(hei)}
            pos = clean_prompt(r["prompt"], cfg)
            neg = (r.get("negative", "") + ", " + EXTRA_NEG).strip(", ")
            t0 = time.time()
            print(f"[{i}/{len(jobs)}] {r['id']} {r.get('name_kr', '')} · {gen[0]}x{gen[1]}→{out[0]}x{out[1]} · seed {sd}", flush=True)
            try:
                png = c.run(build_graph(cfg, pos, neg, gen, out, sd, guide, prefix=f"daedong/{r['id']}"))
            except RuntimeError as e:
                print("  ✗", e)
                fails.append(r["id"])
                if "거부" in str(e):
                    break
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(png)
            dt = time.time() - t0
            log.writerow([time.strftime("%Y-%m-%d %H:%M"), r["id"], str(dest.relative_to(ROOT)), sd, cfg["ckpt"], cfg["lora"], cfg["steps"], cfg["cfg"], round(dt)])
            logf.flush()
            left = (time.time() - t_all) / i * (len(jobs) - i)
            print(f"  ✓ {dest.relative_to(ROOT)} ({dt:.0f}초, 남은 예상 {left / 60:.0f}분)")
    except KeyboardInterrupt:
        print("\n중단했습니다. 같은 명령을 다시 실행하면 이어서 만듭니다.")
    finally:
        logf.close()
    if fails:
        print(f"실패 {len(fails)}건: {', '.join(fails)}")
    if a.test:
        print(f"시험 결과: {DRAFTS.relative_to(ROOT)}/ — 마음에 드는 파일 이름의 seed 숫자를 --set seed=숫자 로 저장하세요.")


if __name__ == "__main__":
    main()
