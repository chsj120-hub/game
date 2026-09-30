#!/usr/bin/env python3
"""콘텐츠 확충(2차) — 이벤트·권역 적·무예 단조 장비·탈것 퀘스트·작설차, 제주 김만덕 시나리오와 튜토리얼·도움말.
여러 번 실행해도 결과가 같다(generated="content2" 행만 교체). 파이프라인에서 craft_trade_update 다음에 실행.

  20_events.json      역사·설화 이벤트 +10, 메인 시나리오 '김만덕 — 제주 객주에서 금강산까지'(시나리오 전용)
  12_enemies.json     권역 적 +6 (제주 도채비·영감, 황당선, 북방 마적, 멧돼지 떼, 반달곰)
  02_equipment.json   무예 단조서 3권(당파창·등패·편곤) 장비
  07_mounts.json      4등급 탈것 퀘스트 +2 (제주 헌마, 경강 조운선) + 14 탈것 스킬
  09_herbal_recipes   작설차
  23_tutorial.json    시나리오(시작 설정) · 튜토리얼 단계 · 도움말 항목  (신규 시트)
"""
from common import load, save

TAG = "content2"


def keep(rows):
    return [r for r in rows if r.get("generated") != TAG]


def tag(rows):
    return [{**r, "generated": TAG} for r in rows]


