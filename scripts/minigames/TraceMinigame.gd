extends MinigameBase
## 주술·봉인형: 부적 획순 일필휘지(ordered: 정해진 순서로 한 번에) · 도깨비불 칠성진 잇기(no_cross: 선이 겹치지 않게 모든 별 연결)
## 마우스를 누른 채 점(반경 params.radius)을 지나가며 긋는다. 손을 떼면 획이 끊겨 처음부터.

var pts: Array = []
var ordered := true
var no_cross := false
var radius := 34.0
var path: Array = []     ## 방문한 점 인덱스
var stroke: PackedVector2Array = PackedVector2Array()
var drawing := false
var fail_flash := 0.0


func _setup() -> void:
	ordered = params.get("ordered", true)
	no_cross = params.get("no_cross", false)
	radius = float(params.get("radius", 34))
	instruction = ("주사 먹선을 떼지 말고 번호 순서대로 그으세요" if ordered else "선이 겹치지 않게 일곱 별을 한붓그리기로 이으세요")


func _area() -> Rect2:
	return Rect2(size.x * 0.2, 150, size.x * 0.6, size.y - 210)


func _pt(i: int) -> Vector2:
	var p: Array = params.get("points", [])[i]
	var a := _area()
	return a.position + Vector2(float(p[0]), float(p[1])) * a.size


func _count() -> int:
	return params.get("points", []).size()


func _reset(msg: bool) -> void:
	path.clear()
	stroke.clear()
	drawing = false
	if msg:
		fail_flash = 0.5


func _segments_cross(a: Vector2, b: Vector2, c: Vector2, d: Vector2) -> bool:
	var d1 := (b - a).cross(c - a)
	var d2 := (b - a).cross(d - a)
	var d3 := (d - c).cross(a - c)
	var d4 := (d - c).cross(b - c)
	return d1 * d2 < 0 and d3 * d4 < 0


func _visit(i: int) -> void:
	if ordered:
		if i != path.size():
			if not (i in path):
				_reset(true)
			return
	else:
		if i in path:
			return
		if no_cross and path.size() >= 1:
			var a := _pt(path[-1])
			var b := _pt(i)
			for k in range(path.size() - 2):
				if _segments_cross(a, b, _pt(path[k]), _pt(path[k + 1])):
					_reset(true)
					return
	path.append(i)
	if path.size() >= _count():
		_end(true)


func _gui_input(ev: InputEvent) -> void:
	if done:
		return
	if ev is InputEventMouseButton and ev.button_index == MOUSE_BUTTON_LEFT:
		if ev.pressed:
			_reset(false)
			drawing = true
		else:
			if drawing and path.size() < _count():
				_reset(true)
		accept_event()
	elif ev is InputEventMouseMotion and drawing:
		stroke.append(ev.position)
		for i in _count():
			if ev.position.distance_to(_pt(i)) <= radius:
				_visit(i)
		accept_event()


func _tick(delta: float) -> void:
	fail_flash = maxf(0.0, fail_flash - delta)


func _draw_game() -> void:
	var a := _area()
	draw_rect(a, Color(0.93, 0.87, 0.6) if ordered else Color(0.05, 0.06, 0.15))
	if fail_flash > 0:
		draw_rect(a, Color(1, 0, 0, fail_flash * 0.4))
	for i in range(1, path.size()):
		draw_line(_pt(path[i - 1]), _pt(path[i]), Color(0.8, 0.1, 0.05) if ordered else Color(0.5, 0.9, 1.0), 6)
	if stroke.size() > 1:
		draw_polyline(stroke, Color(0.7, 0.1, 0.05, 0.5) if ordered else Color(0.6, 0.9, 1, 0.4), 3)
	for i in _count():
		var hit := i in path
		var col := Color(0.6, 0.1, 0.1) if ordered else Color(1, 0.95, 0.5)
		draw_circle(_pt(i), radius * 0.5, col.lightened(0.4) if hit else col)
		if ordered:
			draw_string(font, _pt(i) + Vector2(-8, 8), str(i + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)
