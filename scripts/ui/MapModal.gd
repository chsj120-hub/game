class_name MapModal
extends Control
## 대동여지도 인터랙티브 모달 (완전판 1.2)
##  · 마우스 휠 100~300% 줌(커서 기준) + 좌클릭 드래그 팬
##  · 거점 자석 흡착: 커서가 노드 반경 3.8%(화면 폭 기준) 이내면 가장 가까운 노드로 깃발 흡착
##  · 목적지 지정 시 주황 펄스 점선 경로 + 예상 행군 거리(리)·소요 시간·뱃삯 표시 → [행군 시작]
##  · [전국 지도] 토글: 17권역 조망, 권역 클릭 시 그 권역 대표 거점(hub)을 목적지로
## 닫혀 있을 때 visible=false · process_mode=DISABLED (완전판 11.3)

signal travel_requested(dest: String)
signal fast_travel_requested(dest: String)

var traveler: TravelController
var font: Font
var zoom := 1.0
var pan := Vector2.ZERO
var dragging := false
var drag_moved := 0.0
var snap_node := ""
var dest := ""
var path: Array = []
var overworld := false
var t := 0.0
var region_view := ""
var buttons: HBoxContainer
var info: Label


func _ready() -> void:
	font = (Assets.font_ui if Assets.font_ui else ThemeDB.fallback_font)
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	buttons = HBoxContainer.new()
	buttons.position = Vector2(20, 1020)
	buttons.add_theme_constant_override("separation", 10)
	add_child(buttons)
	info = Label.new()
	info.position = Vector2(20, 975)
	info.add_theme_font_size_override("font_size", 22)
	add_child(info)
	_btn("행군 시작 ▶", _go)
	_btn("역참 쾌속 이동", _fast)
	_btn("전국 지도 ↔ 권역 지도", _toggle_ow)
	_btn("현 위치로", _center_here)
	_btn("닫기 (M)", close)
	close()


func _btn(text: String, cb: Callable) -> void:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(200, 44)
	b.add_theme_font_size_override("font_size", 18)
	b.pressed.connect(cb)
	buttons.add_child(b)


func open() -> void:
	visible = true
	process_mode = Node.PROCESS_MODE_INHERIT
	region_view = GameState.current_region
	_center_here()
	move_to_front()


func close() -> void:
	visible = false
	process_mode = Node.PROCESS_MODE_DISABLED


func _map_size() -> Vector2:
	var ms: Array = DataDB.docs.get("regions.json", {}).get("map_size", [3840, 2160])
	return Vector2(float(ms[0]), float(ms[1]))


func _base_scale() -> float:
	var ms := _map_size()
	return minf(size.x / ms.x, (size.y - 120) / ms.y)


func _to_screen(p: Vector2) -> Vector2:
	return p * _base_scale() * zoom + pan


func _to_map(s: Vector2) -> Vector2:
	return (s - pan) / (_base_scale() * zoom)


func _ow_screen(region_id: String) -> Vector2:
	var p: Array = DataDB.get_row(region_id).get("overworld_pos", [0.5, 0.5])
	var h := size.y - 140
	return Vector2(size.x / 2.0 - h * 0.35 + float(p[0]) * h * 0.7, 20 + float(p[1]) * h)


func _center_here() -> void:
	zoom = 1.0
	region_view = GameState.current_region
	var here := traveler.pos if traveler and traveler.moving else DataDB.node_pos(GameState.current_node)
	pan = size / 2.0 - here * _base_scale() * zoom
	pan.y = minf(pan.y, 20)


func _toggle_ow() -> void:
	overworld = not overworld


func _visible_nodes() -> Array:
	return DataDB.nodes_in(region_view).filter(func(n): return GameState.node_visible(n["id"]))


func _process(delta: float) -> void:
	t += delta
	queue_redraw()


func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton:
		if ev.button_index == MOUSE_BUTTON_WHEEL_UP or ev.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			var z: Array = DataDB.overview.get("movement", {}).get("zoom", [1.0, 3.0])
			var before := _to_map(ev.position)
			zoom = clampf(zoom * (1.1 if ev.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 1.1), float(z[0]), float(z[1]))
			pan = ev.position - before * _base_scale() * zoom
			accept_event()
		elif ev.button_index == MOUSE_BUTTON_LEFT:
			if ev.pressed:
				dragging = true
				drag_moved = 0.0
			else:
				dragging = false
				if drag_moved < 8.0:
					_click(ev.position)
			accept_event()
	elif ev is InputEventMouseMotion:
		if dragging and not overworld:
			pan += ev.relative
			drag_moved += ev.relative.length()
		_update_snap(ev.position)


