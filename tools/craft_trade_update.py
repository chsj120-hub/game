#!/usr/bin/env python3
"""제작·무역 개편 적용기 (docs/제작_무역_개편_제안.md 결정사항). 여러 번 실행해도 결과가 같다(idempotent).

  1) 무역품 등급 사슬: 기본 → 상품(grade 1) → 진상품(grade 2). 이름은 '○○ 상품/진상품', 도감에 실제 명칭(real_name)·설명(desc)
  2) 곡물 '말' 단위(1섬 = 10말, 섬 풀기) + 요리 1등급 폐지(→2등급) + 요리 재료 고증 수정
  3) 고증용 식재료 추가 — 공백 권역(경상 남부·황해 남부·평안·제주) 기본 무역품 겸 재료로 배치
  4) 같은 물건 중복 정리(인삼·대추·인제 황태), 미사용 재료 활용 요리/약/장비
  5) 공용 재료군 · 상위 재료 대체(기본 '확인') → 00_overview.crafting
사용: python3 tools/craft_trade_update.py   (이후 validate_data / gen_asset_manifest 등 파이프라인)
"""
from common import load, save

TAG = "craft_trade"
PRICE = {t: 20 * 3 ** (t - 1) for t in range(1, 6)}      # economy.price.base.specialty × growth^(t−1)

# ---------------------------------------------------------------- 1. 무역품 등급 사슬
# base id: (짧은 이름, [(상품 실제 명칭, 설명), (진상품 실제 명칭, 설명)])  — 등급 상한 5, premium(발전도>0) 기본은 상품까지
CHAIN = {
    "sp_jeonju_hanji": ("전주 한지", [("전주 장지(壯紙)", "두껍고 질겨 관아 문서·족자·창호에 쓰던 상등 한지."),
                                    ("전주 선자지(扇子紙)", "전주 선자청에서 진상 부채를 만들던 최상품 한지. 얇고 질기며 결이 곱다.")]),
    "sp_hansan_mosi": ("한산 모시", [("한산 세모시(열두새)", "열두새 이상으로 가늘게 짠 상품 모시."),
                                   ("한산 보름새 모시", "보름새(15새)로 짠 극상품. 잠자리 날개 같다 하여 진상되었다.")]),
    "sp_andong_po": ("안동포", [("안동포 아홉새", "아홉새로 곱게 짠 상품 삼베."),
                              ("안동 진상포(열두새)", "열두새로 짠 최상품 안동포. 궁중 진상과 수의감으로 귀히 쓰였다.")]),
    "sp_damyang_bamboo": ("담양 죽물", [("담양 참빗", "대오리를 가늘게 쪼개 만든 참빗. 담양·영암 참빗이 이름났다."),
                                     ("담양 채상(彩箱)", "물들인 대오리로 무늬를 엮은 상자. 혼수와 진상에 쓰였다.")]),
    "sp_yeonggwang_gulbi": ("영광 굴비", [("영광 오가재비 굴비", "조기 스무 마리를 두 줄로 엮어 말린 상품 굴비."),
                                       ("법성포 곡우 굴비", "곡우 무렵 잡은 알배기 참조기로 말린 진상 굴비.")]),
    "sp_gaeseong_insam": ("개성 인삼", [None,  # 상품 = 기존 개성 홍삼(sp_gaeseong_hongsam) 연결
                                     ("개성 진상 홍삼", "크고 곧은 뿌리만 골라 쪄 말린 진상·사행 예단용 상등 홍삼.")]),
    "sp_jeju_gamgyul": ("제주 감귤", [("제주 금귤·유감 봉진", "진상 귤 중 으뜸인 금귤·유감을 봉해 올린 것. 이것이 도착하면 성균관에서 황감제를 열었다.")]),
    "sp_hamgyeong_myeongtae": ("북관 명태", [("북관 북어(北魚)", "명태를 덕에 걸어 말려 오래 두고 먹게 한 것. 북관에서 삼남까지 팔려 나갔다."),
                                          ("북관 대태 북어", "큰 명태만 골라 말린 상등 북어(등급명은 설명적 명칭).")]),
    "sp_ganghwa_hwamunseok": ("강화 화문석", [("강화 용문석(龍紋席)", "용무늬를 넣어 짠 최상등 왕골 돗자리. 진상품으로 올렸다.")]),
    "sp_anseong_yugi": ("안성 유기", [("안성 방짜 유기", "구리와 주석을 녹여 메질로 두드려 만든 방짜. 잘 깨지지 않는다."),
                                   ("안성맞춤 유기", "주문에 맞춰 만든 진상 유기. '안성맞춤'이라는 말이 여기서 나왔다.")]),
    "sp_chuncheon_jat": ("춘천 잣", [("춘천 실백(實柏)", "껍질을 벗겨 낸 속 잣. 약식·전복초·신선로 고명에 쓴다."),
                                  ("춘천 진상 실백", "알이 굵고 기름진 것만 골라 올린 진상 실백잣.")]),
    "sp_uljin_daege": ("울진 대게", [("울진 살대게", "살이 꽉 찬 겨울 대게(등급명은 설명적 명칭)."),
                                  ("평해 진상 대게", "평해·울진에서 진상하던 큰 대게.")]),
    "sp_boeun_daechu": ("보은 대추", [("보은 알대추", "알이 굵고 단 보은 대추(설명적 명칭)."),
                                   ("보은 진상 대추", "보은 대추 중 진상하던 상등품. 약식·쌍화탕에 으뜸으로 쳤다.")]),
    "sp_gochang_bokbunja": ("고창 복분자주", [("고창 복분자 청주", "맑게 걸러 낸 복분자술(설명적 명칭)."),
                                           ("고창 복분자 진상주", "오래 묵혀 향이 깊은 상등 복분자술(설명적 명칭).")]),
    "sp_sangju_gotgam": ("상주 곶감", [("상주 둥시 곶감", "상주 토종 감 '둥시'로 말린 곶감."),
                                    ("상주 진상 건시(乾柿)", "흰 분이 곱게 핀 진상 곶감.")]),
    "sp_haeju_meok": ("해주 먹", [("해주 수양매월(首陽梅月) 먹", "해주 먹 가운데 가장 이름난 명품. 사신 예물로도 쓰였다.")]),
    "sp_bongsan_bae": ("봉산 참배", [("봉산 청실배", "껍질이 푸르고 물이 많은 토종 배."),
                                  ("봉산 진상 참배", "봉산 참배 중 크고 단 것만 골라 올린 진상품.")]),
    "sp_pyeongyang_chilgi": ("평양 칠기", [("평양 주칠(朱漆) 소반", "붉은 칠을 여러 번 올린 상등 소반(설명적 명칭).")]),
    "sp_uiju_dambi": ("의주 담비 가죽", [("의주 자초피(紫貂皮)", "짙은 자줏빛 담비 가죽. 담비 가죽 중 최상등으로 친다.")]),
    "sp_hoeryeong_oji": ("회령 오지그릇", [("회령 오지 항아리", "잿물 유약을 두껍게 입힌 상품 오지(설명적 명칭)."),
                                        ("회령 진상 오지", "회령 가마에서 골라 올린 상등 오지그릇(설명적 명칭).")]),
}

