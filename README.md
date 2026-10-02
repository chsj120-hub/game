# 《대동여지도 어드벤처: 삼한팔도 유람기》 (가제) — Godot 4 프로젝트

조선 팔도 오픈월드 탐험 & 지리 전략 CTB RPG. 초기 기획안과 **완전판 통합 기획서**를 합쳐, 데이터 드리븐 구조로 시스템 전체를 연결한 플레이어블 골격입니다.
기획 충돌 정리, 보상 자동 공식, 신분 곡선, 성장 곡선은 **[docs/DESIGN.md](docs/DESIGN.md)** 에 있습니다.

## 실행
1. Godot **4.3 이상**에서 `project.godot`을 엽니다(Compatibility 렌더러). F5를 누르면 직업 선택(어사·상인·도사) 화면이 나옵니다.
2. 조작: `M` 대동여지도, 휠 줌·드래그 팬·노드 클릭으로 목적지 지정, `Space` 행군 긴급 정지. 하단 HUD에서 야영·탐색·채집·사냥과 거점 시설을 씁니다.
3. 저장은 **대도시 주막**에서만 됩니다(숙박하면 자동 체크포인트).

## 파일 위치 · Godot에 적용하기
| 경로 | 내용 |
|---|---|
| `project.godot` | Godot 프로젝트 파일(오토로드 등록 포함) |
| `scenes/` · `scripts/` · `shaders/` | 씬, GDScript, 셰이더 |
| `data/` | 런타임 데이터 JSON(00~22). 수치는 `data/00_overview.json`에 모여 있음 |
| `data_src/` | 기획자가 수정하는 원천 표 |
| `tools/` | Python 생성·검증·시뮬레이터 |
| `docs/DESIGN.md` | 전체 설계서(충돌 정리, 공식, 명성·엽전·전투 밸런스) |
| `docs/DB15_점검보고서.md` · `data_src/db15/` | DB-15 데이터셋 점검 보고서 · 원본/수정본 xlsx · 게임 스키마 변환 JSON. 재생성 순서: `python3 tools/db15/audit_fix.py` → `tools/db15/merge_companions.py`(동료 67명·승급 퀘스트 병합) → `tools/economy_sim.py --write` → `tools/validate_data.py` · `tools/balance_sim.py` · `tools/db15/balance_check.py` |
| `assets/ASSET_MANIFEST.json` · `assets/PROMPTS.csv` | 넣어야 할 에셋 목록과 이미지 생성 프롬프트 |

적용 순서:
1. 압축 파일을 풀고 Godot 4.3 이상을 실행합니다.
2. 프로젝트 관리자에서 **가져오기(Import)** → `project.godot`을 고릅니다.
3. 렌더러는 **Compatibility**로 둡니다.
4. 처음 열면 리소스를 임포트합니다. 끝나면 F5로 실행합니다.
5. 한글이 네모(□)로 보이면 한글 폰트(.ttf/.otf)를 `assets/fonts/`에 넣습니다. 그다음 프로젝트 설정 → GUI → Theme → Custom Font에 지정합니다.
6. 데이터를 고쳤다면 아래 파이프라인을 다시 돌립니다(Python 3.9 이상).

## 데이터 파이프라인
**에셋 만들기:** [docs/에셋_제작_가이드_2025.md](docs/에셋_제작_가이드_2025.md) — 구글 AI 스튜디오(브라우저 무설치)와 Comfy Desktop(맥 앱)을 단계별로 설명합니다. 모든 프롬프트는 `assets/prompts/*.csv`에 미리 만들어져 있습니다(총 1,786건). 파일이 없어도 게임이 대체 그림으로 실행됩니다.

**고치는 법 한눈에:** [docs/수정_가이드.md](docs/수정_가이드.md) — 값·문구는 `tools/overrides.py`(where · set · unset · copy · list)로 `data_src/overrides/`에 기록합니다. `data/*.json`은 생성 결과이므로 직접 고치지 않습니다.

**한 번에 실행:** `python3 tools/run_pipeline.py` (전체 약 33초) · `--fast` (전투 시뮬 생략, 약 17초) · `--terrain` (지형 마스크 재생성 포함) · `--from 단계`

**시나리오 추가:** `data_src/scenarios/*.json` 파일 하나가 1편입니다. [docs/시나리오_작성_가이드.md](docs/시나리오_작성_가이드.md)를 보고 `tools/scenario_tool.py`(nodes · new · check)로 작성합니다.

