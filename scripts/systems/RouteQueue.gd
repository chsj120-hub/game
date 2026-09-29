class_name RouteQueue
extends RefCounted
## 동선 큐 압축 규칙 (2~5 노드): 1~2등급 동일 권역 2노드 / 3~4등급 인접 2~3권역 3노드 / 5등급 전국 3~5권역 4~5노드.
## 국가유산 답사·탈것·장비 전용 퀘스트·동료 영입·탐색 인스턴스·이벤트 단계에 일괄 적용. 보상은 economy quest 공식.


static func rule_for(tier: int) -> Dictionary:
	return DataDB.overview.get("route_rules", {}).get(str(clampi(tier, 1, 5)), {})


static func validate(route: Array, tier: int) -> String:
	var rule := rule_for(tier)
	var n: Array = rule.get("nodes", [2, 5])
	if route.size() < int(n[0]) or route.size() > int(n[1]):
		return "노드 수 %d (허용 %d~%d)" % [route.size(), int(n[0]), int(n[1])]
	var regions := []
	for node in route:
		var r := DataDB.region_of_node(String(node))
		if r == "":
			return "알 수 없는 노드: %s" % node
		if not (r in regions):
			regions.append(r)
	match String(rule.get("scope", "")):
		"same_region":
			if regions.size() != 1:
				return "동일 권역이어야 함 (현재 %d개 권역)" % regions.size()
		"adjacent", "nationwide":
			var rr: Array = rule.get("regions", [1, 17])
			if regions.size() < int(rr[0]) or regions.size() > int(rr[1]):
				return "권역 수 %d (허용 %d~%d)" % [regions.size(), int(rr[0]), int(rr[1])]
			if String(rule["scope"]) == "adjacent" and not _connected(regions):
				return "권역들이 서로 인접하지 않음"
	return ""


static func _connected(regions: Array) -> bool:
	if regions.size() <= 1:
		return true
	var seen := [regions[0]]
	var queue := [regions[0]]
	while queue.size() > 0:
		var cur = queue.pop_front()
		for nb in DataDB.adjacent(String(cur)) + DataDB.sea_adjacent(String(cur)):
			if nb in regions and not (nb in seen):
				seen.append(nb)
				queue.append(nb)
	return seen.size() == regions.size()


static func describe(route: Array) -> String:
	var names := PackedStringArray()
	for n in route:
		names.append(DataDB.display_name(String(n)))
	return " → ".join(names)


## 수락 잠금 사유(빈 문자열 = 수락 가능). 승급 퀘스트는 신분·동행·지식·시작 장소까지 검사
static func lock_reason(q: Dictionary) -> String:
	if q.has("companion"):
		return CompanionSystem.promotion_lock(String(q["companion"]), q)
	if GameState.rank < int(q.get("min_rank", 1)):
		return "Rank %d 필요" % int(q.get("min_rank", 1))
	return ""


static func start_quest(q: Dictionary) -> bool:
	var gs := GameState
	var lock := lock_reason(q)
	if lock != "":
		gs.note("[수락 불가] %s: %s" % [q["name"], lock])
		return false
	var err := validate(q["route"], int(q["tier"]))
	if err != "":
		gs.note("[동선 큐 규칙 위반] %s: %s" % [q["name"], err])
		return false
	if gs.active_quests.has(q["id"]) or q["id"] in gs.completed_quests:
		gs.note("이미 진행 중이거나 완료한 퀘스트입니다.")
		return false
	gs.active_quests[q["id"]] = {"name": q["name"], "tier": int(q["tier"]), "type": q["type"], "route": q["route"].duplicate(), "index": 0, "reward": q["reward"]}
	gs.note("퀘스트 수락: %s — 동선 %s" % [q["name"], describe(q["route"])])
	on_node_visited(gs.current_node)
	gs.stats_changed.emit()
	return true


static func current_target(qid: String) -> String:
	var q: Dictionary = GameState.active_quests.get(qid, {})
	if q.is_empty():
		return ""
	return String(q["route"][mini(int(q["index"]), q["route"].size() - 1)])


## 노드(또는 유산) 방문 시 진행. 유산 목표는 그 유산 노드 도착으로도 인정.
static func on_node_visited(node_id: String) -> Array:
	var gs := GameState
	var finished := []
	for qid in gs.active_quests.keys():
		var q: Dictionary = gs.active_quests[qid]
		if q.get("ready", false):
			continue
		var target := String(q["route"][int(q["index"])])
		if target != node_id and DataDB.node_of(target) != node_id:
			continue
		q["index"] = int(q["index"]) + 1
		if int(q["index"]) >= q["route"].size():
			finished.append(qid)
		else:
			gs.note("[%s] %d/%d — 다음: %s" % [q["name"], q["index"], q["route"].size(), DataDB.display_name(String(q["route"][q["index"]]))])
	for qid in finished:
		_complete(qid)
	return finished


