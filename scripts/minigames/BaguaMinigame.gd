extends MinigameBase
## 2. 팔괘 진법 해제 — 8방위 괘를 제시된 순서대로 해제(클릭 또는 숫자키 1~8). 제한시간 내 완성 시 성공.
## 성공: 적 전체 도술 버프 소멸 + 아군 마법 면역 2턴

const TRIGRAMS := ["☰ 건", "☱ 태", "☲ 리", "☳ 진", "☴ 손", "☵ 감", "☶ 간", "☷ 곤"]
const SEQ_LEN := 6
var sequence: Array = []
var progress := 0
var flash_bad := 0.0


func _setup() -> void:
	instruction = "상단에 제시된 괘 순서대로 8방위를 해제하세요 (클릭 / 숫자키 1~8). 틀리면 처음부터."
	var r := RandomNumberGenerator.new()
	r.randomize()
	for i in SEQ_LEN:
		sequence.append(r.randi_range(0, 7))


func _center() -> Vector2:
	return Vector2(size.x / 2.0, size.y / 2.0 + 60)


func _slot_pos(i: int) -> Vector2:
	var ang := -PI / 2.0 + TAU * i / 8.0
	return _center() + Vector2(cos(ang), sin(ang)) * minf(size.y * 0.32, 220.0)


func _press(i: int) -> void:
	if done:
		return
	if i == sequence[progress]:
		progress += 1
		if progress >= sequence.size():
			_end(true)
	else:
		progress = 0
		flash_bad = 0.4


func _tick(delta: float) -> void:
	flash_bad = maxf(0.0, flash_bad - delta)


func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		for i in 8:
			if ev.position.distance_to(_slot_pos(i)) < 48:
				_press(i)
				accept_event()
				return
	elif ev is InputEventKey and ev.pressed and not ev.echo:
		var k: int = ev.keycode - KEY_1
		if k >= 0 and k < 8:
			_press(k)
			accept_event()


func _draw_game() -> void:
	var x := 40.0
	for i in sequence.size():
		var col := Color(0.4, 0.9, 0.4) if i < progress else Color(1, 0.9, 0.6)
		draw_string(font, Vector2(x, 170), TRIGRAMS[sequence[i]], HORIZONTAL_ALIGNMENT_LEFT, -1, 28, col)
		x += 130
	draw_circle(_center(), 60, Color(0.9, 0.2, 0.2) if flash_bad > 0 else Color(0.15, 0.25, 0.6))
	_draw_center_text("태극", _center().y + 10, 26, Color.WHITE)
	for i in 8:
		var p := _slot_pos(i)
		draw_circle(p, 46, Color(0.18, 0.15, 0.1))
		draw_arc(p, 46, 0, TAU, 32, Color(0.85, 0.7, 0.4), 2)
		draw_string(font, p + Vector2(-38, 10), "%d %s" % [i + 1, TRIGRAMS[i]], HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)