# ================================================================ 역사·설화 이벤트 (동선 규칙: T1·2 같은 권역 2곳, T3·4 인접 2~3권역 3곳, T5 3~5권역 4~5곳)
EVENTS = [
    {"id": "ev_jeju_seolmundae", "name": "설문대할망의 치마폭", "lore": "설화", "type": "event", "tier": 1,
     "trigger": {"region": "MAP_17", "rank_min": 1},
     "stages": [
         {"node": "ND_17_SCENIC_SEONGSANILCHULBONG", "action": "talk",
          "text": "해녀 할망이 들려준다. '옛날 설문대할망이 치마폭에 흙을 담아 날라 한라산을 쌓았지. 치마 터진 구멍으로 흘린 흙이 오름이 되었고.'"},
         {"node": "ND_17_TOWN_SEOGWIPO", "action": "choice",
          "text": "포구 아이들이 할망이 명주 속옷 한 벌만 지어 주면 육지까지 다리를 놓아 주겠다 했다는 대목을 묻는다. 어떻게 답할까?",
          "choices": [{"id": "island", "text": "'명주가 모자라 다리가 끊겼으니, 섬사람은 배와 바람을 믿어야지.'", "effects": {"knowledge_xp": {"sang": 30}}},
                      {"id": "legend", "text": "'오름 하나하나가 할망의 발자국이란다.' 전설을 끝까지 들려준다", "effects": {"knowledge_xp": {"seon": 30}}}]}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "마을 심방이 굿판에서 설문대할망 본풀이를 불러 이야기가 이어졌다."},
     "codex": "제주 창조 여신 설문대할망 설화. 한라산과 360여 오름의 기원을 말한다."},
    {"id": "ev_jeju_yeongdeung", "name": "영등할망 맞이", "lore": "설화", "type": "event", "tier": 2,
     "trigger": {"region": "MAP_17", "rank_min": 1, "solar_terms": ["경칩", "춘분", "청명"]},
     "stages": [
         {"node": "ND_17_CITY_JEJUMOKJEJUEUPSEONG", "action": "talk",
          "text": "음력 2월, 바람의 신 영등할망이 섬에 드는 달이다. 건입포 칠머리당에서 해녀와 선주들이 굿 채비를 한다."},
         {"node": "ND_17_FORT_HWABUKJIN", "action": "minigame",
          "text": "영등 송별제 — 짚배를 띄워 보내며 장단을 맞춘다(정간보 박자).", "minigame": "mg_jeonggan"}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "심방들이 영등굿을 무사히 마치고 영등할망을 떠나보냈다."},
     "codex": "제주 칠머리당 영등굿(국가무형유산). 바람의 신에게 해녀·어부의 무사와 풍어를 빈다."},
    {"id": "ev_jeju_hwangdang", "name": "차귀 앞바다의 황당선", "lore": "역사", "type": "event", "tier": 2,
     "trigger": {"region": "MAP_17", "rank_min": 2},
     "stages": [
         {"node": "ND_17_FORT_CHAGWIJIN", "action": "battle",
          "text": "정체 모를 이양선(황당선)이 차귀도에 닻을 내리고 포구 물자를 약탈한다. 진졸과 함께 막아선다.",
          "waves": [["en_hwangdangseon", "en_hwangdangseon"], ["en_hwangdangseon", "en_pirate"]]},
         {"node": "ND_17_TOWN_DAEJEONGHYEON", "action": "choice",
          "text": "붙잡은 선원들은 말이 통하지 않는다. 대정현감이 처리를 묻는다.",
          "choices": [{"id": "report", "text": "문정(問情)하여 장계를 올린다", "effects": {"knowledge_xp": {"yu": 40}}},
                      {"id": "trade", "text": "싣고 온 물건을 몰래 사들인다", "effects": {"money_mult": 1.3}}]}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "제주목 군관이 출동해 황당선을 쫓아냈다."},
     "codex": "19세기 조선 연해에 출몰한 이양선(異樣船)·황당선(荒唐船). 해안 방어의 골칫거리였다."},
    {"id": "ev_geumgang_seonnyeo", "name": "상팔담의 선녀", "lore": "설화", "type": "event", "tier": 2,
     "trigger": {"region": "MAP_03", "rank_min": 1},
     "stages": [
         {"node": "ND_03_TOWN_HOEYANG", "action": "talk",
          "text": "회양 나무꾼이 속삭인다. '금강산 상팔담에 보름마다 선녀가 멱을 감으러 내려온다오. 날개옷을 숨긴 사내 이야기, 들어 보셨소?'"},
         {"node": "ND_03_SCENIC_GEUMGANGSANGURYONGPOK", "action": "minigame",
          "text": "구룡폭 위 여덟 못에 비친 달빛을 따라 선녀의 길을 잇는다.", "minigame": "mg_chilseong"}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "유람객들 사이에 상팔담 전설이 널리 퍼졌다."},
     "codex": "금강산 상팔담에 얽힌 '나무꾼과 선녀' 설화."},
    {"id": "ev_donghak_1860", "name": "용담정의 새 가르침", "lore": "역사", "type": "event", "tier": 3,
     "trigger": {"region": "MAP_09", "rank_min": 2},
     "stages": [
         {"node": "ND_09_CITY_GYEONGJUBU", "action": "talk",
          "text": "경주 구미산 용담정에서 몰락 양반 최제우가 '사람이 곧 하늘'이라는 가르침을 편다(1860, 동학 창도)."},
         {"node": "ND_09_TOWN_YEONGCHEON", "action": "choice",
          "text": "영천 장터에 주문을 외는 사람들이 모인다. 관아는 '서학 무리'라며 잡아들일 채비를 한다.",
          "choices": [{"id": "listen", "text": "가르침을 끝까지 들어 본다", "effects": {"knowledge_xp": {"seon": 50}}},
                      {"id": "report", "text": "관아에 알린다", "effects": {"money_mult": 1.3}}]},
         {"node": "ND_10_CITY_DAEGUGYEONGSANGGAMYEONG", "action": "minigame",
          "text": "경상감영에서 유·불·선과 새 가르침의 차이를 묻는다.", "minigame": "mg_three_teachings"}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "감영이 용담 일대를 단속하며 소문이 잦아들었다."},
     "codex": "1860년 최제우가 경주에서 창도한 동학. 1864년 대구에서 처형되었다."},
    {"id": "ev_daedong_1861", "name": "대동여지도 판각", "lore": "역사", "type": "event", "tier": 3,
     "trigger": {"region": "MAP_02", "rank_min": 2},
     "stages": [
         {"node": "ND_02_CITY_HANYANGGYEONGJO", "action": "talk",
          "text": "만리재 아래 초가에서 김정호가 스물두 첩 판목을 새기고 있다. '산줄기는 끊기지 않고, 물길은 서로 만나오. 그것만은 틀릴 수 없소.'"},
         {"node": "ND_02_STATION_YANGJAEYEOK", "action": "deliver",
          "text": "판목에 쓸 단단한 나무를 역참 수레로 받아 온다(느티나무 판재 4).", "item": "mat_wood", "qty": 4},
         {"node": "ND_01_CITY_GAESEONGBU", "action": "minigame",
          "text": "개성의 지물포에서 첫 인출본을 찍어 본다(목판 탁본).", "minigame": "mg_takbon"}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "김정호가 끝내 판각을 마쳐 신유년(1861)에 대동여지도를 간행했다."},
     "codex": "1861년 김정호가 간행한 22첩 목판 전국 지도 「대동여지도」."},
    {"id": "ev_baekdu_jangsu", "name": "백두산 아기장수", "lore": "설화", "type": "event", "tier": 3,
     "trigger": {"region": "MAP_16", "rank_min": 3},
     "stages": [
         {"node": "ND_16_STATION_MUSANCHAM", "action": "talk",
          "text": "무산 노인이 말한다. '겨드랑이에 날개 돋은 아기장수가 태어나면, 용마가 백두산에서 내려온다 했지.'"},
         {"node": "ND_16_SCENIC_BAEKDUSANCHEONJI", "action": "battle",
          "text": "천지 기슭에서 용마를 지키던 반달곰이 길을 막는다.", "waves": [["en_bear"], ["en_bear", "en_bear"]]},
         {"node": "ND_15_CITY_HAMHEUNGBU", "action": "choice",
          "text": "함흥 장터에 '용마 발자국'을 보았다는 소문이 돈다. 어떻게 전할까?",
          "choices": [{"id": "hope", "text": "아기장수는 언젠가 온다고 전한다", "effects": {"knowledge_xp": {"seon": 50}}},
                      {"id": "record", "text": "본 대로만 적어 답사록에 남긴다", "effects": {"knowledge_xp": {"sa": 50}}}]}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "장터 이야기꾼이 아기장수 설화를 북관 곳곳에 퍼뜨렸다."},
     "codex": "전국에 전하는 아기장수 설화 가운데 백두산 용마 이야기."},
    {"id": "ev_sherman_1866", "name": "대동강의 제너럴셔먼호", "lore": "역사", "type": "event", "tier": 4,
     "trigger": {"region": "MAP_13", "rank_min": 3},
     "stages": [
         {"node": "ND_13_TOWN_JINNAMPO", "action": "talk",
          "text": "검은 연기를 뿜는 이양선이 대동강을 거슬러 오른다. 통상을 요구하며 물러가지 않는다(1866)."},
         {"node": "ND_13_CITY_PYEONGYANGBU", "action": "battle",
          "text": "배가 양각도에 걸리자 선원들이 총을 쏘며 뭍에 오른다. 평양 군민과 함께 막아선다.",
          "waves": [["en_hwangdangseon", "en_hwangdangseon"], ["en_hwangdangseon", "en_hwangdangseon", "en_pirate"]]},
         {"node": "ND_11_CITY_HWANGJUMOK", "action": "choice",
          "text": "황해감영으로 가는 길, 장계에 무엇을 적을까?",
          "choices": [{"id": "defense", "text": "해안 방비를 서둘러야 한다고 적는다", "effects": {"knowledge_xp": {"yu": 60}}},
                      {"id": "trade", "text": "저들이 가져온 물건과 시세를 자세히 적는다", "effects": {"knowledge_xp": {"sang": 60}}}]}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "평안감사 박규수가 화공으로 이양선을 불태웠다."},
     "codex": "1866년 미국 상선 제너럴셔먼호 사건. 신미양요(1871)의 빌미가 되었다."},
    {"id": "ev_oppert_1868", "name": "가야산 남연군묘 도굴", "lore": "역사", "type": "event", "tier": 4,
     "trigger": {"region": "MAP_06", "rank_min": 3},
     "stages": [
         {"node": "ND_06_TOWN_HAEMI", "action": "talk",
          "text": "덕산 가야산 기슭에 밤마다 낯선 무리가 곡괭이를 들고 오간다. 흥선대원군 부친 남연군의 묘다(1868)."},
         {"node": "ND_06_CITY_HONGJUMOK", "action": "battle",
          "text": "도굴꾼 무리가 관군을 피해 포구로 달아난다.",
          "waves": [["en_hwangdangseon", "en_bandit", "en_bandit"], ["en_hwangdangseon", "en_hwangdangseon"]]},
         {"node": "ND_02_CITY_HANYANGGYEONGJO", "action": "minigame",
          "text": "한양 포도청에서 도굴 경위를 심문한다.", "minigame": "mg_amhaeng_trial"}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "도굴은 실패로 끝났고, 조정은 쇄국의 뜻을 더 굳혔다."},
     "codex": "1868년 독일 상인 오페르트의 남연군묘 도굴 미수 사건."},
    {"id": "ev_sinmi_1871", "name": "광성보의 신미양요", "lore": "역사", "type": "event", "tier": 5,
     "trigger": {"region": "MAP_01", "rank_min": 4},
     "stages": [
         {"node": "ND_12_CITY_YEONANDOHOBU", "action": "talk",
          "text": "연안 앞바다에 미국 함대가 나타났다는 봉수가 오른다(1871)."},
         {"node": "ND_01_FORT_DEOKJINJIN", "action": "battle",
          "text": "덕진진 포대가 함포에 무너진다. 어재연 장군의 수자기(帥字旗) 아래로 모인다.",
          "waves": [["en_hwangdangseon", "en_hwangdangseon", "en_hwangdangseon"], ["en_majeok", "en_hwangdangseon", "en_hwangdangseon"]]},
         {"node": "ND_01_CITY_GANGHWAYUSUBU", "action": "choice",
          "text": "광성보 싸움이 끝났다. 강화유수부에 무엇을 남길까?",
          "choices": [{"id": "memorial", "text": "전사한 군사들의 이름을 적어 남긴다", "effects": {"knowledge_xp": {"yu": 80}}},
                      {"id": "map", "text": "해안 포대의 지형을 그려 남긴다", "effects": {"knowledge_xp": {"sa": 80}}}]},
         {"node": "ND_02_CITY_HANYANGGYEONGJO", "action": "minigame",
          "text": "척화비의 글귀를 새긴다.", "minigame": "mg_talisman_stroke"}],
     "deadline_days": 30, "fail_safe": {"mode": "time_decay", "text": "미 함대가 물러가고, 조정은 전국에 척화비를 세웠다."},
     "codex": "1871년 미국 함대의 강화도 침공(신미양요)과 광성보 전투."},
]

