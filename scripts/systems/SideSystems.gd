class_name SideSystems
extends RefCounted
## 22 시트 보조 시스템 + 생활 스킬(탐색·채집·사냥) + 봉수.
##  · 김홍도·신윤복 풍속도 화첩 스냅샷  · 관아 현상수배지  · 24절기 세시풍속  · 대동여지도 22첩 목판 탁본


static func _sd() -> Dictionary:
	return DataDB.side_doc


static func _fac() -> Dictionary:
	return DataDB.overview.get("facilities", {})


# ================================================================ 생활 스킬
## [탐색] 반경(15리 + 사 지식×3리 + 행장) 내 은닉 노드 판정. 사 지식 5 '선비의 안목'은 자동 힌트.
## 탐색 반경(리)·발견 확률 — [탐색]과 채집·야영·사냥 발견이 같은 규칙을 쓴다
static func _search_params() -> Dictionary:
	var gs := GameState
	var cfg: Dictionary = _fac().get("search", {})
	var sa := int(gs.party_knowledge().get("sa", 0))
	var radius_li := float(cfg.get("radius_li", 15)) + float(cfg.get("radius_li_per_sa", 3)) * sa
	for id in gs.life_gear.values():
		radius_li += float(DataDB.skill(String(DataDB.get_row(id).get("skill", ""))).get("effects", {}).get("field_search_radius_li", 0))
	return {"radius_li": radius_li, "ppl": float(DataDB.docs.get("regions.json", {}).get("px_per_li", 20.0)),
		"chance": float(cfg.get("detect_chance", 0.55)) + float(cfg.get("detect_per_sa", 0.05)) * sa, "hours": float(cfg.get("hours", 1))}


## 현재 노드 주변 은닉지 중 skill 로 찾을 수 있는 것을 확률 판정해 발견
static func _reveal(skill: String, sp: Dictionary) -> Array:
	var gs := GameState
	var here := DataDB.node_pos(gs.current_node)
	var reach := float(sp["radius_li"]) * float(sp["ppl"])
	var found := []
	for n in DataDB.nodes_in(gs.current_region):
		if not n.get("hidden", false) or gs.discovered.has(n["id"]) or not _discover_ok(n, skill):
			continue
		if here.distance_to(DataDB.node_pos(n["id"])) <= reach and gs.rng.randf() < float(sp["chance"]):
			gs.discover(n["id"])
			found.append(n["id"])
	return found


static func search() -> Array:
	var gs := GameState
	var sp := _search_params()
	var radius_li := float(sp["radius_li"])
	var ppl := float(sp["ppl"])
	var here := DataDB.node_pos(gs.current_node)
	var found := _reveal("search", sp)
	gs.add_knowledge_xp("sa", int(DataDB.classes_doc.get("knowledge", {}).get("xp_sources", {}).get("search_sa", 5)))
	gs.advance_minutes(int(float(sp["hours"]) * 60))
	if found.is_empty():
		gs.note("주변 %.0f리를 살폈으나 특별한 것은 없었다." % radius_li)
		var best := ""
		var bd := radius_li * ppl * 1.5
		for n in DataDB.nodes_in(gs.current_region):  # 지식·방법이 맞지 않아 못 찾은 은닉지의 풍문
			if n.get("hidden", false) and not gs.discovered.has(n["id"]) and n.has("discover"):
				var d := here.distance_to(DataDB.node_pos(n["id"]))
				if d < bd:
					bd = d
					best = String(n["id"])
		if best != "":
			var dc: Dictionary = DataDB.get_row(best)["discover"]
			gs.note("풍문: %s — [%s] · 사 지식 %d 필요" % [String(dc.get("clue", "")), {"search": "탐색", "gather": "채집", "camp": "야영", "hunt": "사냥"}.get(String(dc.get("skill", "search")), "탐색"), int(dc.get("sa", 0))])
	return found


