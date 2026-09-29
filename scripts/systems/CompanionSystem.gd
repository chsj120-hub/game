class_name CompanionSystem
extends RefCounted
## 완전판 8장: 파티 3인 · 객주 막사 보관함(10→30슬롯) · 사농공상 파견 · 중복 포획 스택 승급(1~5성) · 동행 일급


static func _bc() -> Dictionary:
	return DataDB.overview.get("barracks", {})


static func barracks_slots() -> int:
	var b := _bc()
	var slots := int(b.get("base_slots", 10))
	slots += int(b.get("rank_bonus", {}).get(str(GameState.rank), 0))
	var best_dev := 0  # 감영 발전 단계 중 최고치만 막사 확장에 반영(주 지출처 = 감영)
	for p in DataDB.overview.get("provinces", []):
		best_dev = maxi(best_dev, int(GameState.town_dev.get(String(p["capital"]), 0)))
	slots += best_dev * int(DataDB.overview.get("town_dev", {}).get("benefits", {}).get("capital_per_level", {}).get("barracks_slots", 2))
	return mini(slots, int(b.get("max_slots", 30)))


# ================================================================ 등급 승급(1~3등급 시작 → 승급 퀘스트로 최대 5등급)
## 현재 등급(저장값 우선, 구 세이브는 데이터 tier)
static func tier_of(cid: String) -> int:
	var row := DataDB.get_row(cid)
	return int(GameState.companions.get(cid, {}).get("tier", row.get("start_tier", row.get("tier", 1))))


## 지식 가산 = 시작 knowledge_add + knowledge_per_promotion × (현재 등급 − 시작 등급)  → 지식 합 = 현재 등급
static func knowledge_of(cid: String) -> Dictionary:
	var row := DataDB.get_row(cid)
	var out: Dictionary = row.get("knowledge_add", row.get("capture_profile", {}).get("companion_bonuses", {}).get("knowledge_add", {})).duplicate()
	var ups := tier_of(cid) - int(row.get("start_tier", row.get("tier", 1)))
	var per: Dictionary = row.get("knowledge_per_promotion", {})
	for k in per.keys():
		out[k] = int(out.get(k, 0)) + int(per[k]) * maxi(0, ups)
	return out


## 다음 승급 퀘스트(없으면 {})
static func next_promotion(cid: String) -> Dictionary:
	var t := tier_of(cid) + 1
	for q in DataDB.get_row(cid).get("promotion", []):
		if int(q["tier"]) == t:
			return q
	return {}


## 승급 퀘스트 수락 조건(빈 문자열 = 가능): 신분 Rank ≥ t · 동행 · 대표 지식 ≥ t · 시작 장소(트리거 노드)에 있음
static func promotion_lock(cid: String, q: Dictionary) -> String:
	var gs := GameState
	if gs.rank < int(q.get("min_rank", q["tier"])):
		return "Rank %d 필요" % int(q.get("min_rank", q["tier"]))
	var req: Dictionary = q.get("requires", {})
	if req.get("in_party", false) and not (cid in gs.party):
		return "%s 동행 필요" % DataDB.display_name(cid)
	var pk := gs.party_knowledge()
	for k in req.get("knowledge", {}).keys():
		if int(pk.get(k, 0)) < int(req["knowledge"][k]):
			return "%s 지식 %d 필요" % [String(DataDB.classes_doc.get("knowledge", {}).get("names", {}).get(k, k)), int(req["knowledge"][k])]
	if gs.current_node != String(q.get("trigger_node", "")):
		return "시작 장소: %s" % DataDB.display_name(String(q.get("trigger_node", "")))
	return ""


static func promote(cid: String, tier: int) -> void:
	var gs := GameState
	if not gs.companions.has(cid):
		return
	var info: Dictionary = gs.companions[cid]
	info["tier"] = clampi(tier, tier_of(cid), int(DataDB.get_row(cid).get("max_tier", 5)))
	var m := Balance.companion_skill_mult(int(info["tier"]), int(info.get("star", 1)))
	gs.note("%s %d등급 승급! 스킬 숙련 ×%.2f · 지식 %s" % [DataDB.display_name(cid), int(info["tier"]), m, str(knowledge_of(cid))])
	gs.stats_changed.emit()


static func add_companion(cid: String, captured: bool) -> void:
	var gs := GameState
	var row := DataDB.get_row(cid)
	if gs.companions.has(cid):
		# 중복 포획 → 카드 스택 흡수, dupes_to_upgrade 마다 1성 승급
		var info: Dictionary = gs.companions[cid]
		info["dupes"] = int(info.get("dupes", 0)) + 1
		var need := int(row.get("capture_profile", {}).get("dupes_to_upgrade", 2))
		if int(info["dupes"]) >= need and int(info.get("star", 1)) < int(_bc().get("max_star", 5)):
			info["dupes"] = 0
			info["star"] = int(info.get("star", 1)) + 1
			gs.note("%s ★%d 승급!" % [row.get("name", cid), info["star"]])
		else:
			gs.note("%s 중복 — 스택 %d/%d" % [row.get("name", cid), info["dupes"], need])
		gs.stats_changed.emit()
		return
	gs.companions[cid] = {"star": 1, "dupes": 0, "captured": captured, "tier": int(row.get("start_tier", row.get("tier", 1)))}
	if gs.party.size() < GameState.MAX_PARTY:
		gs.party.append(cid)
		gs.note("동료 합류: %s" % row.get("name", cid))
	elif gs.barracks.size() < barracks_slots():
		gs.barracks.append(cid)
		gs.note("%s — 파티가 가득 차 객주 막사로 보냈습니다." % row.get("name", cid))
	else:
		gs.note("막사가 가득 찼습니다(%d슬롯). %s 은(는) 합류하지 못했습니다." % [barracks_slots(), row.get("name", cid)])
		gs.companions.erase(cid)
	gs.codex_add(cid, String(row.get("lore_tag", "창작")))
	gs.stats_changed.emit()