# ================================================================ 김만덕 시나리오 (메인, 시나리오 전용 — 클래스 메인 대신 시작)
MANDEOK_MAIN = {
    "id": "ev_main_mandeok", "name": "김만덕 — 제주 객주에서 금강산까지", "class": "cls_merchant", "scenario": "sc_jeju_mandeok",
    "lore": "역사", "type": "main",
    "era_note": "김만덕(1739~1812)의 실제 생애(1790년대)를 따르는 시나리오. 본편 배경(1861)과 시대가 다르며, 이 시나리오에서만 정조 대 인물이 등장한다.",
    "chapters": [
        {"chapter": 1, "tier": 1, "title": "객주를 열다", "stages": [
            {"node": "ND_17_CITY_JEJUMOKJEJUEUPSEONG", "action": "talk",
             "text": "제주목 관아. 만덕은 관기 명부에서 이름을 지워 달라는 소지를 올린다. 목사가 묻는다. '양인으로 돌아가 무엇을 하려느냐?' "
                     "— '포구에 객주를 열어 뭍과 섬을 잇겠습니다. 섬에서 나는 것은 제값에, 뭍에서 오는 것은 제때에.'"},
            {"node": "ND_17_TOWN_JOCHEON", "action": "choice",
             "text": "조천포 첫 거래. 육지 장사꾼이 말총을 헐값에 넘기라며 웃돈 대신 '다음 배'를 약속한다.",
             "choices": [{"id": "fair", "text": "저울을 바로 달고 제값만 받는다 — '신용이 밑천입니다'", "effects": {"knowledge_xp": {"sang": 40}}},
                         {"id": "bargain", "text": "뭍 시세를 짚어 웃돈을 받아 낸다", "effects": {"money_mult": 1.3}}]}]},
        {"chapter": 2, "tier": 2, "title": "뭍으로 가는 배", "stages": [
            {"node": "ND_17_FORT_HWABUKJIN", "action": "deliver",
             "text": "화북포에 뭍으로 가는 상선이 닿았다. 객주의 첫 짐으로 제주 말총을 싣는다(말총 10).", "item": "sp_jeju_malchong", "qty": 10},
            {"node": "ND_17_TOWN_SEOGWIPO", "action": "choice",
             "text": "서귀포 잠녀들이 딴 전복을 객주에 맡기려 한다. 관아의 진상 몫을 떼고 나면 남는 것이 없다는 하소연이다.",
             "choices": [{"id": "share", "text": "잠녀 몫을 먼저 셈해 주고 남은 것으로 이문을 본다", "effects": {"knowledge_xp": {"sang": 40, "nong": 20}}},
                         {"id": "stock", "text": "전복을 모두 사들여 뭍에 비싸게 판다", "effects": {"money_mult": 1.3}}]}]},
        {"chapter": 3, "tier": 3, "title": "을묘년 흉년", "stages": [
            {"node": "ND_08_CITY_NAJUMOK", "action": "choice",
             "text": "을묘년(1795), 태풍과 가뭄으로 제주에 굶주림이 번진다. 만덕은 평생 모은 재산을 들고 나주 영산창으로 건너왔다. 쌀을 얼마나 살까?",
             "choices": [{"id": "all", "text": "객주 재산을 모두 털어 쌀을 산다", "effects": {"knowledge_xp": {"sang": 60}}},
                         {"id": "part", "text": "객주를 이어 갈 밑천은 남긴다", "effects": {"money_mult": 1.2}}]},
            {"node": "ND_08_TOWN_HAENAM", "action": "talk",
             "text": "해남 포구. 사공들이 풍랑을 걱정한다. '섬이 굶는데 바람을 기다릴 수 있소.' 만덕은 쌀배를 띄운다."},
            {"node": "ND_17_CITY_JEJUMOKJEJUEUPSEONG", "action": "deliver",
             "text": "제주목 관덕정 앞에 구휼미를 푼다(백미 3섬). 사람들이 줄지어 만덕의 이름을 부른다.", "item": "food_rice", "qty": 3}]},
        {"chapter": 4, "tier": 4, "title": "바다를 건너는 부름", "stages": [
            {"node": "ND_08_TOWN_HAENAM", "action": "talk",
             "text": "목사가 전한다. '임금께서 소원을 물으셨다.' 만덕이 답한다. '한양 대궐을 우러르고 금강산 일만이천 봉을 보는 것입니다.' "
                     "제주 여인은 뭍에 나갈 수 없다는 출륙금지령이 있었으나, 임금이 특별히 허락했다."},
            {"node": "ND_07_CITY_JEONJUJEONRAGAMYEONG", "action": "talk",
             "text": "전라감영이 역마와 숙식을 내어 준다. 감사가 웃는다. '섬 객주가 감영 손님이 되었구려.'"},
            {"node": "ND_06_CITY_GONGJUCHUNGCHEONGGAMYEONG", "action": "minigame",
             "text": "충청감영에서 구휼 장부를 셈해 올린다(주판 산학).", "minigame": "mg_abacus"}]},
        {"chapter": 5, "tier": 5, "title": "일만이천 봉", "stages": [
            {"node": "ND_02_CITY_HANYANGGYEONGJO", "action": "talk",
             "text": "평민은 임금을 뵐 수 없는 법. 조정은 만덕에게 내의원 의녀반수(醫女班首) 벼슬을 내려 대궐에 들게 한다. "
                     "정조가 말한다. '네가 한 일은 사내도 못 할 일이다.'"},
            {"node": "ND_01_CITY_GAESEONGBU", "action": "choice",
             "text": "금강산 가는 길에 들른 개성. 송상(개성상인)들이 섬 객주가 쓰는 장부법을 묻는다.",
             "choices": [{"id": "teach", "text": "섬과 뭍의 시세를 한 장에 맞춰 적는 법을 가르쳐 준다", "effects": {"knowledge_xp": {"sang": 80}}},
                         {"id": "learn", "text": "송상의 사개치부법(四介治簿法)을 배운다", "effects": {"knowledge_xp": {"sa": 80}}}]},
            {"node": "ND_03_CITY_CHEOLWONDOHOBU", "action": "talk",
             "text": "철원을 지나 단발령에 오르자 구름 사이로 금강산 봉우리가 펼쳐진다. 재상 채제공은 훗날 이 여정을 「만덕전」에 적었다."},
            {"node": "ND_03_SCENIC_GEUMGANGSANGURYONGPOK", "action": "talk",
             "text": "구룡폭 앞. '섬 여인이 금강산을 본 것은 만덕이 처음'이라 했다. 만덕은 바다 쪽을 돌아본다. 객주의 문은 여전히 열려 있다."}]},
    ],
}

