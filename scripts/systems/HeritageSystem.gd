class_name HeritageSystem
extends RefCounted
## 국가유산 답사 → 5대 보상 형태 → 3가지 선택(실사용 / 관아·향교 기증 / 골동상·암시장 매각)
## 보상치는 Balance.heritage_reward (economy 자동 공식). 은닉 노드는 조사 미니게임 성공 시 획득(실패 시 반나절 뒤 재도전).

const DONATE_VENUES := ["gwana", "hyanggyo"]
const SELL_VENUES := ["antique", "black_market"]


static func reward_type(her: Dictionary) -> String:
	return String(DataDB.category_reward_map.get(her.get("category", ""), "record"))


static func reward_type_label(t: String) -> String:
	match t:
		"record": return "《답사록》 생활행장"
		"specialty_recipe": return "【특산물 레시피북】"
		"accessory": return "【장신구】"
		"equipment": return "【장착 장비】"
		"book": return "【서책】"
	return t


## 답사에 필요한 미니게임: 유산 지정값 → 24 시트 유산별 변형(mg_variants) → 은닉 유형 기본값. 없으면 ""
static func required_minigame(her: Dictionary) -> String:
	if her.has("minigame"):
		return String(her["minigame"])
	var v := DataDB.mg_variant(String(her.get("id", "")))
	if not v.is_empty():
		return String(v.get("minigame", ""))
	if not her.get("hidden", false) and String(her.get("node_type", "")) in ["city", "temple", "fort", "scenic"]:
		return ""
	var d: Dictionary = DataDB.docs.get("21_minigames.json", {}).get("node_type_default", {})
	return String(d.get(String(her.get("node_type", "")), ""))


## 유산별 미니게임 내용 덮어쓰기(문항·단계·난이도). 같은 미니게임을 유산마다 다르게 — MinigameBase.create_from_catalog(id, overrides)
static func minigame_overrides(her_id: String) -> Dictionary:
	var her := DataDB.get_row(her_id)
	var v := DataDB.mg_variant(her_id)
	if v.is_empty() or String(v.get("minigame", "")) != required_minigame(her):
		return {}
	var o: Dictionary = v.get("params", {}).duplicate()
	o["_title"] = String(her.get("name", ""))
	return o


## 전설 퀘스트 잠금 사유("" = 없음)
static func lore_lock(her_id: String) -> String:
	var qid := DataDB.lore_gate(her_id)
	if qid == "" or qid in GameState.completed_quests:
		return ""
	var st := "진행 중" if GameState.active_quests.has(qid) else "[퀘스트]에서 수락"
	return "「%s」 전설을 먼저 따라가야 모습을 드러냅니다 — %s" % [DataDB.display_name(qid), st]


static func can_visit(her_id: String) -> String:
	var gs := GameState
	var her := DataDB.get_row(her_id)
	if her.is_empty():
		return "알 수 없는 유산"
	if String(her.get("node", "")) != gs.current_node:
		return "%s 에 가야 답사할 수 있습니다." % DataDB.display_name(String(her.get("node", "")))
	if gs.heritage_state.has(her_id):
		return "이미 답사한 유산입니다."
	var ll := lore_lock(her_id)
	if ll != "":
		return ll
	if int(gs.investigate_retry.get(gs.current_node, 0)) > gs.minutes:
		return "조사 흔적이 흐트러졌습니다 — 반나절 뒤 다시 시도하세요."
	var mg := required_minigame(her)
	if mg != "" and bool(DataDB.minigame(mg).get("params", {}).get("requires_water_mount", false)) and not gs.has_water_mount():
		return "수중 인양에는 선박(황포돛배 등)이 필요합니다."
	return ""


## 조사 결과 반영 (미니게임 없으면 ok=true 로 바로 호출)
static func visit(her_id: String, ok: bool) -> String:
	var gs := GameState
	var err := can_visit(her_id)
	if err != "":
		return err
	var her := DataDB.get_row(her_id)
	var xs: Dictionary = DataDB.classes_doc.get("knowledge", {}).get("xp_sources", {})
	if not ok:
		gs.investigate_retry[gs.current_node] = gs.minutes + 720
		gs.note("조사 실패… 반나절 뒤 다시 도전할 수 있습니다(영구 손실 없음).")
		return ""
	gs.heritage_state[her_id] = "pending"
	gs.add_item(String(her["reward"]))
	var disc := Balance.heritage_reward(her, "discover", "", gs.rank, gs.party_knowledge(), gs.rng)
	var dg := gs.add_reputation(disc, String(her["region"]))
	gs.note("답사 명성 +%d (보상 선택과 무관)" % dg)
	var aff := {"temple": "bul", "stupa": "bul", "seowon": "yu", "shrine": "seon", "tomb": "yu"}.get(String(her.get("node_type", "")), "sa")
	if String(her.get("faction", "")) in ["yu", "bul", "seon"]:  # 국가유산 448: 유·불·선 계열
		aff = String(her["faction"])
	gs.add_knowledge_xp(aff, int(xs.get("heritage_visit_affinity", 40)))
	if her.get("hidden", false):
		gs.add_knowledge_xp("sa", int(xs.get("investigate_success", 60)))
	var perm := int(DataDB.get_row(String(her["reward"])).get("permanent_hp", 0))
	if perm > 0 and gs.hp_max() < float(DataDB.classes_doc.get("hp_cap", 250)):
		gs.permanent_hp += perm
		gs.note("팔도 절경의 기운 — 최대 체력 영구 +%d" % perm)
	gs.codex_add(her_id, String(her.get("lore", "역사")))
	gs.note("답사 완료: %s → %s %s 획득" % [her["name"], reward_type_label(reward_type(her)), DataDB.display_name(String(her["reward"]))])
	RouteQueue.on_node_visited(her_id)
	_check_region_collection(String(her["region"]))
	gs.bump("heritage")
	gs.stats_changed.emit()
	return ""


