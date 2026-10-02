class_name DialogueView
extends Control
## 대화 화면 (1920×1080 전체 오버레이)
##   배경: 노드 삽화(res://assets/scenes/…) — 없으면 노드 유형 색
##   인물: 상반신 초상(res://assets/portraits/<id>.png · npc_<역할>.png) 최대 3명, 말하는 사람만 밝게. 초상이 없으면 실루엣+이름
##   하단 대화창: 이름표 + 타자기 효과 본문. 클릭·Space·Enter 로 넘김
##   선택지: 화면 가운데. 조건(req) 미충족 선택지는 비활성 + 사유 표시. 숫자키 1~9 로도 선택
## 끝나면 finished(choice_id) — 선택지가 없던 대화는 "".

signal finished(choice_id: String)

const W := 1920.0
const H := 1080.0
const BOX_Y := 780.0
const BOX_H := 290.0
const CPS := 48.0
const BUST := Vector2(470, 640)

var d: Dictionary = {}
var lines: Array = []
var li := 0
var shown := 0.0
var typing := false
var in_choice := false
var picked := ""
var showing_result := false
var cast: Array = []
var busts: Dictionary = {}   ## who -> Bust
var bg_tex: TextureRect
var bg_col: ColorRect
var dim: ColorRect
var box: PanelContainer
var name_plate: PanelContainer
var name_lbl: Label
var title_lbl: Label
var text_lbl: Label
var next_mark: Label
var choice_box: VBoxContainer
var choice_buttons: Array = []


class Bust extends Control:
	var info: Dictionary = {}
	var tex: Texture2D

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		if tex:
			var ts := tex.get_size()
			var sc := minf(r.size.x / ts.x, r.size.y / ts.y)
			var ds := ts * sc
			draw_texture_rect(tex, Rect2(Vector2((r.size.x - ds.x) / 2.0, r.size.y - ds.y), ds), false)
			return
		var col: Color = info.get("color", Color(0.4, 0.4, 0.4))
		var cx := r.size.x / 2.0
		var body := PackedVector2Array([Vector2(cx - 190, r.size.y), Vector2(cx - 150, r.size.y - 230), Vector2(cx - 70, r.size.y - 300),
			Vector2(cx + 70, r.size.y - 300), Vector2(cx + 150, r.size.y - 230), Vector2(cx + 190, r.size.y)])
		draw_colored_polygon(body, col.darkened(0.35))
		draw_circle(Vector2(cx, r.size.y - 390), 92, col.darkened(0.15))
		draw_rect(Rect2(cx - 120, r.size.y - 505, 240, 26), col.darkened(0.55))  # 갓 챙
		draw_rect(Rect2(cx - 50, r.size.y - 575, 100, 72), col.darkened(0.55))   # 갓 모자
		var f: Font = Assets.font_ui if Assets.font_ui else ThemeDB.fallback_font
		var nm := String(info.get("name", ""))
		var w := f.get_string_size(nm, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x
		draw_string(f, Vector2(cx - w / 2.0, r.size.y - 120), nm, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, Color(1, 1, 1, 0.85))


func _ready() -> void:
	position = Vector2.ZERO
	size = Vector2(W, H)
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_ALL
	bg_col = ColorRect.new()
	bg_col.size = size
	bg_col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg_col)
	bg_tex = TextureRect.new()
	bg_tex.size = size
	bg_tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	bg_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	bg_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg_tex)
	box = PanelContainer.new()
	box.position = Vector2(40, BOX_Y)
	box.size = Vector2(W - 80, BOX_H)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_theme_stylebox_override("panel", Assets.panel_style("dialogue", Color(0.08, 0.06, 0.04, 0.93), Color(0.85, 0.68, 0.35)))
	var v := VBoxContainer.new()
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(v)
	title_lbl = Label.new()
	title_lbl.add_theme_font_size_override("font_size", 18)
	title_lbl.add_theme_color_override("font_color", Color(0.85, 0.75, 0.5, 0.8))
	v.add_child(title_lbl)
	text_lbl = Label.new()
	text_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text_lbl.custom_minimum_size = Vector2(W - 140, 190)
	text_lbl.add_theme_font_size_override("font_size", 30)
	text_lbl.add_theme_color_override("font_color", Color(1, 0.96, 0.88))
	v.add_child(text_lbl)
	next_mark = Label.new()
	next_mark.text = "▼ 클릭 · Space"
	next_mark.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	next_mark.add_theme_font_size_override("font_size", 18)
	next_mark.add_theme_color_override("font_color", Color(0.9, 0.8, 0.5, 0.7))
	v.add_child(next_mark)
	name_plate = PanelContainer.new()
	name_plate.position = Vector2(80, BOX_Y - 52)
	name_plate.mouse_filter = Control.MOUSE_FILTER_IGNORE
	name_lbl = Label.new()
	name_lbl.add_theme_font_size_override("font_size", 28)
	Assets.title(name_lbl, 36)
	name_plate.add_child(name_lbl)
	var skip := Button.new()
	skip.text = "건너뛰기 ▶▶"
	skip.position = Vector2(W - 230, BOX_Y - 50)
	skip.pressed.connect(_skip)
	dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0.45)
	dim.size = Vector2(W, BOX_Y)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	dim.hide()
	choice_box = VBoxContainer.new()
	choice_box.add_theme_constant_override("separation", 14)
	choice_box.hide()
	# 층 순서: 배경 → 인물 → (dim) → 대화창 → 이름표 → 선택지
	add_child(dim)
	add_child(box)
	add_child(name_plate)
	add_child(skip)
	add_child(choice_box)
	grab_focus()