func _update_snap(mp: Vector2) -> void:
	snap_node = ""
	if overworld:
		return
	var r := float(DataDB.overview.get("movement", {}).get("snap_radius_ratio", 0.038)) * size.x
	var best := r
	for n in _visible_nodes():
		var d := _to_screen(DataDB.node_pos(n["id"])).distance_to(mp)
		if d <= best:
			best = d
			snap_node = n["id"]


func _click(mp: Vector2) -> void:
	if overworld:
		for r in DataDB.regions():
			if _ow_screen(r["id"]).distance_to(mp) < 22:
				region_view = String(r["id"])
				overworld = false
				_select(String(r["hub"]))
				_center_on(String(r["hub"]))
				return
		return
	if snap_node != "":
		_select(snap_node)


func _center_on(nid: String) -> void:
	pan = size / 2.0 - DataDB.node_pos(nid) * _base_scale() * zoom


func _select(nid: String) -> void:
	dest = nid
	path = TravelSystem.find_path(GameState.current_node, dest)
	if path.is_empty() and dest != GameState.current_node:
		info.text = "%s — 경로 없음 (미발견 노드·수로(선박 필요)·봉쇄·검문 확인)" % DataDB.display_name(dest)
		return
	var li := TravelSystem.path_li(path)
	var fare := TravelSystem.path_fare(path)
	var eta := TravelSystem.eta_minutes(path)
	info.text = "목적지 %s │ 예상 행군 %.0f리 │ 소요 약 %d시간 %d분 │ 뱃삯 %d냥 │ 노드 %d곳 경유" % [DataDB.display_name(dest), li, eta / 60, eta % 60, fare, path.size()]


func _go() -> void:
	if dest == "" or path.is_empty():
		return
	travel_requested.emit(dest)
	close()


func _fast() -> void:
	if dest == "":
		return
	fast_travel_requested.emit(dest)
	close()


func _unhandled_key_input(ev: InputEvent) -> void:
	if visible and ev.pressed and (ev.keycode == KEY_M or ev.keycode == KEY_ESCAPE):
		close()
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------ 그리기
func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.08, 0.06, 0.04, 0.96))
	if overworld:
		_draw_overworld()
	else:
		_draw_region()
	draw_rect(Rect2(0, 960, size.x, 120), Color(0.1, 0.07, 0.04, 0.95))


func _draw_overworld() -> void:
	var ow := Assets.overworld()
	if ow:
		var h := size.y - 140
		draw_texture_rect(ow, Rect2(size.x / 2.0 - h * 0.35, 20, h * 0.7, h), false)
	for r in DataDB.regions():
		for nb in r["adjacent"]:
			if String(r["id"]) < String(nb):
				draw_line(_ow_screen(r["id"]), _ow_screen(nb), Color(0.6, 0.45, 0.3), 2)
	for r in DataDB.regions():
		var p := _ow_screen(r["id"])
		var cur: bool = r["id"] == GameState.current_region
		draw_circle(p, 16, Color(0.85, 0.2, 0.15) if cur else Color(0.3, 0.22, 0.15))
		draw_string(font, p + Vector2(20, 7), "%s (쌀 %d냥)" % [r["name"], int(r["rice_price"])], HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(1, 0.9, 0.7))
	draw_string(font, Vector2(30, 40), "전국 지도 — 권역을 클릭하면 그 권역 대표 거점으로 경로를 잡습니다", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color.WHITE)