**대화·서사 수정:** 동료 영입·승급, 고등급 장비·탈것, 특산물 비전 전수, 국보급 전설 퀘스트의 대사와 선택지는 `tools/gen_story.py`가 초안을 만듭니다. 고친 내용은 `data_src/story/edits/`에만 두면 초안을 다시 만들어도 사라지지 않습니다. `tools/story_tool.py`(list · show · edit · export · import · check)를 쓰고, 엑셀(`docs/대화_서사.xlsx`)로 왕복할 수도 있습니다. [docs/대화_서사_편집_가이드.md](docs/대화_서사_편집_가이드.md)

```
data_src/world_table.json, heritage_curated.json   ← 기획자가 수정하는 원천 (완전판 3.3 노드 표 + 분류 보정 + 은닉 노드)
        │  python3 tools/import_heritage450.py 국가유산 448·공식/이벤트 노드(data_src/heritage450/*.xlsx) 중복·좌표·지명 검증 → import.json
        │  python3 tools/build_world.py       17권역·763노드·도로/국경/뱃길 + 유산 721종 + 보상 아이템 자동 생성
        │        [--report] 배치 간격·고증 노드 슬롯 리포트  [--period] 고증 대체 후보로 교체(좌표·id 고정)
        │  python3 tools/craft_trade_update.py  무역품 등급 사슬(상품·진상품)·곡물 말 단위·요리 고증·공용 재료군/상위 대체 적용
        │  python3 tools/content_expand.py    이벤트·권역 적·무예 장비·탈것·김만덕 시나리오·튜토리얼·도움말(23 시트)
        │  python3 tools/gen_systematic.py    4·5등급 유불선 세트 24 · 모작 24 · 포획구 20
        │  python3 tools/overrides.py apply   data_src/overrides/*.json 사람이 고친 값·새 행을 생성 결과 위에 덮어쓰기(되돌리기 기록)
        │  python3 tools/gen_story.py         대화·서사 443건 + 비전 전수 61 · 전설 83 퀘스트 + 유산별 미니게임 변형 481 → 24_story (edits 병합)
        ▼
data/00~24 *.json, regions.json                    ← 런타임 데이터 (DataDB 가 로드)
        │  python3 tools/economy_sim.py --write   명성 총량·진행 몬테카를로 → 신분 임계·도 명성 요건 기록, 엽전 여유 점검
        │        (기본 = 실제 데이터 개수로 보정, --plan = 계획 수량 content_plan 기준 비교)
        │  python3 tools/travel_sim.py            이동 시간·피로·탐색 반경 측정
        │  python3 tools/trade_sim.py             자유 무역(시장 매매) 수익 상한 — 콘텐츠 수입 대비
        │  python3 tools/balance_sim.py           CTB v2 보스 클러치 몬테카를로(3클래스) — 실패 시 exit 1
        │  python3 tools/validate_data.py         교차 참조·동선 큐·규칙 검증 — 실패 시 exit 1
        │  python3 tools/gen_asset_manifest.py    assets/ASSET_MANIFEST.json · PROMPTS.csv · 폴더 생성
        │  python3 tools/export_xlsx.py           docs/데이터셋_전체.xlsx (전 시트 + 목차·재검증)
        │  python3 tools/report_heritage450.py    docs/국가유산450_반영_점검.xlsx (충돌·수정 내역·등급·보상)
        │  python3 tools/gen_terrain.py --jobs 8  노드가 바뀌면 권역 마스크·밑그림 재생성(투영 변경)
```
Python 3.9 이상이면 되고 외부 패키지는 필요 없습니다. 수치는 `data/00_overview.json` 한 곳에만 있습니다.

