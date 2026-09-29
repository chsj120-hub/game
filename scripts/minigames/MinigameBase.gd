class_name MinigameBase
extends Control
## 4대 전투 미니게임 공통 베이스. 성공/실패를 finished 로 알린다.
## 결과 효과는 17_instances.json minigames.<type>.effects 가 CTBEngine.set_minigame 으로 적용한다.

signal finished(success: bool)

var title: String = ""
var instruction: String = ""
var time_limit: float = 15.0
var time_left: float = 15.0
var done: bool = false
var font: Font


static func create(kind: String, cfg: Dictionary, variant: String = "") -> MinigameBase:
	var mg: MinigameBase
	match kind:
		"archery": mg = load("res://scripts/minigames/ArcheryMinigame.gd").new()
		"bagua": mg = load("res://scripts/minigames/BaguaMinigame.gd").new()
		"ssireum": mg = load("res://scripts/minigames/SsireumMinigame.gd").new()
		"rhythm": mg = load("res://scripts/minigames/RhythmMinigame.gd").new()
		_: return null
	mg.title = String(cfg.get("name", kind)) + ("" if variant == "" else " — " + variant)
	mg.time_limit = float(cfg.get("time_limit", 15))
	return mg


const IMPL := {
	"archery": "res://scripts/minigames/ArcheryMinigame.gd", "bagua": "res://scripts/minigames/BaguaMinigame.gd",
	"ssireum": "res://scripts/minigames/SsireumMinigame.gd", "rhythm": "res://scripts/minigames/RhythmMinigame.gd",
	"quiz": "res://scripts/minigames/QuizMinigame.gd", "gauge": "res://scripts/minigames/GaugeMinigame.gd",
	"sliding": "res://scripts/minigames/SlidingMinigame.gd", "trace": "res://scripts/minigames/TraceMinigame.gd",
	"rubbing": "res://scripts/minigames/RubbingMinigame.gd", "timing": "res://scripts/minigames/TimingMinigame.gd",
}

var params: Dictionary = {}


## 21 시트 카탈로그 id 로 생성. 제한시간 = time × (1 + 0.03 × 해당 지식 랭크)
static func create_from_catalog(mg_id: String) -> MinigameBase:
	var row := DataDB.minigame(mg_id)
	if row.is_empty() or not IMPL.has(String(row.get("impl", ""))):
		push_warning("미니게임 정의 없음: " + mg_id)
		return null
	var mg: MinigameBase = load(IMPL[row["impl"]]).new()
	mg.title = String(row.get("name", mg_id))
	mg.params = row.get("params", {})
	var k := String(row.get("knowledge", "sa"))
	var bonus := float(DataDB.classes_doc.get("life_effects", {}).get("sa", {}).get("puzzle_time", 0.03))
	mg.time_limit = float(row.get("time", 20)) * (1.0 + bonus * int(GameState.party_knowledge().get(k, 0)))
	return mg


func _ready() -> void:
	font = ThemeDB.fallback_font
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_ALL
	time_left = time_limit
	grab_focus()
	_setup()


func _setup() -> void:
	pass


func _process(delta: float) -> void:
	if done:
		return
	time_left -= delta
	_tick(delta)
	if time_left <= 0.0:
		_end(_on_timeout())
	queue_redraw()


func _tick(_delta: float) -> void:
	pass


## 시간 초과 시 성공 여부 판정 (기본: 실패)
func _on_timeout() -> bool:
	return false


func _end(success: bool) -> void:
	if done:
		return
	done = true
	queue_redraw()
	await get_tree().create_timer(0.9).timeout
	finished.emit(success)
	queue_free()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.04, 0.03, 0.82))
	draw_string(font, Vector2(40, 60), title, HORIZONTAL_ALIGNMENT_LEFT, -1, 34, Color(1, 0.9, 0.6))
	draw_string(font, Vector2(40, 100), instruction, HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(0.9, 0.9, 0.85))
	var bar_w := size.x - 80.0
	draw_rect(Rect2(40, 118, bar_w, 10), Color(0.2, 0.2, 0.2))
	draw_rect(Rect2(40, 118, bar_w * clampf(time_left / time_limit, 0, 1), 10), Color(0.85, 0.3, 0.2))
	draw_string(font, Vector2(size.x - 160, 60), "%.1f초" % maxf(time_left, 0), HORIZONTAL_ALIGNMENT_LEFT, -1, 28, Color.WHITE)
	_draw_game()
	if done:
		draw_string(font, Vector2(size.x / 2 - 120, size.y / 2), "종료", HORIZONTAL_ALIGNMENT_LEFT, -1, 48, Color.YELLOW)


func _draw_game() -> void:
	pass


func _draw_center_text(text: String, y: float, fs: int, col: Color) -> void:
	var w := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	draw_string(font, Vector2((size.x - w) / 2.0, y), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, col)