## 국가유산 이벤트 노드의 발견 조건: discover{skill: search|gather|camp|hunt, sa: 파티 사(士) 지식 요구}
static func _discover_ok(n: Dictionary, skill: String) -> bool:
	var dc: Dictionary = n.get("discover", {})
	if dc.is_empty():
		return skill == "search"
	if String(dc.get("skill", "search")) != skill:
		return false
	return int(GameState.party_knowledge().get("sa", 0)) >= int(dc.get("sa", 0))


## [채집]·[야영]·[사냥]으로만 드러나는 은닉지(약초 캐다 발견한 폐사지 등). 반경·확률은 [탐색]과 같음
static func reveal_by_skill(skill: String) -> Array:
	return _reveal(skill, _search_params())


static func hint_hidden() -> Array:
	## '선비의 안목': 현재 권역 미발견 노드 중 가장 가까운 것 방향 힌트
	var gs := GameState
	if not gs.has_life_passive("pas_sa"):
		return []
	var out := []
	for n in DataDB.nodes_in(gs.current_region):
		if n.get("hidden", false) and not gs.discovered.has(n["id"]):
			out.append(n["id"])
	return out


## [채집] 권역·절기 기반 약초/구황 식물 (농 지식 수확 보너스)
static func gather() -> Array:
	var gs := GameState
	var cfg: Dictionary = _fac().get("gather", {})
	var pool := []
	for h in DataDB.table("10_herbs.json", "herbs"):
		var regs: Array = h.get("regions", [])
		if String(h.get("source", "")) == "gather" and ("*" in regs or gs.current_region in regs) and int(h["tier"]) <= gs.rank + 1:
			pool.append(h["id"])
		elif String(h.get("source", "")) == "yakbang" and int(h["tier"]) == 1:
			pool.append(h["id"])
	for f in DataDB.table("04_food_staples.json", "foods"):
		var regs2: Array = f.get("regions", [])
		if String(f.get("kind", "")) == "forage" and ("*" in regs2 or gs.current_region in regs2):
			pool.append(f["id"])
	if gs.season() == 3:  # 겨울엔 구황 위주
		pool = pool.filter(func(id): return DataDB.sheet_of(id) == "04_food_staples.json:foods")
	var y: Array = cfg.get("yield", [1, 3])
	var n := int(round(gs.rng.randi_range(int(y[0]), int(y[1])) * (1.0 + gs.life_effect("nong", "gather_yield"))))
	if gs.has_life_passive("pas_nong") and gs.rng.randf() < 0.2:
		n *= 2
	var got := []
	for i in n:
		if pool.is_empty():
			break
		var id: String = pool[gs.rng.randi_range(0, pool.size() - 1)]
		gs.add_item(id)
		got.append(id)
	gs.add_knowledge_xp("nong", int(DataDB.classes_doc.get("knowledge", {}).get("xp_sources", {}).get("gather_nong", 8)))
	gs.advance_minutes(int(float(cfg.get("hours", 2)) * 60))
	gs.note("채집: " + (", ".join(PackedStringArray(got.map(func(x): return DataDB.display_name(String(x))))) if got.size() > 0 else "빈손"))
	return got


## [사냥] 맹수 조우 웨이브 반환 (전투는 UI 가 시작)
static func hunt_waves() -> Array:
	var gs := GameState
	gs.advance_minutes(int(float(_fac().get("hunt", {}).get("hours", 3)) * 60))
	var beasts := []
	for e in DataDB.table("12_enemies.json", "enemies"):
		if String(e.get("kind", "")) == "beast" and int(e.get("boss_tier", 0)) == 0 and int(e["tier"]) <= gs.rank + 1:
			var regs: Array = e.get("spawn_conditions", {}).get("regions", ["*"])
			if "*" in regs or gs.current_region in regs:
				beasts.append(e["id"])
	if beasts.is_empty() or gs.rng.randf() > float(_fac().get("hunt", {}).get("encounter_beast_chance", 0.6)):
		var got := _hunt_game()
		gs.add_item(got)
		gs.note("사냥: %s을(를) 얻었다." % DataDB.display_name(got))
		return []
	return [[beasts[gs.rng.randi_range(0, beasts.size() - 1)]]]


