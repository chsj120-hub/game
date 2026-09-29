class_name BattleView
extends Control
## 상단 전투 뷰어(1920×720): 전장 + 우측 상단 '향후 7턴 깃발 예측 타임라인' + AP 표시 + 커맨드 바.

signal battle_finished(result: String, summary: Dictionary)

const SLOT_W := 300.0
const SLOT_H := 92.0
const TIMELINE_TURNS := 7

var engine: CTBEngine
var instance: Dictionary = {}
var quest_id: String = ""
var current: Combatant = null
var selected_target: Combatant = null
var auto_mode := false
var font: Font
var bar: HFlowContainer
var info_label: Label
var log_label: RichTextLabel
var intermission_left := 0
var used_gimmicks: Dictionary = {}
var _busy := false


func _ready() -> void:
	font = ThemeDB.fallback_font
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	info_label = Label.new()
	info_label.position = Vector2(20, 560)
	info_label.add_theme_font_size_override("font_size", 20)
	add_child(info_label)
	bar = HFlowContainer.new()
	bar.position = Vector2(20, 592)
	bar.size = Vector2(1880, 120)
	bar.add_theme_constant_override("h_separation", 8)
	bar.add_theme_constant_override("v_separation", 6)
	add_child(bar)
	log_label = RichTextLabel.new()
	log_label.position = Vector2(700, 110)
	log_label.size = Vector2(500, 430)
	log_label.scroll_following = true
	log_label.add_theme_font_size_override("normal_font_size", 15)
	add_child(log_label)


func start(instance_row: Dictionary, q_id: String = "") -> void:
	instance = instance_row
	quest_id = q_id
	used_gimmicks = {}
	auto_mode = false
	log_label.clear()
	var mg := String(instance.get("minigame", ""))
	if mg != "":
		_ask_minigame(mg)
	else:
		_begin({}, 1.0)


func _ask_minigame(kind: String) -> void:
	var cfg: Dictionary = DataDB.battle_minigames.get(kind, {})
	_clear_bar()
	info_label.text = "현장 미니게임: %s — 성공 시 적의 선제 방어막을 해체합니다." % cfg.get("name", kind)
	_add_btn("도전하기", _play_minigame.bind(kind, cfg))
	_add_btn("건너뛰기", _begin.bind({}, 1.0))


func _play_minigame(kind: String, cfg: Dictionary) -> void:
	_clear_bar()
	var mg := MinigameBase.create(kind, cfg, String(instance.get("minigame_variant", "")))
	add_child(mg)
	mg.finished.connect(_on_minigame_done.bind(cfg))


func _on_minigame_done(ok: bool, cfg: Dictionary) -> void:
	GameState.note("미니게임 %s" % ("성공!" if ok else "실패…"))
	_begin(cfg.get("effects", {}) if ok else {}, float(cfg.get("boss_scale", 1.0)))


func _begin(mg_effects: Dictionary, boss_scale: float) -> void:
	engine = CTBEngine.new()
	engine.event.connect(func(t): log_label.append_text(t + "\n"))
	engine.instance_id = String(instance.get("id", ""))
	if not mg_effects.is_empty():
		engine.set_minigame(mg_effects, String(instance.get("minigame_applies_to", "final_wave")), boss_scale)
	engine.setup(GameState.party_combat_stats(), instance.get("waves", []), GameState.inventory)
	_advance()


# ------------------------------------------------------------ 턴 진행
func _advance() -> void:
	if _busy:
		return
	_busy = true
	_clear_bar()
	while true:
		if engine.state == CTBEngine.State.INTERMISSION:
			_show_intermission()
			break
		if engine.is_over():
			_show_result()
			break
		current = engine.begin_next_turn()
		if current == null or engine.state != CTBEngine.State.RUNNING:
			continue
		queue_redraw()
		if current.side == "enemy":
			await get_tree().create_timer(0.4).timeout
			engine.enemy_act(current)
			continue
		if auto_mode:
			await get_tree().create_timer(0.25).timeout
			engine.auto_ally_turn(current)
			continue
		_show_commands()
		break
	_busy = false
	queue_redraw()


func _after_action() -> void:
	selected_target = null
	_advance()


## 주인공 턴 안에서의 한 수 뒤: 전투 상태가 바뀌었으면 진행, AP 가 다 떨어지면 자동 턴 종료, 아니면 계속 선택
func _continue_turn() -> void:
	if engine.state != CTBEngine.State.RUNNING or not current.is_alive():
		_after_action()
		return
	var any := false
	for sid in current.skills:
		if engine.can_use(current, String(sid)):
			any = true
			break
	if current.ap <= 0 or not any:
		engine.end_ally_turn(current)
		_after_action()
		return
	_show_commands()
	queue_redraw()