# ---------------------------------------------------------------- 3. 고증 식재료 겸 기본 무역품 (공백 권역 우선)
NEW_SPECIALTIES = [
    # id, 이름, 권역, 노드, 등급, 무게, 신선, 실제 명칭, 설명
    ("sp_chuncheon_jat", "춘천 잣", "MAP_03", "ND_03_CITY_CHUNCHEONBU", 1, 0.5, False, "춘천 백자(柏子)",
     "가평·춘천 잣나무 숲에서 거둔 잣. 약식·전복초·신선로의 고명으로 쓴다."),
    ("sp_pyeongyang_nokdu", "평양 녹두", "MAP_13", "ND_13_CITY_PYEONGYANGBU", 1, 1.0, False, "평양 녹두",
     "평양 녹두지짐(빈대떡)의 재료. 녹말을 앉혀 어만두·청포묵에도 쓴다."),
    ("sp_ongjin_daeha", "옹진 대하", "MAP_12", "ND_12_TOWN_ONGJIN", 1, 1.0, True, "옹진 대하(大蝦)",
     "황해 옹진 앞바다에서 잡은 큰 새우. 궁중 대하찜의 재료."),
    ("sp_uiju_jinmal", "의주 진말", "MAP_14", "ND_14_CITY_UIJUMOK", 1, 1.0, False, "의주 진말(眞末·밀가루)",
     "의주 만상의 청 교역과 서북 밭에서 들어온 밀가루. 조선에서는 귀해 잔치 음식에 썼다."),
    ("sp_gadeok_daegu", "가덕 대구", "MAP_10", "ND_10_TOWN_GIMHAE", 1, 1.0, False, "가덕 건대구(乾大口)",
     "가덕도 앞바다 대구를 말린 것. 진상품으로 이름났고 어만두·신선로의 흰살 생선으로 쓴다."),
    ("sp_jeju_malchong", "제주 말총", "MAP_17", "ND_17_CITY_JEJUMOKJEJUEUPSEONG", 1, 0.3, False, "제주 말총",
     "제주 말의 갈기·꼬리털. 통영·한양 갓방으로 팔려 가 갓·탕건·망건의 재료가 되었다."),
    ("sp_jeju_jeonbok", "제주 전복", "MAP_17", "ND_17_TOWN_DAEJEONGHYEON", 2, 0.5, False, "제주 추복(搥鰒)",
     "잠녀가 딴 전복을 두드려 말린 진상 전복. 전복초의 재료."),
    ("sp_hanyang_tarak", "타락", "MAP_02", "ND_02_CITY_HANYANGGYEONGJO", 2, 1.0, True, "타락(駝酪·우유)",
     "낙산 아래 유우소에서 짜던 우유. 궁중 타락죽의 재료로 한양에서만 구할 수 있다."),
    # 밸런스·공백 보강 특산 (2차)
    ("sp_namhae_yuja", "남해 유자", "MAP_10", "ND_10_TOWN_NAMHAE", 1, 1.0, True, "남해 유자(柚子)",
     "남해안 섬에서 나는 유자. 향이 짙어 청과 차로 담가 진상하였다."),
    ("sp_hadong_jakseol", "하동 작설차", "MAP_10", "ND_10_CITY_JINJUMOK", 2, 0.3, False, "지리산 작설차(雀舌茶)",
     "쌍계사 일대 야생 차나무의 어린 잎을 덖은 차. 참새 혀처럼 작은 잎이라 작설이라 불렀다."),
    ("sp_yeonan_chamgireum", "연안 참기름", "MAP_12", "ND_12_CITY_YEONANDOHOBU", 2, 1.0, False, "연안 진유(眞油·참기름)",
     "연안 평야의 참깨로 짠 기름. 비빔밥·나물·전에 두루 쓴다."),
    ("sp_jeju_miyeok", "제주 미역", "MAP_17", "ND_17_TOWN_JOCHEON", 1, 0.5, False, "제주 곽(藿·미역)",
     "잠녀가 물질로 딴 돌미역을 말린 것. 산모의 미역국에 쓰였다."),
]
PREMIUM_SPECIALTIES = [  # id, 이름, 권역, 노드, 등급, 발전도, 무게, 사슬, 실제 명칭, 설명
    ("sp_dongnae_waegwan", "동래 왜관 교역품", "MAP_10", "ND_10_CITY_DONGRAEHYEON", 3, 2, 1.0, None, "왜관 무역품(후추·단목·명반)",
     "초량 왜관 개시(開市)에서 들여온 후추·소목(단목)·명반. 동래 상인이 전국으로 넘겼다."),
    ("sp_ganggye_sam", "강계 삼", "MAP_14", "ND_14_TOWN_GANGGYE", 3, 1, 0.5, "ginseng", "강삼(江蔘)",
     "강계·폐사군 산골에서 캔 삼. 조선 후기 강계 삼은 개성 삼과 함께 으뜸으로 쳤다."),
]
CRAFTED = [  # 특산 제작품 + 비전서(무역 퀘스트 보상)
    {"sp": {"id": "sp_tongyeong_gat", "name": "통영 갓", "region": "MAP_10", "node": "ND_10_FORT_TONGYEONGTONGJEYEONG", "kind": "crafted", "tier": 3,
            "base_price": 540, "dev_level": 0, "weight": 0.5, "real_name": "통영 흑립(黑笠)",
            "desc": "제주 말총과 대오리로 결은 통영 갓. 통제영 12공방의 갓방에서 만들어 양반 사회 전체로 팔렸다."},
     "recipe": {"id": "spr_tongyeong_gat", "name": "【통영 갓방 비전서】", "tier": 3, "produces": "sp_tongyeong_gat", "facility": "gongbang",
                "materials": [{"id": "sp_jeju_malchong", "qty": 3}, {"id": "mat_bamboo", "qty": 2}, {"id": "mat_lacquer", "qty": 1}]}},
]
CRAFTED += [
    {"sp": {"id": "sp_haeju_songyeonmuk", "name": "해주 송연먹", "region": "MAP_12", "node": "ND_12_CITY_HAEJUMOK", "kind": "crafted", "tier": 3,
            "base_price": 540, "dev_level": 0, "weight": 0.3, "real_name": "해주 송연묵(松煙墨)",
            "desc": "송연을 어교와 반죽해 틀에 박고 오래 말린 먹. 해주 먹은 결이 곱고 향이 맑아 사대부와 사신 예물로 귀히 쓰였다."},
     "recipe": {"id": "spr_haeju_muk", "name": "【해주 먹방 비전서】", "tier": 3, "produces": "sp_haeju_songyeonmuk", "facility": "gongbang",
                "materials": [{"id": "mat_songyeon", "qty": 4}, {"id": "mat_fish_glue", "qty": 2}]}},
    {"sp": {"id": "sp_hansan_mosi_jeoksam", "name": "한산 모시 적삼", "region": "MAP_06", "node": "ND_06_TOWN_BUYEO", "kind": "crafted", "tier": 3,
            "base_price": 540, "dev_level": 0, "weight": 0.5, "real_name": "한산 세모시 적삼",
            "desc": "한산 모시로 지은 여름 홑저고리. 풀을 먹여 다듬이질하면 잠자리 날개처럼 비친다."},
     "recipe": {"id": "spr_hansan_jeoksam", "name": "【한산 모시 침선 비전서】", "tier": 3, "produces": "sp_hansan_mosi_jeoksam", "facility": "gongbang",
                "materials": [{"id": "sp_hansan_mosi", "qty": 3}, {"id": "mat_silk_thread", "qty": 1}]}},
]
STOCK_OVERRIDE = {"sp_uiju_dambi_g1": 5}   # R5 자유 무역 상한 조정