## 구조
```
scripts/autoload   DataDB(시트·그래프) · Balance(모든 공식) · Assets(선택적 에셋 로더) · GameState(진행·생존·시간·지식·저장)
scripts/systems    Dialogue(대화 조건·효과·화자·서사 조회) · Survival(속도·피로·포만·질병·휴식) · Travel(경로·역참·뱃길·조우) · Heritage(답사·3택) · RouteQueue(동선 큐)
                   Trade(5일장·시세·무역·투자) · Crafting(비전서·모작·단조) · Companion(막사·파견·포획 스택) · Event(이벤트·Fail-safe)
                   SideSystems(탐색·채집·사냥·봉수·화첩·현상수배·세시풍속·탁본) · Facility(시설 행동 목록)
scripts/battle     Combatant · CTBEngine(게이지 1000·AP·상성·상태이상, balance_sim.py 와 1:1) · BattleView(7턴 타임라인)
scripts/world      TravelController(실시간 행군·10리 틱·5px 도착 판정·마스크 샘플링)
scripts/minigames  전투 4종(궁술·팔괘·씨름·제령) + 범용 6종(퀴즈·게이지·슬라이딩·획순·탁본·타이밍) → 카탈로그 21종 매핑
scripts/ui         Main(SubViewport·CanvasLayer 분리, 시설 모달 상태 머신, 대화 대기열) · DialogueView(배경·상반신·하단 대화창·가운데 선택지) · FieldView · MapModal · Dashboard
```

## 구현 범위(완전판 대응)
| 완전판 | 구현 |
|---|---|
| 1.1 2:1 화면·HUD | 상단 SubViewport(1920×720), 하단 CanvasLayer HUD 4영역(초상·칭호·인장 / HP·피로·이속·AP / 야영·탐색·채집·사냥 / 지도·배낭·장착·도감) |
| 1.2 지도 모달 | 줌 100~300%, 팬, 반경 3.8% 자석 흡착, 주황 펄스 점선 경로와 리(里)·소요 시간·뱃삯 표시, Space 정지, 5px 도착 시 [진입]/[외곽 통과] 분기 |
| 2 3계층 맵 | 전국(17권역) → 권역 노드맵 → 마스크맵(파일이 있으면 픽셀 샘플링) |
| 3 노드 | 상시 7유형 + 은닉 7유형 + 확장 1(위험 고개). 원문 표 전수 반영, 분류 오류 22건 보정, 은닉 노드 51곳·봉수 17곳 추가 |
| 4 이동·생존 | 최종 속도 공식, 10리 틱마다 피로(4단계)·포만(허기·아사 후송)·신선도, 악천후 질병, 과적, 밤 횃불 |
| 5 거점 시설 | 관아(승급 심사·봉납·공문·수배·탁본)·주막(숙박·저장·조리·막사)·역참(마필 교체·쾌속 이동)·5일장·대장간(단조 미니게임)·서점(지식 강독)·나루터(풍향·요금)·온천·명찰·병영·봉수 |
| 6 미니게임 | 5대 분류 16종 + 범종·탁본·단조·인양·진설 → 21종 카탈로그, 지식 랭크당 제한시간 +3%, 국가유산청 공공데이터 필드(`public_data`) |
| 7 성장·지식·CTB | 레벨 없는 성장(HP 100→250), 유·불·선 상성 1.5배 + 지식 +8%/랭크, 사농공상 효과와 5랭크 패시브 4종, 게이지 1000·AP·7턴 예측 |
| 8 동료·막사 | 전장에는 주인공 1명. 동료 스킬은 주인공 스킬 목록에 합쳐지고 동료 1명당 AP 최대 +1·회복 +1(3명이면 최대 8·회복 5). AP가 남으면 한 턴에 여러 번 행동하고 **[턴 종료 ▶]**로 넘김. 동료마다 턴당 1스킬. **동료 67명은 1~3등급으로 영입해 서사 맞춤 승급 퀘스트 201건으로 최대 5등급**(승급마다 스킬 숙련 +8%·대표 지식 +1). 지식 합산·짐 무게 가산(스탯 합산 없음), 막사 10→30슬롯, 사농공상 파견 4종, 중복 포획 스택 1~5성 |
| 명성·도시 | 답사 명성 35% 보장 + 기증 65%, 도(道) 명성으로 도시 발전 5단계 해금, 메인 N장 = Rank N, 5장 완료 = 엔딩 |
| 엽전 | 수입 공식은 그대로. **감영 9곳 5단계 발전 = 필수 지출**(단계마다 도 전체 구매 −2%·숙박 −10%·쾌속 이동 −8%·막사 +2, 5단계에 도 명성 +10%). 나머지 28개 도시 발전은 선택(해당 도시 구매 −3%·판매 +2%) |
| 9 저장·Fail-safe | 대도시 주막 전용 저장, 기한 30일 후 관군 수습(감점 없음·포고문으로 도감 등록), 봉쇄 시 무료 우회로 |
| 대화·서사 | 노드 배경 위 인물 상반신(최대 3명, 말하는 사람만 밝게) + 하단 대화창(타자기 효과) + 가운데 선택지. 조건을 채우지 못한 선택지는 비활성으로 두고 사유(예: 「상(商) 지식 3 필요」)를 보여 줌. 퀘스트는 수락·동선 노드 도착·완료 때마다 장면 재생, 이벤트 단계도 같은 대화로 진행 |
| 새 퀘스트 | 특산물 **비전 전수** 61(유산 비전서를 기증·매각한 뒤의 두 번째 길, 명성 0.3배·엽전 0) · 국보급 **전설** 83(같은 권역 3~4노드 동선을 따라가야 그 유산을 답사할 수 있음, 보상 0) |
| 미니게임 변형 | 유산 481곳이 분류에 맞는 미니게임을 받음(도자 → 파편 맞추기, 비·석탑 → 탁본, 불상·범종 → 타종, 금속 → 단조, 전적·건축 → 유산 문답, 무덤 → 진설, 침몰선 → 인양 …). 문항·크기·명중대·점 배치·판목은 유산마다 다르고 등급이 오를수록 어려움 |
| 보조 4선 | 김홍도·신윤복 화첩 14장면, 관아 현상수배(5일 갱신), 24절기 세시풍속, 대동여지도 22첩 탁본 |