SCENARIOS = [{
    "id": "sc_jeju_mandeok", "name": "[테스트] 제주 객주 김만덕 편", "hero_name": "김만덕", "class": "cls_merchant",
    "start_node": "ND_17_CITY_JEJUMOKJEJUEUPSEONG", "money": 500, "tutorial": "tut_jeju", "main": "ev_main_mandeok",
    "items": {"food_rice_mal": 3, "mat_jang": 1, "bk_food_jumak": 1},
    "desc": "제주목에서 객주를 여는 상인 김만덕으로 시작합니다. 튜토리얼이 장터·제작·이동·답사·전투·무역·이벤트·저장을 차례로 안내합니다.",
    "portrait": "res://assets/portraits/hero_mandeok.png", "costume": "jeju_merchant_woman",
    "prompt_who": "Kim Man-deok (1739-1812), Jeju island merchant and philanthropist who fed the island in the 1795 famine",
}]

# 조건 type: ack(다음 버튼) · counter{key,n} · visited{n} · at_node{node} · has_item{item,n} · event_progress{event,n}
TUTORIAL = [
    {"id": "tut_jeju_01", "tutorial": "tut_jeju", "title": "제주목에 오신 것을 환영합니다",
     "text": "화면 위쪽은 필드, 아래쪽은 대시보드입니다. 체력·피로·포만·배낭 무게를 늘 확인하세요. 오른쪽 기록창에 모든 소식이 쌓입니다.",
     "hint": "읽었으면 [다음]을 누르세요.", "cond": {"type": "ack"}},
    {"id": "tut_jeju_02", "tutorial": "tut_jeju", "title": "거점 시설 열기",
     "text": "도시·고을에는 장터·주막·관아 같은 시설이 있습니다. [거점 시설]을 누르면 지금 있는 곳의 시설 목록이 열립니다.",
     "hint": "대시보드 [거점 시설] 버튼", "cond": {"type": "counter", "key": "open_facilities", "n": 1}},
    {"id": "tut_jeju_03", "tutorial": "tut_jeju", "title": "장터에서 사기",
     "text": "장터에서 콩나물을 하나 사 보세요. 특산물은 원산지에서 싸고(×0.72) 멀리 갈수록 비싸게 팔립니다. 5일장마다 물량이 다시 채워집니다.",
     "hint": "거점 시설 → 장터 → 콩나물", "cond": {"type": "has_item", "item": "food_kongnamul", "n": 1}},
    {"id": "tut_jeju_04", "tutorial": "tut_jeju", "title": "요리하기",
     "text": "주막 국밥 조리서가 있으니 콩나물국밥(곡물 한 말 + 콩나물 + 장)을 만들 수 있습니다. 비전서가 있어야 레시피가 열리고, 주막 가마솥이나 야영 노구솥이 필요합니다.",
     "hint": "대시보드 [제작] → 콩나물국밥 (주막이 있는 곳에서)", "cond": {"type": "counter", "key": "craft", "n": 1}},
    {"id": "tut_jeju_05", "tutorial": "tut_jeju", "title": "대동여지도 펼치기",
     "text": "[지도](M 키)에서 목적지를 누르면 길을 따라 걸어갑니다. 산길은 느리고, 한 번 걸은 길은 빨라집니다. 이동 중에는 Space로 멈춥니다.",
     "hint": "[지도] 또는 M", "cond": {"type": "counter", "key": "open_map", "n": 1}},
    {"id": "tut_jeju_06", "tutorial": "tut_jeju", "title": "조천포로 가기",
     "text": "지도에서 동쪽 조천을 골라 이동하세요. 걷는 동안 피로가 쌓이고 포만감이 줄어듭니다. 신선 식품은 노드를 지날 때마다 신선도가 떨어집니다.",
     "hint": "지도 → 조천", "cond": {"type": "at_node", "node": "ND_17_TOWN_JOCHEON"}},
    {"id": "tut_jeju_07", "tutorial": "tut_jeju", "title": "이야기 진행",
     "text": "주황 표시가 있는 곳에서 [이벤트]를 누르면 시나리오가 진행됩니다. 김만덕 1장의 첫 이야기는 제주목에서, 두 번째는 조천에서 이어집니다.",
     "hint": "제주목·조천에서 [이벤트] → 진행", "cond": {"type": "event_progress", "event": "ev_main_mandeok", "n": 2}},
    {"id": "tut_jeju_08", "tutorial": "tut_jeju", "title": "유산 답사",
     "text": "방사탑·진·절 같은 유산에 가면 [거점 시설]에서 답사할 수 있습니다. 답사하면 명성과 보상(답사록·장비·비전서)을 얻고, 보상은 쓰기·기증·매각 중 하나를 고릅니다.",
     "hint": "조천 방사탑 또는 화북진에서 답사", "cond": {"type": "counter", "key": "heritage", "n": 1}},
    {"id": "tut_jeju_09", "tutorial": "tut_jeju", "title": "첫 전투",
     "text": "밤길이나 산길에서는 적과 마주칩니다. 전투는 행동 순서(CTB) 방식이라 빠른 쪽이 자주 움직입니다. [사냥]으로 연습 전투를 할 수도 있습니다.",
     "hint": "[사냥] 또는 이동 중 조우", "cond": {"type": "counter", "key": "battle_win", "n": 1}},
    {"id": "tut_jeju_10", "tutorial": "tut_jeju", "title": "보부상 위탁",
     "text": "밑천이 없어도 [무역]의 [위탁] 의뢰로 짐을 날라 운임을 벌 수 있습니다. 제주목 → 조천 말총 배달부터 해 보세요. 일반 무역 퀘스트는 대금 1.8배와 명성을 줍니다.",
     "hint": "제주목 장터 → 무역 → [위탁] 제주 말총 조천포 배달", "cond": {"type": "counter", "key": "trade_accept", "n": 1}},
    {"id": "tut_jeju_11", "tutorial": "tut_jeju", "title": "여정 기록(저장)",
     "text": "저장은 대도시 주막(온돌방)에서만 됩니다. 제주에서는 제주목 주막입니다. 먼 길을 떠나기 전에 꼭 기록하세요.",
     "hint": "제주목 → 주막 → 여정 기록", "cond": {"type": "counter", "key": "save", "n": 1}},
    {"id": "tut_jeju_12", "tutorial": "tut_jeju", "title": "튜토리얼 완료",
     "text": "이제 1장을 마치고 신분 Rank 2가 되면 2장 '뭍으로 가는 배'가 열립니다. 막히면 [도움말]에서 각 시스템 설명을 볼 수 있습니다.",
     "hint": "[다음]으로 마칩니다.", "cond": {"type": "ack"}},
]

