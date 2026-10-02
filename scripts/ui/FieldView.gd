class_name FieldView
extends Control
## 상단 월드 뷰어(1920×720, SubViewport 내부): 횡스크롤 패럴랙스 3중 레이어(원경·중경·근경) + 주인공 보행 +
## 24절기/날씨/낮밤 셰이더. 에셋: res://assets/parallax/map_nn/{far,mid,near}.png (1920×720 심리스) — 없으면 절차적 수묵 산세.

var traveler: TravelController
var font: Font
var weather_rect: ColorRect
var t := 0.0
const LAYERS := [
	{"name": "far", "par": 0.15, "y": 330.0, "amp": 120.0, "freq": 0.004, "col": Color(0.42, 0.5, 0.55)},
	{"name": "mid", "par": 0.45, "y": 430.0, "amp": 90.0, "freq": 0.007, "col": Color(0.3, 0.38, 0.36)},
	{"name": "near", "par": 1.0, "y": 560.0, "amp": 50.0, "freq": 0.012, "col": Color(0.2, 0.26, 0.22)},
]
const WEATHER_IDX := {"clear": 0, "rain": 1, "storm": 2, "snow": 3, "fog": 4}


func _ready() -> void:
	font = (Assets.font_ui if Assets.font_ui else ThemeDB.fallback_font)
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	weather_rect = ColorRect.new()
	weather_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	weather_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/season_weather.gdshader")
	weather_rect.material = mat
	add_child(weather_rect)
	GameState.stats_changed.connect(_queue_refresh)
	_refresh()


var _refresh_queued := false


func _queue_refresh() -> void:
	if not _refresh_queued:
		_refresh_queued = true
		call_deferred("_do_refresh")


func _do_refresh() -> void:
	_refresh_queued = false
	_refresh()


func _refresh() -> void:
	var mat := weather_rect.material as ShaderMaterial
	var gs := GameState
	mat.set_shader_parameter("season", gs.season())
	mat.set_shader_parameter("weather", int(WEATHER_IDX.get(gs.weather, 0)))
	mat.set_shader_parameter("term_progress", float(gs.solar_term_index() % 6) / 6.0)
	mat.set_shader_parameter("night", _night_factor())
	var clim := String(DataDB.get_row(gs.current_region).get("climate", "temperate"))
	mat.set_shader_parameter("intensity", {"warm": 0.45, "temperate": 0.6, "cold": 0.75, "frigid": 0.9}.get(clim, 0.6))


func _night_factor() -> float:
	var m := float(GameState.minutes % 1440) / 60.0
	var dh: Array = DataDB.overview.get("time", {}).get("day_hours", [5, 19])
	var dawn := float(dh[0])
	var dusk := float(dh[1])
	if m >= dawn + 1 and m <= dusk - 1:
		return 0.0
	if m > dusk - 1 and m < dusk + 1:
		return (m - (dusk - 1)) / 2.0
	if m > dawn - 1 and m < dawn + 1:
		return 1.0 - (m - (dawn - 1)) / 2.0
	return 1.0


func _process(delta: float) -> void:
	t += delta
	if traveler and traveler.moving:
		_refresh()
	queue_redraw()


func _scroll() -> float:
	return traveler.walked_total * 0.5 if traveler else 0.0


func _draw() -> void:
	var gs := GameState
	var sky: Color = [Color(0.62, 0.74, 0.86), Color(0.5, 0.7, 0.85), Color(0.78, 0.66, 0.5), Color(0.7, 0.75, 0.82)][gs.season()]
	draw_rect(Rect2(Vector2.ZERO, size), sky.darkened(0.1))
	for L in LAYERS:
		var tex := Assets.parallax(gs.current_region, String(L["name"]))
		var off := fmod(_scroll() * float(L["par"]), size.x)
		if tex:
			draw_texture_rect(tex, Rect2(-off, 0, size.x, size.y), false)
			draw_texture_rect(tex, Rect2(size.x - off, 0, size.x, size.y), false)
		else:
			_procedural_ridge(L, _scroll() * float(L["par"]))
	_draw_walker()
	_draw_strip()


