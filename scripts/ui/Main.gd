extends Control
## 메인 씬 — 완전판 11.3 CanvasLayer 분리:
##   상단 월드/전투 뷰어: SubViewportContainer(1920×720) > SubViewport > FieldView | BattleView
##   하단 대시보드 HUD : CanvasLayer(layer 1) > Dashboard(1920×360)
##   모달 오버레이     : CanvasLayer(layer 5) > MapModal · 메뉴/시설 모달 · 도착 분기 · 필드 미니게임
## 시설 모달은 상태 머신(CLOSED→FACILITY_LIST→FACILITY→ACTION)으로 동작한다.

enum FacState { CLOSED, FACILITY_LIST, FACILITY, ACTION }

const TOP := Vector2(1920, 720)

var top_vp: SubViewport
var field: FieldView
var battle: BattleView
var hud: CanvasLayer
var dash: Dashboard
var overlay: CanvasLayer
var map_modal: MapModal
var menu: PanelContainer
var menu_title: Label
var menu_list: VBoxContainer
var mg_host: Control
var traveler: TravelController
var fac_state: int = FacState.CLOSED
var fac_current: String = ""
var in_battle := false
var tut_panel: PanelContainer
var tut_title: Label
var tut_body: Label
var tut_next: Button


func _ready() -> void:
	var svc := SubViewportContainer.new()
	svc.position = Vector2.ZERO
	svc.size = TOP
	svc.stretch = true
	add_child(svc)
	top_vp = SubViewport.new()
	top_vp.size = Vector2i(TOP)
	top_vp.handle_input_locally = true
	svc.add_child(top_vp)
	field = FieldView.new()
	top_vp.add_child(field)
	field.size = TOP
	battle = BattleView.new()
	top_vp.add_child(battle)
	battle.size = TOP
	battle.hide()
	hud = CanvasLayer.new()
	hud.layer = 1
	add_child(hud)
	dash = Dashboard.new()
	dash.position = Vector2(0, TOP.y)
	dash.size = Vector2(1920, 360)
	hud.add_child(dash)
	overlay = CanvasLayer.new()
	overlay.layer = 5
	add_child(overlay)
	mg_host = Control.new()
	mg_host.position = Vector2.ZERO
	mg_host.size = TOP
	mg_host.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.add_child(mg_host)
	_build_menu()
	map_modal = MapModal.new()
	map_modal.size = Vector2(1920, 1080)
	overlay.add_child(map_modal)
	traveler = TravelController.new()
	add_child(traveler)
	field.traveler = traveler
	map_modal.traveler = traveler
	traveler.arrived.connect(_on_arrived)
	traveler.encounter.connect(_on_encounter)
	traveler.stopped.connect(_on_stopped)
	map_modal.travel_requested.connect(_start_travel)
	map_modal.fast_travel_requested.connect(_fast_travel)
	dash.command.connect(_on_command)
	battle.battle_finished.connect(_on_battle_finished)
	GameState.rank_up.connect(func(_r): field.queue_redraw())
	_build_tutorial_panel()
	GameState.stats_changed.connect(_refresh_tutorial)
	Settings.changed.connect(func(_k): _refresh_tutorial())
	_title_screen()


# ================================================================ 범용 메뉴(시설·배낭·도감 등 모달)
func _build_menu() -> void:
	menu = PanelContainer.new()
	menu.position = Vector2(460, 40)
	menu.size = Vector2(1000, 660)
	menu.add_theme_stylebox_override("panel", Assets.panel_style("modal", Color(0.12, 0.09, 0.06, 0.97), Color(0.85, 0.68, 0.35)))
	var v := VBoxContainer.new()
	menu.add_child(v)
	var head := HBoxContainer.new()
	v.add_child(head)
	menu_title = Label.new()
	menu_title.add_theme_font_size_override("font_size", 24)
	Assets.title(menu_title, 34)  # 메뉴 제목: 나눔손글씨 붓
	menu_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(menu_title)
	var back := Button.new()
	back.text = "← 뒤로"
	back.pressed.connect(_menu_back)
	head.add_child(back)
	var close := Button.new()
	close.text = "닫기 ✕"
	close.pressed.connect(_close_menu)
	head.add_child(close)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(960, 590)
	v.add_child(scroll)
	menu_list = VBoxContainer.new()
	menu_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(menu_list)
	overlay.add_child(menu)
	menu.hide()


## entries: [{text, cb?, disabled?, hint?}]
func open_menu(title: String, entries: Array) -> void:
	menu_title.text = title
	for c in menu_list.get_children():
		c.queue_free()
	if entries.is_empty():
		entries = [{"text": "(항목 없음)"}]
	for e in entries:
		if not e.has("cb"):
			var l := Label.new()
			l.text = String(e["text"])
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			l.custom_minimum_size = Vector2(940, 0)
			l.add_theme_font_size_override("font_size", 17)
			l.add_theme_color_override("font_color", Color(1, 0.88, 0.6))
			menu_list.add_child(l)
			continue
		var b := Button.new()
		var hint := String(e.get("hint", ""))
		b.text = String(e["text"]) + ("" if hint == "" else "   — " + hint)
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.disabled = e.get("disabled", false)
		b.custom_minimum_size = Vector2(940, 40)
		b.add_theme_font_size_override("font_size", 17)
		b.pressed.connect(_menu_pick.bind(e["cb"], e.get("keep", false)))
		menu_list.add_child(b)
	menu.show()
	menu.move_to_front()


func _menu_pick(cb: Callable, keep: bool) -> void:
	if not keep:
		menu.hide()
	cb.call()


func _close_menu() -> void:
	menu.hide()
	fac_state = FacState.CLOSED


func _menu_back() -> void:
	match fac_state:
		FacState.ACTION:
			_open_facility(fac_current)
		FacState.FACILITY:
			_open_facilities()
		_:
			_close_menu()


