class_name SurvivalSystem
extends RefCounted
## 완전판 4장: 이동 속도 공식 · 10리(200px) 생존 틱 · 피로 4단계 · 포만/아사 · 질병 · 휴식(야영/주막/온천/사찰)


static func _sv() -> Dictionary:
	return DataDB.overview.get("survival", {})


static func has_torch() -> bool:
	return GameState.has_item("item_torch")


## Final Speed = (V_base + V_mount) × M_terrain × M_weather × M_time × M_weight × (피로·질병)
static func speed_now(terrain: String) -> float:
	var gs := GameState
	var fs := gs.fatigue_stage()
	if fs.get("immobile", false):
		return 0.0
	var v_mount := 0.0
	var mid := String(gs.equipped.get("mount", ""))
	if terrain == "water" and gs.has_water_mount():
		for id in gs.inventory.keys():
			var r := DataDB.get_row(id)
			if DataDB.sheet_of(id) == "07_mounts.json:mounts" and String(r.get("terrain", "")) in ["water", "air"]:
				v_mount = maxf(v_mount, float(r.get("v_mount", 0)))
	elif gs.mounted():
		v_mount = float(DataDB.get_row(mid).get("v_mount", 0))
		if String(DataDB.get_row(mid).get("terrain", "")) == "air":
			terrain = "road"  # 비행: 지형 배율 1.0
		var sk := DataDB.skill(String(DataDB.get_row(mid).get("skill", "")))
		if terrain == "mountain" and sk.get("effects", {}).has("field_terrain_mountain"):
			terrain = "trail"
	else:
		v_mount = float(DataDB.get_row(String(gs.equipped.get("shoes", ""))).get("stats", {}).get("spd", 0))
	var mult := float(fs.get("speed", 1.0))
	var b := gs.buff_totals()
	mult *= float(b.get("speed_mult", 1.0))
	return Balance.move_speed(v_mount, terrain, gs.weather, gs.is_night(), has_torch(), gs.weight_ratio(), mult)


static func _weight_fatigue(ratio: float) -> float:
	for w in _sv().get("fatigue_mult", {}).get("weight", []):
		if ratio < float(w["max"]):
			return float(w["mult"])
	return 1.6