static func can_use_barracks() -> bool:
	return DataDB.node_has(GameState.current_node, "gaekju") or DataDB.node_has(GameState.current_node, "jumak")


## 파티 ↔ 막사 이동 (객주·주막에서만)
static func to_barracks(cid: String) -> String:
	var gs := GameState
	if not can_use_barracks():
		return "객주·주막 막사에서만 가능"
	if gs.barracks.size() >= barracks_slots():
		return "막사 슬롯 부족"
	gs.party.erase(cid)
	gs.barracks.append(cid)
	gs.stats_changed.emit()
	return ""


static func to_party(cid: String) -> String:
	var gs := GameState
	if not can_use_barracks():
		return "객주·주막 막사에서만 가능"
	if gs.party.size() >= GameState.MAX_PARTY:
		return "파티 3인 가득 참"
	gs.barracks.erase(cid)
	gs.dispatch.erase(cid)
	gs.party.append(cid)
	gs.stats_changed.emit()
	return ""


## 사농공상 거점 파견: 막사 대기 동료만, 해당 시설이 있는 노드에서
static func send_dispatch(cid: String, dtype: String) -> String:
	var gs := GameState
	var d: Dictionary = _bc().get("dispatch", {}).get(dtype, {})
	if d.is_empty():
		return "알 수 없는 파견"
	if not (cid in gs.barracks):
		return "막사 대기 동료만 파견 가능"
	if not DataDB.node_has(gs.current_node, String(d.get("facility", ""))):
		return "%s 시설이 필요합니다" % d.get("facility", "")
	gs.dispatch[cid] = {"type": dtype, "node": gs.current_node, "since": gs.day()}
	gs.note("%s → %s 파견" % [DataDB.display_name(cid), d.get("name", dtype)])
	gs.stats_changed.emit()
	return ""


## 일일 처리: 동행 일급·식량 / 파견 수익 (막사 대기는 비용 0)
static func daily(_d: int) -> void:
	var gs := GameState
	var wage := 0
	for cid in gs.party:
		var info: Dictionary = gs.companions.get(cid, {})
		if info.get("captured", false):
			var up: Dictionary = DataDB.get_row(String(cid)).get("capture_profile", {}).get("companion_bonuses", {}).get("upkeep", {})
			wage += int(up.get("cost", 0))
		else:
			wage += Balance.wage_per_day(tier_of(String(cid)))
	if wage > 0:
		if gs.money >= wage:
			gs.money -= wage
		else:
			gs.note("일급 %d냥을 치르지 못해 동료들의 사기가 떨어집니다." % wage)
	for cid in gs.dispatch.keys():
		var dp: Dictionary = gs.dispatch[cid]
		var d: Dictionary = _bc().get("dispatch", {}).get(String(dp["type"]), {}).get("per_day", {})
		var tier := tier_of(String(cid))
		for it in d.get("items", []):
			gs.add_item(String(it["id"]), int(it["qty"]))
		if d.has("money_per_tier"):
			gs.money += int(d["money_per_tier"]) * tier
		for k in d.get("knowledge_xp", {}).keys():
			gs.add_knowledge_xp(k, int(d["knowledge_xp"][k]))
	gs.stats_changed.emit()


## 포획 성공 → 계통별 후처리(고용비) 후 동료화
static func on_captured(enemy_id: String, tool_row: Dictionary) -> void:
	var m: Dictionary = DataDB.overview.get("capture", {}).get("methods", {}).get(String(tool_row.get("family", "")), {})
	if m.has("hire_fee_per_tier"):
		var fee := int(m["hire_fee_per_tier"]) * int(DataDB.get_row(enemy_id).get("tier", 1))
		GameState.money = maxi(0, GameState.money - fee)
		GameState.note("고용 계약금 %d냥" % fee)
	add_companion(enemy_id, true)


## 포획 보너스: 지식(해당 계통 학식) + 클래스 + 미끼 + 답사록
static func capture_bonus(tool_row: Dictionary) -> float:
	var gs := GameState
	var c: Dictionary = DataDB.overview.get("capture", {})
	var fam := String(tool_row.get("family", ""))
	var k: String = {"yu": "yu", "bul": "bul", "seon": "seon", "mu": "sa"}.get(fam, "sa")
	var b := float(c.get("knowledge_bonus_per_rank", 0.03)) * int(gs.party_knowledge().get(k, 0))
	b += float(gs.buff_totals().get("capture_rate", 0.0))
	if fam == "seon":
		b += float(gs.class_passive().get("seal_capture_bonus", 0.0))
	if fam == "mu" and gs.has_item("item_bait"):
		b += float(c.get("methods", {}).get("mu", {}).get("bait_bonus", 0.2))
	return b