# ---------------------------------------------------------------- 초반 무역 · 보부상 위탁 (공백 권역)
TRADE_QUESTS = [
    {"id": "tq_ct_01", "name": "말총 갓방 운송", "item": "sp_jeju_malchong", "qty": 20, "from": "ND_17_CITY_JEJUMOKJEJUEUPSEONG",
     "to": "ND_10_FORT_TONGYEONGTONGJEYEONG", "margin": 1.8, "tier": 1, "reward_item": "spr_tongyeong_gat"},
    {"id": "tq_ct_02", "name": "옹진 대하 강화 뱃길", "item": "sp_ongjin_daeha", "qty": 15, "from": "ND_12_TOWN_ONGJIN",
     "to": "ND_01_CITY_GANGHWAYUSUBU", "margin": 1.8, "tier": 1},
    {"id": "tq_ct_03", "name": "평양 녹두 한양 진상", "item": "sp_pyeongyang_nokdu", "qty": 20, "from": "ND_13_CITY_PYEONGYANGBU",
     "to": "ND_02_CITY_HANYANGGYEONGJO", "margin": 1.8, "tier": 1},
    {"id": "tq_ct_04", "name": "의주 진말 평양 운송", "item": "sp_uiju_jinmal", "qty": 20, "from": "ND_14_CITY_UIJUMOK",
     "to": "ND_13_CITY_PYEONGYANGBU", "margin": 1.8, "tier": 1},
    {"id": "tq_ct_06", "name": "해주 먹 한양 진상", "item": "sp_haeju_meok", "qty": 5, "from": "ND_12_CITY_HAEJUMOK",
     "to": "ND_02_CITY_HANYANGGYEONGJO", "margin": 1.8, "tier": 3, "reward_item": "spr_haeju_muk"},
    {"id": "tq_ct_07", "name": "한산 모시 한양 진상", "item": "sp_hansan_mosi", "qty": 10, "from": "ND_06_TOWN_BUYEO",
     "to": "ND_02_CITY_HANYANGGYEONGJO", "margin": 1.8, "tier": 2, "reward_item": "spr_hansan_jeoksam"},
    {"id": "tq_ct_05", "name": "가덕 대구 감영 진상", "item": "sp_gadeok_daegu", "qty": 20, "from": "ND_10_TOWN_GIMHAE",
     "to": "ND_10_CITY_DAEGUGYEONGSANGGAMYEONG", "margin": 1.8, "tier": 1},
    # 보부상 위탁(consign): 밑천 없이 짐을 받아 나르고 운임(대금 × margin) — 매 장(5일) 반복
    {"id": "tq_cs_01", "name": "[위탁] 옹진 대하 해주 배달", "item": "sp_ongjin_daeha", "qty": 20, "from": "ND_12_TOWN_ONGJIN",
     "to": "ND_12_CITY_HAEJUMOK", "margin": 0.3, "tier": 1, "consign": True, "repeat": True},
    {"id": "tq_cs_02", "name": "[위탁] 평양 녹두 안주 배달", "item": "sp_pyeongyang_nokdu", "qty": 20, "from": "ND_13_CITY_PYEONGYANGBU",
     "to": "ND_13_CITY_ANJUMOK", "margin": 0.3, "tier": 1, "consign": True, "repeat": True},
    {"id": "tq_cs_03", "name": "[위탁] 의주 진말 영변 배달", "item": "sp_uiju_jinmal", "qty": 20, "from": "ND_14_CITY_UIJUMOK",
     "to": "ND_14_CITY_YEONGBYEONDAEDOHOBU", "margin": 0.3, "tier": 1, "consign": True, "repeat": True},
    {"id": "tq_cs_04", "name": "[위탁] 제주 말총 조천포 배달", "item": "sp_jeju_malchong", "qty": 20, "from": "ND_17_CITY_JEJUMOKJEJUEUPSEONG",
     "to": "ND_17_TOWN_JOCHEON", "margin": 0.3, "tier": 1, "consign": True, "repeat": True},
    {"id": "tq_cs_05", "name": "[위탁] 가덕 대구 동래 배달", "item": "sp_gadeok_daegu", "qty": 20, "from": "ND_10_TOWN_GIMHAE",
     "to": "ND_10_CITY_DONGRAEHYEON", "margin": 0.3, "tier": 1, "consign": True, "repeat": True},
]