func _show_commands() -> void:
	_clear_bar()
	info_label.text = "▶ %s 차례 — AP %d/%d (이번 턴 %d 사용 → 다음 턴 지연 %d) · HP %d/%d · 대상: %s   AP가 남는 동안 연속 행동" % [current.name, current.ap,
		current.ap_max, current.spent, int(-Balance.restart_gauge(current.spent)), int(current.hp), int(current.max_hp), selected_target.name if selected_target else "자동"]
	for sid in current.skills:
		var sk := engine.skill_row(String(sid))
		var cd := maxi(0, int(current.cooldowns.get(sid, 0)) - 1)
		var who := ""
		if current.comp_skills.has(sid):
			who = "%s·" % current.comp_skills[sid].get("name", "")
		var tag := ""
		if current.comp_skills.has(sid) and current.used_comp.has(String(current.comp_skills[sid]["cid"])):
			tag = " (동료 행동 완료)"
		elif int(sk.get("ap_cost", 1)) == 1 and current.used_basic.has(sid):
			tag = " (이번 턴 사용)"
		elif int(current.cooldowns.get(sid, 0)) > 0:
			tag = " (대기 %d턴)" % maxi(1, cd)
		var b := _add_btn("%s%s [%dAP]%s" % [who, sk.get("name", sid), int(sk.get("ap_cost", 1)), tag], _do_skill.bind(String(sid)))
		b.disabled = not engine.can_use(current, String(sid))
	var end_btn := _add_btn("턴 종료 ▶", _cmd.bind("end_turn"))
	end_btn.disabled = current.spent == 0
	_add_btn("방어(턴 종료)", _cmd.bind("defend"))
	var items_btn := _add_btn("한방약/음식 [1AP]", _open_items.bind(false))
	items_btn.disabled = current.ap < 1
	var cap_btn := _add_btn("포획 [2AP]", _open_capture)
	cap_btn.disabled = current.ap < 2
	var gm_btn := _add_btn("기믹(설득·뇌물·유인·제령) [1AP]", _open_gimmicks)
	gm_btn.disabled = current.ap < 1
	_add_btn("도주", _cmd.bind("flee"))
	_add_btn("자동 전투", _cmd.bind("auto"))


func _cmd(kind: String) -> void:
	match kind:
		"defend": engine.defend(current)
		"end_turn": engine.end_ally_turn(current)
		"flee": engine.try_flee(current)
		"auto":
			auto_mode = true
			if current and current.side == "ally" and engine.state == CTBEngine.State.RUNNING:
				engine.auto_ally_turn(current)
		"next_wave":
			engine.remove_meta("im")
			intermission_left = 0
			engine.next_wave()
		"retreat":
			engine.state = CTBEngine.State.FLED
			_show_result()
			return
	_after_action()


func _do_skill(sid: String) -> void:
	engine.use_skill(current, sid, selected_target)
	selected_target = null
	_continue_turn()


func _battle_items() -> Array:
	var out := []
	for id in engine.items.keys():
		if int(engine.items[id]) <= 0:
			continue
		var r := DataDB.get_row(id)
		var eff: Dictionary = r.get("effect", {})
		var sh := String(r.get("_sheet", ""))
		if sh == "09_herbal_recipes.json:recipes" and r.get("battle_usable", false):
			out.append(id)
		elif sh == "11_food_recipes.json:recipes" and (eff.has("heal_pct") or eff.has("cure")):
			out.append(id)
	return out


func _open_items(free: bool) -> void:
	_clear_bar()
	info_label.text = "소모품 선택 (대상: %s)" % (selected_target.name if selected_target and selected_target.side == "ally" else "가장 위급한 아군")
	for id in _battle_items():
		_add_btn("%s ×%d" % [DataDB.display_name(id), int(engine.items[id])], _use_item.bind(String(id), free))
	_add_btn("← 뒤로", _show_intermission if free else _show_commands)


func _use_item(id: String, free: bool) -> void:
	var revive := DataDB.get_row(id).get("effect", {}).has("revive_pct")
	var t: Combatant = selected_target if selected_target and selected_target.side == "ally" else _most_wounded(revive)
	var actor: Combatant = current if not free else engine.living(engine.allies)[0]
	engine.use_item(actor, id, t, free)
	if free:
		intermission_left -= 1
		_show_intermission()
	else:
		_continue_turn()


