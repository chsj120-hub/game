class_name Dashboard
extends Control
## 하단 1/3 상시 제어 HUD (1920×360, CanvasLayer) — 완전판 1.1 4개 영역
##  ① 아바타·신분(수묵 초상, 직업 아이콘, 칭호, 소속 인장)  ② 상태창(HP/피로도/이동속도/행동력)
##  ③ 생활 스킬 [야영][탐색][채집][사냥]                    ④ 서브 메뉴 독 [지도][배낭][장착][도감] + 시스템 줄

signal command(cmd: String)

const LIFE := [["camp", "야 영"], ["search", "탐 색"], ["gather", "채 집"], ["hunt", "사 냥"]]
const DOCK := [["map", "지도 (대동여지도)"], ["bag", "배낭 (인벤토리)"], ["equip", "장착 (5슬롯+동료)"], ["codex", "도감 (3중 분류)"]]
const SYS := [["here", "거점 시설"], ["event", "이벤트"], ["quest", "퀘스트"], ["craft", "제작"], ["party", "동료·막사"], ["knowledge", "지식"], ["stop", "정지(Space)"], ["ff", "빨리 ×3"]]

var status_box: RichTextLabel
var title_label: RichTextLabel
var log_box: RichTextLabel
var portrait: Control
var bars: Dictionary = {}
var buttons: Array = []


func _ready() -> void:
	var bg := ColorRect.new()
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tex := Assets.tex("res://assets/ui/panels/dashboard_frame.png")
	if tex:
		var tr := TextureRect.new()
		tr.texture = tex
		tr.set_anchors_preset(Control.PRESET_FULL_RECT)
		tr.stretch_mode = TextureRect.STRETCH_SCALE
		tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(tr)
	else:
		var mat := ShaderMaterial.new()
		mat.shader = load("res://shaders/hanji.gdshader")
		bg.material = mat
		add_child(bg)
	# ① 아바타
	portrait = Control.new()
	portrait.position = Vector2(16, 16)
	portrait.size = Vector2(230, 328)
	portrait.draw.connect(_draw_portrait)
	add_child(portrait)
	title_label = RichTextLabel.new()
	title_label.bbcode_enabled = true
	title_label.position = Vector2(20, 262)
	title_label.size = Vector2(222, 80)
	title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_font(title_label, 16)
	Assets.title(title_label, 22)  # 칭호·신분
	add_child(title_label)
	# ② 상태창
	var y := 20.0
	for k in [["hp", "체력(HP)", Color(0.75, 0.15, 0.1)], ["fatigue", "피로도", Color(0.55, 0.35, 0.1)], ["satiety", "포만감", Color(0.35, 0.55, 0.2)], ["weight", "배낭 무게", Color(0.35, 0.35, 0.5)]]:
		var l := Label.new()
		l.position = Vector2(265, y)
		l.add_theme_color_override("font_color", Color(0.15, 0.08, 0.03))
		l.add_theme_font_size_override("font_size", 16)
		l.text = k[1]
		add_child(l)
		var pb := ProgressBar.new()
		pb.position = Vector2(360, y + 2)
		pb.size = Vector2(280, 22)
		pb.show_percentage = false
		var sb := StyleBoxFlat.new()
		sb.bg_color = k[2]
		pb.add_theme_stylebox_override("fill", sb)
		add_child(pb)
		var v := Label.new()
		v.position = Vector2(360, y)
		v.size = Vector2(280, 24)
		v.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_theme_color_override("font_color", Color.WHITE)
		v.add_theme_font_size_override("font_size", 15)
		add_child(v)
		bars[k[0]] = [pb, v]
		y += 32
	status_box = RichTextLabel.new()
	status_box.bbcode_enabled = true
	status_box.position = Vector2(265, y + 4)
	status_box.size = Vector2(380, 340 - y)
	status_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_font(status_box, 16)
	add_child(status_box)
	# ③ 생활 스킬
	var lg := VBoxContainer.new()
	lg.position = Vector2(665, 18)
	lg.add_theme_constant_override("separation", 8)
	add_child(lg)
	for c in LIFE:
		lg.add_child(_btn("[ %s ]" % c[1], c[0], Vector2(170, 72), 22))
	# ④ 서브 메뉴 독
	var dock := GridContainer.new()
	dock.columns = 2
	dock.position = Vector2(855, 18)
	dock.add_theme_constant_override("h_separation", 8)
	dock.add_theme_constant_override("v_separation", 8)
	add_child(dock)
	for c in DOCK:
		dock.add_child(_btn("[%s]" % c[1], c[0], Vector2(250, 70), 18))
	var sys := GridContainer.new()
	sys.columns = 4
	sys.position = Vector2(855, 180)
	sys.add_theme_constant_override("h_separation", 6)
	sys.add_theme_constant_override("v_separation", 6)
	add_child(sys)
	for c in SYS:
		sys.add_child(_btn(c[1], c[0], Vector2(123, 50), 15))
	log_box = RichTextLabel.new()
	log_box.position = Vector2(1380, 16)
	log_box.size = Vector2(525, 328)
	log_box.scroll_following = true
	_font(log_box, 15)
	add_child(log_box)
	GameState.stats_changed.connect(refresh)
	GameState.log_message.connect(func(t): log_box.append_text("· " + t + "\n"))
	refresh()