func _draw_region() -> void:
	var ms := _map_size()
	var tl := _to_screen(Vector2.ZERO)
	var br := _to_screen(ms)
	var tex := Assets.region_map(region_view)
	if tex:
		draw_texture_rect(tex, Rect2(tl, br - tl), false)
	else:
		draw_rect(Rect2(tl, br - tl), Color(0.9, 0.85, 0.72))
		for i in range(1, 20):  # 방안(10리 눈금 = 200px)
			var gx := tl.x + (br.x - tl.x) * i / 19.2
			var gy := tl.y + (br.y - tl.y) * i / 10.8
			draw_line(Vector2(gx, tl.y), Vector2(gx, br.y), Color(0.6, 0.5, 0.35, 0.18))
			if i < 11:
				draw_line(Vector2(tl.x, gy), Vector2(br.x, gy), Color(0.6, 0.5, 0.35, 0.18))
	var vis := {}
	for n in _visible_nodes():
		vis[n["id"]] = n
	for e in DataDB.edges_in(region_view):  # 권역 색인(전체 900여 간선을 매 프레임 훑지 않음)
		if vis.has(e["a"]) and vis.has(e["b"]):
			var col := {"road": Color(0.15, 0.1, 0.05), "mountain": Color(0.35, 0.25, 0.1), "water": Color(0.2, 0.35, 0.7), "trail": Color(0.4, 0.3, 0.2)}.get(String(e["terrain"]), Color.BLACK)
			draw_line(_to_screen(DataDB.node_pos(e["a"])), _to_screen(DataDB.node_pos(e["b"])), col, 3.0 if e["terrain"] == "road" else 2.0)
	# 경로 미리보기: 주황 펄스 점선
	var pulse := 0.6 + 0.4 * sin(t * 5.0)
	for leg in path:
		if DataDB.region_of_node(String(leg["from"])) != region_view and DataDB.region_of_node(String(leg["to"])) != region_view:
			continue
		var a := _to_screen(DataDB.node_pos(String(leg["from"])))
		var b := _to_screen(DataDB.node_pos(String(leg["to"])))
		if DataDB.region_of_node(String(leg["from"])) != DataDB.region_of_node(String(leg["to"])):
			b = a + (b - a).normalized() * 60.0
		_dashed(a, b, Color(1.0, 0.55, 0.1, pulse), 6.0, fmod(t * 60.0, 24.0))
	var targets := []
	for qid in GameState.active_quests.keys():
		targets.append(DataDB.node_of(RouteQueue.current_target(qid)))
	for eid in GameState.events_state.keys():
		if EventSystem.is_active(eid):
			targets.append(String(EventSystem.current_stage(eid).get("node", "")))
	for n in vis.values():
		var p := _to_screen(DataDB.node_pos(n["id"]))
		var mk := Assets.node_marker(String(n["type"]))
		var col := _type_color(String(n["type"]))
		if mk:
			draw_texture_rect(mk, Rect2(p - Vector2(16, 16), Vector2(32, 32)), false)
		else:
			draw_circle(p, 9 * clampf(zoom, 1, 1.6), col)
		if n.get("hidden", false):
			draw_string(font, p + Vector2(-5, -12), "?", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(1, 1, 0.5))
		if n["id"] in targets:
			draw_arc(p, 16 + sin(t * 4.0) * 2.0, 0, TAU, 24, Color(1, 0.8, 0.1), 3)
		if n["id"] == dest:
			draw_arc(p, 20, 0, TAU, 24, Color(1, 0.5, 0.1), 3)
		if zoom >= 1.4 or String(n["type"]) == "city" or n["id"] == snap_node:
			draw_string(font, p + Vector2(12, 6), n["name"], HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.12, 0.08, 0.04))
		if n.has("border_to"):
			draw_string(font, p + Vector2(12, 24), "→ " + ", ".join(PackedStringArray(n["border_to"].map(func(r): return DataDB.display_name(String(r))))), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.5, 0.1, 0.1))
	var here := traveler.pos if traveler and traveler.moving else DataDB.node_pos(GameState.current_node)
	if region_view == GameState.current_region:
		var hp := _to_screen(here)
		draw_circle(hp, 12, Color(0.9, 0.1, 0.1))
		draw_arc(hp, 18, 0, TAU, 24, Color.WHITE, 2)
	if snap_node != "":  # 흡착 깃발 커서
		var sp := _to_screen(DataDB.node_pos(snap_node))
		draw_line(sp, sp + Vector2(0, -42), Color(0.2, 0.1, 0.05), 3)
		draw_colored_polygon(PackedVector2Array([sp + Vector2(0, -42), sp + Vector2(26, -34), sp + Vector2(0, -26)]), Color(0.85, 0.15, 0.1))
		var n2 := DataDB.get_row(snap_node)
		draw_string(font, sp + Vector2(30, -30), "%s [%s]" % [n2["name"], n2.get("type_label", "")], HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.1, 0.05, 0.0))
	draw_string(font, Vector2(20, 36), "%s — 줌 %d%% (휠) · 드래그 이동 · 노드 클릭으로 목적지" % [DataDB.display_name(region_view), int(zoom * 100)], HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(1, 0.9, 0.7))


func _dashed(a: Vector2, b: Vector2, col: Color, w: float, phase: float) -> void:
	var L := a.distance_to(b)
	if L < 1:
		return
	var dir := (b - a) / L
	var s := -phase
	while s < L:
		var s0 := maxf(0.0, s)
		var s1 := minf(L, s + 14.0)
		if s1 > s0:
			draw_line(a + dir * s0, a + dir * s1, col, w)
		s += 24.0


func _type_color(t_: String) -> Color:
	return {"city": Color(0.7, 0.1, 0.1), "town": Color(0.2, 0.3, 0.7), "station": Color(0.5, 0.3, 0.1), "temple": Color(0.8, 0.55, 0.1),
		"spring": Color(0.2, 0.6, 0.8), "fort": Color(0.3, 0.3, 0.3), "beacon": Color(0.95, 0.35, 0.05), "hazard": Color(0.5, 0.0, 0.3)}.get(t_, Color(0.55, 0.2, 0.6))