## 검증 결과
- `validate_data.py`: **PASS** — 레코드 2,996건, 오류 0, 경고 0, 동선 큐 491건 검증(동료 영입·승급, 비전 전수, 전설 포함). 대화 장면 2,234개와 선택지 1,390개의 화자·조건·효과 키도 함께 검사합니다.
- `balance_sim.py`: **PASS**(동료 통합 전투 모델, 어사 / 상인 / 도사).
  - 동료는 신분까지 승급을 마친 상태로 가정(Rank 3 클러치 3등급, Rank 5 세트 5등급).
  - 4등급 보스를 Rank 3 클러치 세팅으로: 평균 승률 88 / 83 / 71%(불가사리·이무기·산신), 16.0 / 15.7 / 14.7턴, 승리한 전투의 최저 HP 15~17%.
  - 5등급 원본 세트: 승률 99 / 97 / 94%. 4등급 세트로 도전하면 27 / 26 / 27%.
  - 일반 필드 전투: 적 1~2마리 99~100%, 3마리 59~73%.
- `economy_sim.py` 엽전(수입 ÷ 필수 지출 약 235,163냥): 기증형 1.47 / 균형형 1.93 / 매각형 2.85. 나머지 28개 도시까지 전부 올리면 0.59~1.14배라서 고르고 골라서 투자해야 합니다.
- `economy_sim.py`: 명성 총량(반복 제외) 최대 562,546 / 기준 421,640 / 최소 351,187(비전 전수 퀘스트 포함).
  - 신분 임계 0 / 4,000 / 19,000 / 47,500 / 90,500 ≈ 4,027·(L−1)^2.245. 균형형이 콘텐츠 1/3을 찾으면 Rank 5(엔딩 가능).
  - 도(道) 명성 5단계 요건은 도 콘텐츠 2/3 시점 기준(균형형 70% 달성). 도별 값은 `docs/DESIGN.md` §3-4.
- `travel_sim.py`: 전국 종단 도보 첫길 391초 / 익숙한 길 195초 / 준마 243초, 전 노드 답사 순수 이동 약 1.1시간.
- **GDScript는 이 환경에 Godot이 없어 에디터로 파싱·실행해 보지 못했습니다.** 대신 다음을 확인했습니다.
  - 클래스 간 멤버 참조 정적 교차 점검(33파일)
  - Variant 타입 추론 위험 구문 제거
  - 파싱이 불안정한 여러 줄 람다를 메서드로 교체

  처음 열 때 출력 패널에 오류가 나오면 알려 주세요.

## 데이터 커버리지 (현재 / 목표)
완비된 시트:
- 포획구 20, 음식 레시피 18, 비전서 24, 모작 24, 연속전투 8, 클래스 3, 미니게임 21

부분 반영(같은 스키마로 행을 추가한 뒤 `validate_data.py`를 실행하면 됩니다):
- 국가유산 144/450, 장착 67/205, 특산물 32/136, 식량 15/105, 적 21/42, 동료 14/65, 스킬 68/346
- 유산은 노드만 추가하고 `build_world.py`를 실행하면 보상 아이템까지 자동으로 생깁니다.