## 맹수와 마주치지 않은 사냥의 수렵육 — 신분 Rank 이하 등급, 낮은 등급일수록 흔함(가중치 2^(Rank−등급)), 권역 한정(regions) 반영
static func _hunt_game() -> String:
	var gs := GameState
	var pool := []
	var total := 0.0
	for f in DataDB.table("04_food_staples.json", "foods"):
		var regs: Array = f.get("regions", ["*"])
		if String(f.get("kind", "")) != "game" or int(f["tier"]) > gs.rank or not ("*" in regs or gs.current_region in regs):
			continue
		var w := pow(2.0, gs.rank - int(f["tier"]))
		pool.append([String(f["id"]), w])
		total += w
	var roll := gs.rng.randf() * total
	for p in pool:
		roll -= float(p[1])
		if roll <= 0.0:
			return String(p[0])
	return "food_hare"


## [봉수] 점화 → 권역 은닉 노드 영구 해금 (완전판 3.1)
static func light_beacon() -> String:
	var gs := GameState
	if not DataDB.node_has(gs.current_node, "beacon"):
		return "봉수대가 아닙니다"
	if gs.lit_beacons.has(gs.current_region):
		return "이미 점화한 봉수입니다"
	if not gs.spend_money(int(_fac().get("beacon", {}).get("light_cost_money", 30))):
		return "봉화 재료값 부족"
	gs.lit_beacons[gs.current_region] = true
	for n in DataDB.nodes_in(gs.current_region):
		if n.get("hidden", false):
			gs.discovered[n["id"]] = true
	gs.note("봉수 점화! %s 권역의 숨은 장소가 모두 지도에 드러났습니다." % DataDB.display_name(gs.current_region))
	gs.stats_changed.emit()
	return ""


# ================================================================ 화첩
static func hwacheop_available() -> Array:
	var gs := GameState
	var n := DataDB.get_row(gs.current_node)
	var out := []
	for sc in _sd().get("hwacheop", {}).get("scenes", []):
		var key := String(sc["id"])
		if sc.get("repeatable_per_node", false):
			key = "%s@%s" % [sc["id"], gs.current_node]
		if gs.hwacheop.has(key):
			continue
		var t: Dictionary = sc.get("trigger", {})
		if t.has("facility") and not (String(t["facility"]) in n.get("facilities", [])):
			continue
		if t.has("node_type") and String(n.get("type", "")) != String(t["node_type"]):
			continue
		if t.has("solar_terms") and not (gs.solar_term() in t["solar_terms"]):
			continue
		if String(t.get("time", "")) == "NIGHT" and not gs.is_night():
			continue
		if String(t.get("time", "")) == "DAY" and gs.is_night():
			continue
		out.append({"key": key, "scene": sc})
	return out


static func take_snapshot(entry: Dictionary) -> void:
	var gs := GameState
	var hw: Dictionary = _sd().get("hwacheop", {})
	gs.hwacheop[String(entry["key"])] = gs.day()
	var r: Dictionary = hw.get("reward", {})
	for k in r.get("knowledge_xp", {}).keys():
		gs.add_knowledge_xp(k, int(r["knowledge_xp"][k]))
	gs.add_reputation(int(r.get("reputation", 0)), gs.current_region, entry["key"].begins_with("_"))
	var sc: Dictionary = entry["scene"]
	if String(DataDB.get_row(gs.current_node).get("type", "")) == "scenic":  # 팔도 절경: 최대 HP 영구 가산
		var cap := float(DataDB.classes_doc.get("hp_cap", 250))
		if gs.hp_max() < cap:
			gs.permanent_hp += int(DataDB.classes_doc.get("permanent_hp_per_scenic", 1))
			gs.note("절경의 기운 — 최대 체력 영구 +1")
		gs.fatigue = 0.0
	gs.note("화첩 기록: 「%s」(%s)" % [sc["title"], sc["painter"]])
	var total := 0
	for s in hw.get("scenes", []):
		if not s.get("repeatable_per_node", false):
			total += 1
	var have := gs.hwacheop.keys().filter(func(k): return not ("@" in String(k))).size()
	if have >= total and not gs.hwacheop.has("_complete"):
		gs.hwacheop["_complete"] = gs.day()
		gs.add_reputation(int(hw.get("complete_bonus", {}).get("reputation", 0)), gs.current_region)
		gs.note("화첩 완성! 칭호 「%s」" % hw.get("complete_bonus", {}).get("title", ""))