# ================================================================ 시작 화면
func _title_screen() -> void:
	var entries := [{"text": "《대동여지도 어드벤처: 삼한팔도 유람기》 — 시나리오 또는 직업을 선택하세요"}]
	if GameState.has_save():
		entries.append({"text": "▶ 이어하기 (마지막 주막)", "cb": _continue_game})
	for sc in DataDB.table("23_tutorial.json", "scenarios"):
		entries.append({"text": "★ %s" % sc["name"], "hint": String(sc.get("desc", "")), "cb": _new_game.bind(String(sc["class"]), String(sc["id"]))})
	entries.append({"text": "── 본편: 한양에서 시작 (직업 선택)"})
	for c in DataDB.table("19_classes_knowledge.json", "classes"):
		entries.append({"text": "[%s] %s" % [c["name"], c.get("desc", "")], "hint": "시작 엽전 %d냥" % int(c.get("start", {}).get("money", 0)), "cb": _new_game.bind(String(c["id"]))})
	entries.append({"text": "⚙ 설정", "cb": _open_settings.bind(true), "keep": true})
	entries.append({"text": "? 도움말", "cb": _open_help.bind(true), "keep": true})
	open_menu("새 여정", entries)


func _continue_game() -> void:
	GameState.load_game()
	_after_start()


func _new_game(cls: String, scenario := "") -> void:
	GameState.new_game(cls, scenario)
	SideSystems.refresh_bounties()
	_after_start()


func _after_start() -> void:
	var gs := GameState
	if gs.scenario_id != "":
		var sc := DataDB.get_row(gs.scenario_id)
		gs.note("【%s】 %s에서 %s의 이야기가 시작됩니다." % [sc.get("name", ""), DataDB.display_name(gs.current_node), gs.hero_name])
		var m := DataDB.get_row(String(sc.get("main", "")))
		if m.has("era_note"):
			gs.note("※ " + String(m["era_note"]))
	else:
		gs.note("한양 경조에서 여정을 시작합니다. [지도]로 목적지를 정하고, [거점 시설]에서 주막·관아·장터를 이용하세요.")
	gs.note("저장은 대도시 주막에서만 가능합니다. 이동 중 Space = 긴급 정지, M = 지도. 막히면 [도움말].")
	EventSystem.check_triggers()
	field.queue_redraw()
	_refresh_tutorial()


# ================================================================ 입력
func _unhandled_input(ev: InputEvent) -> void:
	if not (ev is InputEventKey) or not ev.pressed or ev.echo:
		return
	if ev.keycode == KEY_SPACE and traveler.moving:
		traveler.stop("user")
		get_viewport().set_input_as_handled()
	elif ev.keycode == KEY_M and not in_battle:
		if map_modal.visible:
			map_modal.close()
		else:
			map_modal.open()
			GameState.bump("open_map")
		get_viewport().set_input_as_handled()


# ================================================================ 커맨드
func _on_command(cmd: String) -> void:
	if in_battle and not (cmd in ["codex", "knowledge", "help", "settings"]):
		return
	if traveler.moving and not (cmd in ["stop", "ff", "map", "codex", "knowledge", "bag", "help", "settings"]):
		GameState.note("행군 중입니다 — 먼저 정지(Space)하세요.")
		return
	match cmd:
		"map":
			map_modal.open()
			GameState.bump("open_map")
		"help": _open_help()
		"settings": _open_settings()
		"bag": _open_bag()
		"equip": _open_equip()
		"codex": _open_codex()
		"camp":
			SurvivalSystem.camp()
			GameState.bump("camp")
			SideSystems.reveal_by_skill("camp")
		"search":
			SideSystems.search()
		"gather":
			SideSystems.gather()
			GameState.bump("gather")
			SideSystems.reveal_by_skill("gather")
		"hunt":
			SideSystems.reveal_by_skill("hunt")
			var w := SideSystems.hunt_waves()
			if not w.is_empty():
				_begin_battle({"id": "hunt", "name": "사냥", "waves": w}, "")
		"here": _open_facilities()
		"event": _open_events()
		"quest": _open_quests()
		"craft": _open_craft()
		"party": _open_party()
		"knowledge": _open_knowledge()
		"stop": traveler.stop("user")
		"ff":
			traveler.fast_forward = float(Settings.get_value("fast_forward")) if traveler.fast_forward < 1.5 else 1.0
			GameState.note("행군 배속 ×%d" % int(traveler.fast_forward))


# ================================================================ 이동
func _start_travel(dest: String) -> void:
	var legs := TravelSystem.find_path(GameState.current_node, dest)
	if legs.is_empty():
		GameState.note("경로를 찾을 수 없습니다.")
		return
	_close_menu()
	traveler.start(legs)


func _fast_travel(dest: String) -> void:
	var err := TravelSystem.station_fast_travel(dest)
	if err != "":
		GameState.note(err)


func _on_arrived(node_id: String, is_final: bool) -> void:
	var n := DataDB.get_row(node_id)
	var entries := [{"text": "%s [%s] 도착 — %s" % [n["name"], n.get("type_label", ""), "목적지" if is_final else "경유지"]}]
	entries.append({"text": "거점 진입하기", "cb": _enter_node})
	if not is_final:
		entries.append({"text": "외곽 통과 (계속 행군)", "cb": func(): traveler.continue_march()})
	else:
		entries.append({"text": "외곽에 머무르기", "cb": func(): pass})
	open_menu("거점 도달", entries)


func _enter_node() -> void:
	GameState.inside_node = true
	GameState.stats_changed.emit()
	_open_facilities()


func _on_stopped(reason: String) -> void:
	match reason:
		"exhausted":
			GameState.note("완전 탈진 — 야영하거나 탕약을 복용하기 전에는 움직일 수 없습니다.")
		"starved":
			SurvivalSystem.rescue_to_inn()
		"ferry":
			pass


func _on_encounter(waves: Array, near: String) -> void:
	GameState.note("%s 부근에서 적과 조우했습니다!" % DataDB.display_name(near))
	_begin_battle({"id": "encounter", "name": "노상 조우", "waves": waves, "resume_travel": true}, "")


