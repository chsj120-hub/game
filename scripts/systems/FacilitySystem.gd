class_name FacilitySystem
extends RefCounted
## 완전판 5장 거점 시설 독립 모달의 '행동 목록'과 시설 전용 서비스.
## UI(FacilityModal)는 actions(facility) 결과로 버튼을 만들고, 선택된 action id 를 Main 으로 라우팅한다.

const NAMES := {"gwana": "관아", "jumak": "주막", "gaekju": "객주(막사)", "market": "상설시장", "market5": "5일장", "forge": "대장간",
	"forge_basic": "촌 대장간", "bookstore": "서점·학관", "yakbang": "약방", "hyeminseo": "혜민서", "yakryeongsi": "약령시",
	"antique": "골동상", "black_market": "암시장", "hyanggyo": "향교", "restaurant": "식당", "gongbang": "공방", "carpenter": "목공소",
	"yeokcham": "역참", "temple": "명찰", "bath": "온천탕", "checkpoint": "관문 검문소", "drill": "병영", "bounty": "현상수배 방",
	"beacon": "봉수대", "scenic": "절경", "investigate": "유적 조사", "hazard": "위험 고개", "ferry": "나루터"}


static func facilities_here() -> Array:
	return DataDB.get_row(GameState.current_node).get("facilities", [])