# ================================================================ 현상수배
static func refresh_bounties() -> void:
	var gs := GameState
	var cfg: Dictionary = _sd().get("bounty", {})
	gs.bounties = gs.bounties.filter(func(b): return int(b["expire"]) > gs.day() and not b.get("done", false))
	var tw: Array = cfg.get("tier_window", [-1, 1])
	var pool := DataDB.table("12_enemies.json", "enemies").filter(func(e): return int(e.get("boss_tier", 0)) == 0 and int(e["tier"]) >= gs.rank + int(tw[0]) and int(e["tier"]) <= gs.rank + int(tw[1]))
	var kc: Array = cfg.get("kill_count", [1, 3])
	while gs.bounties.size() < int(cfg.get("board_size", 3)) and pool.size() > 0:
		var e: Dictionary = pool[gs.rng.randi_range(0, pool.size() - 1)]
		var n := gs.rng.randi_range(int(kc[0]), int(kc[1]))
		var mult := sqrt(float(n))
		gs.bounties.append({"id": "bt_%d_%d" % [gs.day(), gs.rng.randi()], "enemy": e["id"], "count": n, "killed": 0,
			"rep": int(Balance.quest_reward(int(e["tier"]), "bounty", "rep") * mult),
			"money": int(Balance.quest_reward(int(e["tier"]), "bounty", "money") * mult),
			"expire": gs.day() + int(cfg.get("expire_days", 15))})
	gs.bounty_refresh_day = gs.day()


static func on_kill(enemy_id: String) -> void:
	var gs := GameState
	for b in gs.bounties:
		if b["enemy"] == enemy_id and not b.get("done", false):
			b["killed"] = int(b["killed"]) + 1


static func claim_bounties() -> int:
	var gs := GameState
	var n := 0
	for b in gs.bounties:
		if not b.get("done", false) and int(b["killed"]) >= int(b["count"]):
			b["done"] = true
			var r := gs.add_reputation(int(b["rep"]), gs.current_region, true)
			gs.add_money(int(b["money"]))
			gs.note("현상금 수령: %s ×%d — 명성 +%d, %d냥" % [DataDB.display_name(String(b["enemy"])), int(b["count"]), r, int(b["money"])])
			n += 1
	return n


# ================================================================ 세시풍속
static func seasonal_today() -> Dictionary:
	for s in _sd().get("seasonal", []):
		if s["term"] == GameState.solar_term():
			return s
	return {}


static func seasonal_available() -> String:
	var gs := GameState
	var s := seasonal_today()
	if s.is_empty():
		return "해당 절기 활동 없음"
	if gs.seasonal_done.has("%d:%s" % [gs.year(), s["term"]]):
		return "이번 절기에는 이미 참여함"
	var rule: Dictionary = _sd().get("seasonal_rule", {})
	var ok := false
	for f in rule.get("requires_facility_any", []):
		if DataDB.node_has(gs.current_node, String(f)):
			ok = true
	if s.has("facility") and not DataDB.node_has(gs.current_node, String(s["facility"])):
		ok = false
	return "" if ok else "마을(주막·장터·관아·사찰)에서 참여할 수 있습니다"


