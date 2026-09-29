extends MinigameBase
## 4. 벽사 진언 타격 (제령 리듬 액션) — 4레인(D F J K)으로 떨어지는 방울/목탁 비트를 판정선에서 입력.
## 명중률 70% 이상 성공: 원혼 즉시 성불(비보스) 또는 적 공격력 50% 약화

const LANES := [KEY_D, KEY_F, KEY_J, KEY_K]
const LANE_LABEL := ["D 방울", "F 목탁", "J 징", "K 방울"]
const FALL_TIME := 1.6
const HIT_WINDOW := 0.14
const NEED_RATE := 0.7
var notes: Array = []   ## [{lane, t, state}] t=판정선 도달 시각, state 0 대기 1 명중 2 놓침
var elapsed := 0.0
var hits := 0
var judged := 0


func _setup() -> void:
	instruction = "떨어지는 비트가 판정선에 닿을 때 D·F·J·K 입력 — 명중률 %d%% 이상이면 제령 성공" % int(NEED_RATE * 100)
	var r := RandomNumberGenerator.new()
	r.randomize()
	var t := 1.8
	while t < time_limit - 1.0:
		notes.append({"lane": r.randi_range(0, 3), "t": t, "state": 0})
		t += r.randf_range(0.35, 0.7)


func _tick(delta: float) -> void:
	elapsed += delta
	for n in notes:
		if n["state"] == 0 and elapsed - float(n["t"]) > HIT_WINDOW:
			n["state"] = 2
			judged += 1
	if judged >= notes.size():
		_end(_rate() >= NEED_RATE)


func _rate() -> float:
	return float(hits) / maxf(1.0, float(notes.size()))


func _on_timeout() -> bool:
	return _rate() >= NEED_RATE


func _gui_input(ev: InputEvent) -> void:
	if done or not (ev is InputEventKey) or not ev.pressed or ev.echo:
		return
	var lane := LANES.find(ev.keycode)
	if lane < 0:
		return
	for n in notes:
		if n["state"] == 0 and n["lane"] == lane and absf(elapsed - float(n["t"])) <= HIT_WINDOW:
			n["state"] = 1
			hits += 1
			judged += 1
			break
	accept_event()


func _draw_game() -> void:
	var lane_w := 140.0
	var x0 := (size.x - lane_w * 4) / 2.0
	var top := 150.0
	var judge_y := size.y - 90.0
	for i in 4:
		draw_rect(Rect2(x0 + i * lane_w, top, lane_w - 6, judge_y - top + 30), Color(0.12, 0.1, 0.08))
		draw_string(font, Vector2(x0 + i * lane_w + 20, judge_y + 60), LANE_LABEL[i], HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)
	draw_line(Vector2(x0, judge_y), Vector2(x0 + lane_w * 4, judge_y), Color(1, 0.85, 0.3), 4)
	for n in notes:
		if n["state"] != 0:
			continue
		var dt := float(n["t"]) - elapsed
		if dt > FALL_TIME:
			continue
		var y := judge_y - (dt / FALL_TIME) * (judge_y - top)
		draw_circle(Vector2(x0 + n["lane"] * lane_w + lane_w / 2.0 - 3, y), 22, Color(0.95, 0.8, 0.3))
	draw_string(font, Vector2(40, size.y - 30), "명중 %d / %d  (%.0f%%)" % [hits, notes.size(), _rate() * 100], HORIZONTAL_ALIGNMENT_LEFT, -1, 24, Color.WHITE)
