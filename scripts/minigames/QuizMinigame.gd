extends MinigameBase
## 논리·문답형 공용: 자모 조합 · 연표 배치 · 산학 주판 · 암행어사 심판 · 사자성어 · 유불선 문답 · 도깨비 수수께끼 · 제향 진설
## params.bank[{q, options[], answer}] 에서 무작위 출제, params.need 문항 연속 정답 시 성공(오답 1회까지 허용).

var questions: Array = []
var order: Array = []   ## 보기 섞은 순서
var qi := 0
var correct := 0
var wrong := 0
var need := 3
var feedback := ""
var buttons: Array = []


func _setup() -> void:
	var bank: Array = params.get("bank", []).duplicate()
	bank.shuffle()
	need = mini(int(params.get("need", 3)), bank.size())
	questions = bank.slice(0, mini(bank.size(), need + 1))
	instruction = "정답을 고르세요 — %d문항 정답 시 성공(오답 1회 허용). %s" % [need, String(params.get("note", ""))]
	_show()


func _show() -> void:
	for b in buttons:
		b.queue_free()
	buttons.clear()
	if qi >= questions.size():
		_end(correct >= need)
		return
	var q: Dictionary = questions[qi]
	order = range(q["options"].size())
	order.shuffle()
	for i in order.size():
		var b := Button.new()
		b.text = "%d. %s" % [i + 1, q["options"][order[i]]]
		b.position = Vector2(80, 260 + i * 64)
		b.custom_minimum_size = Vector2(760, 52)
		b.add_theme_font_size_override("font_size", 22)
		b.pressed.connect(_pick.bind(order[i]))
		add_child(b)
		buttons.append(b)


func _pick(opt: int) -> void:
	if done:
		return
	var q: Dictionary = questions[qi]
	if opt == int(q["answer"]):
		correct += 1
		feedback = "정답!"
	else:
		wrong += 1
		feedback = "오답 — 정답: %s" % q["options"][int(q["answer"])]
		if wrong > 1:
			_end(false)
			return
	qi += 1
	if correct >= need:
		_end(true)
		return
	_show()


func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventKey and ev.pressed and not ev.echo:
		var k: int = ev.keycode - KEY_1
		if k >= 0 and k < order.size():
			_pick(order[k])
			accept_event()


func _draw_game() -> void:
	if qi < questions.size():
		draw_string(font, Vector2(80, 210), "문항 %d — %s" % [qi + 1, questions[qi]["q"]], HORIZONTAL_ALIGNMENT_LEFT, size.x - 160, 26, Color(1, 0.95, 0.8))
	draw_string(font, Vector2(80, size.y - 40), "정답 %d/%d   %s" % [correct, need, feedback], HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color(0.9, 0.9, 0.6))