---

## 에셋 삽입 사양

**원칙: 파일이 없으면 게임이 절차적 그리기로 대체합니다.** 규격대로 아래 경로에 넣기만 하면 코드 수정 없이 바로 반영되고, 어떤 순서로 넣어도 됩니다.
전체 목록(644건, 파일마다 경로·규격·용도·보유 여부)은 `assets/ASSET_MANIFEST.json`에 있습니다. `python3 tools/gen_asset_manifest.py`를 다시 실행하면 새로 넣은 파일의 보유 여부가 갱신되고, 데이터가 늘어나면 목록도 같이 늘어납니다.

### 경로와 규격
| 분류 | 경로 패턴 | 크기 | 형식 · Godot 임포트 | 대체(파일 없을 때) |
|---|---|---|---|---|
| 권역 지도 | `assets/maps/regions/map_01.png` ~ `map_17.png` | 3840×2160 | PNG 8-bit 무손실 · Lossless, Filter Linear, Mipmaps off | 한지색 + 10리 방안 격자 |
| 지형 마스크 | `assets/maps/masks/map_01_mask.png` ~ | 3840×2160 (지도와 1:1) | PNG 24-bit · **Lossless, Filter Nearest, sRGB off** | 간선 속성(road/mountain/water/trail) |
| 전국 지도 | `assets/maps/overworld.png` | 1400×2000 권장 | PNG | 권역 점·인접선 |
| 패럴랙스 | `assets/parallax/map_nn/far.png` · `mid.png` · `near.png` | 1920×720, 좌우 심리스 | PNG 32-bit(상단 투명) · Repeat Enabled | 절차적 수묵 산세 |
| 전투 배경 | `assets/battle/bg_map_nn.png` | 1920×720 | PNG/WebP | 단색 배경 |
| 캐릭터 스프라이트 | `assets/characters/hero_cls_eosa/walk.png`, `idle.png` · `characters/<동료 id>/walk.png` | 프레임 128×128, **가로 8프레임(1024×128)** | PNG 32-bit 투명 | 도형 캐릭터 |
| 초상화 | `assets/portraits/hero_cls_eosa.png` · `<동료 id>.png` · `<적 id>.png` | 512×640 | PNG 32-bit | 갓 쓴 실루엣 / 슬롯 색상 |
| 아이템 아이콘 | `assets/icons/items/<아이템 id>.png` | 256×256, 단색 한지 배경 | PNG · Mipmaps on | 텍스트 |
| 유산 아이콘 | `assets/icons/heritage/her_###.png` | 256×256 | PNG | 텍스트 |
| 답사록 공통 | `assets/icons/common/icon_scroll_jokja.png` | 256×256 | PNG | 텍스트 |
| 노드 마커 | `assets/ui/markers/<유형>.png` (city town station temple spring fort beacon stupa tomb scenic wreck ruin seowon shrine hazard) | 64×64 | PNG 투명 | 유형별 색 원 |
| 상태이상 아이콘 | `assets/ui/status/<stun·poison·bleed·burn·fear·curse·charm·frost·shoeless>.png` | 64×64 | PNG 투명 | 텍스트 |
| 직업 아이콘 · 인장 | `assets/ui/class/cls_*.png` · `assets/ui/seals/rank_1~5.png` | 128×128 · 64×64 | PNG | 붉은 낙관 사각형 |
| 패널(9-패치) | `assets/ui/panels/modal.png` · `dashboard_frame.png`(1920×360) | 64~512 정사각, 여백 24px | PNG | StyleBoxFlat / 한지 셰이더 |
| 미니게임 | `assets/minigames/sliding/sumuk_01.png`, `celadon_01.png` · `assets/minigames/takbon/sheet_01~22.png` | 1024×1024 · 1600×1000 | PNG | 번호 타일 / 절차적 먹선 |
| 한글 글꼴 | `assets/fonts/` (예: NotoSansKR, 나눔명조) | — | TTF/OTF → 프로젝트 설정 GUI > Theme > Custom Font | OS 기본 글꼴 |

### 지형 마스크 채널 인코딩
완전판 2.2는 R 채널 설명에 RGB 색상을 섞어 써서 채널끼리 뜻이 겹칩니다. 그래서 아래처럼 정했습니다.