# ================================================================ 시설 모달 (상태 머신)
func _open_facilities() -> void:
	fac_state = FacState.FACILITY_LIST
	var gs := GameState
	gs.counters["open_facilities"] = int(gs.counters.get("open_facilities", 0)) + 1
	_refresh_tutorial()
	var n := DataDB.get_row(gs.current_node)
	var entries := [{"text": "%s [%s] — %s" % [n["name"], n.get("type_label", ""), n.get("note", "")]}]
	if n.has("anachronism"):
		entries.append({"text": "※ 고증 메모: " + String(n["anachronism"])})
	if not gs.inside_node:
		entries.append({"text": "거점 진입하기", "cb": _enter_node})
	else:
		for f in FacilitySystem.facilities_here():
			entries.append({"text": FacilitySystem.NAMES.get(f, f), "cb": _open_facility.bind(String(f)), "keep": true})
	for her in DataDB.heritages_at(gs.current_node):
		var st := String(gs.heritage_state.get(her["id"], ""))
		var desig := (" · " + String(her["designation"])) if her.has("designation") else ""
		entries.append({"text": "【유산】 %s (%d등급 · %s%s)" % [her["name"], int(her["tier"]), HeritageSystem.reward_type_label(HeritageSystem.reward_type(her)), desig],
			"hint": {"": "답사 가능", "pending": "보상 선택 대기"}.get(st, "완료"), "cb": _heritage_node.bind(String(her["id"])), "keep": true})
	for a in EventSystem.actionable_here():
		entries.append({"text": "【이벤트】 %s" % EventSystem.definition(a["eid"]).get("name", ""), "hint": a["block"] if a["block"] != "" else String(a["stage"].get("text", "")).left(40),
			"disabled": a["block"] != "", "cb": _event_stage.bind(String(a["eid"]))})
	for hw in SideSystems.hwacheop_available():
		entries.append({"text": "【화첩】 「%s」 스냅샷 (%s)" % [hw["scene"]["title"], hw["scene"]["painter"]], "cb": func(): SideSystems.take_snapshot(hw)})
	open_menu("거점 — %s" % n["name"], entries)


func _open_facility(fac: String) -> void:
	fac_state = FacState.FACILITY
	fac_current = fac
	var entries := []
	for a in FacilitySystem.actions(fac):
		entries.append({"text": a["text"], "hint": a.get("hint", ""), "disabled": a.get("disabled", false), "cb": _facility_action.bind(fac, String(a["id"]))})
	open_menu("%s · %s" % [DataDB.display_name(GameState.current_node), FacilitySystem.NAMES.get(fac, fac)], entries)


func _facility_action(fac: String, aid: String) -> void:
	fac_state = FacState.ACTION
	var gs := GameState
	var err := ""
	if aid.begins_with("read:"):
		err = FacilitySystem.read_book(aid.substr(5))
	else:
		match aid:
			"promote": gs.promote()
			"heritage_pending": _open_pending()
			"gwana_doc":
				var q := FacilitySystem.gwana_doc_quest()
				if not q.is_empty():
					RouteQueue.start_quest(q)
			"bounty_board": _open_bounties()
			"takbon": _do_takbon()
			"seasonal": err = SideSystems.do_seasonal()
			"inn": err = SurvivalSystem.inn_rest()
			"save": gs.save_game()
			"load":
				gs.load_game()
			"craft": _open_craft()
			"barracks": _open_party()
			"trade": _open_trade()
			"shop": _open_shop()
			"sell": _open_sell()
			"invest": TradeSystem.invest_town()
			"cure_all": gs.cure_field(gs.diseases())
			"swap_horse": err = FacilitySystem.swap_horse()
			"fast_travel": _open_fast_travel()
			"temple_rest": err = SurvivalSystem.temple_rest()
			"blessing": err = FacilitySystem.blessing()
			"haewon": _play_field_mg("mg_bell", func(ok): FacilitySystem.haewon_done(ok))
			"bath": err = SurvivalSystem.spring_bath()
			"checkpoint_info": pass
			"drill": err = FacilitySystem.drill()
			"beacon": err = SideSystems.light_beacon()
			"hwacheop":
				var av := SideSystems.hwacheop_available()
				if av.is_empty():
					err = "지금 기록할 장면이 없습니다"
				else:
					SideSystems.take_snapshot(av[0])
			"investigate":
				var target := ""
				for h in DataDB.heritages_at(gs.current_node):  # 아직 답사하지 않은 첫 유산
					if not gs.heritage_state.has(h["id"]):
						target = String(h["id"])
						break
				if target == "":
					err = "조사할 유적이 없습니다(모두 답사함)"
				else:
					_heritage_node(target)
			"ferry": _open_ferry()
			"hazard_fight":
				var w := TravelSystem.roll_encounter("mountain", gs.current_node)
				if not w.is_empty():
					_begin_battle({"id": "hazard", "name": "고개 돌파", "waves": w}, "")
	if err != "":
		gs.note(err)


# ================================================================ 유산
func _heritage_node(her_id: String) -> void:
	var gs := GameState
	var st := String(gs.heritage_state.get(her_id, ""))
	if st == "":
		var err := HeritageSystem.can_visit(her_id)
		if err != "":
			gs.note(err)
			return
		var mg := HeritageSystem.required_minigame(DataDB.get_row(her_id))
		if mg == "":
			HeritageSystem.visit(her_id, true)
			_heritage_choice(her_id)
		else:
			gs.note("유적 조사: %s" % DataDB.minigame(mg).get("name", mg))
			_play_field_mg(mg, _on_investigate_done.bind(her_id))
	elif st == "pending":
		_heritage_choice(her_id)
	else:
		RouteQueue.on_node_visited(her_id)
		gs.note("%s — 이미 답사 완료(%s)" % [DataDB.display_name(her_id), st])


func _on_investigate_done(ok: bool, her_id: String) -> void:
	HeritageSystem.visit(her_id, ok)
	if ok:
		_heritage_choice(her_id)


func _heritage_choice(her_id: String) -> void:
	var h := DataDB.get_row(her_id)
	var pv := HeritageSystem.preview(her_id)
	var e := [
		{"text": "획득: %s %s   출처: %s %s" % [HeritageSystem.reward_type_label(HeritageSystem.reward_type(h)), DataDB.display_name(String(h["reward"])),
			h.get("public_data", {}).get("provider", ""), h.get("public_data", {}).get("license", "")]},
		{"text": "[선택 1] 실사용 — 장착 / 비전서 등록", "cb": _resolve_her.bind(her_id, "use")},
		{"text": "답사 명성은 이미 받았습니다(약 %d). 신분 격차 배율 ×%.2f %s" % [int(pv["discovery"]), float(pv["rank_gap"]),
			"— 윗등급 선행 발견 보너스!" if float(pv["rank_gap"]) > 1.0 else ("— 신분보다 낮은 유산이라 감쇠" if float(pv["rank_gap"]) < 1.0 else "")]},
		{"text": "[선택 2] 관아·향교 기증 — 명성 약 %d" % int(pv["reputation"]), "disabled": pv["donate"] != "", "hint": pv["donate"], "cb": _resolve_her.bind(her_id, "donate")},
		{"text": "[선택 3] 골동상 매각 — 엽전 약 %d냥" % int(pv["money"]), "disabled": pv["sell"] != "" or not DataDB.node_has(GameState.current_node, "antique"), "hint": pv["sell"], "cb": _resolve_her.bind(her_id, "sell")},
	]
	if pv["black_market"]:
		e.append({"text": "[선택 3′] 암시장 매각 — 엽전 약 %d냥 (×1.25, 적발 10%% 시 명성 감소)" % int(pv["money"] * 1.25), "cb": _resolve_her.bind(her_id, "sell_black")})
	e.append({"text": "나중에 결정 (보관)", "cb": func(): pass})
	open_menu("%s — 3가지 선택형 보상" % h["name"], e)