## 장면 시작
func start(scene: Dictionary) -> void:
	d = scene
	lines = d.get("lines", [])
	var bg := String(d.get("bg", GameState.current_node))
	bg_col.color = DialogueSystem.background_color(bg)
	bg_tex.texture = DialogueSystem.background(bg)
	title_lbl.text = String(d.get("title", ""))
	cast = []
	for w in d.get("cast", []):
		if not (String(w) in cast):
			cast.append(String(w))
	for ln in lines:
		var w2 := String(ln.get("who", ""))
		if w2 != "" and w2 != "narration" and not (w2 in cast):
			cast.append(w2)
	if cast.has("hero"):
		cast.erase("hero")
		cast.push_front("hero")
	cast = cast.slice(0, 3)
	_build_busts()
	li = 0
	if lines.is_empty():
		_after_lines()
	else:
		_show_line()


func _build_busts() -> void:
	for b in busts.values():
		b.queue_free()
	busts.clear()
	var xs: Array = {1: [960.0], 2: [620.0, 1300.0], 3: [470.0, 960.0, 1450.0]}.get(cast.size(), [])
	for i in cast.size():
		var b := Bust.new()
		b.info = DialogueSystem.speaker(String(cast[i]))
		b.tex = b.info.get("portrait")
		b.size = BUST
		b.position = Vector2(float(xs[i]) - BUST.x / 2.0, BOX_Y + 40 - BUST.y)
		b.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(b)
		move_child(b, 2 + i)  # 배경 바로 위
		busts[String(cast[i])] = b


func _focus(who: String) -> void:
	for w in busts.keys():
		var on: bool = w == who
		var b: Control = busts[w]
		b.modulate = Color(1, 1, 1) if on else Color(0.42, 0.42, 0.48)
		b.position = Vector2(b.position.x, BOX_Y + 40 - BUST.y - (12.0 if on else 0.0))


func _show_line() -> void:
	var ln: Dictionary = lines[li]
	var who := String(ln.get("who", ""))
	var sp := DialogueSystem.speaker(who)
	_set_name(String(sp.get("name", "")), sp.get("color", Color(0.3, 0.3, 0.3)))
	_focus(who)
	_type(String(ln.get("text", "")))