HELP = [
    {"id": "help_move", "title": "이동·지도", "text": "지도에서 목적지를 누르면 최단 경로로 걷습니다. 산길 ×0.65, 뱃길 ×0.85 속도이고, 비·눈·밤에는 느려집니다. 한 번 걸은 간선은 빨라집니다. 역참에서는 엽전을 내고 빠른 이동을 할 수 있고, 나루에서는 뱃길을 탑니다(폭풍이면 결항)."},
    {"id": "help_survival", "title": "피로·포만·신선도", "text": "걷거나 싸우면 피로가 쌓이고, 70을 넘기면 휴식(야영·주막)이 필요합니다. 포만감은 시간에 따라 줄고, 30 아래로 떨어지면 자동 섭취가 켜져 있을 때 배낭 음식을 먹습니다. 신선 식품은 노드를 지날 때마다 신선도가 5%씩 떨어지고, 0%가 되면 버려집니다."},
    {"id": "help_trade", "title": "장터·무역", "text": "특산물은 원산지에서 기준가 ×0.72에 사서 권역 거리에 따라 0.60/0.95/1.15/1.35배에 팝니다. 5일장마다 원산지 권역 전체가 물량(기본 20·상품 8·진상품 3)을 나눠 씁니다. 같은 장터에 연달아 팔면 개당 2%씩(최저 60%) 값이 떨어지니 여러 장터에 나눠 파세요. 무역 퀘스트는 대금 1.8배와 명성을, 보부상 위탁은 밑천 없이 운임 30%를 줍니다."},
    {"id": "help_craft", "title": "제작·요리·재료 대체", "text": "비전서가 있어야 레시피가 열립니다. 곡물은 '한 말' 단위로 쓰고, 섬은 [제작 → 섬 풀기]로 10말로 나눕니다. '곡물'·'수렵육'처럼 군으로 적힌 재료는 그 군의 아무 품목이나 씁니다. 상위 등급 재료는 하위 재료를 1:1로 대신합니다(설정: 확인/자동/끔). 2등급 이상 높은 재료가 쓰일 때는 확인창이 뜹니다."},
    {"id": "help_heritage", "title": "유산 답사·보상 3택", "text": "유산에 가서 답사(필요하면 미니게임)하면 답사 명성과 보상을 얻습니다. 보상은 [쓰기] 장착·소지, [기증] 관아·향교에 바쳐 명성, [매각] 골동상·암시장에 팔아 엽전 중 하나를 고릅니다. 권역 유산을 모두 답사하면 수집 보너스를 받습니다. 숨은 유산은 [탐색]이나 봉수 점화로 찾습니다."},
    {"id": "help_battle", "title": "전투(CTB)", "text": "속도가 빠를수록 행동 차례가 자주 돌아옵니다. 행동마다 AP를 쓰고, 유>불>선>유 상성과 지식 랭크가 대미지에 더해집니다. 동료는 스킬·지식·운반량만 보태고 능력치를 더하지는 않습니다. 짐승·요괴는 포획 도구로 잡아 동료로 삼을 수 있습니다."},
    {"id": "help_rank", "title": "신분·도 명성·엔딩", "text": "명성이 쌓이면 관아 승급 심사로 신분 Rank가 오릅니다(1~5). 콘텐츠의 약 1/3을 찾으면 Rank 5에 닿아 엔딩(메인 시나리오 5장)이 가능합니다. 도(道) 명성은 그 도 감영의 발전 단계 조건이고, 2/3 정도 둘러보면 5단계까지 올릴 수 있습니다."},
    {"id": "help_companion", "title": "동료·승급", "text": "동료는 1~3등급으로 합류하고, 서사 승급 퀘스트로 5등급까지 오릅니다. 파티는 3명이고 나머지는 막사에서 기다립니다. 동행 중에는 일급이 나갑니다."},
    {"id": "help_knowledge", "title": "지식(유·불·선·사농공상)", "text": "학식(유·불·선)은 상성 대미지를, 생활 지식(사·농·공·상)은 필드 효과를 줍니다. 상(商)은 매매가와 뱃삯 할인(랭크당 5%), 농(農)은 채집·신선도, 공(工)은 재료 절감, 사(士)는 탐색 반경을 높입니다."},
    {"id": "help_save", "title": "저장·체크포인트", "text": "여정 기록은 대도시 주막에서만 됩니다. 쓰러지면 가까운 주막으로 옮겨지고, 잃는 것은 시간뿐입니다."},
]