## 10리 1틱 처리. 반환: {"stop": bool, "reason": String}
static func tick(terrain: String) -> Dictionary:
	var gs := GameState
	var sv := _sv()
	var fm: Dictionary = sv.get("fatigue_mult", {})
	var b := gs.buff_totals()
	# 피로
	var f := float(sv.get("fatigue_per_tick", 2.0))
	f *= float(fm.get("terrain", {}).get(terrain, 1.0))
	f *= float(fm.get("weather", {}).get(gs.weather, 1.0))
	var shoes := String(gs.equipped.get("shoes", ""))
	f *= float(fm.get("no_shoes", 1.3)) if shoes == "" else float(DataDB.get_row(shoes).get("fatigue_mult", 1.0))
	f *= _weight_fatigue(gs.weight_ratio())
	if gs.mounted():
		f *= float(fm.get("mounted", 0.5))
		var cost := float(DataDB.overview.get("movement", {}).get("mount_stamina_per_10li", 3.0))
		var sk := DataDB.skill(String(DataDB.get_row(String(gs.equipped["mount"])).get("skill", "")))
		cost *= 1.0 + float(sk.get("effects", {}).get("field_stamina_cost", 0.0))
		gs.mount_stamina = maxf(0.0, gs.mount_stamina - cost)
		if gs.mount_stamina <= 0.0:
			gs.note("탈것이 지쳤습니다 — 역참에서 마필을 교체하세요(도보 전환).")
	if gs.satiety <= float(sv.get("hunger_threshold", 30)):
		f *= float(sv.get("hunger_fatigue_mult", 1.3))
	f *= float(b.get("fatigue_gain_mult", 1.0)) * maxf(0.2, 1.0 + float(b.get("fatigue_gain", 0.0)))
	f *= float(b.get("region_fatigue_gain_mult", 1.0))
	gs.fatigue = minf(100.0, gs.fatigue + f)
	# 포만
	var s := float(sv.get("satiety_per_tick", 2.5))
	if gs.season() == 3:
		s *= float(sv.get("satiety_winter_mult", 1.5))
	s *= float(b.get("satiety_drain_mult", 1.0))
	gs.satiety = maxf(0.0, gs.satiety - s)
	if gs.auto_eat and gs.satiety < float(sv.get("auto_eat_below", 30)):
		auto_eat()
	# 체력
	if gs.satiety <= 0.0:
		gs.hp = maxf(1.0, gs.hp - gs.hp_max() * float(sv.get("starve_hp_loss_per_5li", 0.05)) * 2.0)
	elif gs.satiety > float(sv.get("hunger_threshold", 30)) and not ("fever" in gs.diseases()):
		gs.hp = minf(gs.hp_max(), gs.hp + float(sv.get("hp_regen_per_tick", 1)))
	for sid in gs.diseases():
		gs.hp = maxf(1.0, gs.hp - gs.hp_max() * float(DataDB.status_field[sid].get("hp_loss_per_tick", 0.0)))
	# 질병 (위험 단계 + 악천후)
	var dt: Dictionary = DataDB.docs.get("18_status_effects.json", {}).get("disease_triggers", {})
	if gs.fatigue >= float(dt.get("fatigue_min", 90)) and gs.weather in dt.get("weathers", []) and gs.rng.randf() < float(dt.get("chance_per_tick", 0.1)):
		var sid := String(dt.get("table", {}).get(gs.weather, "cold"))
		gs.add_field_status(sid, float(DataDB.status_field.get(sid, {}).get("days", 3)))
	if terrain == "mountain" and gs.fatigue >= 90 and gs.rng.randf() < float(dt.get("fall_chance_mountain_exhausted", 0.02)):
		gs.add_field_status("fracture", float(DataDB.status_field.get("fracture", {}).get("days", 10)))
		gs.note("탈진한 채 산길에서 넘어졌습니다!")
	gs.stats_changed.emit()
	if gs.hp <= 1.0 and gs.satiety <= 0.0:
		return {"stop": true, "reason": "starved"}
	if gs.fatigue >= 100.0:
		return {"stop": true, "reason": "exhausted"}
	return {"stop": false, "reason": ""}


## 가장 싼 휴대 식량부터 섭취
static func auto_eat() -> bool:
	var best := ""
	var best_score := 1.0e9
	for id in GameState.inventory.keys():
		var r := DataDB.get_row(id)
		var sat := float(r.get("satiety", r.get("effect", {}).get("satiety", 0)))
		if sat <= 0 or String(r.get("kind", "")) == "staple":
			continue
		var score := float(r.get("price", 10)) / sat - float(100 - float(GameState.freshness.get(id, 100))) * 0.01
		if score < best_score:
			best_score = score
			best = id
	if best == "":
		return false
	return eat(best)


static func eat(id: String) -> bool:
	var r := DataDB.get_row(id)
	var sat := float(r.get("satiety", r.get("effect", {}).get("satiety", 0)))
	if sat <= 0 or not GameState.remove_item(id):
		return false
	var fresh := float(GameState.freshness.get(id, 100.0)) / 100.0
	GameState.satiety = minf(100.0, GameState.satiety + sat * maxf(0.5, fresh))
	GameState.note("%s 섭취 — 포만 %.0f" % [r.get("name", id), GameState.satiety])
	var eff: Dictionary = r.get("effect", {})
	if eff.has("battle_buff"):
		GameState.apply_food_buff(eff["battle_buff"])
	if eff.has("heal_pct"):
		GameState.hp = minf(GameState.hp_max(), GameState.hp + GameState.hp_max() * float(eff["heal_pct"]))
	GameState.stats_changed.emit()
	return true


