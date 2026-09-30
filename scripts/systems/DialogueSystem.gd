class_name DialogueSystem
extends RefCounted
## 대화 장면 데이터(24_story) 해석: 조건(req) 판정 · 효과(effects) 적용 · 화자(who) 해석 · 퀘스트 서사 조회.
## 장면 = {bg, cast[], lines[{who, text}], choices[{id, text, req, effects, result}]}
## who = "hero" | 동료 id | "npc:<역할>:<이름>"
## 화면 표시는 DialogueView, 재생 순서는 GameState.dialogue_queue(요청 → Main 이 전투·미니게임이 아닐 때 재생).

const NPC_COLOR := {
	"official": Color(0.35, 0.42, 0.62), "monk": Color(0.55, 0.45, 0.3), "elder": Color(0.5, 0.48, 0.42), "soldier": Color(0.55, 0.3, 0.28),
	"merchant": Color(0.42, 0.52, 0.35), "shaman": Color(0.65, 0.3, 0.45), "scholar": Color(0.3, 0.45, 0.5), "fisher": Color(0.28, 0.45, 0.58),
	"innkeeper": Color(0.62, 0.48, 0.3), "traveler": Color(0.45, 0.5, 0.45),
}


static func doc() -> Dictionary:
	return DataDB.docs.get("24_story.json", {})


static func narrative(qid: String) -> Dictionary:
	return doc().get("narratives", {}).get("quest:" + qid, {})


## part = intro | outro | step (i = 동선 인덱스)
static func narrative_scene(qid: String, part: String, i: int = -1) -> Dictionary:
	var n := narrative(qid)
	if n.is_empty():
		return {}
	if part == "step":
		var st: Array = n.get("steps", [])
		return st[i] if i >= 0 and i < st.size() else {}
	return n.get(part, {})


## 퀘스트 서사 장면을 대화 대기열에 올린다(없으면 아무것도 안 함)
static func play_quest(qid: String, part: String, i: int = -1) -> void:
	var sc := narrative_scene(qid, part, i)
	if sc.is_empty() or Array(sc.get("lines", [])).is_empty():
		return
	var d := sc.duplicate(true)
	d["title"] = String(narrative(qid).get("title", ""))
	d["key"] = "quest:%s:%s%s" % [qid, part, "" if i < 0 else str(i)]
	GameState.request_dialogue(d, Callable())


# ---------------------------------------------------------------- 화자
static func speaker(who: String) -> Dictionary:
	var gs := GameState
	if who == "" or who == "narration":
		return {"name": "", "portrait": null, "color": Color(0.3, 0.3, 0.3), "role": "narration"}
	if who == "hero":
		var nm := gs.hero_name if gs.hero_name != "" else String(DataDB.class_row(gs.class_id).get("name", "나그네"))
		var p: Texture2D = null
		if gs.scenario_id != "":  # 시나리오 주인공 초상(23 시트 portrait) → 직업 초상
			p = Assets.tex(String(DataDB.get_row(gs.scenario_id).get("portrait", "")))
		if p == null:
			p = Assets.portrait("hero_" + gs.class_id)
		return {"name": nm, "portrait": p, "color": Color(0.72, 0.55, 0.28), "role": "hero"}
	if who.begins_with("npc:"):
		var parts := who.split(":", false, 2)
		var role := parts[1] if parts.size() > 1 else "elder"
		var nm2 := parts[2] if parts.size() > 2 else role
		return {"name": nm2, "portrait": Assets.portrait("npc_" + role), "color": NPC_COLOR.get(role, Color(0.45, 0.45, 0.45)), "role": role}
	var row := DataDB.get_row(who)
	var col := Color(0.4, 0.5, 0.6)
	match String(row.get("family", row.get("yu_bul_seon_type", ""))):
		"yu": col = Color(0.3, 0.45, 0.62)
		"bul": col = Color(0.62, 0.45, 0.25)
		"seon": col = Color(0.4, 0.6, 0.45)
	return {"name": String(row.get("name", who)), "portrait": Assets.portrait(who), "color": col, "role": "companion"}