func _resolve_her(her_id: String, choice: String) -> void:
	var err := HeritageSystem.resolve(her_id, choice)
	if err != "":
		GameState.note(err)


func _open_pending() -> void:
	var e := []
	for id in HeritageSystem.pending():
		e.append({"text": DataDB.display_name(String(id)), "cb": _heritage_choice.bind(String(id))})
	open_menu("보상 선택 대기 유산", e)


# ================================================================ 필드 미니게임
func _play_field_mg(mg_id: String, cb: Callable) -> void:
	var mg := MinigameBase.create_from_catalog(mg_id)
	if mg == null:
		cb.call(true)
		return
	menu.hide()
	mg_host.mouse_filter = Control.MOUSE_FILTER_STOP
	mg_host.add_child(mg)
	mg.finished.connect(_on_field_mg_done.bind(cb))


func _on_field_mg_done(ok: bool, cb: Callable) -> void:
	mg_host.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cb.call(ok)


func _do_takbon() -> void:
	var err := SideSystems.takbon_can()
	if err != "":
		GameState.note(err)
		return
	var mg := MinigameBase.create_from_catalog("mg_takbon")
	if mg == null:
		return
	mg.params = mg.params.duplicate()
	mg.params["sheet"] = int(SideSystems.takbon_sheets_here()[0])
	menu.hide()
	mg_host.mouse_filter = Control.MOUSE_FILTER_STOP
	mg_host.add_child(mg)
	mg.finished.connect(_on_field_mg_done.bind(func(ok): SideSystems.takbon_done(ok)))


# ================================================================ 상점·무역·뱃길·쾌속
func _open_shop() -> void:
	var e := []
	for s in TradeSystem.shop_list():
		e.append({"text": "%s — %d냥 (재고 %d)" % [s["name"], int(s["price"]), int(s["stock"])], "hint": String(s["lock"]),
			"disabled": s["lock"] != "" or GameState.money < int(s["price"]), "cb": func(): TradeSystem.buy(s), "keep": true})
	open_menu("%s 상점 (보유 %d냥)" % [DataDB.display_name(GameState.current_node), GameState.money], e)


func _open_sell() -> void:
	var e := []
	var worn := GameState.equipped.values() + GameState.life_gear.values()
	for id in GameState.inventory.keys():
		if id in worn:
			continue
		var sid := String(id)
		var fresh := " · 신선도 %d%%" % int(GameState.freshness[sid]) if GameState.freshness.has(sid) else ""
		e.append({"text": "%s ×%d%s" % [DataDB.display_name(sid), GameState.count(sid), fresh], "hint": _sell_hint(sid), "cb": _sell_one.bind(sid), "keep": true})
	var sat: Dictionary = DataDB.overview.get("trade", {}).get("sell_saturation", {})
	var head := "매각 (%s 시세)" % DataDB.display_name(GameState.current_region)
	if not sat.is_empty():
		e.push_front({"text": "장터 포화: 같은 특산물을 이 장터에서 이번 장(5일)에 팔수록 개당 −%d%% (최저 %d%%). 포화가 크면 다른 장터에 나눠 파세요." % [int(float(sat.get("per_unit", 0.02)) * 100), int(float(sat.get("floor", 0.6)) * 100)]})
	open_menu(head, e)


## "개당 120냥 · 포화 −8% (4개 판매) · 10개 더 팔면 −28%" / 계절 교역 표시
func _sell_hint(sid: String) -> String:
	var h := "개당 %d냥" % TradeSystem.sell_price(sid)
	if DataDB.sheet_of(sid) != "03_specialties.json:specialties":
		return h
	var sm := TradeSystem.saturation_mult(sid)
	if sm < 0.999:
		h += " · 이 장터 포화 −%d%%" % int(round((1.0 - sm) * 100))
	var more := mini(GameState.count(sid), 10)
	if more > 1:
		h += " · %d개 더 팔면 −%d%%" % [more, int(round((1.0 - TradeSystem.saturation_mult(sid, more)) * 100))]
	var season := TradeSystem.seasonal_mult(sid)
	if season > 1.001:
		h += " · 계절 교역 ×%.2f" % season
	return h


func _sell_one(sid: String) -> void:
	TradeSystem.sell(sid)
	_open_sell()


func _open_trade() -> void:
	var e := []
	for q in TradeSystem.trade_quests_here():
		var st := TradeSystem.quest_state(q)
		var terms := "위탁 운임 %d%% · 짐은 화주 제공(매 장 반복)" % int(float(q.get("margin", 0.3)) * 100) if q.get("consign", false) else "대금 %.1f배 + 명성" % float(q.get("margin", 1.8))
		if String(q.get("reward_item", "")) != "":
			terms += " + " + DataDB.display_name(String(q["reward_item"]))
		var desc := "%s: %s ×%d  %s → %s (%s)" % [q["name"], DataDB.display_name(String(q["item"])), int(q["qty"]), DataDB.display_name(String(q["from"])), DataDB.display_name(String(q["to"])), terms]
		if st == "":
			e.append({"text": desc, "hint": "수락", "cb": func(): TradeSystem.accept_trade(q)})
		elif st == "accepted":
			e.append({"text": desc, "hint": "납품", "cb": func(): TradeSystem.deliver_trade(q)})
	for b in DataDB.overview.get("trade", {}).get("seasonal_sell_bonus", []):
		e.append({"text": "계절 교역: %s — %s 매도가 ×%.2f" % [b["name"], DataDB.display_name(String(b["region"])), float(b["mult"])]})
	e.append({"text": "쌀 시세: %s %d냥 — 삼남(35냥)에서 사서 북방(80냥)에 팔면 차익. 1섬 무게 20" % [DataDB.display_name(GameState.current_region), Balance.regional_rice_price(GameState.current_region)]})
	open_menu("무역", e)