# ---------------------------------------------------------------- 2. 곡물 말 단위 · 식재료
MAL = [("food_rice_mal", "백미 한 말", "food_rice"), ("food_barley_mal", "보리 한 말", "food_barley"), ("food_millet_mal", "조 한 말", "food_millet")]
NEW_FOODS = [
    {"id": "food_beef", "name": "쇠고기", "kind": "meat", "tier": 2, "price": 30, "weight": 1.0, "perishable": True,
     "note": "도회 현방(懸房)에서 파는 쇠고기. 대도시 장터(market)에서만 판매", "real_name": "현방 쇠고기",
     "desc": "한양 현방(푸줏간)에서 팔던 쇠고기. 설렁탕·갈비찜·신선로에 쓴다."},
    {"id": "food_kongnamul", "name": "콩나물", "kind": "ingredient", "tier": 1, "price": 3, "weight": 0.5, "perishable": True,
     "note": "콩나물국밥·비빔밥 재료"},
]
NEW_MATS = [{"id": "mat_jang", "name": "장(간장·된장)", "tier": 1, "price": 6, "weight": 1.0},
            {"id": "mat_songyeon", "name": "송연(松煙)", "tier": 1, "price": 6, "weight": 0.3,
             "note": "소나무를 태워 받은 그을음. 먹의 재료", "real_name": "송연(松煙)", "desc": "관솔을 태운 그을음을 모은 것. 아교(어교)와 반죽해 먹을 만든다."}]

# 요리: id → (등급, 재료, 효과 변경)   g() = 공용 재료군
def g(group, qty):
    return {"group": group, "qty": qty}