# ---------------------------------------------------------------- 조건
## 조건 사유("" = 충족). req 키: rank · money · items{} · knowledge{} · party(id|[]) · class(id|[]) · flag(이름|!이름|[]) · visited(노드|[])
static func check_req(req: Dictionary) -> String:
	var gs := GameState
	if req.is_empty():
		return ""
	if req.has("rank") and gs.rank < int(req["rank"]):
		return "신분 Rank %d 필요" % int(req["rank"])
	if req.has("money") and gs.money < int(req["money"]):
		return "엽전 %d냥 필요(보유 %d)" % [int(req["money"]), gs.money]
	var items: Dictionary = req.get("items", {})
	for id in items.keys():
		if not gs.has_item(String(id), int(items[id])):
			return "%s ×%d 필요" % [DataDB.display_name(String(id)), int(items[id])]
	var kn: Dictionary = req.get("knowledge", {})
	if not kn.is_empty():
		var pk := gs.party_knowledge()
		var names: Dictionary = DataDB.classes_doc.get("knowledge", {}).get("names", {})
		for k in kn.keys():
			if int(pk.get(k, 0)) < int(kn[k]):
				return "%s 지식 %d 필요(파티 %d)" % [names.get(k, k), int(kn[k]), int(pk.get(k, 0))]
	for cid in _as_list(req.get("party", [])):
		if not (cid in gs.party):
			return "%s 동행 필요" % DataDB.display_name(String(cid))
	var cls := _as_list(req.get("class", []))
	if not cls.is_empty() and not (gs.class_id in cls):
		return "%s 전용" % " · ".join(PackedStringArray(cls.map(func(c): return String(DataDB.class_row(String(c)).get("name", c)))))
	for f in _as_list(req.get("flag", [])):
		var fs := String(f)
		var neg := fs.begins_with("!")
		var key := fs.substr(1) if neg else fs
		if bool(gs.flags.get(key, false)) == neg:
			return "조건 미충족" if not neg else "이미 선택한 길"
	for nd in _as_list(req.get("visited", [])):
		if not gs.visited_nodes.has(String(nd)):
			return "%s 방문 필요" % DataDB.display_name(String(nd))
	return ""


static func _as_list(v) -> Array:
	if typeof(v) == TYPE_ARRAY:
		return v
	if typeof(v) == TYPE_STRING and String(v) != "":
		return [v]
	return []


# ---------------------------------------------------------------- 효과
## effects 키: knowledge_xp{} · money(±) · money_mult · give{} · take{} · flag(이름|!이름|[]) · reputation
## 반환: {"money_mult": x} (이벤트 보상 배율처럼 호출한 쪽이 쓰는 값)
static func apply_effects(fx: Dictionary) -> Dictionary:
	var gs := GameState
	var out := {}
	for k in fx.get("knowledge_xp", {}).keys():
		gs.add_knowledge_xp(String(k), int(fx["knowledge_xp"][k]))
	if fx.has("money"):
		var m := int(fx["money"])
		if m < 0:
			gs.money = maxi(0, gs.money + m)
			gs.note("엽전 %d냥 지출" % -m)
		elif m > 0:
			gs.add_money(m)
	var tk: Dictionary = fx.get("take", {})
	for id in tk.keys():
		gs.remove_item(String(id), int(tk[id]))
	var gv: Dictionary = fx.get("give", {})
	for id in gv.keys():
		gs.add_item(String(id), int(gv[id]))
		gs.note("획득: %s ×%d" % [DataDB.display_name(String(id)), int(gv[id])])
	for f in _as_list(fx.get("flag", [])):
		var fs := String(f)
		if fs.begins_with("!"):
			gs.flags.erase(fs.substr(1))
		else:
			gs.flags[fs] = true
	if fx.has("reputation"):
		gs.note("명성 +%d" % gs.add_reputation(int(fx["reputation"]), gs.current_region))
	if fx.has("money_mult"):
		out["money_mult"] = float(fx["money_mult"])
	gs.stats_changed.emit()
	return out