## 권역 유산 전수 답사 보너스 = 권역 유산 기증가 합 × 10% (선택과 무관하게 탐험 완주 보상)
static func _check_region_collection(region: String) -> void:
	var gs := GameState
	var key := "_collect_" + region
	if gs.heritage_state.has(key):
		return
	var total := 0
	for h in DataDB.heritage_list():
		if String(h["region"]) != region:
			continue
		if not gs.heritage_state.has(h["id"]):
			return
		total += Balance.heritage_reward_expect(h, "donate", "gwana", int(h["tier"]), {})
	gs.heritage_state[key] = "done"
	var bonus := int(total * float(DataDB.overview.get("economy", {}).get("region_collection_bonus", 0.1)))
	var got := gs.add_reputation(bonus, region)
	gs.note("【%s 유산 전수 답사】 수집 보너스 명성 +%d" % [DataDB.display_name(region), got])


static func pending() -> Array:
	return GameState.heritage_state.keys().filter(func(k): return GameState.heritage_state[k] == "pending")


static func _venue_here(venues: Array) -> String:
	for v in venues:
		if DataDB.node_has(GameState.current_node, String(v)):
			return String(v)
	return ""


## 선택지 미리보기: {use, donate, sell 사유("" = 가능), 기대 명성/엽전, venue}
static func preview(her_id: String) -> Dictionary:
	var gs := GameState
	var her := DataDB.get_row(her_id)
	var dv := _venue_here(DONATE_VENUES)
	var sv := _venue_here(SELL_VENUES)
	var need := Balance.donate_min_rank(int(her.get("tier", 1)))
	var donate_err := ""
	if dv == "":
		donate_err = "이 고을에 관아/향교가 없습니다"
	elif gs.rank < need:
		donate_err = "관아가 감정을 거부 — 신분 Rank %d 필요(보관 또는 매각)" % need
	var pk := gs.party_knowledge()
	return {
		"use": "",
		"donate": donate_err, "donate_venue": dv,
		"sell": "" if sv != "" else "이 고을에 골동상/암시장이 없습니다", "sell_venue": sv,
		"reputation": Balance.heritage_reward_expect(her, "donate", dv if dv != "" else "gwana", gs.rank, pk),
		"discovery": Balance.heritage_reward_expect(her, "discover", "", gs.rank, pk),
		"rank_gap": Balance.rank_gap_mult(int(her.get("tier", 1)), gs.rank),
		"money": Balance.heritage_reward_expect(her, "sell", sv if sv != "" else "antique", gs.rank, pk),
		"black_market": DataDB.node_has(gs.current_node, "black_market"),
	}


## choice: use | donate | sell | sell_black
static func resolve(her_id: String, choice: String) -> String:
	var gs := GameState
	if gs.heritage_state.get(her_id, "") != "pending":
		return "선택 대기 중인 유산이 아닙니다."
	var her := DataDB.get_row(her_id)
	var item_id := String(her["reward"])
	var pv := preview(her_id)
	var pk := gs.party_knowledge()
	match choice:
		"use":
			var rt := reward_type(her)
			if rt in ["record", "accessory", "equipment", "book"]:
				gs.equip(item_id)
			else:
				gs.note("%s 를 비전서함에 등록 — 공방에서 영구 제작 가능." % DataDB.display_name(item_id))
		"donate":
			if String(pv["donate"]) != "":
				return String(pv["donate"])
			gs.remove_item(item_id)
			var v := Balance.heritage_reward(her, "donate", String(pv["donate_venue"]), gs.rank, pk, gs.rng)
			if String(pv["donate_venue"]) == "gwana":
				v = int(v * float(gs.class_passive().get("gwana_rep_mult", 1.0)))
			var got := gs.add_reputation(v, String(her["region"]))
			gs.note("%s 봉납: 명성 +%d" % ["관아" if pv["donate_venue"] == "gwana" else "향교", got])
		"sell", "sell_black":
			var venue := "black_market" if choice == "sell_black" else "antique"
			if not DataDB.node_has(gs.current_node, venue):
				return "이 고을에 %s 이(가) 없습니다" % ("암시장" if venue == "black_market" else "골동상")
			gs.remove_item(item_id)
			var m := Balance.heritage_reward(her, "sell", venue, gs.rank, pk, gs.rng)
			m = int(m * float(gs.class_passive().get("sell_mult", 1.0)))
			gs.add_money(m)
			gs.note("%s 매각: 엽전 +%d냥" % ["암시장" if venue == "black_market" else "골동상", m])
			var bm: Dictionary = DataDB.overview.get("economy", {}).get("venue", {}).get("black_market", {})
			if venue == "black_market" and gs.rng.randf() < float(bm.get("bust_chance", 0.1)):
				var loss := int(Balance.heritage_reward_expect(her, "donate", "gwana", gs.rank, pk) * float(bm.get("bust_rep_loss", 0.3)))
				gs.reputation = maxi(0, gs.reputation - loss)
				gs.note("포도청에 암거래가 적발되었습니다! 명성 −%d" % loss)
			var mj := String(DataDB.get_row(item_id).get("mojak_recipe", ""))
			if mj != "" and not (mj in gs.mojak_unlocked):
				gs.mojak_unlocked.append(mj)
				gs.note("%s 단조법 해금" % DataDB.display_name(mj))
		_:
			return "잘못된 선택"
	gs.heritage_state[her_id] = choice
	gs.stats_changed.emit()
	return ""
