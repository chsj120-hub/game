extends MinigameBase
## 타이밍형: 편전 사복개궁(바람·호흡 일치점) · 범종 타종 · 대장간 망치 단조.
## 좌우로 왕복하는 커서가 명중대(zone)에 있을 때 스페이스/클릭. attempts 안에 hits 회 명중 시 성공.
## result_quality = 명중률 → 대장간 단조 품질에 사용.

var hits_need := 3
var attempts := 5
var zone := 0.12
var spd := 1.2
var pos := 0.0
var dir := 1.0
var zone_c := 0.5
var hits := 0
var tries := 0
var marks: Array = []
var result_quality := 0.0
var rnd := RandomNumberGenerator.new()


func _setup() -> void:
	hits_need = int(params.get("hits", 3))
	attempts = int(params.get("attempts", 5))
	zone = float(params.get("zone", 0.12))
	if params.get("quality_bonus", false):  # 대장간: 공 지식 랭크당 명중대 +5%
		zone *= 1.0 + GameState.life_effect("gong", "forge_window")
	spd = float(params.get("speed", 1.2))
	if params.has("seed"):  # 유산별 변형: 명중대 위치 고정
		rnd.seed = int(params["seed"])
	else:
		rnd.randomize()
	zone_c = rnd.randf_range(0.25, 0.75)
	instruction = "커서가 금빛 명중대에 들어올 때 [스페이스] 또는 클릭 — %d회 중 %d회 명중" % [attempts, hits_need]


func _tick(delta: float) -> void:
	pos += dir * spd * delta
	if pos > 1.0:
		pos = 1.0
		dir = -1.0
	elif pos < 0.0:
		pos = 0.0
		dir = 1.0


func _strike() -> void:
	if done:
		return
	tries += 1
	var ok := absf(pos - zone_c) <= zone / 2.0
	marks.append({"p": pos, "ok": ok})
	if ok:
		hits += 1
		zone_c = rnd.randf_range(0.2, 0.8)  # 다음 호흡점
		spd *= 1.08
	result_quality = float(hits) / float(maxi(1, tries))
	if hits >= hits_need:
		_end(true)
	elif attempts - tries < hits_need - hits:
		_end(false)


func _gui_input(ev: InputEvent) -> void:
	if (ev is InputEventKey and ev.pressed and not ev.echo and ev.keycode == KEY_SPACE) or (ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT):
		_strike()
		accept_event()


func _draw_game() -> void:
	var w := size.x * 0.7
	var x := (size.x - w) / 2.0
	var y := size.y / 2.0
	draw_rect(Rect2(x, y, w, 30), Color(0.2, 0.18, 0.15))
	draw_rect(Rect2(x + w * (zone_c - zone / 2.0), y, w * zone, 30), Color(0.95, 0.75, 0.2))
	for m in marks:
		draw_line(Vector2(x + w * float(m["p"]), y - 8), Vector2(x + w * float(m["p"]), y + 38), Color(0.4, 1, 0.4) if m["ok"] else Color(1, 0.3, 0.3), 3)
	draw_rect(Rect2(x + w * pos - 4, y - 14, 8, 58), Color.WHITE)
	_draw_center_text("명중 %d/%d · 남은 기회 %d" % [hits, hits_need, attempts - tries], y + 100, 26, Color.WHITE)