func _most_wounded(include_dead: bool) -> Combatant:
	var best: Combatant = null
	for a in engine.allies:
		if (a.is_alive() or include_dead) and (best == null or a.hp_ratio() < best.hp_ratio()):
			best = a
	return best


func _open_capture() -> void:
	_clear_bar()
	var t: Combatant = selected_target if selected_target and selected_target.side == "enemy" else engine._lowest_hp(engine.living(engine.enemies))
	info_label.text = "포획 대상: %s (HP %d%%) — 빈사(30%% 이하)에서만, 보스 불가" % [t.name if t else "-", int(t.hp_ratio() * 100) if t else 0]
	for id in GameState.inventory.keys():
		var r := DataDB.get_row(id)
		if String(r.get("_sheet", "")) != "08_capture_tools.json:tools" or t == null:
			continue
		var chance := Balance.capture_chance(r, t.row, t.hp_ratio(), CompanionSystem.capture_bonus(r))
		_add_btn("%s(%s) ×%d — %.0f%%" % [r["name"], r.get("method", ""), GameState.count(id), chance * 100], _capture.bind(String(id), t))
	_add_btn("← 뒤로", _show_commands)


func _capture(id: String, t: Combatant) -> void:
	var r := DataDB.get_row(id)
	GameState.remove_item(id)
	engine.items[id] = GameState.count(id)
	engine.try_capture(current, r, t, CompanionSystem.capture_bonus(r))
	if not engine.captured.is_empty() and engine.captured[-1] == t.id:
		CompanionSystem.on_captured(t.id, r)
	_continue_turn()


func _open_gimmicks() -> void:
	_clear_bar()
	info_label.text = "비전투 제압/약화 (적마다 1회)"
	for e in engine.living(engine.enemies):
		for g in e.row.get("gimmicks", []):
			var key := "%d:%s" % [e.uid, g["type"]]
			if used_gimmicks.has(key):
				continue
			_add_btn("%s — %s" % [e.name, _gimmick_label(g)], _gimmick.bind(e, g, key))
	_add_btn("← 뒤로", _show_commands)


func _gimmick_label(g: Dictionary) -> String:
	match String(g["type"]):
		"bribe": return "뇌물 %d냥" % int(int(g["money"]) * float(GameState.class_passive().get("bribe_mult", 1.0)))
		"persuade": return "설득 (Rank %d)" % int(g.get("min_rank", 1))
		"lure": return "먹이 유인 (%s ×%d)" % [DataDB.display_name(String(g["item"])), int(g.get("qty", 1))]
		"purify": return "제령 (리듬)"
		"riddle": return "수수께끼 문답"
		"debate": return "삼도 문답"
	return String(g["type"])


func _gimmick(e: Combatant, g: Dictionary, key: String) -> void:
	used_gimmicks[key] = true
	var mg_id := String(g.get("minigame", ""))
	if g["type"] in ["purify", "riddle", "debate"]:
		var mg: MinigameBase
		if mg_id == "rhythm" or mg_id == "":
			mg = MinigameBase.create("rhythm", DataDB.battle_minigames.get("rhythm", {}), "제령")
		else:
			mg = MinigameBase.create_from_catalog(mg_id)
		if mg:
			add_child(mg)
			mg.finished.connect(_do_gimmick.bind(e, g))
			return
	_do_gimmick(false, e, g)


func _do_gimmick(mg_ok: bool, e: Combatant, g: Dictionary) -> void:
	var gs := GameState
	var bribe := int(int(g.get("money", 0)) * float(gs.class_passive().get("bribe_mult", 1.0)))
	var ctx := {"money": gs.money - engine.money_spent, "rank": gs.rank, "item_count": gs.count(String(g.get("item", ""))),
		"minigame_success": mg_ok, "has_required_item": gs.has_item(String(g.get("requires_item", ""))),
		"persuade_any_rank": gs.class_passive().get("persuade_any_rank", false)}
	var gg := g.duplicate()
	gg["money"] = bribe
	var err := engine.apply_gimmick(e, gg, ctx)
	if err != "":
		log_label.append_text("기믹 실패: " + err + "\n")
		_show_commands()
		return
	if g["type"] == "bribe":
		engine.money_spent += bribe
	elif g["type"] == "lure":
		gs.remove_item(String(g["item"]), int(g.get("qty", 1)))
	current.ap -= 1  # 기믹 1AP, 턴은 계속
	current.spent += 1
	_continue_turn()