# ================================================================ 권역 적 (기존 동일 등급 평균치 기준)
def enemy(id_, name, kind, tier, et, hp, atk, df, spd, elem, skills, lore, drops, regions, terrains, time="ANY", carry=10, extra=None):
    e = {"id": id_, "name": name, "kind": kind, "yu_bul_seon_type": "none", "tier": tier, "enemy_tier": et, "hp": hp, "atk": atk, "def": df,
         "speed": spd, "combat_scale": {"NORMAL": 1.2, "ELITE": 1.35}[et] + (0.05 if tier >= 3 else 0), "base_ap": 3, "element": elem, "res": {},
         "flee_rate": 0.9, "capturable": True, "skills": skills, "lore_tag": lore, "drops": drops,
         "spawn_conditions": {"regions": regions, "terrains": terrains, "allowed_time": time},
         "capture_profile": {"dupes_to_upgrade": 2, "companion_bonuses": {"knowledge_add": {}, "upkeep": {"type": "wage", "cost": 0}, "carry": carry}}}
    e.update(extra or {})
    return e


ENEMIES = [
    enemy("en_jeju_dochaebi", "제주 도채비", "yokai", 1, "NORMAL", 55, 13, 7, 92, "fire", ["sk_en_bite"], "[설화] 제주 도깨비 '도채비'",
          [{"id": "food_songgi", "rate": 0.3}], ["MAP_17"], ["road", "mountain", "trail"], "NIGHT_ONLY", 8),
    enemy("en_jeju_yeonggam", "영감(도깨비신)", "yokai", 2, "ELITE", 190, 26, 18, 96, "fire", ["sk_en_bite", "sk_en_fox_charm"],
          "[설화] 제주 영감놀이의 도깨비신", [{"id": "sp_jeju_malchong", "rate": 0.4}], ["MAP_17"], ["road", "mountain"], "NIGHT_ONLY", 10,
          {"flee_rate": 0.9}),
    enemy("en_hwangdangseon", "황당선 선원", "human", 2, "NORMAL", 140, 24, 12, 92, "water", ["sk_en_bandit_rush", "sk_en_bleed_slash"],
          "[역사] 19세기 연해의 이양선·황당선", [{"id": "mat_copper", "rate": 0.3}], ["MAP_06", "MAP_12", "MAP_13", "MAP_17"], ["water", "road"], "ANY", 10),
    enemy("en_majeok", "북방 마적", "human", 3, "NORMAL", 280, 38, 24, 104, "metal", ["sk_en_bandit_rush", "sk_en_bleed_slash"],
          "[역사] 두만강·압록강 너머의 마적 떼", [{"id": "mat_cowhide", "rate": 0.5}, {"id": "mat_iron", "rate": 0.3}],
          ["MAP_14", "MAP_15", "MAP_16"], ["road", "mountain"], "ANY", 12),
    enemy("en_boar_herd", "멧돼지 떼", "beast", 2, "NORMAL", 160, 25, 14, 90, "none", ["sk_en_bite"], "역사",
          [{"id": "food_boar", "rate": 0.5}, {"id": "mat_cowhide", "rate": 0.3}], ["*"], ["mountain"], "ANY", 14,
          {"gimmicks": [{"type": "lure", "item": "item_bait", "qty": 1, "result": "weaken", "atk_mult": 0.8}]}),
    enemy("en_bear", "반달곰", "beast", 3, "NORMAL", 320, 40, 26, 96, "none", ["sk_en_bite", "sk_en_bleed_slash"], "역사",
          [{"id": "food_bear", "rate": 0.4}, {"id": "mat_cowhide", "rate": 0.5}], ["MAP_03", "MAP_04", "MAP_14", "MAP_15", "MAP_16"], ["mountain"], "ANY", 18),
]