func _font(r: RichTextLabel, s: int) -> void:
	r.add_theme_color_override("default_color", Color(0.15, 0.08, 0.03))
	r.add_theme_font_size_override("normal_font_size", s)
	r.add_theme_font_size_override("bold_font_size", s + 2)


func _btn(text: String, cmd: String, sz: Vector2, fs: int) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = sz
	b.add_theme_font_size_override("font_size", fs)
	b.pressed.connect(func(): command.emit(cmd))
	buttons.append(b)
	return b


func set_enabled(on: bool) -> void:
	for b in buttons:
		b.disabled = not on


func _bar(k: String, v: float, mx: float, text: String) -> void:
	var pb: ProgressBar = bars[k][0]
	pb.max_value = maxf(mx, 1.0)
	pb.value = v
	bars[k][1].text = text


func refresh() -> void:
	var gs := GameState
	var hs := gs.hero_combat_stats()
	_bar("hp", gs.hp, gs.hp_max(), "%d / %d" % [int(gs.hp), int(gs.hp_max())])
	var fs := gs.fatigue_stage()
	_bar("fatigue", gs.fatigue, 100, "%d / 100 %s" % [int(gs.fatigue), ("(" + String(fs["name"]) + ")") if not fs.is_empty() else ""])
	_bar("satiety", gs.satiety, 100, "%d / 100" % int(gs.satiety))
	_bar("weight", gs.carry_weight(), gs.carry_capacity(), "%.1f / %.0f" % [gs.carry_weight(), gs.carry_capacity()])
	var ap := Balance.start_ap(float(hs["move_speed"]), int(hs["ap_penalty"]))
	var base_ap := int(DataDB.overview.get("battle", {}).get("ap", {}).get("start", 3))
	var prog := gs.next_rank_progress()
	var ill := PackedStringArray()
	for sid in gs.field_statuses.keys():
		ill.append(String(DataDB.field_buffs.get(sid, DataDB.status_field.get(sid, {})).get("name", sid)))
	status_box.text = "이  속 : [b]%.1f px/s[/b] (%s)\n행동력 : [b]%d + %d AP[/b]\n엽전 %d냥 · 명성 %d / %d%s\n%s\n%s" % [
		SurvivalSystem.speed_now("road"), DataDB.display_name(String(gs.equipped.get("mount", ""))) if gs.mounted() else "도보",
		base_ap, maxi(0, ap - base_ap), gs.money, prog.x, prog.y, "  [color=#a01010]▲승급 심사 가능[/color]" if gs.promotion_available() else "",
		"상태: " + ", ".join(ill) if ill.size() > 0 else "", "도핑: 전투 %d회" % int(gs.food_buff.get("battles", 0)) if not gs.food_buff.is_empty() else ""]
	var c := DataDB.class_row(gs.class_id)
	var pv := Balance.province_of_region(gs.current_region)
	title_label.text = "[b]%s[/b] · Rank %d\n%s · %s 명성 %d" % [Balance.rank_title(gs.rank, gs.class_id), gs.rank, c.get("name", ""), pv.get("name", ""), int(gs.province_rep.get(pv.get("id", ""), 0))]
	portrait.queue_redraw()


func _draw_portrait() -> void:
	var p := portrait
	var gs := GameState
	p.draw_rect(Rect2(Vector2.ZERO, p.size), Color(0.3, 0.2, 0.12))
	p.draw_rect(Rect2(Vector2(6, 6), p.size - Vector2(12, 12)), Color(0.88, 0.82, 0.68))
	var tex := Assets.portrait("hero_" + gs.class_id)
	if tex:
		p.draw_texture_rect(tex, Rect2(Vector2(10, 10), Vector2(210, 240)), false)
	else:
		var cx := p.size.x / 2.0
		p.draw_colored_polygon(PackedVector2Array([Vector2(cx - 70, 250), Vector2(cx - 50, 150), Vector2(cx + 50, 150), Vector2(cx + 70, 250)]), Color(0.93, 0.92, 0.88))
		p.draw_circle(Vector2(cx, 112), 36, Color(0.93, 0.78, 0.62))
		p.draw_rect(Rect2(cx - 72, 68, 144, 8), Color(0.1, 0.1, 0.1))
		p.draw_rect(Rect2(cx - 26, 36, 52, 34), Color(0.1, 0.1, 0.1))
	var ci := Assets.class_icon(gs.class_id)
	if ci:
		p.draw_texture_rect(ci, Rect2(Vector2(12, 12), Vector2(48, 48)), false)
	var seal := Assets.tex("res://assets/ui/seals/rank_%d.png" % gs.rank)
	if seal:
		p.draw_texture_rect(seal, Rect2(Vector2(p.size.x - 62, 12), Vector2(50, 50)), false)
	else:  # 소속 인장(붉은 낙관)
		p.draw_rect(Rect2(Vector2(p.size.x - 60, 14), Vector2(46, 46)), Color(0.72, 0.1, 0.08))
		p.draw_string((Assets.font_ui if Assets.font_ui else ThemeDB.fallback_font), Vector2(p.size.x - 52, 46), str(gs.rank), HORIZONTAL_ALIGNMENT_LEFT, -1, 26, Color(1, 0.9, 0.8))