## [{id, text, hint, disabled}]
static func actions(fac: String) -> Array:
	var gs := GameState
	var out := []
	match fac:
		"gwana":
			var pa := gs.promotion_available()
			out.append({"id": "promote", "text": "신분 승급 심사", "disabled": not pa,
				"hint": "Rank %d 심사 가능" % (gs.rank + 1) if pa else "명성 %d/%d" % [gs.reputation, Balance.rank_threshold(mini(gs.rank + 1, Balance.max_rank()))]})
			out.append({"id": "heritage_pending", "text": "유산 정식 봉납(기증)", "hint": "대기 %d건" % HeritageSystem.pending().size()})
			out.append({"id": "gwana_doc", "text": "조정 공문 수령(전령 퀘스트)", "hint": "권역 내 2노드"})
			out.append({"id": "bounty_board", "text": "포도청 현상수배지", "hint": "%d건" % gs.bounties.size()})
			out.append({"id": "takbon", "text": "대동여지도 판목 탁본 인출", "hint": SideSystems.takbon_can()})
			out.append({"id": "seasonal", "text": "세시풍속 참여 (%s)" % gs.solar_term(), "hint": SideSystems.seasonal_available()})
		"jumak":
			out.append({"id": "inn", "text": "온돌방 숙박(피로 완전 회복)", "hint": "여정 자동 기록" if gs.can_save_here() == "" else ""})
			var se := gs.can_save_here()
			out.append({"id": "save", "text": "여정 기록(저장)", "disabled": se != "", "hint": se})
			out.append({"id": "load", "text": "여정 불러오기", "disabled": se != "" or not gs.has_save(), "hint": se})
			out.append({"id": "craft", "text": "가마솥 조리", "hint": "조리서 필요"})
			out.append({"id": "barracks", "text": "별채 막사(동료 보관·파견)", "hint": "%d/%d" % [gs.barracks.size(), CompanionSystem.barracks_slots()]})
			out.append({"id": "seasonal", "text": "세시풍속 참여 (%s)" % gs.solar_term(), "hint": SideSystems.seasonal_available()})
		"gaekju":
			out.append({"id": "barracks", "text": "객주 막사(동료 보관·파견)", "hint": "%d/%d 슬롯" % [gs.barracks.size(), CompanionSystem.barracks_slots()]})
			out.append({"id": "trade", "text": "무역 의뢰", "hint": ""})
		"market", "market5":
			out.append({"id": "shop", "text": "물건 사기", "hint": "5일 주기 갱신"})
			out.append({"id": "sell", "text": "물건 팔기", "hint": "원산지에서 멀수록 비싸게"})
			out.append({"id": "trade", "text": "무역 의뢰", "hint": ""})
			if fac == "market":
				var is_cap := String(Balance.province_of_node(gs.current_node).get("capital", "")) == gs.current_node
				out.append({"id": "invest", "text": "%s 발전기금 투자" % ("감영(도 전역 혜택)" if is_cap else "도시(국지 혜택·선택 과제)"), "hint": TradeSystem.invest_hint(gs.current_node)})
		"forge", "forge_basic", "gongbang", "carpenter":
			out.append({"id": "craft", "text": "도면 선택 → 단조·제작", "hint": "비전서 필요"})
			out.append({"id": "shop", "text": "무구 구매", "hint": ""})
		"bookstore":
			for k in GameState.KNOWLEDGE_KEYS:
				var r := int(gs.knowledge.get(k, 0))
				out.append({"id": "read:" + k, "text": "%s 강독서 정독" % DataDB.classes_doc.get("knowledge", {}).get("names", {}).get(k, k),
					"hint": "%d냥 · 현재 %d랭크" % [read_price(k), r], "disabled": r >= 10})
			out.append({"id": "shop", "text": "서책·비전서 구매", "hint": ""})
			out.append({"id": "takbon", "text": "판목 탁본 인출", "hint": SideSystems.takbon_can()})
		"yakbang", "hyeminseo", "yakryeongsi", "restaurant":
			out.append({"id": "shop", "text": "구매", "hint": ""})
			out.append({"id": "craft", "text": "조제·조리", "hint": "의서·조리서 필요"})
			if fac == "hyeminseo":
				out.append({"id": "cure_all", "text": "혜민서 진료(역병 무료 치료)", "hint": ""})
		"antique", "black_market", "hyanggyo":
			out.append({"id": "heritage_pending", "text": "유산 감정·거래", "hint": "대기 %d건" % HeritageSystem.pending().size()})
			out.append({"id": "sell", "text": "물건 팔기", "hint": ""})
		"yeokcham":
			out.append({"id": "swap_horse", "text": "마필 교체(탈것 기력 회복)", "hint": "%d냥" % swap_horse_cost()})
			out.append({"id": "fast_travel", "text": "역참 쾌속 이동", "hint": "경유 이벤트 생략"})
			out.append({"id": "shop", "text": "탈것 매매", "hint": ""})
		"temple":
			out.append({"id": "temple_rest", "text": "요사채 휴식(피로 60~80 회복)", "hint": ""})
			out.append({"id": "blessing", "text": "불가 헌납(7일 가호)", "hint": "%d냥" % int(DataDB.overview.get("facilities", {}).get("temple_blessing", {}).get("donation", 100))})
			out.append({"id": "haewon", "text": "원혼 해원(범종 타종)", "hint": "불교 지식 상승"})
			out.append({"id": "shop", "text": "사찰 비록 구매", "hint": ""})
		"bath":
			out.append({"id": "bath", "text": "온천욕(피로 완치·질병 치료·3일 버프)", "hint": ""})
		"checkpoint":
			out.append({"id": "checkpoint_info", "text": "검문 조건 확인", "hint": TravelSystem.checkpoint_block(gs.current_node) if TravelSystem.checkpoint_block(gs.current_node) != "" else "통과 가능"})
		"drill":
			out.append({"id": "drill", "text": "병영 군사 훈련", "hint": "%d냥" % drill_cost()})
		"bounty":
			out.append({"id": "bounty_board", "text": "토벌 현상수배", "hint": "%d건" % gs.bounties.size()})
		"beacon":
			out.append({"id": "beacon", "text": "봉화 점화(권역 은닉 노드 해금)", "hint": "완료" if gs.lit_beacons.has(gs.current_region) else ""})
			out.append({"id": "takbon", "text": "판목 탁본 인출", "hint": SideSystems.takbon_can()})
		"scenic":
			out.append({"id": "hwacheop", "text": "화첩 기록(진경)", "hint": "%d건 가능" % SideSystems.hwacheop_available().size()})
		"investigate":
			out.append({"id": "investigate", "text": "유적 정밀 조사", "hint": ""})
		"ferry":
			out.append({"id": "ferry", "text": "뱃길 선택", "hint": "풍향·요금"})
		"hazard":
			out.append({"id": "hazard_fight", "text": "고개 돌파(조우)", "hint": "위험"})
	return out