| 채널 | 값 | 의미 |
|---|---|---|
| **R** | 0–31 | 통행불가(절벽·심해) |
| | 32–95 | 수계(선박 필요, M_terrain 0.85) |
| | 96–191 | 산악·고개(0.65, 조우 +15%) |
| | 192–255 | 관로·평지(1.0) |
| **G** | 0–255 | 위험도(조우율에 최대 +10% 가산) |
| **B** | ≥128 | 나루·도하 지점 |

### 실제 지형 → 마스크·밑그림 (`tools/gen_terrain.py`)
```
bash tools/fetch_geo.sh                 # 원자료 → data_src/geo_raw/ (git 제외, 약 1GB)
python3 tools/gen_terrain.py --jobs 8    # 17권역 약 3분 (--regions MAP_08, --scale 1 = 원해상도 계산)
```
권역마다 다음 파일을 만듭니다(모두 3840×2160).
- `assets/maps/masks/map_nn_mask.png`: 위 채널 규칙을 따르는 마스크입니다. 고도·경사·수계(바다·하천·호수)·해안 거리로 계산합니다.
- `assets/maps/guides/map_nn_relief.png`: 고도 음영 밑그림입니다. ControlNet lineart/canny나 img2img에 넣어 해안선과 산줄기 구도를 고정합니다.
- `assets/maps/guides/map_nn_height.png`: 고도를 흑백으로 담은 그림입니다. depth 입력용입니다.
- `assets/maps/guides/map_nn_layout.png` (1920×1080): 노드와 도로를 겹친 확인용 그림입니다.
- `terrain_report.json`: 통계와 바다 위 노드 경고입니다.

원자료는 모두 퍼블릭 도메인입니다.
- 남한: NASA SRTM1(30 m)
- 북한: USGS GTOPO30(약 0.9 km). 해상도가 낮아서 북부 권역은 밑그림이 부드럽게 나옵니다.
- 하천·호수: Natural Earth 10m

### 노드 좌표 (실제 위경도 투영)
`data_src/node_geo.json`에는 노드 311개의 `[위도, 경도, 신뢰도]`가 들어 있습니다. 신뢰도 A는 위치가 확실한 곳, B는 근사, C는 역참·봉수처럼 추정한 곳입니다.

`build_world.py`는 권역마다 등장방형 투영으로 노드 범위를 3840×2160(여백 260/220)에 맞춥니다. 노드 사이 간격은 최소 150px을 유지합니다. 은닉지는 부모 거점 기준 방향은 실제대로 두고 거리만 150–420px로 제한합니다.

투영 정보는 `regions[].geo_projection`에, 보정으로 옮겨진 거리는 `nodes[].geo_shift_km`에 기록합니다. 좌표를 고친 뒤에는 `build_world.py`를 다시 실행하고 이어서 `gen_terrain.py`를 실행하세요.

### 이미지 생성 프롬프트
- `assets/prompts/<배치>.csv`: 22개 파일, 728건입니다. 아이콘은 분류별로, 초상은 주인공·동료·적으로 나누었고, 지도·패럴랙스·전투배경·스프라이트·마커·미니게임은 각각 한 파일입니다.
  - `prompt` = 본문 + **복식 고증**(인물) + **공통 스타일** + 규격 꼬리
  - `negative` = 공통 금지어(청·일본 복식, 사실사진, 애니 등) + 종류별 금지어
- 문구 사전은 `tools/prompt_lib.py`에 있습니다. 배경 연도는 1861년입니다. 그보다 앞 시대 인물(고구려·신라·고려 등)은 그 시대 복식을 씁니다.
- 일괄 생성은 `tools/comfy_batch.py`(ComfyUI 로컬 API)로 합니다. 초심자용 따라 하기는 [`docs/AI_에셋_제작_가이드.txt`](docs/AI_에셋_제작_가이드.txt)를 보세요.
- `assets/PROMPTS.csv`: 구 형식 아이콘 424건입니다(호환용). `path` 열에 적힌 경로에 그대로 저장하면 됩니다.

### 공공데이터
유산마다 `public_data`(제공 국가유산청, 공공누리 제1유형, `ccbaKdcd` · `ccbaAsno` · `ccbaCtcd` · `source_url` · `description`)가 빈칸으로 준비되어 있습니다. 채워 넣으면 도감에 출처가 자동으로 표시됩니다.