static func _complete(qid: String) -> void:
	var gs := GameState
	var q: Dictionary = gs.active_quests[qid]
	if q["reward"].has("instance"):
		q["index"] = q["route"].size() - 1
		q["ready"] = true
		gs.note("[%s] 결전지 도착! 연속전투를 시작하세요." % q["name"])
		return
	complete_external(qid)


static func complete_external(qid: String) -> void:
	var gs := GameState
	if not gs.active_quests.has(qid):
		return
	var q: Dictionary = gs.active_quests[qid]
	gs.active_quests.erase(qid)
	gs.completed_quests.append(qid)
	grant(q["reward"], int(q["tier"]), String(q["type"]), DataDB.region_of_node(String(q["route"][-1])))
	gs.note("퀘스트 완료: %s" % q["name"])


static func fail_quest(qid: String) -> void:
	var gs := GameState
	var q: Dictionary = gs.active_quests.get(qid, {})
	if q.is_empty():
		return
	gs.active_quests.erase(qid)
	var cons := String(q["reward"].get("fail_consolation", ""))
	if cons != "" and not (cons in gs.mojak_unlocked):
		gs.mojak_unlocked.append(cons)
		gs.note("퀘스트 포기… 패자부활: %s 단조법 해금" % DataDB.display_name(cons))
	gs.stats_changed.emit()


static func grant(reward: Dictionary, tier: int, qtype: String, region: String = "") -> void:
	var gs := GameState
	if reward.has("item"):
		gs.add_item(String(reward["item"]))
		gs.note("획득: %s" % DataDB.display_name(String(reward["item"])))
	if reward.has("mount"):
		gs.add_item(String(reward["mount"]))
		gs.equip(String(reward["mount"]), "mount")
	if reward.has("companion"):
		gs.recruit(String(reward["companion"]))
	if reward.has("companion_tier"):
		CompanionSystem.promote(String(reward["companion_tier"]["id"]), int(reward["companion_tier"]["tier"]))
	var rep := Balance.quest_reward(tier, qtype, "rep")
	var mon := Balance.quest_reward(tier, qtype, "money")
	if rep > 0:
		gs.note("명성 +%d" % gs.add_reputation(rep, region, qtype in ["gwana_doc", "bounty"]))
	if mon > 0:
		gs.add_money(mon)
		gs.note("엽전 +%d냥" % mon)


## 데이터에서 퀘스트형 획득 경로 수집
static func available_quests() -> Array:
	var out := []
	for it in DataDB.table("02_equipment.json", "items"):
		var a: Dictionary = it.get("acquire", {})
		if a.get("type", "") == "quest":
			out.append({"id": "q_" + it["id"], "name": String(a.get("quest_name", it["name"])), "tier": int(it["tier"]), "type": "gear",
				"min_rank": int(a.get("min_rank", it["tier"])), "route": a["route"],
				"reward": {"item": it["id"], "fail_consolation": a.get("fail_consolation", "")}})
	for m in DataDB.table("07_mounts.json", "mounts"):
		var a2: Dictionary = m.get("acquire", {})
		if a2.get("type", "") == "quest":
			out.append({"id": "q_" + m["id"], "name": String(a2["quest_name"]), "tier": int(m["tier"]), "type": "mount",
				"min_rank": int(m.get("min_rank", 1)), "route": a2["route"], "reward": {"mount": m["id"]}})
	for c in DataDB.table("13_companions.json", "companions"):
		var r: Dictionary = c.get("recruit", {})
		if r.has("route"):
			out.append({"id": "q_" + c["id"], "name": "동료 영입: " + String(c["name"]), "tier": int(c["tier"]), "type": "companion",
				"min_rank": int(r.get("min_rank", 1)), "route": r["route"], "reward": {"companion": c["id"]}})
	for cid in GameState.companions.keys():  # 보유 동료의 다음 승급 퀘스트(서사 맞춤, 시작 장소 트리거)
		var pq := CompanionSystem.next_promotion(String(cid))
		if not pq.is_empty():
			out.append({"id": String(pq["id"]), "name": String(pq["name"]), "tier": int(pq["tier"]), "type": String(DataDB.overview.get("companion_promotion", {}).get("quest_type", "companion_promo")),
				"min_rank": int(pq["min_rank"]), "route": pq["route"], "companion": String(cid), "lore": String(pq.get("lore", "")),
				"reward": {"companion_tier": {"id": String(cid), "tier": int(pq["tier"])}}})
	for inst in DataDB.instances():
		out.append({"id": "q_" + inst["id"], "name": "[탐색] " + String(inst["name"]), "tier": int(inst["tier"]), "type": "instance",
			"min_rank": maxi(1, int(inst["tier"]) - 1), "route": inst["route"], "reward": {"instance": inst["id"]}})
	return out