# ================================================================ 무예 단조서 장비 (3등급 대장간 단조, 별운검·경번갑 급)
MARTIAL = [
    {"id": "eq_w3_dangpa", "name": "당파창(鏜鈀槍)", "slot": "weapon", "tier": 3, "family": "none", "element": "metal", "affinity": "none",
     "stats": {"atk": 19, "def": 3}, "weight": 3.5,
     "acquire": {"type": "forge", "book": "bk_mar_spear", "min_rank": 3,
                 "materials": [{"id": "mat_iron", "qty": 6}, {"id": "mat_charcoal", "qty": 4}, {"id": "mat_wood", "qty": 2}]},
     "desc": "끝이 세 갈래인 창. 『무예도보통지』 24기의 하나로, 적의 창칼을 걸어 막고 찌른다."},
    {"id": "eq_c3_deungpae", "name": "등패(藤牌)", "slot": "accessory", "tier": 3, "family": "none", "element": "none", "affinity": "none",
     "stats": {"def": 8, "res": 0.05}, "weight": 2.0,
     "acquire": {"type": "forge", "book": "bk_mar_shield", "min_rank": 3,
                 "materials": [{"id": "mat_bamboo", "qty": 6}, {"id": "mat_cowhide", "qty": 2}, {"id": "mat_lacquer", "qty": 1}]},
     "desc": "등나무를 엮어 옻칠한 방패. 등패수는 요도와 표창을 함께 썼다."},
    {"id": "eq_w3_pyeongon", "name": "편곤(鞭棍)", "slot": "weapon", "tier": 3, "family": "none", "element": "metal", "affinity": "none",
     "stats": {"atk": 21, "crit": 0.05}, "weight": 3.0,
     "acquire": {"type": "forge", "book": "bk_mar_flail", "min_rank": 3,
                 "materials": [{"id": "mat_iron", "qty": 5}, {"id": "mat_charcoal", "qty": 3}, {"id": "mat_cowhide", "qty": 2}]},
     "desc": "긴 자루 끝에 짧은 도리깨를 쇠사슬로 단 무기. 기병의 마상편곤으로 이름났다."},
]