def i(id_, qty):
    return {"id": id_, "qty": qty}


FOOD = {
    # 서민 — 1등급 폐지 → 2등급 (말 단위 곡물)
    "fr_gukbap": (2, [g("grain", 1), i("food_beef", 1), i("mat_jang", 1)], {"satiety": 56, "heal_pct": 0.12}),
    "fr_kongnamul": (2, [g("grain", 1), i("food_kongnamul", 1), i("mat_jang", 1)], {"satiety": 48, "cure": ["fear"]}),
    "fr_jumeokbap": (2, [g("grain", 1), i("mat_salt", 1)], {"satiety": 40}),
    "fr_sujebi": (2, [g("flour", 2), i("mat_jang", 1)], {"satiety": 44}),
    "fr_bindaetteok": (2, [i("sp_pyeongyang_nokdu", 2), g("meat_game", 1)], None),        # 녹두지짐
    "fr_seolleongtang": (2, [i("food_beef", 2), g("grain", 1), i("mat_salt", 1)], None),   # 소 사골
    "fr_tteokguk": (2, [i("food_rice_mal", 2), i("food_pheasant", 1), i("mat_jang", 1)], None),  # 가래떡 + 꿩 육수
    "fr_jeonju_bibimbap": (3, [i("food_rice_mal", 1), i("food_beef", 1), i("food_kongnamul", 1), i("mat_jang", 1), i("sp_yeonan_chamgireum", 1)], None),
    "fr_pyeongyang_naengmyeon": (3, [i("food_buckwheat", 3), i("food_pheasant", 1)], None),  # 메밀 + 꿩 육수(고증 맞음)
    # 수라
    "fr_galbijjim": (3, [i("food_beef", 2), i("herb_daechu", 2), i("mat_jang", 1)], None),
    "fr_gujeolpan": (3, [i("sp_uiju_jinmal", 1), i("food_beef", 1), i("food_kongnamul", 1)], None),   # 밀전병 + 소
    "fr_jeonbokcho": (3, [i("sp_jeju_jeonbok", 2), i("mat_jang", 1), i("sp_chuncheon_jat", 1)], None),  # 전복 + 잣가루
    "fr_eomandu": (3, [i("sp_gadeok_daegu", 2), i("sp_pyeongyang_nokdu", 1)], None),      # 흰살생선 + 녹말
    "fr_tarakjuk": (2, [i("food_rice_mal", 1), i("sp_hanyang_tarak", 1)], None),          # 쌀 + 우유
    "fr_yaksik": (2, [i("food_rice_mal", 1), i("herb_daechu", 2), i("sp_chuncheon_jat", 1)], None),
    "fr_gungjung_tteokbokki": (3, [i("food_rice_mal", 2), i("food_beef", 1), i("mat_jang", 1)], None),  # 간장 떡볶이
    "fr_daehajjim": (4, [i("sp_ongjin_daeha", 2), i("herb_saenggang", 1), i("sp_chuncheon_jat", 1)], None),  # 대하 + 잣즙
    "fr_sinseollo": (4, [i("food_beef", 1), i("food_pheasant", 1), i("sp_gadeok_daegu", 1), i("sp_chuncheon_jat", 1)], None),
}
NEW_DISHES = [  # 미사용 재료 활용 + 신규 특산 활용
    {"id": "fr_tangpyeongchae", "name": "탕평채", "class": "sura", "tier": 3, "book": "bk_food_sura", "cook_at": ["jumak_gamasot"],
     "ingredients": [i("sp_pyeongyang_nokdu", 2), i("food_beef", 1), i("sp_yeonan_chamgireum", 1)],
     "effect": {"satiety": 48, "battle_buff": {"res_all": 0.1, "duration_battles": 3}}, "weight": 0.6, "perishable": True,
     "note": "청포묵(녹두묵)에 쇠고기·나물을 참기름에 무친 궁중 음식. 영조의 탕평책에서 이름이 나왔다"},
    {"id": "fr_yakgwa", "name": "약과", "class": "sura", "tier": 3, "book": "bk_food_sura", "cook_at": ["jumak_gamasot"],
     "ingredients": [i("sp_uiju_jinmal", 2), i("sp_yeonan_chamgireum", 1), g("jujube", 1)],
     "effect": {"satiety": 40, "heal_pct": 0.1, "battle_buff": {"spd_bonus": 0.05, "duration_battles": 2}}, "weight": 0.3, "perishable": False,
     "note": "밀가루를 참기름에 반죽해 기름에 지진 유밀과. 상하지 않아 먼 길에 좋다"},
    {"id": "fr_yuja_hwachae", "name": "유자화채", "class": "sura", "tier": 3, "book": "bk_food_sura", "cook_at": ["jumak_gamasot"],
     "ingredients": [i("sp_namhae_yuja", 1), i("sp_bongsan_bae", 1), i("sp_chuncheon_jat", 1)],
     "effect": {"satiety": 24, "heal_pct": 0.2, "cure": ["burn"]}, "weight": 0.5, "perishable": True,
     "note": "유자와 배를 가늘게 채 썰어 꿀물에 띄우고 잣을 얹은 궁중 화채"},
    {"id": "fr_miyeokguk", "name": "미역국", "class": "seomin", "tier": 2, "book": "bk_food_jumak", "cook_at": ["jumak_gamasot", "campfire"],
     "ingredients": [i("sp_jeju_miyeok", 1), i("food_beef", 1), i("mat_jang", 1)], "effect": {"satiety": 44, "heal_pct": 0.15}, "weight": 0.6, "perishable": True},
    {"id": "fr_dotorimuk", "name": "도토리묵", "class": "seomin", "tier": 2, "book": "bk_food_campfire", "cook_at": ["campfire", "jumak_gamasot"],
     "ingredients": [i("food_acorn", 4), i("mat_jang", 1)], "effect": {"satiety": 36, "heal_pct": 0.05}, "weight": 0.6, "perishable": True},
    {"id": "fr_songgitteok", "name": "송기떡", "class": "seomin", "tier": 2, "book": "bk_food_campfire", "cook_at": ["campfire", "jumak_gamasot"],
     "ingredients": [i("food_songgi", 3), g("grain", 1)], "effect": {"satiety": 44}, "weight": 0.5, "perishable": False},
    {"id": "fr_sanjeok", "name": "야영 산적", "class": "seomin", "tier": 2, "book": "bk_food_campfire", "cook_at": ["campfire"],
     "ingredients": [g("meat_game", 1), i("mat_salt", 1)], "effect": {"satiety": 40, "battle_buff": {"atk_pct": 0.04, "duration_battles": 1}},
     "weight": 0.5, "perishable": True},
    {"id": "fr_ungjang", "name": "웅장찜(熊掌)", "class": "sura", "tier": 4, "book": "bk_food_bukgwan", "cook_at": ["jumak_gamasot"],
     "ingredients": [i("food_bear", 1), i("mat_jang", 1), i("herb_saenggang", 1)],
     "effect": {"satiety": 70, "battle_buff": {"def_pct": 0.15, "hp_pct": 0.1, "duration_battles": 3}}, "weight": 0.8, "perishable": True},
    {"id": "fr_nokpo", "name": "녹포(鹿脯)", "class": "sura", "tier": 5, "book": "bk_food_bukgwan", "cook_at": ["jumak_gamasot", "campfire"],
     "ingredients": [i("food_white_deer", 1), i("mat_salt", 2), i("mat_jang", 1)],
     "effect": {"satiety": 100, "battle_buff": {"atk_pct": 0.15, "def_pct": 0.15, "duration_battles": 3}}, "weight": 0.3, "perishable": False},
]
YUJACHA = {"id": "hr_yujacha", "name": "유자차", "form": "탕약", "tier": 1, "book": "bk_med_dongui",
           "ingredients": [i("sp_namhae_yuja", 1), i("herb_saenggang", 1)], "effect": {"heal_pct": 0.08, "cure": ["frost"]}, "battle_usable": True}