# ------------------------------------------------------------ 시설 서비스
static func read_price(k: String) -> int:
	return int(round(Balance.curve(DataDB.overview.get("facilities", {}).get("bookstore", {}).get("knowledge_book_price", {}), maxi(1, int(GameState.knowledge.get(k, 0))))))


static func read_book(k: String) -> String:
	var gs := GameState
	if not gs.spend_money(read_price(k)):
		return "엽전 부족"
	gs.add_knowledge_xp(k, int(DataDB.classes_doc.get("knowledge", {}).get("xp_sources", {}).get("bookstore_read", 150)))
	gs.advance_minutes(240)
	return ""


static func drill_cost() -> int:
	return int(round(Balance.curve(DataDB.overview.get("facilities", {}).get("drill", {}).get("cost", {}), GameState.rank)))


static func drill() -> String:
	var gs := GameState
	if not gs.spend_money(drill_cost()):
		return "훈련비 부족"
	var aff := String(DataDB.class_row(gs.class_id).get("affinity", "yu"))
	gs.add_knowledge_xp(aff if aff != "none" else "sa", 80)
	gs.apply_food_buff({"atk_pct": 0.08, "def_pct": 0.05, "duration_battles": 3})
	gs.fatigue = minf(100.0, gs.fatigue + 25.0)
	gs.advance_minutes(360)
	gs.note("병영 훈련 — 다음 전투 3회 공격 +8%·방어 +5%")
	return ""


static func swap_horse_cost() -> int:
	var m := String(GameState.equipped.get("mount", ""))
	return 5 * int(DataDB.get_row(m).get("tier", 1)) if m != "" else 0


static func swap_horse() -> String:
	var gs := GameState
	if String(gs.equipped.get("mount", "")) == "":
		return "탈것이 없습니다"
	if not gs.spend_money(swap_horse_cost()):
		return "엽전 부족"
	gs.mount_stamina = 100.0
	gs.note("역참에서 마필을 교체했습니다(기력 100).")
	gs.stats_changed.emit()
	return ""


static func blessing() -> String:
	var gs := GameState
	var b: Dictionary = DataDB.overview.get("facilities", {}).get("temple_blessing", {})
	if not gs.spend_money(int(b.get("donation", 100))):
		return "헌납금 부족"
	gs.add_field_status(String(b.get("buff", "BUFF_TEMPLE_GAHO")), float(b.get("days", 7)))
	gs.add_knowledge_xp("bul", 30)
	return ""


static func haewon_done(ok: bool) -> void:
	var gs := GameState
	if ok:
		gs.add_knowledge_xp("bul", 60)
		gs.add_reputation(Balance.quest_reward(maxi(1, gs.rank - 1), "gwana_doc", "rep"), gs.current_region, true)
		gs.note("원혼이 성불했습니다.")
	else:
		gs.note("종소리가 흐트러졌습니다…")
	gs.advance_minutes(120)


## 조정 공문: 같은 권역 다른 대도시/역참으로 전달 (1~2등급 규칙: 동일 권역 2노드)
static func gwana_doc_quest() -> Dictionary:
	var gs := GameState
	var cands := DataDB.nodes_in(gs.current_region).filter(func(n): return n["id"] != gs.current_node and String(n["type"]) in ["city", "station", "fort"] and not n.get("hidden", false))
	if cands.is_empty():
		return {}
	var dst: Dictionary = cands[gs.rng.randi_range(0, cands.size() - 1)]
	return {"id": "q_doc_%d_%s" % [gs.day(), gs.current_node], "name": "공문 전달 → %s" % dst["name"], "tier": mini(gs.rank, 2),
		"type": "gwana_doc", "route": [gs.current_node, dst["id"]], "reward": {}}