# ------------------------------------------------------------ 정비 · 결과
func _show_intermission() -> void:
	_clear_bar()
	if intermission_left <= 0 and engine.state == CTBEngine.State.INTERMISSION and not engine.has_meta("im"):
		intermission_left = int(DataDB.overview.get("battle", {}).get("wave_intermission_free_actions", 1)) * engine.living(engine.allies).size()
		engine.set_meta("im", true)
	info_label.text = "웨이브 %d/%d 돌파 — 간이 정비 (남은 무료 행동 %d)" % [engine.wave_index + 1, engine.waves.size(), intermission_left]
	if intermission_left > 0:
		_add_btn("한방약/음식 복용", _open_items.bind(true))
	_add_btn("다음 웨이브 ▶", _cmd.bind("next_wave"))
	_add_btn("도주(안전 복귀)", _cmd.bind("retreat"))


func _show_result() -> void:
	_clear_bar()
	var summary := {"money": 0, "reputation": 0, "drops": [], "killed": [], "captured": engine.captured.duplicate(), "hero_turns": engine.hero_turns}
	var result := "fled"
	if engine.state == CTBEngine.State.VICTORY:
		result = "victory"
		for row in engine.defeated:
			summary["money"] += int(row.get("money_reward", 0))
			if int(row.get("boss_tier", 0)) > 0:
				summary["rep_boss"] = int(summary.get("rep_boss", 0)) + int(row.get("rep_reward", 0))
			else:
				summary["reputation"] += int(row.get("rep_reward", 0))
			summary["killed"].append(String(row.get("id", "")))
			for d in row.get("drops", []):
				if GameState.rng.randf() < float(d["rate"]):
					summary["drops"].append(d["id"])
		for d2 in instance.get("rewards", {}).get("items", []):
			if GameState.rng.randf() < float(d2["rate"]):
				summary["drops"].append(d2["id"])
	elif engine.state == CTBEngine.State.DEFEAT:
		result = "defeat"
	GameState.sync_after_battle(engine)
	info_label.text = {"victory": "승리! 명성 +%d · 엽전 +%d냥 · 전리품 %d · 포획 %d (주인공 %d턴)" % [summary["reputation"], summary["money"], summary["drops"].size(), summary["captured"].size(), engine.hero_turns],
		"defeat": "패배… 가까운 주막으로 후송됩니다", "fled": "무사히 빠져나왔습니다."}[result]
	_add_btn("필드로 돌아가기", func(): battle_finished.emit(result, summary))
	queue_redraw()


# ------------------------------------------------------------ 입력·그리기
func _gui_input(ev: InputEvent) -> void:
	if engine == null or not (ev is InputEventMouseButton) or not ev.pressed:
		return
	for c in engine.allies + engine.enemies:
		if c.is_alive() and _slot_rect(c).has_point(ev.position):
			selected_target = c
			if current and current.side == "ally" and engine.state == CTBEngine.State.RUNNING and not _busy:
				_show_commands()
			queue_redraw()
			return


func _slot_rect(c: Combatant) -> Rect2:
	var list := engine.allies if c.side == "ally" else engine.enemies
	var i := list.find(c)
	var x := 250.0 if c.side == "ally" else 1360.0
	return Rect2(x - SLOT_W / 2.0 + (i % 2) * 50.0, 110 + i * (SLOT_H + 10), SLOT_W, SLOT_H)


func _draw() -> void:
	var bgt := Assets.tex("res://assets/battle/bg_%s.png" % GameState.current_region.to_lower())
	if bgt:
		draw_texture_rect(bgt, Rect2(Vector2.ZERO, size), false)
	else:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.1, 0.09, 0.12))
		draw_rect(Rect2(0, 430, size.x, 120), Color(0.16, 0.13, 0.1))
	if engine == null:
		return
	# 우측 상단: 향후 7턴 깃발 예측 타임라인
	var x := size.x - 20 - TIMELINE_TURNS * 104
	draw_string(font, Vector2(x, 26), "향후 %d턴 행동 순서" % TIMELINE_TURNS, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(1, 0.9, 0.6))
	var idx := 0
	for c in engine.preview(TIMELINE_TURNS):
		var col := Color(0.25, 0.45, 0.85) if c.side == "ally" else Color(0.8, 0.25, 0.2)
		var fx := x + idx * 104
		draw_line(Vector2(fx + 6, 36), Vector2(fx + 6, 92), Color(0.3, 0.2, 0.1), 3)
		draw_colored_polygon(PackedVector2Array([Vector2(fx + 8, 38), Vector2(fx + 98, 46), Vector2(fx + 8, 76)]), col)
		draw_string(font, Vector2(fx + 12, 64), c.name.left(5), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color.WHITE)
		idx += 1
	draw_string(font, Vector2(20, 40), "웨이브 %d/%d · 주인공 턴 %d" % [engine.wave_index + 1, engine.waves.size(), engine.hero_turns], HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)
	for c in engine.allies + engine.enemies:
		_draw_slot(c)
	_draw_companion_cards()


