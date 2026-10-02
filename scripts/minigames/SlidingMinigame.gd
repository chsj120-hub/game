extends MinigameBase
## 복원형: 한지 수묵 슬라이딩 퍼즐 · 도자기 파편 맞추기. N×N 타일(params.size), 이미지(params.image) 없으면 번호·먹선 대체.
## 빈칸 옆 타일을 클릭(또는 방향키)해 밀어 원본 순서로 복원.

var n := 3
var tiles: Array = []   ## 인덱스 → 타일 번호(0=빈칸)
var tex: Texture2D
var moves := 0


func _setup() -> void:
	n = clampi(int(params.get("size", 3)), 3, 5)
	var img_path := String(params.get("image", ""))
	if img_path == "" or not ResourceLoader.exists(img_path):
		img_path = String(params.get("image_fallback", ""))  # 유산 전용 그림이 아직 없으면 카탈로그 기본 그림
	if img_path != "" and ResourceLoader.exists(img_path):
		tex = load(img_path)
	tiles = []
	for i in n * n:
		tiles.append((i + 1) % (n * n))
	var r := RandomNumberGenerator.new()
	r.randomize()
	for i in 60 * n:  # 풀 수 있는 배열 보장: 빈칸을 무작위로 이동해 섞음
		var nb := _neighbors(tiles.find(0))
		_swap(tiles.find(0), nb[r.randi_range(0, nb.size() - 1)])
	moves = 0
	instruction = "빈칸 옆 조각을 클릭해 밀어 원본을 복원하세요 (%d×%d)" % [n, n]


func _neighbors(i: int) -> Array:
	var out := []
	var x := i % n
	var y := i / n
	if x > 0: out.append(i - 1)
	if x < n - 1: out.append(i + 1)
	if y > 0: out.append(i - n)
	if y < n - 1: out.append(i + n)
	return out


func _swap(a: int, b: int) -> void:
	var t = tiles[a]
	tiles[a] = tiles[b]
	tiles[b] = t


func _board() -> Rect2:
	var s := minf(size.y - 220, size.x * 0.5)
	return Rect2((size.x - s) / 2.0, 170, s, s)


func _try_move(i: int) -> void:
	if done:
		return
	var e := tiles.find(0)
	if i in _neighbors(e):
		_swap(i, e)
		moves += 1
		if _solved():
			_end(true)


func _solved() -> bool:
	for i in n * n:
		if tiles[i] != (i + 1) % (n * n):
			return false
	return true


func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		var b := _board()
		if b.has_point(ev.position):
			var cell := b.size.x / n
			var cx := int((ev.position.x - b.position.x) / cell)
			var cy := int((ev.position.y - b.position.y) / cell)
			_try_move(cy * n + cx)
			accept_event()
	elif ev is InputEventKey and ev.pressed and not ev.echo:
		var e := tiles.find(0)
		var d := {KEY_LEFT: 1, KEY_RIGHT: -1, KEY_UP: n, KEY_DOWN: -n}
		if d.has(ev.keycode):
			var t: int = e + int(d[ev.keycode])
			if t >= 0 and t < n * n and t in _neighbors(e):
				_try_move(t)
			accept_event()


func _draw_game() -> void:
	var b := _board()
	var cell := b.size.x / n
	draw_rect(b.grow(6), Color(0.35, 0.22, 0.12))
	for i in n * n:
		var v: int = tiles[i]
		if v == 0:
			continue
		var r := Rect2(b.position + Vector2(i % n, i / n) * cell, Vector2(cell, cell)).grow(-3)
		if tex:
			var src_i := v - 1
			var tw := tex.get_width() / float(n)
			var th := tex.get_height() / float(n)
			draw_texture_rect_region(tex, r, Rect2((src_i % n) * tw, (src_i / n) * th, tw, th))
		else:
			draw_rect(r, Color(0.9, 0.85, 0.72))
			var sx := float((v - 1) % n) / n
			draw_line(r.position + Vector2(0, r.size.y * (0.3 + sx * 0.4)), r.end - Vector2(0, r.size.y * 0.3), Color(0.15, 0.12, 0.1), 5)
			draw_string(font, r.position + Vector2(8, 30), str(v), HORIZONTAL_ALIGNMENT_LEFT, -1, 24, Color(0.3, 0.2, 0.1))
	draw_string(font, Vector2(40, size.y - 30), "이동 %d회" % moves, HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color.WHITE)