func _open_ferry() -> void:
	var e := []
	for leg in DataDB.neighbors(GameState.current_node):
		if String(leg["kind"]) == "ferry":
			var to := String(leg["to"])
			e.append({"text": "%s 행 (%d일 · %d냥%s)" % [DataDB.display_name(to), int(leg.get("days", 1)), int(leg.get("fare", 0)), " · 풍향 영향" if leg.get("wind", false) else ""], "cb": _start_travel.bind(to)})
	open_menu("나루터 뱃길", e)


func _open_fast_travel() -> void:
	var e := []
	for n in DataDB.nodes_in(GameState.current_region) + DataDB.nodes().filter(func(x): return x["region"] in DataDB.adjacent(GameState.current_region)):
		if "yeokcham" in n.get("facilities", []) and n["id"] != GameState.current_node:
			e.append({"text": "%s (%s)" % [n["name"], DataDB.display_name(String(n["region"]))], "cb": _fast_travel.bind(String(n["id"]))})
	open_menu("역참 쾌속 이동 (현 권역·인접 권역)", e)


# ================================================================ 배낭·장착·도감·지식
func _open_bag() -> void:
	var gs := GameState
	var e := [{"text": "무게 %.1f / %.0f · 엽전 %d냥 · 포만 %d · 자동 섭취 %s" % [gs.carry_weight(), gs.carry_capacity(), gs.money, int(gs.satiety), "켜짐" if gs.auto_eat else "꺼짐"]},
		{"text": "자동 섭취 전환", "cb": _toggle_auto_eat}]
	var ids := gs.inventory.keys()
	ids.sort_custom(func(a, b): return int(DataDB.get_row(a).get("tier", 1)) > int(DataDB.get_row(b).get("tier", 1)))
	for id in ids:
		var r := DataDB.get_row(id)
		var sid := String(id)
		var tail := ""
		if gs.freshness.has(sid):
			tail += " · 신선도 %d%%" % int(gs.freshness[sid])
		var usable := r.has("effect") or r.has("satiety")
		e.append({"text": "[%d등급] %s ×%d%s" % [int(r.get("tier", 1)), r.get("name", sid), gs.count(sid), tail], "hint": "사용" if usable else "무게 %.1f" % gs.item_weight(sid),
			"disabled": not usable, "cb": func(): CraftingSystem.use_consumable(sid)})
	open_menu("배낭", e)


func _toggle_auto_eat() -> void:
	GameState.auto_eat = not GameState.auto_eat
	_open_bag()


func _open_equip() -> void:
	var gs := GameState
	var ko := {"weapon": "무기", "armor": "갑주", "shoes": "신발", "mount": "탈것", "acc1": "장신구1", "acc2": "장신구2", "acc3": "장신구3", "nav": "행장·지남", "carry": "행장·운반", "camp": "행장·야영", "record": "행장·답사록"}
	var e := []
	for slot in GameState.EQUIP_SLOTS + GameState.LIFE_SLOTS:
		var cur := String(gs.equipped.get(slot, gs.life_gear.get(slot, "")))
		e.append({"text": "%s: %s" % [ko[slot], DataDB.display_name(cur) if cur != "" else "(비어 있음)"], "hint": ("기력 %d" % int(gs.mount_stamina)) if slot == "mount" and cur != "" else "", "cb": _equip_slot.bind(slot), "keep": true})
	e.append({"text": "── 동료 3인 카드: " + ", ".join(PackedStringArray(gs.party.map(func(c): return "%s★%d" % [DataDB.display_name(String(c)), int(gs.companions.get(c, {}).get("star", 1))])))})
	open_menu("장착 (5슬롯 + 장신구 3 + 행장 4)", e)


func _equip_slot(slot: String) -> void:
	var gs := GameState
	var e := [{"text": "해제", "cb": _do_unequip.bind(slot)}]
	for id in gs.inventory.keys():
		var sid := String(id)
		var r := DataDB.get_row(sid)
		var s := gs.slot_for(sid)
		var fits := (s == slot) or (slot in GameState.ACC_SLOTS and String(r.get("slot", "")) in ["accessory", "book"])
		if not fits:
			continue
		var err := gs.can_equip(sid, slot)
		e.append({"text": String(r["name"]), "hint": err if err != "" else JSON.stringify(r.get("stats", r.get("buffs", {"v_mount": r.get("v_mount", 0)}))), "disabled": err != "", "cb": _do_equip.bind(sid, slot)})
	open_menu("장착 — " + slot, e)


func _do_unequip(slot: String) -> void:
	GameState.unequip(slot)
	_open_equip()


func _do_equip(id: String, slot: String) -> void:
	GameState.equip(id, slot)
	_open_equip()


func _open_codex() -> void:
	var gs := GameState
	var e := []
	for cat in ["역사", "설화", "창작", "물산"]:
		var ids := gs.codex.keys().filter(func(k): return gs.codex[k]["cat"] == cat)
		e.append({"text": "▣ [%s] %d건" % [cat, ids.size()]})
		for id in ids:
			var r := DataDB.get_row(String(id))
			if cat == "물산":  # 상품/진상품 등 — 실제 명칭과 설명
				e.append({"text": "   %s (%d등급) — %s: %s" % [r.get("name", id), int(r.get("tier", 1)), r.get("real_name", ""), r.get("desc", "")]})
				continue
			var pd: Dictionary = r.get("public_data", {})
			var src := ""
			if not pd.is_empty():
				src = " — 출처: %s (%s) %s" % [pd.get("provider", ""), pd.get("license", ""), pd.get("source_url", "")]
			e.append({"text": "   %s%s" % [r.get("name", id), src]})
	for p in DataDB.overview.get("provinces", []):
		var lv := int(gs.town_dev.get(String(p["capital"]), 0))
		e.append({"text": "【%s】 도 명성 %d · 감영 발전 %d/5 (다음 요건 %d)" % [p["name"], int(gs.province_rep.get(p["id"], 0)), lv, Balance.standing_required(p, mini(lv + 1, 5))]})
	e.append({"text": "화첩 %d장 · 탁본 %d/22첩 · 발견 은닉지 %d곳" % [gs.hwacheop.size(), gs.takbon.keys().filter(func(k): return k != "_complete").size(), gs.discovered.size()]})
	open_menu("도감 (역사·설화·창작 / 국가유산청 공공누리 제1유형)", e)