func _procedural_ridge(L: Dictionary, shift: float) -> void:
	var pts := PackedVector2Array()
	pts.append(Vector2(0, size.y))
	var x := 0.0
	var f := float(L["freq"])
	while x <= size.x + 16:
		var xx := x + shift
		var y: float = float(L["y"]) - float(L["amp"]) * (0.6 * sin(xx * f) + 0.4 * sin(xx * f * 2.7 + 1.3)) * 0.5 - float(L["amp"]) * 0.5
		pts.append(Vector2(x, y))
		x += 16.0
	pts.append(Vector2(size.x, size.y))
	draw_colored_polygon(pts, L["col"])


func _draw_walker() -> void:
	var gs := GameState
	var moving := traveler != null and traveler.moving
	var base := Vector2(size.x * 0.42, 600)
	var bob := sin(t * 10.0) * 4.0 if moving else 0.0
	var sheet := Assets.sprite_sheet("hero_" + gs.class_id, "walk" if moving else "idle")
	if sheet:  # 128×128 프레임 가로 배열(8프레임)
		var frames := maxi(1, int(sheet.get_width() / 128))
		var fi := int(t * 10.0) % frames if moving else 0
		draw_texture_rect_region(sheet, Rect2(base + Vector2(-64, -128), Vector2(128, 128)), Rect2(fi * 128, 0, 128, 128))
	else:
		var p := base + Vector2(0, bob)
		draw_colored_polygon(PackedVector2Array([p + Vector2(-22, 0), p + Vector2(-14, -60), p + Vector2(14, -60), p + Vector2(22, 0)]), Color(0.92, 0.9, 0.85))
		draw_circle(p + Vector2(0, -74), 13, Color(0.93, 0.78, 0.62))
		draw_rect(Rect2(p + Vector2(-26, -90), Vector2(52, 4)), Color(0.1, 0.1, 0.1))
		draw_rect(Rect2(p + Vector2(-9, -104), Vector2(18, 14)), Color(0.1, 0.1, 0.1))
		if moving:
			var sw := sin(t * 10.0) * 10.0
			draw_line(p + Vector2(-6, 0), p + Vector2(-6 + sw, 18), Color(0.3, 0.25, 0.2), 4)
			draw_line(p + Vector2(6, 0), p + Vector2(6 - sw, 18), Color(0.3, 0.25, 0.2), 4)
	if gs.mounted() and not sheet:
		draw_rect(Rect2(base + Vector2(-60, -10), Vector2(120, 34)), Color(0.45, 0.3, 0.2))
	# 동료 행렬
	for i in gs.party.size():
		var q := base + Vector2(-90 - i * 70, sin(t * 10.0 + i) * 3.0 if moving else 0.0)
		var ps := Assets.sprite_sheet(String(gs.party[i]), "walk")
		if ps:
			var fr := maxi(1, int(ps.get_width() / 128))
			draw_texture_rect_region(ps, Rect2(q + Vector2(-48, -96), Vector2(96, 96)), Rect2((int(t * 10.0) % fr if moving else 0) * 128, 0, 128, 128))
		else:
			draw_circle(q + Vector2(0, -40), 16, Color(0.55, 0.45, 0.35))
			draw_string(font, q + Vector2(-20, -64), DataDB.display_name(String(gs.party[i])).left(3), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color.WHITE)


func _draw_strip() -> void:
	var gs := GameState
	draw_rect(Rect2(0, 0, size.x, 44), Color(0.05, 0.04, 0.03, 0.6))
	var where := DataDB.display_name(gs.current_node)
	if traveler and traveler.moving and traveler.leg_i < traveler.legs.size():
		where = "%s → %s (남은 %.0f리 · %.0fpx/s · %s)" % [DataDB.display_name(String(traveler.legs[traveler.leg_i]["from"])),
			DataDB.display_name(String(traveler.legs[-1]["to"])), traveler.remaining_li(), traveler.speed_now, {"road": "관로", "mountain": "산길", "water": "수로", "trail": "오솔길"}.get(traveler.terrain_now, "")]
	elif not gs.inside_node:
		where += " (외곽)"
	draw_string(font, Vector2(16, 30), "%s · %s │ %s │ %s · %s%s" % [DataDB.display_name(gs.current_region), where, gs.clock_text(),
		gs.solar_term(), GameState.WEATHER_KO.get(gs.weather, gs.weather), " · 밤" if gs.is_night() else ""], HORIZONTAL_ALIGNMENT_LEFT, size.x - 32, 20, Color(1, 0.93, 0.78))
