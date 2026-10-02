extends MinigameBase
## 1. 착호 쇠뇌 / 활쏘기 — 움직이는 표적(맹수·정찰병·적 수괴)을 마우스로 조준 사격. 화살 5발 중 3발 명중 시 성공.

const ARROWS := 5
const NEED_HITS := 3
var arrows_left := ARROWS
var hits := 0
var target_pos := Vector2.ZERO
var target_r := 42.0
var t := 0.0
var shots: Array = []  ## [{pos, hit, age}]


func _setup() -> void:
	instruction = "움직이는 표적을 클릭해 쏘세요 — 화살 %d발 중 %d발 명중 시 성공 (적 수괴 방어구 파괴 + HP 30%% 선제 삭감)" % [ARROWS, NEED_HITS]


func _tick(delta: float) -> void:
	t += delta
	var c := size / 2.0 + Vector2(0, 40)
	target_pos = c + Vector2(sin(t * 1.3) * size.x * 0.33, sin(t * 2.7) * size.y * 0.18)
	for s in shots:
		s["age"] += delta


func _gui_input(ev: InputEvent) -> void:
	if done:
		return
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		arrows_left -= 1
		var hit: bool = ev.position.distance_to(target_pos) <= target_r
		if hit:
			hits += 1
		shots.append({"pos": ev.position, "hit": hit, "age": 0.0})
		if hits >= NEED_HITS:
			_end(true)
		elif arrows_left <= 0 or arrows_left < NEED_HITS - hits:
			_end(false)
		accept_event()


func _draw_game() -> void:
	draw_circle(target_pos, target_r, Color(0.75, 0.2, 0.15))
	draw_circle(target_pos, target_r * 0.66, Color(0.95, 0.9, 0.8))
	draw_circle(target_pos, target_r * 0.33, Color(0.75, 0.2, 0.15))
	for s in shots:
		var col := Color(1, 1, 0.3) if s["hit"] else Color(0.6, 0.6, 0.6)
		draw_line(s["pos"] - Vector2(10, 10), s["pos"] + Vector2(10, 10), col, 3)
		draw_line(s["pos"] - Vector2(10, -10), s["pos"] + Vector2(10, -10), col, 3)
	var m := get_local_mouse_position()
	draw_arc(m, 18, 0, TAU, 24, Color(1, 1, 1, 0.8), 2)
	draw_string(font, Vector2(40, size.y - 30), "화살 %d  명중 %d/%d" % [arrows_left, hits, NEED_HITS], HORIZONTAL_ALIGNMENT_LEFT, -1, 26, Color.WHITE)