func _open_knowledge() -> void:
	var gs := GameState
	var names: Dictionary = DataDB.classes_doc.get("knowledge", {}).get("names", {})
	var pk := gs.party_knowledge()
	var e := [{"text": "지식 랭크(본인 / 파티 합산) — 학식은 유>불>선>유 상성 대미지 +8%/랭크, 생활 지식은 필드 효과"}]
	for k in GameState.KNOWLEDGE_KEYS:
		var r := int(gs.knowledge.get(k, 0))
		e.append({"text": "%s: %d / %d  (XP %d/%d)" % [names.get(k, k), r, int(pk.get(k, 0)), int(gs.knowledge_xp.get(k, 0)), Balance.knowledge_xp_to_next(maxi(1, r))]})
	for p in DataDB.classes_doc.get("four_passives", []):
		e.append({"text": "사농공상 패시브 「%s」 %s" % [p["name"], "✔ 활성" if gs.has_life_passive(String(p["id"])) else "(조건 %s)" % JSON.stringify(p["req"])]})
	var cp := DataDB.class_row(gs.class_id).get("passive", {})
	e.append({"text": "클래스 패시브 「%s」" % cp.get("name", "")})
	open_menu("지식", e)


# ================================================================ 퀘스트·이벤트·수배·제작·동료
func _open_quests() -> void:
	var gs := GameState
	var e := [{"text": "▣ 진행 중"}]
	for qid in gs.active_quests.keys():
		var q: Dictionary = gs.active_quests[qid]
		if q.get("ready", false):
			var here := DataDB.node_of(RouteQueue.current_target(qid)) == gs.current_node
			e.append({"text": "⚔ 결전: %s" % q["name"], "disabled": not here, "hint": "" if here else "결전지로 이동", "cb": _start_instance.bind(String(q["reward"]["instance"]), String(qid))})
		else:
			e.append({"text": "%s — 다음: %s" % [q["name"], DataDB.display_name(RouteQueue.current_target(qid))], "hint": "포기(패자부활)", "cb": _abandon_quest.bind(String(qid))})
	e.append({"text": "▣ 수락 가능 (동선 큐 2~5노드 규칙 검증)"})
	for q2 in RouteQueue.available_quests():
		if gs.active_quests.has(q2["id"]) or q2["id"] in gs.completed_quests:
			continue
		var lock := RouteQueue.lock_reason(q2)
		e.append({"text": "[%d등급] %s" % [int(q2["tier"]), q2["name"]], "hint": lock if lock != "" else RouteQueue.describe(q2["route"]),
			"disabled": lock != "", "cb": func(): RouteQueue.start_quest(q2)})
	open_menu("퀘스트", e)


func _abandon_quest(qid: String) -> void:
	RouteQueue.fail_quest(qid)


func _event_choice(eid: String, choice: String) -> void:
	EventSystem.resolve_stage(eid, {"ok": true, "choice": choice})


func _open_events() -> void:
	var gs := GameState
	var e := []
	for eid in gs.events_state.keys():
		var st: Dictionary = gs.events_state[eid]
		var d := EventSystem.definition(eid)
		var status := String(st.get("status", ""))
		var left := ""
		if status == "active" and int(d.get("deadline_days", 0)) > 0:
			left = " · 기한 %d일" % (int(d["deadline_days"]) - (gs.day() - int(st.get("started", gs.day()))))
		e.append({"text": "%s [%s]%s" % [d.get("name", DataDB.display_name(eid)), {"active": "진행", "done": "완료", "resolved_by_court": "관군 수습"}.get(status, status), left],
			"hint": EventSystem.stage_text(eid) if status == "active" else ""})
	open_menu("이벤트·시나리오", e)


func _event_stage(eid: String) -> void:
	var s := EventSystem.current_stage(eid)
	match String(s.get("action", "talk")):
		"talk":
			EventSystem.resolve_stage(eid, {"ok": true})
		"choice":
			var e := [{"text": String(s.get("text", ""))}]
			for c in s.get("choices", []):
				e.append({"text": String(c["text"]), "cb": _event_choice.bind(eid, String(c["id"]))})
			open_menu(EventSystem.definition(eid)["name"], e)
		"minigame":
			_play_field_mg(String(s["minigame"]), func(ok): EventSystem.resolve_stage(eid, {"ok": ok}))
		"deliver":
			var ok := GameState.remove_item(String(s["item"]), int(s.get("qty", 1)))
			if not ok:
				GameState.note("필요 물품: %s ×%d" % [DataDB.display_name(String(s["item"])), int(s.get("qty", 1))])
			EventSystem.resolve_stage(eid, {"ok": ok})
		"battle":
			_begin_battle({"id": "ev_" + eid, "name": EventSystem.definition(eid)["name"], "waves": s["waves"], "event": eid}, "")
		"instance":
			var inst := DataDB.get_row(String(s["instance"]))
			var row := inst.duplicate()
			row["event"] = eid
			_begin_battle(row, "")


func _open_bounties() -> void:
	var gs := GameState
	if gs.bounties.is_empty():
		SideSystems.refresh_bounties()
	var n := SideSystems.claim_bounties()
	var e := [{"text": "현상수배지 (%d일마다 갱신) — 수령 %d건" % [int(DataDB.side_doc.get("bounty", {}).get("refresh_days", 5)), n]}]
	for b in gs.bounties:
		e.append({"text": "%s ×%d (%d/%d) — 명성 %d · %d냥 · ~%d일" % [DataDB.display_name(String(b["enemy"])), int(b["count"]), int(b["killed"]), int(b["count"]), int(b["rep"]), int(b["money"]), int(b["expire"])]})
	open_menu("포도청 현상수배", e)


const SUB_MODE_KO := {"off": "끔(정확한 재료만)", "confirm": "확인(2등급 이상 높은 재료는 묻기)", "auto": "자동"}