func _set_name(nm: String, col: Color) -> void:
	name_lbl.text = nm
	name_plate.visible = nm != ""
	var sb := StyleBoxFlat.new()
	sb.bg_color = col.darkened(0.2)
	sb.border_color = Color(0.9, 0.75, 0.4)
	sb.set_border_width_all(2)
	sb.set_content_margin_all(8)
	sb.content_margin_left = 22
	sb.content_margin_right = 22
	name_plate.add_theme_stylebox_override("panel", sb)


func _type(t: String) -> void:
	text_lbl.text = t
	text_lbl.visible_characters = 0
	shown = 0.0
	typing = true
	next_mark.modulate.a = 0.0


func _process(delta: float) -> void:
	if not typing:
		next_mark.modulate.a = 0.5 + 0.5 * sin(Time.get_ticks_msec() / 250.0)
		return
	shown += CPS * delta
	text_lbl.visible_characters = int(shown)
	if int(shown) >= text_lbl.text.length():
		_finish_typing()


func _finish_typing() -> void:
	typing = false
	text_lbl.visible_characters = -1


func _advance() -> void:
	if in_choice:
		return
	if typing:
		_finish_typing()
		return
	if showing_result:
		_finish()
		return
	if li < lines.size() - 1:
		li += 1
		_show_line()
		return
	_after_lines()


func _after_lines() -> void:
	if Array(d.get("choices", [])).size() > 0 and picked == "":
		_show_choices()
	else:
		_finish()


func _skip() -> void:
	if in_choice:
		return
	_finish_typing()
	li = maxi(0, lines.size() - 1)
	if showing_result:
		_finish()
	else:
		_after_lines()


# ---------------------------------------------------------------- 선택지 (가운데)
func _show_choices() -> void:
	in_choice = true
	next_mark.modulate.a = 0.0
	for b in choice_buttons:
		b.queue_free()
	choice_buttons.clear()
	var n := 0
	for c in d.get("choices", []):
		var reason := DialogueSystem.check_req(c.get("req", {}))
		var b := Button.new()
		n += 1
		b.text = "%d. %s%s" % [n, String(c.get("text", "")), "" if reason == "" else "   ✕ " + reason]
		b.disabled = reason != ""
		b.tooltip_text = reason
		b.custom_minimum_size = Vector2(760, 58)
		b.add_theme_font_size_override("font_size", 24)
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.pressed.connect(_pick.bind(String(c.get("id", "")), String(c.get("result", ""))))
		choice_box.add_child(b)
		choice_buttons.append(b)
	dim.show()
	choice_box.show()
	choice_box.size = Vector2(760, 0)
	var hgt := n * 72.0
	choice_box.position = Vector2((W - 760) / 2.0, maxf(60.0, (BOX_Y - hgt) / 2.0))
	for b in choice_buttons:
		if not b.disabled:
			b.grab_focus()
			break


func _pick(cid: String, result: String) -> void:
	picked = cid
	in_choice = false
	dim.hide()
	choice_box.hide()
	if result == "":
		_finish()
		return
	showing_result = true
	var nm := ""
	var body := result
	var k := result.find(": ")
	if k > 0 and k < 18:
		nm = result.substr(0, k)
		body = result.substr(k + 2)
	var who := ""
	for w in busts.keys():
		if String(busts[w].info.get("name", "")) == nm:
			who = w
	_set_name(nm, busts[who].info.get("color", Color(0.3, 0.3, 0.3)) if who != "" else Color(0.3, 0.3, 0.3))
	_focus(who)
	_type(body)


func _finish() -> void:
	set_process(false)
	finished.emit(picked)
	queue_free()


# ---------------------------------------------------------------- 입력
func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		_advance()
		accept_event()


func _input(ev: InputEvent) -> void:
	if not visible or not (ev is InputEventKey) or not ev.pressed or ev.echo:
		return
	if in_choice:
		var k: int = ev.keycode - KEY_1
		if k >= 0 and k < choice_buttons.size():
			if not choice_buttons[k].disabled:
				choice_buttons[k].emit_signal("pressed")
			get_viewport().set_input_as_handled()
		return
	if ev.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		_advance()
		get_viewport().set_input_as_handled()
