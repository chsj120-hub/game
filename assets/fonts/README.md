# 폰트 (고운·Noto = SIL OFL 1.1 · 나눔 = 나눔글꼴 라이선스 — 모두 게임에 포함·판매 가능, 폰트 단독 판매만 금지)

| 파일 | 용도 | 출처 | 라이선스 |
|---|---|---|---|
| GowunDodum-Regular.ttf | 기본 UI·HUD·메뉴 | github.com/yangheeryu/Gowun-Dodum | OFL_GowunDodum.txt |
| GowunBatang-Regular.ttf / -Bold.ttf | 본문·서사(RichTextLabel 일반/굵게) | github.com/yangheeryu/Gowun-Batang | OFL_GowunBatang.txt |
| NanumBrush.ttf (나눔손글씨 붓) | 제목·메뉴 머리말·칭호·지명 (`Assets.title()`) · 없는 글자는 고운바탕 Bold → Noto 순으로 대체 | 네이버 나눔글꼴 | 나눔글꼴 라이선스(글꼴 자체 판매 외 상업 사용 가능, 저작권 표기 권장) |
| NotoSerifKR-Regular.otf | 한자 대체(fallback) — 고운 계열에 없는 한자 133자 | github.com/notofonts/noto-cjk | OFL_NotoSerifKR.txt |

적용: `scripts/autoload/Assets.gd` `_apply_fonts()` 가 시작 시 창 전체 테마로 지정(파일이 없으면 엔진 기본 폰트).
게임 데이터(data/*.json)의 모든 글자가 고운돋움 + Noto Serif KR 로 표시됨을 확인함(미수록 이체자 㝵 → 碍 정규화).