func _open_craft() -> void:
	var e := [{"text": "비전서 %d권 등록 — 비전서 없이는 제작 불가. [모작]은 전국 어디서나 야외 단조. 공 지식 재료 −%d%%" % [GameState.owned_books().size(), int(-GameState.life_effect("gong", "craft_material") * 100)]},
		{"text": "상위 재료 대체: " + String(SUB_MODE_KO.get(GameState.substitute_mode, GameState.substitute_mode)), "hint": "눌러서 전환", "cb": _cycle_sub_mode, "keep": true}]
	for card in CraftingSystem.known_recipes():
		var err := CraftingSystem.check(card)
		e.append({"text": "[%s] %s" % [card["kind"], card["name"]], "hint": err if err != "" else CraftingSystem.materials_text(card.get("materials", [])),
			"disabled": err != "", "cb": _craft.bind(card)})
	open_menu("제작", e)


func _cycle_sub_mode() -> void:
	var order := ["confirm", "auto", "off"]
	GameState.substitute_mode = order[(order.find(GameState.substitute_mode) + 1) % order.size()]
	_open_craft()


## 상위 재료 대체 확인(설정 '확인' + 요구보다 2등급 이상 높은 재료 사용 시)
func _craft(card: Dictionary) -> void:
	var plan := GameState.material_plan(card.get("materials", []), 1.0 if card["kind"] == "unpack" else CraftingSystem.material_mult())
	if CraftingSystem.check(card) == "" and GameState.needs_substitute_confirm(plan):
		var e := [{"text": "%s — 상위 등급 재료가 대신 쓰입니다." % card["name"]}]
		for su in plan["subs"]:
			e.append({"text": "   %s ×%d → %s 대신 (+%d등급)" % [DataDB.display_name(String(su["used"])), int(su["qty"]), su["need"], int(su["gap"])]})
		e.append({"text": "그대로 제작", "cb": _craft_go.bind(card)})
		e.append({"text": "취소", "cb": _open_craft, "keep": true})
		open_menu("상위 재료 대체 확인", e)
		menu.show()
		return
	_craft_go(card)


func _craft_go(card: Dictionary) -> void:
	if card.has("minigame"):
		var mg := MinigameBase.create_from_catalog(String(card["minigame"]))
		if mg:
			menu.hide()
			mg_host.mouse_filter = Control.MOUSE_FILTER_STOP
			mg_host.add_child(mg)
			mg.finished.connect(_on_field_mg_done.bind(_craft_done.bind(card)))
			return
	CraftingSystem.craft(card)


func _craft_done(ok: bool, card: Dictionary) -> void:
	CraftingSystem.craft(card, 1.0 if ok else 0.0)


func _party_cmd(kind: String, cid: String, arg: String) -> void:
	var err := ""
	match kind:
		"barracks": err = CompanionSystem.to_barracks(cid)
		"party": err = CompanionSystem.to_party(cid)
		"dispatch": err = CompanionSystem.send_dispatch(cid, arg)
	if err != "":
		GameState.note(err)
	_open_party()


func _open_party() -> void:
	var gs := GameState
	var here := CompanionSystem.can_use_barracks()
	var e := [{"text": "파티 %d/3 · 막사 %d/%d슬롯 %s" % [gs.party.size(), gs.barracks.size(), CompanionSystem.barracks_slots(), "" if here else "(막사 조작은 객주·주막에서)"]},
		{"text": "동료 기여: 스킬을 주인공에게 합산(동료당 AP 상한·충전 +1) · 지식 합산 · 짐 무게 +%d (스탯 합산 없음)" % int(gs.companion_carry())}]
	for cid in gs.party:
		var c := String(cid)
		var cb_ := DataDB.get_row(c).get("carry_bonus", DataDB.get_row(c).get("capture_profile", {}).get("companion_bonuses", {}).get("carry", 0))
		var ct := CompanionSystem.tier_of(c)
		var nq := CompanionSystem.next_promotion(c)
		var nxt := "최고 등급" if nq.is_empty() else "다음 승급: %s (%s)" % [String(nq["name"]), CompanionSystem.promotion_lock(c, nq) if CompanionSystem.promotion_lock(c, nq) != "" else "수락 가능 — 퀘스트 메뉴"]
		e.append({"text": "%d등급 ★%d %s — 동행 (숙련 ×%.2f · 일급 %d냥 · 짐 +%d)" % [ct, int(gs.companions.get(c, {}).get("star", 1)), DataDB.display_name(c),
			Balance.companion_skill_mult(ct, int(gs.companions.get(c, {}).get("star", 1))), Balance.wage_per_day(ct), int(cb_)],
			"hint": "막사로", "disabled": not here, "cb": _party_cmd.bind("barracks", c, "")})
		e.append({"text": "      └ 지식 %s · %s" % [str(CompanionSystem.knowledge_of(c)), nxt], "disabled": true})
	for cid in gs.barracks:
		var c2 := String(cid)
		var dp: Dictionary = gs.dispatch.get(c2, {})
		e.append({"text": "%d등급 ★%d %s — 막사 대기%s (비용 0)" % [CompanionSystem.tier_of(c2), int(gs.companions.get(c2, {}).get("star", 1)), DataDB.display_name(c2), " · 파견: " + String(DataDB.overview.get("barracks", {}).get("dispatch", {}).get(String(dp.get("type", "")), {}).get("name", "")) if not dp.is_empty() else ""],
			"hint": "동행", "disabled": not here, "cb": _party_cmd.bind("party", c2, "")})
		for dt in DataDB.overview.get("barracks", {}).get("dispatch", {}).keys():
			e.append({"text": "      └ %s 파견" % DataDB.overview["barracks"]["dispatch"][dt]["name"], "disabled": not here, "cb": _party_cmd.bind("dispatch", c2, String(dt))})
	open_menu("동료·객주 막사", e)


# ================================================================ 전투
func _start_instance(inst_id: String, qid: String) -> void:
	var inst := DataDB.get_row(inst_id)
	if not inst.is_empty():
		_begin_battle(inst, qid)


func _begin_battle(inst: Dictionary, qid: String) -> void:
	menu.hide()
	map_modal.close()
	in_battle = true
	field.hide()
	battle.show()
	dash.set_enabled(false)
	GameState.note("전투 개시: %s" % inst.get("name", ""))
	battle.start(inst, qid)


