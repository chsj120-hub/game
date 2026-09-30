class_name EventSystem
extends RefCounted
## 20 시트: 역사·설화 이벤트 + 클래스 메인 시나리오. 단계(stage) 노드를 동선 큐로 진행.
## 완전판 9장 Fail-safe: 기한(30일) 경과 시 관군 급파로 자동 정상화(명성 감점 없음), 봉쇄 시 무료 우회로 개방, 포고문으로 도감 등록 보장.

static func _fs() -> Dictionary:
	return DataDB.overview.get("failsafe", {})


## 이벤트 정의를 {id, name, tier, stages, ...} 로 통일 (메인 시나리오는 현재 챕터)
static func definition(eid: String) -> Dictionary:
	var e := DataDB.get_row(eid)
	if e.is_empty():
		return {}
	if String(e.get("type", "")) == "main":
		var st: Dictionary = GameState.events_state.get(eid, {})
		var chi := int(st.get("chapter", 0))
		var chs: Array = e.get("chapters", [])
		if chi >= chs.size():
			return {}
		var ch: Dictionary = chs[chi]
		return {"id": eid, "name": "%s %d장" % [e["name"], int(ch["chapter"])], "tier": int(ch["tier"]), "stages": ch["stages"],
			"lore": e.get("lore", "창작"), "type": "main", "deadline_days": 0, "codex": "", "min_rank": int(ch["tier"]),
			"final": chi == chs.size() - 1}
	return e


static func state(eid: String) -> Dictionary:
	return GameState.events_state.get(eid, {})


static func is_active(eid: String) -> bool:
	return String(state(eid).get("status", "")) == "active"


static func blocked_nodes() -> Array:
	var out := []
	for eid in GameState.events_state.keys():
		if is_active(eid):
			var b: Dictionary = DataDB.get_row(eid).get("blockade", {})
			if b.has("node"):
				out.append(String(b["node"]))
	return out


## 트리거 확인 (권역 진입·절기·시간·신분·클래스)
static func check_triggers() -> void:
	var gs := GameState
	for e in DataDB.events():
		var eid := String(e["id"])
		if gs.events_state.has(eid) and String(gs.events_state[eid].get("status", "")) != "expired_recurring":
			continue
		var t: Dictionary = e.get("trigger", {})
		if t.has("region") and gs.current_region != String(t["region"]):
			continue
		if gs.rank < int(t.get("rank_min", 1)):
			continue
		if t.has("solar_terms") and not (gs.solar_term() in t["solar_terms"]):
			continue
		if String(t.get("time", "")) == "NIGHT_ONLY" and not gs.is_night():
			continue
		start(eid)
	for m in DataDB.main_scenarios():  # 시나리오 시작이면 그 시나리오 메인만, 아니면 클래스 기본 메인
		var sc := String(m.get("scenario", ""))
		var mine := sc == gs.scenario_id if gs.scenario_id != "" else (sc == "" and String(m.get("class", "")) == gs.class_id)
		if mine and not gs.events_state.has(m["id"]):
			start(String(m["id"]))


static func start(eid: String) -> void:
	var gs := GameState
	var d := definition(eid)
	if d.is_empty():
		return
	var st: Dictionary = gs.events_state.get(eid, {})
	st["status"] = "active"
	st["stage"] = 0
	st["started"] = gs.day()
	gs.events_state[eid] = st
	var b: Dictionary = DataDB.get_row(eid).get("blockade", {})
	if b.has("detour"):
		var dt: Dictionary = b["detour"]
		DataDB.add_runtime_link(String(dt["a"]), String(dt["b"]), {"li": 0.0, "terrain": "water", "kind": "ferry", "fare": int(dt.get("fare", 0)), "days": int(dt.get("days", 1)), "wind": false})
		gs.note("[봉쇄] %s 통행 금지 — %s" % [DataDB.display_name(String(b["node"])), dt.get("text", "우회로 개방")])
	gs.note("【%s】 시작 — %s" % [d["name"], stage_text(eid)])
	gs.stats_changed.emit()


static func current_stage(eid: String) -> Dictionary:
	var d := definition(eid)
	var i := int(state(eid).get("stage", 0))
	var stages: Array = d.get("stages", [])
	return stages[i] if i < stages.size() else {}


static func stage_text(eid: String) -> String:
	var s := current_stage(eid)
	if s.is_empty():
		return ""
	return "%s — %s" % [DataDB.display_name(String(s["node"])), s.get("text", "")]


static func on_node(node_id: String) -> void:
	check_triggers()
	for eid in GameState.events_state.keys():
		if is_active(eid) and String(current_stage(eid).get("node", "")) == node_id:
			GameState.note("【%s】 이 장소에서 이야기가 진행됩니다 — [이벤트]" % definition(eid).get("name", eid))