## 대화가 끝난 뒤: 고른 선택지의 효과 적용
static func apply_choice(d: Dictionary, choice_id: String) -> Dictionary:
	for c in d.get("choices", []):
		if String(c.get("id", "")) == choice_id:
			if check_req(c.get("req", {})) != "":
				return {}
			GameState.flags["choice:%s" % String(d.get("key", ""))] = choice_id
			return apply_effects(c.get("effects", {}))
	return {}


# ---------------------------------------------------------------- 이벤트 단계 → 장면
## stage.dialogue 가 있으면 그대로, 없으면 text + choices 로 한 장면을 만든다
static func from_stage(eid: String, s: Dictionary) -> Dictionary:
	var d: Dictionary = s.get("dialogue", {}).duplicate(true)
	var node := String(s.get("node", GameState.current_node))
	if d.is_empty():
		var who := String(s.get("who", npc_for(node)))
		d = {"bg": node, "lines": [{"who": who, "text": String(s.get("text", ""))}]}
		if s.has("choices"):
			d["choices"] = s["choices"]
		d["cast"] = ["hero", who]
	if not d.has("bg"):
		d["bg"] = node
	if not d.has("choices") and s.has("choices"):
		d["choices"] = s["choices"]
	d["title"] = String(EventSystem.definition(eid).get("name", ""))
	d["key"] = "event:%s:%d" % [eid, int(EventSystem.state(eid).get("stage", 0))]
	return d


const NT_ROLE := {"city": ["official", "아전"], "temple": ["monk", "노승"], "station": ["soldier", "역졸"], "town": ["elder", "촌로"],
	"spring": ["innkeeper", "주모"], "fort": ["soldier", "군관"], "scenic": ["traveler", "유람객"], "tomb": ["official", "능참봉"],
	"seowon": ["scholar", "유생"], "shrine": ["shaman", "무녀"], "stupa": ["monk", "노승"], "ruin": ["elder", "촌로"],
	"wreck": ["fisher", "어부"], "beacon": ["soldier", "봉수군"]}


static func npc_for(node_id: String) -> String:
	var t := String(DataDB.get_row(DataDB.node_of(node_id)).get("type", "town"))
	var r: Array = NT_ROLE.get(t, ["elder", "촌로"])
	return "npc:%s:%s" % [r[0], r[1]]


## 배경 텍스처: 노드 전용 삽화 → 공식 노드 삽화 → 노드 유형 배경 → null(색 배경)
static func background(bg: String) -> Texture2D:
	if bg.begins_with("res://"):
		return Assets.tex(bg)
	var nid := DataDB.node_of(bg)
	var t := Assets.tex("res://assets/scenes/nodes/%s.png" % nid)
	if t == null and bg != nid:
		t = Assets.tex("res://assets/scenes/heritage/%s.png" % bg)
	if t == null:
		var ill := String(DataDB.get_row(nid).get("official", {}).get("illustration", ""))
		if ill != "":
			t = Assets.tex(ill)
	if t == null:
		t = Assets.tex("res://assets/scenes/%s.png" % String(DataDB.get_row(nid).get("type", "town")))
	return t


const BG_COLOR := {"city": Color(0.22, 0.2, 0.26), "town": Color(0.26, 0.24, 0.18), "temple": Color(0.2, 0.24, 0.18), "stupa": Color(0.22, 0.22, 0.2),
	"scenic": Color(0.16, 0.26, 0.28), "fort": Color(0.26, 0.18, 0.16), "station": Color(0.24, 0.2, 0.16), "shrine": Color(0.26, 0.14, 0.2),
	"tomb": Color(0.16, 0.2, 0.16), "seowon": Color(0.18, 0.2, 0.26), "ruin": Color(0.22, 0.2, 0.18), "wreck": Color(0.12, 0.18, 0.26),
	"spring": Color(0.24, 0.2, 0.2), "beacon": Color(0.26, 0.16, 0.12)}


static func background_color(bg: String) -> Color:
	return BG_COLOR.get(String(DataDB.get_row(DataDB.node_of(bg)).get("type", "")), Color(0.16, 0.14, 0.12))