static func do_seasonal() -> String:
	var gs := GameState
	var err := seasonal_available()
	if err != "":
		return err
	var s := seasonal_today()
	gs.seasonal_done["%d:%s" % [gs.year(), s["term"]]] = true
	var fx: Dictionary = s.get("effect", {})
	for k in fx.keys():
		match k:
			"reputation": gs.add_reputation(int(fx[k]), gs.current_region, true)
			"money": gs.add_money(int(fx[k]))
			"hp": gs.hp = minf(gs.hp_max(), gs.hp + float(fx[k]))
			"fatigue": gs.fatigue = clampf(gs.fatigue + float(fx[k]), 0, 100)
			"satiety": gs.satiety = minf(100.0, gs.satiety + float(fx[k]))
			"cure": gs.cure_field(fx[k])
			"knowledge_xp":
				for kk in fx[k].keys():
					gs.add_knowledge_xp(kk, int(fx[k][kk]))
			"weather_force": gs.weather = String(fx[k])
	var buff := {}
	for k in ["reputation_gain", "res_all", "atk_pct", "fatigue_gain_mult", "satiety_drain_mult"]:
		if fx.has(k):
			buff[k] = fx[k]
	if not buff.is_empty():
		DataDB.field_buffs["BUFF_SEASONAL"] = {"id": "BUFF_SEASONAL", "name": String(s["activity"])}
		DataDB.field_buffs["BUFF_SEASONAL"].merge(buff)
		gs.add_field_status("BUFF_SEASONAL", float(_sd().get("seasonal_rule", {}).get("buff_days", 15)))
	gs.note("세시풍속 「%s」(%s)" % [s["activity"], s["term"]])
	return ""


# ================================================================ 탁본
static func takbon_sheets_here() -> Array:
	var r := DataDB.get_row(GameState.current_region)
	return r.get("daedong_sheets", []).filter(func(n): return not GameState.takbon.has(str(n)))


static func takbon_can() -> String:
	var gs := GameState
	var t: Dictionary = _sd().get("takbon", {})
	var ok := false
	for f in t.get("facilities", []):
		if DataDB.node_has(gs.current_node, String(f)):
			ok = true
	if not ok:
		return "봉수대·관아·서점에서 판목을 빌릴 수 있습니다"
	if takbon_sheets_here().is_empty():
		return "이 권역의 첩은 모두 인출했습니다"
	if not gs.has_materials(t.get("materials", [])):
		return "재료 부족(닥나무 껍질 2, 참숯 1)"
	return ""


static func takbon_done(ok: bool) -> void:
	var gs := GameState
	var t: Dictionary = _sd().get("takbon", {})
	gs.consume_materials(t.get("materials", []))
	if not ok:
		gs.note("탁본이 번졌습니다… 다시 시도하세요.")
		return
	var sheet := int(takbon_sheets_here()[0])
	gs.takbon[str(sheet)] = gs.day()
	var ps: Dictionary = t.get("per_sheet", {})
	gs.add_reputation(int(ps.get("reputation", 0)), gs.current_region)
	if ps.get("reveal_region_nodes", false):
		for n in DataDB.nodes_in(gs.current_region):
			if n.get("hidden", false):
				gs.discovered[n["id"]] = true
	gs.note("대동여지도 제%d첩 인출 (%d/22)" % [sheet, gs.takbon.size()])
	if gs.takbon.size() >= int(t.get("sheets", 22)) and not gs.takbon.has("_complete"):
		gs.takbon["_complete"] = gs.day()
		var cb: Dictionary = t.get("complete_bonus", {})
		gs.add_reputation(int(cb.get("reputation", 0)), gs.current_region)
		if cb.has("item"):
			gs.add_item(String(cb["item"]))
		gs.note("22첩 완성! 칭호 「%s」" % cb.get("title", ""))


static func takbon_region_bonus() -> float:
	## 해당 권역 첩을 모두 인출했으면 피로 누적 −5%
	var r := DataDB.get_row(GameState.current_region)
	for n in r.get("daedong_sheets", []):
		if not GameState.takbon.has(str(n)):
			return 1.0
	return float(_sd().get("takbon", {}).get("per_sheet", {}).get("region_fatigue_gain_mult", 0.95))


# ================================================================ 일일 처리
static func daily(d: int) -> void:
	var gs := GameState
	if d - gs.bounty_refresh_day >= int(_sd().get("bounty", {}).get("refresh_days", 5)):
		refresh_bounties()