## 현재 노드에서 진행 가능한 단계 목록 [{eid, stage}]
## 메인 시나리오 N장은 신분 Rank N 이상 (00_overview.rank.ending)
static func rank_block(eid: String) -> String:
	var need := int(definition(eid).get("min_rank", 0))
	return "" if GameState.rank >= need else "신분 Rank %d 필요(관아 승급 심사)" % need


static func actionable_here() -> Array:
	var out := []
	for eid in GameState.events_state.keys():
		if is_active(eid) and String(current_stage(eid).get("node", "")) == GameState.current_node:
			out.append({"eid": eid, "stage": current_stage(eid), "block": rank_block(eid)})
	return out


## 단계 해결. result: {"ok": bool, "choice": id}
static func resolve_stage(eid: String, result: Dictionary) -> void:
	var gs := GameState
	if not result.get("ok", false):
		gs.note("【%s】 실패 — 다시 도전할 수 있습니다(기한 내)." % definition(eid).get("name", eid))
		return
	var s := current_stage(eid)
	if s.has("choices") and result.has("choice"):
		for c in s["choices"]:
			if c["id"] == result["choice"]:
				if DialogueSystem.check_req(c.get("req", {})) != "":
					gs.note("그 선택지는 조건이 맞지 않습니다.")
					return
				gs.flags["choice:%s:%d" % [eid, int(gs.events_state[eid].get("stage", 0))]] = String(c["id"])
				var got := DialogueSystem.apply_effects(c.get("effects", {}))  # 지식·엽전·물품·플래그·명성 (24_story 와 같은 효과 키)
				gs.events_state[eid]["money_mult"] = float(got.get("money_mult", 1.0))
	gs.events_state[eid]["stage"] = int(gs.events_state[eid]["stage"]) + 1
	gs.bump("event_stage")
	if current_stage(eid).is_empty():
		complete(eid)
	else:
		gs.note("【%s】 다음: %s" % [definition(eid).get("name", eid), stage_text(eid)])
	gs.stats_changed.emit()


static func complete(eid: String) -> void:
	var gs := GameState
	var d := definition(eid)
	var qtype := "main" if String(d.get("type", "")) == "main" else "event"
	var tier := int(d.get("tier", 1))
	var mm := float(gs.events_state[eid].get("money_mult", 1.0))
	var stg: Array = d.get("stages", [])
	var reg := DataDB.region_of_node(String(stg[-1]["node"])) if stg.size() > 0 else gs.current_region
	var rep := gs.add_reputation(Balance.quest_reward(tier, qtype, "rep"), reg)
	var mon := int(Balance.quest_reward(tier, qtype, "money") * mm)
	gs.add_money(mon)
	gs.codex_add(eid, String(d.get("lore", "역사")))
	gs.note("【%s】 완료 — 명성 +%d, 엽전 +%d냥" % [d["name"], rep, mon])
	for q in DataDB.get_row(eid).get("unlocks", []):
		gs.note("새 탐색 퀘스트 해금: %s" % q)
	if qtype == "main":
		gs.events_state[eid]["chapter"] = int(gs.events_state[eid].get("chapter", 0)) + 1
		gs.events_state[eid]["stage"] = 0
		if definition(eid).is_empty():
			gs.events_state[eid]["status"] = "done"
			gs.ending_seen = true
			gs.note("【엔딩】 %s 완결 — 삼한팔도 유람기의 한 장이 닫혔습니다. 남은 유산과 도시 발전은 계속 이어서 즐길 수 있습니다." % DataDB.display_name(eid))
		else:
			gs.events_state[eid]["started"] = gs.day()
			gs.note("다음 장: %s — %s" % [definition(eid)["name"], stage_text(eid)])
	else:
		gs.events_state[eid]["status"] = "done"


## 일일: 기한 경과 이벤트 자동 정상화 (Time Decay Fail-safe)
static func daily(d: int) -> void:
	var gs := GameState
	for eid in gs.events_state.keys():
		if not is_active(eid):
			continue
		var dd := definition(eid)
		var dl := int(dd.get("deadline_days", _fs().get("deadline_days", 30)))
		if dl <= 0:
			continue
		if d - int(gs.events_state[eid].get("started", d)) >= dl:
			var fs: Dictionary = dd.get("fail_safe", {})
			gs.events_state[eid]["status"] = "resolved_by_court"
			gs.note("[포고문] %s" % fs.get("text", _fs().get("time_decay_text", "")))
			if _fs().get("codex_via_proclamation", true):
				gs.codex_add(eid, String(dd.get("lore", "역사")))
			if String(eid) == "ev_yagwanggwi":  # 해마다 반복되는 세시 설화
				gs.events_state.erase(eid)