## 동행 동료 카드(전장에 서지 않음): 스킬 제공·이번 턴 행동 여부
func _draw_companion_cards() -> void:
	if engine.allies.is_empty():
		return
	var hero: Combatant = engine.allies[0]
	var y := 230.0
	draw_string(font, Vector2(100, y - 8), "동행 동료 (스킬·지식 합산 · AP +%d/턴)" % (hero.ap_regen - int(DataDB.overview.get("battle", {}).get("ap", {}).get("per_turn", 2))), HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(1, 0.9, 0.6))
	for cid in GameState.party:
		var c := String(cid)
		var r := Rect2(100, y, 300, 44)
		var acted := hero.used_comp.has(c)
		draw_rect(r, Color(0.18, 0.2, 0.28) if not acted else Color(0.12, 0.12, 0.14))
		var pt := Assets.portrait(c)
		if pt:
			draw_texture_rect(pt, Rect2(r.position + Vector2(3, 3), Vector2(38, 38)), false)
		var star := int(GameState.companions.get(c, {}).get("star", 1))
		draw_string(font, r.position + Vector2(48, 27), "%s ★%d %s" % [DataDB.display_name(c), star, "· 행동 완료" if acted else ""], HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.95, 0.95, 0.9) if not acted else Color(0.6, 0.6, 0.6))
		y += 50


func _draw_slot(c: Combatant) -> void:
	var r := _slot_rect(c)
	var base := Color(0.2, 0.25, 0.35) if c.side == "ally" else Color(0.35, 0.18, 0.16)
	if not c.is_alive():
		base = Color(0.15, 0.15, 0.15)
	draw_rect(r, base)
	var pt := Assets.portrait(c.id)
	if pt:
		draw_texture_rect(pt, Rect2(r.position + Vector2(4, 4), Vector2(r.size.y - 8, r.size.y - 8)), false)
	if c == current:
		draw_rect(r, Color(1, 0.9, 0.3), false, 4)
	elif c == selected_target:
		draw_rect(r, Color(0.4, 1, 0.6), false, 3)
	draw_string(font, r.position + Vector2(10, 24), ("【보스】" if c.is_boss() else "") + c.name + " [%s]" % {"yu": "유", "bul": "불", "seon": "선"}.get(c.aff, "무"), HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color.WHITE)
	var w := r.size.x - 20
	draw_rect(Rect2(r.position + Vector2(10, 34), Vector2(w, 12)), Color(0.1, 0.1, 0.1))
	draw_rect(Rect2(r.position + Vector2(10, 34), Vector2(w * c.hp_ratio(), 12)), Color(0.3, 0.85, 0.35) if c.side == "ally" else Color(0.9, 0.35, 0.3))
	draw_rect(Rect2(r.position + Vector2(10, 49), Vector2(w * clampf(c.gauge / Balance.gauge_max(), 0, 1), 4)), Color(0.9, 0.8, 0.3))
	draw_string(font, r.position + Vector2(10, 70), "HP %d/%d  AP %d  ATK %d DEF %d" % [int(c.hp), int(c.max_hp), c.ap, int(c.atk()), int(c.defense())], HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.9, 0.9, 0.9))
	var flags := PackedStringArray()
	for sid in c.statuses.keys():
		flags.append(String(DataDB.status_battle.get(sid, {}).get("name", sid)))
	if c.taunt_turns > 0: flags.append("도발")
	if c.enraged: flags.append("격노")
	if c.atk_mult < 1.0: flags.append("약화")
	if flags.size() > 0:
		draw_string(font, r.position + Vector2(10, 87), " ".join(flags), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(1, 0.8, 0.4))


func _clear_bar() -> void:
	for ch in bar.get_children():
		ch.queue_free()


func _add_btn(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 42)
	b.add_theme_font_size_override("font_size", 17)
	b.pressed.connect(cb)
	bar.add_child(b)
	return b