func _on_battle_finished(result: String, summary: Dictionary) -> void:
	var gs := GameState
	in_battle = false
	battle.hide()
	field.show()
	dash.set_enabled(true)
	gs.tick_battle_buffs()
	var inst := battle.instance
	match result:
		"victory":
			gs.add_money(int(summary["money"]))
			var rep := gs.add_reputation(int(summary["reputation"]), gs.current_region, true)  # 일반 처치 = 반복 원천
			rep += gs.add_reputation(int(summary.get("rep_boss", 0)), gs.current_region)     # 보스 = 1회성, 도 명성 적립
			gs.note("전투 보상: 명성 +%d · 엽전 +%d냥" % [rep, int(summary["money"])])
			gs.bump("battle_win")
			for k in summary["killed"]:
				SideSystems.on_kill(String(k))
			for d in summary["drops"]:
				gs.add_item(String(d))
				gs.note("전리품: %s" % DataDB.display_name(String(d)))
			if battle.quest_id != "":
				RouteQueue.complete_external(battle.quest_id)
			if inst.has("event"):
				EventSystem.resolve_stage(String(inst["event"]), {"ok": true})
			if inst.get("resume_travel", false):
				traveler.resume()
		"defeat":
			SurvivalSystem.rescue_to_inn()
			if inst.has("event"):
				EventSystem.resolve_stage(String(inst["event"]), {"ok": false})
		_:
			gs.note("전장에서 이탈했습니다.")
			if inst.get("resume_travel", false):
				traveler.resume()
	gs.stats_changed.emit()



# ================================================================ 튜토리얼 안내 창 (23 시트 · TutorialSystem)
func _build_tutorial_panel() -> void:
	tut_panel = PanelContainer.new()
	tut_panel.position = Vector2(1480, 24)
	tut_panel.custom_minimum_size = Vector2(420, 0)
	tut_panel.add_theme_stylebox_override("panel", Assets.panel_style("modal", Color(0.14, 0.1, 0.06, 0.94), Color(0.85, 0.68, 0.35)))
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	tut_panel.add_child(v)
	tut_title = Label.new()
	tut_title.add_theme_color_override("font_color", Color(1, 0.85, 0.5))
	Assets.title(tut_title, 24)
	v.add_child(tut_title)
	tut_body = Label.new()
	tut_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tut_body.custom_minimum_size = Vector2(400, 0)
	tut_body.add_theme_font_size_override("font_size", 16)
	tut_body.add_theme_color_override("font_color", Color(0.98, 0.94, 0.85))
	v.add_child(tut_body)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 6)
	v.add_child(h)
	tut_next = Button.new()
	tut_next.text = "다음 ▶"
	tut_next.pressed.connect(_tut_next_pressed)
	h.add_child(tut_next)
	var hb := Button.new()
	hb.text = "도움말"
	hb.pressed.connect(_open_help)
	h.add_child(hb)
	var sk := Button.new()
	sk.text = "건너뛰기"
	sk.pressed.connect(_tut_skip_pressed)
	h.add_child(sk)
	overlay.add_child(tut_panel)
	tut_panel.hide()


func _tut_next_pressed() -> void:
	TutorialSystem.advance()
	_refresh_tutorial()


func _tut_skip_pressed() -> void:
	TutorialSystem.skip_all()
	_refresh_tutorial()


func _refresh_tutorial() -> void:
	if tut_panel == null:
		return
	TutorialSystem.check()
	var st := TutorialSystem.current()
	if st.is_empty() or not bool(Settings.get_value("tutorial")):
		tut_panel.hide()
		return
	tut_title.text = "안내 %s · %s" % [TutorialSystem.progress_text(), st.get("title", "")]
	tut_body.text = "%s\n\n▶ %s" % [st.get("text", ""), st.get("hint", "")]
	tut_next.visible = String(st.get("cond", {}).get("type", "")) == "ack"
	tut_panel.show()
	tut_panel.move_to_front()


# ================================================================ 도움말 (23 시트 help)
func _open_help(from_title := false) -> void:
	var e := [{"text": "시스템 설명 — 항목을 누르면 자세히 봅니다."}]
	for h in DataDB.table("23_tutorial.json", "help"):
		e.append({"text": "▸ " + String(h["title"]), "cb": _show_help.bind(String(h["id"]), from_title), "keep": true})
	if GameState.tutorial_id != "":
		e.append({"text": "튜토리얼 처음부터 다시 보기", "cb": _tutorial_restart})
	if from_title:
		e.append({"text": "← 시작 화면", "cb": _title_screen, "keep": true})
	open_menu("도움말", e)


func _show_help(hid: String, from_title := false) -> void:
	var h := DataDB.get_row(hid)
	open_menu("도움말 — " + String(h.get("title", "")), [{"text": String(h.get("text", ""))},
		{"text": "← 도움말 목록", "cb": _open_help.bind(from_title), "keep": true}])


# ================================================================ 설정 (Settings 자동 로드, user://settings.json)
func _open_settings(from_title := false) -> void:
	var e := [{"text": "설정은 게임 저장과 따로 보관됩니다. 항목을 누를 때마다 값이 바뀝니다."}]
	for o in Settings.OPTIONS:
		var key := String(o[0])
		e.append({"text": "%s: %s" % [o[1], Settings.label(key)], "hint": String(o[3]), "cb": _cycle_setting.bind(key, from_title), "keep": true})
	if not from_title:
		e.append({"text": "이번 게임 — 자동 섭취: %s · 상위 재료 대체: %s" % ["켜짐" if GameState.auto_eat else "꺼짐", SUB_MODE_KO.get(GameState.substitute_mode, "")]})
	e.append({"text": "기본값으로 되돌리기", "cb": _settings_reset.bind(from_title), "keep": true})
	e.append({"text": "← 시작 화면" if from_title else "닫기", "cb": _title_screen if from_title else _close_menu, "keep": from_title})
	open_menu("설정", e)


func _settings_reset(from_title: bool) -> void:
	Settings.reset()
	_open_settings(from_title)


func _tutorial_restart() -> void:
	TutorialSystem.restart()
	Settings.set_value("tutorial", true)
	_refresh_tutorial()


func _cycle_setting(key: String, from_title: bool) -> void:
	Settings.cycle(key)
	_open_settings(from_title)