# ------------------------------------------------------------ 휴식
static func camp() -> String:
	var gs := GameState
	var c: Dictionary = _sv().get("camp", {})
	var meals := int(c.get("meals", 1))
	if not gs.has_life_passive("pas_nong"):
		for i in meals:
			if not auto_eat():
				gs.note("먹을 것이 없어 굶주린 채 노숙합니다.")
	var r: Array = c.get("fatigue_recover", [30, 50])
	var rec := float(gs.rng.randi_range(int(r[0]), int(r[1])))
	rec += gs.life_effect("gong", "camp_fatigue")
	if gs.has_item("item_tent"):
		rec += 10
	gs.fatigue = maxf(0.0, gs.fatigue - rec)
	if int(gs.party_knowledge().get("gong", 0)) >= 3:
		gs.add_field_status("BUFF_CAMP_PERFORMANCE", 1)
	gs.advance_minutes(int(c.get("hours", 8)) * 60)
	gs.note("야영 — 피로 −%d" % int(rec))
	return ""


static func inn_rest() -> String:
	var gs := GameState
	var n := DataDB.get_row(gs.current_node)
	var inn: Dictionary = _sv().get("inn", {})
	var cost := int(inn.get("cost_city", 20)) if String(n.get("type", "")) == "city" else int(inn.get("cost_town", 10))
	cost = maxi(0, int(round(cost * (1.0 - Balance.dev_benefit("inn_discount", gs.current_node)))))
	if not gs.spend_money(cost):
		return "숙박비 부족"
	gs.fatigue = 0.0
	gs.hp = gs.hp_max()
	if gs.diseases().has("cold"):
		gs.cure_field(["cold"])
	var wait := (6 - gs.hour() + 24) % 24  # 다음 날 묘시(06시)까지
	if wait < 4:
		wait += 24 if wait == 0 else 0
	gs.advance_minutes(maxi(4, wait) * 60)
	gs.note("온돌방 숙박(−%d냥) — 피로·체력 완전 회복" % cost)
	if DataDB.overview.get("save", {}).get("checkpoint_on_inn_rest", true) and gs.can_save_here() == "":
		gs.save_game(true)
	return ""


static func spring_bath() -> String:
	var gs := GameState
	var sp: Dictionary = _sv().get("spring", {})
	if not gs.spend_money(int(sp.get("cost", 15))):
		return "목욕값 부족"
	gs.fatigue = 0.0
	gs.cure_field(gs.diseases())
	gs.add_field_status(String(sp.get("buff", "BUFF_WARM_SPRING_VITALITY")), float(sp.get("buff_days", 3)))
	gs.advance_minutes(120)
	gs.note("온천욕 — 피로 완치, 질병 치료, 온천 기력 버프")
	return ""


static func temple_rest() -> String:
	var gs := GameState
	var t: Dictionary = _sv().get("temple_rest", {})
	if not gs.spend_money(int(t.get("donation", 10))):
		return "시주 부족"
	var r: Array = t.get("fatigue_recover", [60, 80])
	var rec := gs.rng.randi_range(int(r[0]), int(r[1]))
	gs.fatigue = maxf(0.0, gs.fatigue - rec)
	gs.advance_minutes(360)
	gs.note("사찰 요사채에서 쉼 — 피로 −%d" % rec)
	return ""


## 아사 위기/HP1: 인근 주막 강제 후송 + 엽전 분실 (완전판 4.2)
static func rescue_to_inn() -> void:
	var gs := GameState
	var best := ""
	var best_d := 1.0e9
	for n in DataDB.nodes_in(gs.current_region):
		if "jumak" in n.get("facilities", []):
			var d := DataDB.node_pos(gs.current_node).distance_to(DataDB.node_pos(n["id"]))
			if d < best_d:
				best_d = d
				best = n["id"]
	var lost := int(gs.money * 0.1)
	gs.money -= lost
	gs.hp = gs.hp_max() * 0.3
	gs.satiety = 40.0
	gs.fatigue = 60.0
	if best != "":
		gs.current_node = best
		gs.inside_node = true
	gs.advance_minutes(720)
	gs.note("쓰러져 %s 주막으로 후송되었습니다 (엽전 %d냥 분실)" % [DataDB.display_name(best), lost])
	gs.node_changed.emit(gs.current_node)