GALGEUN = {"id": "hr_galgeun", "name": "갈근탕", "form": "탕약", "tier": 1, "book": "bk_med_dongui",
           "ingredients": [i("food_kudzu", 2), i("herb_saenggang", 1), i("herb_daechu", 1)], "effect": {"heal_pct": 0.1}, "battle_usable": False}

# ---------------------------------------------------------------- 5. 재료군 · 대체 사슬
LINE_KEY = {"sp_boeun_daechu": "jujube", "sp_gaeseong_insam": "ginseng", "sp_chuncheon_jat": "jat"}

def chain_ids(base):
    if base == "sp_gaeseong_insam":
        return [base, "sp_gaeseong_hongsam", base + "_g2"]
    n = len(CHAIN[base][1])
    return [base] + [f"{base}_g{k}" for k in range(1, n + 1)]


def lines():
    L = {
        "grain": {"name": "곡물(한 말)", "items": ["food_rice_mal", "food_barley_mal", "food_millet_mal"]},
        "flour": {"name": "가루(진말·메밀)", "items": ["sp_uiju_jinmal", "food_buckwheat"]},
        "meat_game": {"name": "수렵육", "items": ["food_hare", "food_pheasant", "food_boar", "food_bear", "food_white_deer"]},
        "gu": {"name": "구황 산물", "items": ["food_songgi", "food_acorn", "food_kudzu"]},
        "fiber": {"name": "섬유", "items": ["mat_hemp", "mat_cotton", "mat_silk_thread"]},
        "jujube": {"name": "대추", "items": ["herb_daechu"] + chain_ids("sp_boeun_daechu")},
        "ginseng": {"name": "인삼", "items": chain_ids("sp_gaeseong_insam")[:2] + ["herb_insam", "sp_ganggye_sam"] + chain_ids("sp_gaeseong_insam")[2:] + ["herb_sansam"]},
        "jat": {"name": "잣", "items": chain_ids("sp_chuncheon_jat")},
    }
    for base, (short, _) in CHAIN.items():
        if base in ("sp_boeun_daechu", "sp_gaeseong_insam", "sp_chuncheon_jat"):
            continue
        L["trade_" + base[3:]] = {"name": short, "items": chain_ids(base)}
    return L