# ================================================================ 4등급 탈것 퀘스트
MOUNTS = [
    {"id": "mt_jeju_heonma", "name": "제주 헌마(獻馬)", "terrain": "ground", "tier": 4, "v_mount": 72, "carry_capacity": 32, "stamina": 110,
     "spd_bonus": 0.07, "min_rank": 4, "skill": "sk_mt_heonma",
     "acquire": {"type": "quest", "quest_name": "산마장 진상마 호송",
                 "route": ["ND_17_TOWN_JEONGUIHYEON", "ND_17_CITY_JEJUMOKJEJUEUPSEONG", "ND_08_TOWN_HAENAM"]},
     "desc": "제주 산마장에서 골라 조정에 바치던 진상마. 작지만 지구력이 뛰어나다."},
    {"id": "mt_joun_ship", "name": "경강 조운선", "terrain": "water", "tier": 4, "v_mount": 55, "carry_capacity": 90, "stamina": 100,
     "spd_bonus": 0.05, "min_rank": 4, "skill": "sk_mt_joun",
     "acquire": {"type": "quest", "quest_name": "영산창 세곡 조운",
                 "route": ["ND_08_CITY_NAJUMOK", "ND_07_CITY_JEONJUJEONRAGAMYEONG", "ND_06_CITY_GONGJUCHUNGCHEONGGAMYEONG"]},
     "desc": "삼남의 세곡을 경강(한강)까지 나르던 조운선. 짐을 많이 싣는다."},
]
MOUNT_SKILLS = [
    {"id": "sk_mt_heonma", "name": "산마장 질주", "owner": "mount", "target": "self", "ap_cost": 2, "power": 0.0, "element": "none", "affinity": "none",
     "cooldown": 4, "effects": {"gauge_boost": 300}},
    {"id": "sk_mt_joun", "name": "세곡 방진", "owner": "mount", "target": "allies", "ap_cost": 3, "power": 0.0, "element": "none", "affinity": "none",
     "cooldown": 4, "effects": {"buff": {"def_pct": 0.1, "turns": 2}}},
]

JAKSEOL = {"id": "hr_jakseol", "name": "작설차", "form": "탕약", "tier": 2, "book": "bk_med_daegu",
           "ingredients": [{"id": "sp_hadong_jakseol", "qty": 1}, {"id": "herb_gamcho", "qty": 1}],
           "effect": {"heal_pct": 0.05, "cure": ["stun", "fear"]}, "battle_usable": True}


def main():
    doc = load("20_events.json")
    doc["events"] = keep(doc["events"]) + tag(EVENTS)
    doc["main_scenarios"] = keep(doc["main_scenarios"]) + tag([MANDEOK_MAIN])
    doc["_schema"] = doc["_schema"].split(" | 시나리오")[0] + (" | 시나리오: main_scenarios[].scenario 가 있으면 그 시작 설정(23_tutorial.scenarios)으로 "
                                                         "새 게임을 시작했을 때만 진행(클래스 기본 메인 대신).")
    save("20_events.json", doc)

    doc = load("12_enemies.json")
    doc["enemies"] = keep(doc["enemies"]) + tag(ENEMIES)
    save("12_enemies.json", doc)

    doc = load("02_equipment.json")
    doc["items"] = keep(doc["items"]) + tag(MARTIAL)
    save("02_equipment.json", doc)
    doc = load("15_recipe_books.json")
    for b in doc["books"]:
        for m in MARTIAL:
            if b["id"] == m["acquire"]["book"] and m["id"] not in b["unlocks"]:
                b["unlocks"].append(m["id"])
        if b["id"] == "bk_med_daegu" and JAKSEOL["id"] not in b["unlocks"]:
            b["unlocks"].append(JAKSEOL["id"])
    save("15_recipe_books.json", doc)

    doc = load("07_mounts.json")
    doc["mounts"] = keep(doc["mounts"]) + tag(MOUNTS)
    save("07_mounts.json", doc)
    doc = load("14_skills.json")
    doc["skills"] = keep(doc["skills"]) + tag(MOUNT_SKILLS)
    save("14_skills.json", doc)

    doc = load("09_herbal_recipes.json")
    doc["recipes"] = keep(doc["recipes"]) + tag([JAKSEOL])
    save("09_herbal_recipes.json", doc)

    save("23_tutorial.json", {
        "_schema": "23_튜토리얼·시나리오·도움말. scenarios=새 게임 시작 설정(클래스·시작 노드·엽전·아이템·튜토리얼·메인 시나리오). "
                   "steps=튜토리얼 단계(tutorial 묶음 순서대로, cond 충족 시 다음 단계). cond.type: ack|counter{key,n}|visited{n}|at_node{node}|"
                   "has_item{item,n}|event_progress{event,n}. counter 키: open_facilities·open_map·buy·sell·craft·unpack·heritage·battle_win·"
                   "trade_accept·trade_done·save·event_stage·gather·camp. help=도움말 항목(대시보드 [도움말]).",
        "scenarios": SCENARIOS, "steps": TUTORIAL, "help": HELP})
    print(f"이벤트 +{len(EVENTS)} · 메인 시나리오 +1(김만덕 5장) · 적 +{len(ENEMIES)} · 무예 장비 +{len(MARTIAL)} · 탈것 +{len(MOUNTS)} · "
          f"작설차 · 튜토리얼 {len(TUTORIAL)}단계 · 도움말 {len(HELP)}")


if __name__ == "__main__":
    main()
