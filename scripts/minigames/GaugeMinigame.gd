extends MinigameBase
## 환경·균형형 공용: 장경판전 통풍(습도) · 탕약 불조절(온도) · 줄타기(중심추) · 수중 인양(밧줄 장력)
## 값이 drift 로 흔들리고, ←/→ (또는 A/D·마우스 좌/우 버튼 홀드)로 보정. 제한시간 중 band 안에 머문 비율 ≥ hold_ratio 면 성공.

var value := 50.0
var vel := 0.0
var inside_time := 0.0
var total_time := 0.0
var band := Vector2(45, 55)
var drift := 15.0
var control := 40.0
var hold_ratio := 0.65
var label := "값"
var balance_mode := false
var push := 0.0
var noise_t := 0.0


func _setup() -> void:
	var b: Array = params.get("band", [45, 55])
	band = Vector2(float(b[0]), float(b[1]))
	drift = float(params.get("drift", 15))
	control = float(params.get("control", 40))
	hold_ratio = float(params.get("hold_ratio", 0.65))
	label = String(params.get("label", "균형"))
	balance_mode = String(params.get("mode", "hold")) == "balance"
	value = (band.x + band.y) / 2.0
	instruction = "←/→(A/D) 로 %s 을(를) %d~%d 사이에 유지 — 시간의 %d%% 이상 유지 시 성공" % [label, int(band.x), int(band.y), int(hold_ratio * 100)]


func _tick(delta: float) -> void:
	noise_t += delta
	push = 0.0
	if Input.is_key_pressed(KEY_LEFT) or Input.is_key_pressed(KEY_A) or Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
		push -= 1.0
	if Input.is_key_pressed(KEY_RIGHT) or Input.is_key_pressed(KEY_D) or Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		push += 1.0
	var d := sin(noise_t * 1.7) * 0.6 + sin(noise_t * 3.1 + 1.0) * 0.4
	if balance_mode:  # 줄타기: 중심에서 멀어질수록 가속 (역진자)
		vel += ((value - 50.0) * 0.06 + d * drift * 0.1 + push * control * 0.1) * delta * 10.0
		vel *= 0.96
		value += vel * delta
	else:
		value += (d * drift + push * control) * delta
	value = clampf(value, 0.0, 100.0)
	total_time += delta
	if value >= band.x and value <= band.y:
		inside_time += delta
	if balance_mode and (value <= 0.0 or value >= 100.0):
		_end(false)


func _on_timeout() -> bool:
	return total_time > 0.0 and inside_time / total_time >= hold_ratio


func _draw_game() -> void:
	var w := size.x * 0.7
	var x := (size.x - w) / 2.0
	var y := size.y / 2.0
	draw_rect(Rect2(x, y, w, 36), Color(0.2, 0.2, 0.2))
	draw_rect(Rect2(x + w * band.x / 100.0, y, w * (band.y - band.x) / 100.0, 36), Color(0.3, 0.7, 0.35, 0.8))
	var px := x + w * value / 100.0
	draw_rect(Rect2(px - 5, y - 16, 10, 68), Color(1, 0.85, 0.3))
	_draw_center_text("%s %.0f" % [label, value], y - 30, 28, Color.WHITE)
	var ratio := inside_time / maxf(total_time, 0.01)
	_draw_center_text("유지율 %.0f%% (목표 %d%%)" % [ratio * 100, int(hold_ratio * 100)], y + 110, 24, Color(0.9, 1, 0.8) if ratio >= hold_ratio else Color(1, 0.7, 0.6))
