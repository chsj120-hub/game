extends MinigameBase
## 3. 백병전 맞잡이 (씨름·일기토 QTE) — 스페이스 연타로 샅바 게이지를 채우고, 쳐내기 프롬프트(방향키)를 제때 입력.
## 성공: 적 전열 강제 기절 2턴 + 진형 붕괴

const DECAY := 14.0      ## 초당 게이지 감소
const MASH_GAIN := 4.5
const PROMPT_WINDOW := 0.9
const DIRS := {KEY_LEFT: "←", KEY_RIGHT: "→", KEY_UP: "↑", KEY_DOWN: "↓"}
var gauge := 20.0
var prompt_key := 0
var prompt_left := 0.0
var next_prompt := 1.5
var rnd := RandomNumberGenerator.new()
var feedback := ""


func _setup() -> void:
	instruction = "[스페이스] 연타로 샅바를 당기고, 화면에 뜨는 방향키로 쳐내기! 게이지 100 도달 시 승리"
	rnd.randomize()


func _tick(delta: float) -> void:
	gauge = maxf(0.0, gauge - DECAY * delta)
	if prompt_key != 0:
		prompt_left -= delta
		if prompt_left <= 0.0:
			prompt_key = 0
			gauge = maxf(0.0, gauge - 20.0)
			feedback = "쳐내기 실패! 샅바를 놓침"
	else:
		next_prompt -= delta
		if next_prompt <= 0.0:
			var keys := DIRS.keys()
			prompt_key = keys[rnd.randi_range(0, keys.size() - 1)]
			prompt_left = PROMPT_WINDOW
			next_prompt = rnd.randf_range(1.2, 2.2)


func _on_timeout() -> bool:
	return gauge >= 100.0


func _gui_input(ev: InputEvent) -> void:
	if done or not (ev is InputEventKey) or not ev.pressed or ev.echo:
		return
	if ev.keycode == KEY_SPACE:
		gauge = minf(100.0, gauge + MASH_GAIN)
	elif DIRS.has(ev.keycode):
		if ev.keycode == prompt_key:
			gauge = minf(100.0, gauge + 15.0)
			feedback = "쳐내기 성공!"
		else:
			gauge = maxf(0.0, gauge - 10.0)
			feedback = "헛손질!"
		prompt_key = 0
	accept_event()
	if gauge >= 100.0:
		_end(true)


func _draw_game() -> void:
	var w := size.x * 0.6
	var x := (size.x - w) / 2.0
	var y := size.y / 2.0
	draw_rect(Rect2(x, y, w, 40), Color(0.2, 0.2, 0.2))
	draw_rect(Rect2(x, y, w * gauge / 100.0, 40), Color(0.9, 0.6, 0.2))
	_draw_center_text("샅바 게이지 %d / 100" % int(gauge), y - 16, 26, Color.WHITE)
	if prompt_key != 0:
		_draw_center_text(String(DIRS[prompt_key]), y + 150, 96, Color(1, 0.3, 0.3))
	_draw_center_text(feedback, y + 200, 24, Color(1, 1, 0.6))
