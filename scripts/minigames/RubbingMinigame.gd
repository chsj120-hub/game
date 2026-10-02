extends MinigameBase
## 대동여지도 목판 탁본 인출: 먹방망이(마우스 드래그)로 한지를 두드려 판목 전체를 coverage 이상 찍어낸다.
## 판목 이미지 res://assets/minigames/takbon/sheet_<nn>.png 가 있으면 사용, 없으면 절차적 산줄기·물길 패턴.

const GRID := 32
var covered: Dictionary = {}
var need := 0.85
var brush := 42.0
var tex: Texture2D
var pattern_seed := 0


func _setup() -> void:
	need = float(params.get("coverage", 0.85))
	brush = float(params.get("brush", 42))
	var sheet := int(params.get("sheet", 1))
	var p := "res://assets/minigames/takbon/sheet_%02d.png" % sheet
	if ResourceLoader.exists(p):
		tex = load(p)
	pattern_seed = sheet
	instruction = "마우스를 누른 채 한지 위를 문질러 먹을 입히세요 — %d%% 이상 인출 시 성공" % int(need * 100)


func _area() -> Rect2:
	return Rect2(size.x * 0.15, 150, size.x * 0.7, size.y - 200)


func _ratio() -> float:
	return float(covered.size()) / float(GRID * GRID)


func _gui_input(ev: InputEvent) -> void:
	if done:
		return
	if (ev is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT)) or (ev is InputEventMouseButton and ev.pressed):
		var a := _area()
		var cw := a.size.x / GRID
		var ch := a.size.y / GRID
		var r := int(ceil(brush / cw))
		var cx := int((ev.position.x - a.position.x) / cw)
		var cy := int((ev.position.y - a.position.y) / ch)
		for dx in range(-r, r + 1):
			for dy in range(-r, r + 1):
				var x := cx + dx
				var y := cy + dy
				if x >= 0 and y >= 0 and x < GRID and y < GRID and Vector2(dx * cw, dy * ch).length() <= brush:
					covered[y * GRID + x] = true
		if _ratio() >= need:
			_end(true)
		accept_event()


func _on_timeout() -> bool:
	return _ratio() >= need


func _draw_game() -> void:
	var a := _area()
	draw_rect(a, Color(0.95, 0.92, 0.84))
	var cw := a.size.x / GRID
	var ch := a.size.y / GRID
	for k in covered.keys():
		var x := int(k) % GRID
		var y := int(k) / GRID
		var r := Rect2(a.position + Vector2(x * cw, y * ch), Vector2(cw + 1, ch + 1))
		if tex:
			var tw := tex.get_width() / float(GRID)
			var th := tex.get_height() / float(GRID)
			draw_texture_rect_region(tex, r, Rect2(x * tw, y * th, tw, th))
		else:
			var v := sin(x * 0.4 + pattern_seed) * cos(y * 0.35) + sin((x + y) * 0.2)
			draw_rect(r, Color(0.1, 0.09, 0.08) if absf(v) < 0.25 else Color(0.45, 0.42, 0.38))
	_draw_center_text("인출 %.0f%% / %d%%" % [_ratio() * 100, int(need * 100)], size.y - 20, 24, Color.WHITE)