def main():
    # --- 03 특산물
    doc = load("03_specialties.json")
    sp = [r for r in doc["specialties"] if r.get("generated") != TAG and r["id"] != "sp_inje_hwangtae"]
    by = {r["id"]: r for r in sp}
    for id_, name, reg, node, tier, w, per, real, desc in NEW_SPECIALTIES:
        row = {"id": id_, "name": name, "region": reg, "node": node, "kind": "basic", "tier": tier, "base_price": PRICE[tier],
               "dev_level": 0, "weight": w, "real_name": real, "desc": desc, "grade": 0, "generated": TAG}
        if per:
            row["perishable"] = True
        if id_ == "sp_chuncheon_jat":
            row["note"] = "구 '인제 황태'(sp_inje_hwangtae) 대체 — 황태 덕장은 1950년대 이후라 1861년 배경에 맞지 않음"
        sp.append(row)
        by[id_] = row
    for id_, name, reg, node, tier, dev, w, line, real, desc in PREMIUM_SPECIALTIES:
        row = {"id": id_, "name": name, "region": reg, "node": node, "kind": "premium", "tier": tier, "base_price": PRICE[tier],
               "dev_level": dev, "weight": w, "real_name": real, "desc": desc, "grade": 0, "generated": TAG}
        sp.append(row)
    for c in CRAFTED:
        sp.append({**c["sp"], "generated": TAG})
    for base, (short, grades) in CHAIN.items():
        b = by[base]
        b["line"], b["grade"] = LINE_KEY.get(base, "trade_" + base[3:]), 0
        b.setdefault("real_name", b["name"])
        for k, info in enumerate(grades, 1):
            t = b["tier"] + k
            gid = chain_ids(base)[k]
            if info is None:                       # 기존 개성 홍삼을 상품으로 연결
                h = by[gid]
                h.update({"name": f"{short} 상품", "real_name": "개성 홍삼(紅蔘)", "grade": 1, "line": b["line"],
                          "desc": "수삼을 쪄서 말린 것. 사행 무역의 으뜸 품목으로 청에서 값이 높았다."})
                continue
            row = {"id": gid, "name": f"{short} {'상품' if k == 1 else '진상품'}", "region": b["region"], "node": b["node"],
                   "kind": "basic", "tier": t, "base_price": PRICE[t], "dev_level": min(3, int(b["dev_level"]) + k + (1 if gid.endswith("insam_g2") else 0)),
                   "weight": b["weight"], "real_name": info[0], "desc": info[1], "line": b["line"], "grade": k, "generated": TAG}
            if b.get("perishable"):
                row["perishable"] = True
            sp.append(row)
    for r in sp:
        if r["id"] in STOCK_OVERRIDE:
            r["stock"] = STOCK_OVERRIDE[r["id"]]
    doc["specialties"] = sp
    doc["specialty_recipes"] = [r for r in doc["specialty_recipes"] if r.get("generated") != TAG] + [{**c["recipe"], "generated": TAG} for c in CRAFTED]
    doc["trade_quests"] = [q for q in doc["trade_quests"] if q.get("generated") != TAG] + [{**q, "generated": TAG} for q in TRADE_QUESTS]
    doc["_schema"] = doc["_schema"].split(" | 등급 사슬")[0] + (
        " | 등급 사슬: line=사슬 id, grade 0 기본/1 상품/2 진상품(해금 = 원산지 발전도 dev_level + 신분 Rank ≥ tier, 5일 물량 trade.stock_by_grade)."
        " real_name·desc = 도감 표시(실제 명칭·설명).")
    save("03_specialties.json", doc)

    # --- 04 식량
    doc = load("04_food_staples.json")
    foods = [r for r in doc["foods"] if r.get("generated") != TAG]
    fb = {r["id"]: r for r in foods}
    for mid, name, of in MAL:
        fb[of]["unpack"] = {"to": mid, "qty": 10}
        fb[of]["note"] = "섬 단위 교역품(무게 20). 제작 탭 '섬 풀기'로 1섬 → 10말. 조리는 말 단위"
        foods.append({"id": mid, "name": name, "kind": "grain", "tier": 1, "unit_of": of, "unit_ratio": 0.1, "weight": 2.0,
                      "note": "조리용 곡물 1말 = 1/10섬. 값 = 섬 시세 × 0.1 × 1.1(소매)", "generated": TAG})
    for f in NEW_FOODS:
        foods.append({**f, "generated": TAG})
    doc["foods"] = foods
    doc["_schema"] = doc["_schema"].split(" | 말 단위")[0] + (
        " | 말 단위: kind=grain(조리용 한 말, unit_of 섬 시세 연동)|meat(도회 장터)|ingredient(식재료). 섬의 unpack = 섬 풀기(1섬→10말).")
    save("04_food_staples.json", doc)

    # --- 05 재료
    doc = load("05_materials.json")
    doc["materials"] = [r for r in doc["materials"] if r.get("generated") != TAG] + [{**m, "generated": TAG} for m in NEW_MATS]
    save("05_materials.json", doc)

    # --- 10 약초 (같은 물건 정리)
    doc = load("10_herbs.json")
    for h in doc["herbs"]:
        if h["id"] == "herb_insam":
            h["name"] = "산양삼(山養蔘)"
            h["note"] = "심산에서 반쯤 자연으로 자란 삼. 재배 인삼(개성 인삼 2등급)보다 상등, 백두 산삼(5등급)보다 하등"
        if h["id"] == "herb_daechu":
            h["name"] = "건대추(약재)"
            h["note"] = "약방에서 파는 약재용 마른 대추. 보은 대추(특산)로 대신 쓸 수 있다"
    save("10_herbs.json", doc)

    # --- 11 요리
    doc = load("11_food_recipes.json")
    rs = [r for r in doc["recipes"] if r.get("generated") != TAG]
    for r in rs:
        if r["id"] in FOOD:
            t, ing, eff = FOOD[r["id"]]
            r["tier"], r["ingredients"] = t, ing
            if eff:
                r["effect"] = eff
    rs += [{**d, "generated": TAG} for d in NEW_DISHES]
    doc["recipes"] = rs
    doc["_schema"] = doc["_schema"].split(" | 재료")[0] + (
        " | 재료: {id,qty} 또는 {group,qty}(공용 재료군 = 00_overview.crafting.lines). 곡물은 '한 말' 단위. 1등급 요리 없음(2~5등급).")
    save("11_food_recipes.json", doc)

    # --- 09 한방약
    doc = load("09_herbal_recipes.json")
    rs = [r for r in doc["recipes"] if r.get("generated") != TAG]
    for r in rs:
        if r["id"] in ("hr_sipjeon", "hr_gyeongok"):   # 재배 인삼(2등급)으로 — 산양삼·홍삼은 상위 대체
            for x in r["ingredients"]:
                if x.get("id") == "herb_insam":
                    x["id"] = "sp_gaeseong_insam"
    rs.append({**GALGEUN, "generated": TAG})
    rs.append({**YUJACHA, "generated": TAG})
    doc["recipes"] = rs
    save("09_herbal_recipes.json", doc)

    # --- 15 비전서 해금
    doc = load("15_recipe_books.json")
    add = {"bk_food_sura": ["fr_tangpyeongchae", "fr_yakgwa", "fr_yuja_hwachae"], "bk_food_jumak": ["fr_miyeokguk"], "bk_food_campfire": ["fr_dotorimuk", "fr_songgitteok", "fr_sanjeok"], "bk_food_bukgwan": ["fr_ungjang", "fr_nokpo"],
           "bk_med_dongui": ["hr_galgeun", "hr_yujacha"]}
    for b in doc["books"]:
        for x in add.get(b["id"], []):
            if x not in b["unlocks"]:
                b["unlocks"].append(x)
    save("15_recipe_books.json", doc)

    # --- 18 감기 치료: 갈근탕
    doc = load("18_status_effects.json")
    for f in doc["field"]:
        if f["id"] == "cold":
            for x in ("hr_galgeun", "hr_yujacha"):
                if x not in f["cure_by"]:
                    f["cure_by"].insert(1, x)
    save("18_status_effects.json", doc)

    # --- 00 개요: 재료군·대체 규칙, 등급별 물량
    ov = load("00_overview.json")
    ov["crafting"] = {
        "_note": "재료 {id}: 같은 line 에서 등급 ≥ 요구 등급인 품목이 1:1 대체(정확한 품목 → 낮은 등급 → 신선도 낮은 것 순). "
                 "{group}: line 전체(최저 등급 기준). no_substitute 는 직접 요구할 때만 소모. substitute_default: off|confirm|auto, "
                 "confirm = 요구보다 confirm_tier_gap 등급 이상 높은 재료가 쓰일 때만 확인창.",
        "substitute_default": "confirm", "confirm_tier_gap": 2,
        "lines": lines(),
        "no_substitute": ["food_white_deer", "herb_sansam", "mat_meteor_iron", "mat_sarira_crystal", "mat_cinnabar"],
    }
    ov["trade"]["stock_by_grade"] = [20, 8, 3]
    ov["trade"]["grade_rank_gate"] = True
    ov["trade"]["stock_scope"] = "region"        # 특산물 5일 물량을 원산지 권역 전체가 공유
    ov["trade"]["sell_saturation"] = {"per_unit": 0.02, "floor": 0.6, "_note": "같은 장터·같은 특산물을 이번 장(5일)에 판 개수만큼 개당 −2%, 하한 60%"}
    ov["trade"]["seasonal_sell_bonus"] = [{"name": "동지사 사행(의주 만상)", "region": "MAP_14", "season": 3, "mult": 1.2}]
    ov["trade"]["free_trade_model"] = {"trips_per_tier": 6, "efficiency": 0.5,
                                       "_note": "economy_sim 자유 무역 수입 = 신분 등급마다 편도 trips_per_tier 회 × trade_sim 최선 편도 이익 × efficiency"}
    ov["facilities"]["ferry"]["sang_discount_per_rank"] = 0.05   # 상(商) 지식 랭크당 뱃삯 −5% (하한 50%)
    save("00_overview.json", ov)
    n_chain = sum(1 for r in load("03_specialties.json")["specialties"] if r.get("grade", 0) > 0)
    print(f"특산물 등급품 {n_chain}종 · 신규 식재료 특산 {len(NEW_SPECIALTIES)} · 말 {len(MAL)} · 식재료 {len(NEW_FOODS) + len(NEW_MATS)} · "
          f"요리 수정 {len(FOOD)} + 신규 {len(NEW_DISHES)} · 약 +1 · 재료군 {len(lines())}")


if __name__ == "__main__":
    main()
