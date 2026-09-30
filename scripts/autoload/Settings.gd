extends Node
## 설정(게임 진행과 별도 저장: user://settings.json) — 음량·화면·글자 크기·행군 속도·튜토리얼·편의 기능.
## 게임 세이브(user://save.json)와 분리되어, 새 게임·불러오기와 무관하게 유지된다.

const PATH := "user://settings.json"
const DEFAULTS := {
	"master_volume": 0.8,     ## 0~1 (Master 버스)
	"bgm_volume": 0.7,        ## 0~1 (BGM 버스가 있을 때)
	"sfx_volume": 0.8,        ## 0~1 (SFX 버스가 있을 때)
	"fullscreen": false,
	"ui_scale": 1.0,          ## 0.9 / 1.0 / 1.15 / 1.3 — 전체 화면 배율(content_scale_factor)
	"march_speed": 1.0,       ## 필드 행군 화면 속도 배율 0.75~1.5 (게임 시간·피로는 거리 기준이라 불변)
	"fast_forward": 3.0,      ## [빨리] 버튼 배속 2 / 3 / 4
	"tutorial": true,         ## 튜토리얼 안내 창 표시
	"auto_eat": true,         ## 새 게임 기본값(배낭에서 언제든 전환)
	"confirm_substitute": "confirm",  ## 새 게임 기본 상위 재료 대체: off | confirm | auto
	"log_lines": 200,         ## 기록창 보관 줄 수
}

## 설정 메뉴 표시용: [키, 이름, 선택지(순환), 설명]
const OPTIONS := [
	["master_volume", "전체 음량", [0.0, 0.25, 0.5, 0.8, 1.0], "모든 소리의 크기"],
	["bgm_volume", "배경 음악", [0.0, 0.25, 0.5, 0.7, 1.0], "BGM 버스 음량(음원을 넣으면 적용)"],
	["sfx_volume", "효과음", [0.0, 0.25, 0.5, 0.8, 1.0], "SFX 버스 음량(음원을 넣으면 적용)"],
	["fullscreen", "전체 화면", [false, true], "창 모드 / 전체 화면"],
	["ui_scale", "화면 배율(글자 크기)", [0.9, 1.0, 1.15, 1.3], "UI 전체를 키우거나 줄입니다"],
	["march_speed", "행군 화면 속도", [0.75, 1.0, 1.25, 1.5], "걷는 화면 속도만 바뀝니다(게임 시간·피로는 거리 기준)"],
	["fast_forward", "[빨리] 배속", [2.0, 3.0, 4.0], "대시보드 [빨리] 버튼의 배속"],
	["tutorial", "튜토리얼 안내", [true, false], "화면 오른쪽 위 안내 창"],
	["auto_eat", "자동 섭취(새 게임)", [true, false], "포만 30 아래에서 배낭 음식 자동 섭취"],
	["confirm_substitute", "상위 재료 대체(새 게임)", ["confirm", "auto", "off"], "확인 = 2등급 이상 높은 재료가 쓰일 때 묻기"],
	["log_lines", "기록창 보관 줄 수", [100, 200, 500], "오래된 기록부터 지웁니다"],
]

var data: Dictionary = {}

signal changed(key: String)


func _ready() -> void:
	load_settings()
	apply_all()


func get_value(key: String):
	return data.get(key, DEFAULTS.get(key))


func set_value(key: String, v) -> void:
	data[key] = v
	save_settings()
	apply(key)
	changed.emit(key)


## 선택지 순환(설정 메뉴 버튼)
func cycle(key: String) -> void:
	for o in OPTIONS:
		if o[0] == key:
			var opts: Array = o[2]
			var i := opts.find(get_value(key))
			set_value(key, opts[(i + 1) % opts.size()])
			return


func label(key: String) -> String:
	var v = get_value(key)
	match typeof(v):
		TYPE_BOOL:
			return "켜짐" if v else "꺼짐"
		TYPE_FLOAT:
			if key.ends_with("volume"):
				return "%d%%" % int(round(float(v) * 100))
			return "×%.2f" % float(v)
	if key == "confirm_substitute":
		return {"confirm": "확인", "auto": "자동", "off": "끔"}.get(String(v), String(v))
	return str(v)


func reset() -> void:
	data = DEFAULTS.duplicate()
	save_settings()
	apply_all()


func load_settings() -> void:
	data = DEFAULTS.duplicate()
	if not FileAccess.file_exists(PATH):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	if typeof(d) == TYPE_DICTIONARY:
		for k in d.keys():
			if DEFAULTS.has(k):
				data[k] = d[k]


func save_settings() -> void:
	var f := FileAccess.open(PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data, "\t"))


func apply_all() -> void:
	for k in DEFAULTS.keys():
		apply(k)


func apply(key: String) -> void:
	match key:
		"master_volume", "bgm_volume", "sfx_volume":
			var bus: String = {"master_volume": "Master", "bgm_volume": "BGM", "sfx_volume": "SFX"}[key]
			var idx := AudioServer.get_bus_index(bus)
			if idx >= 0:
				var v := float(get_value(key))
				AudioServer.set_bus_mute(idx, v <= 0.001)
				AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(v, 0.001)))
		"fullscreen":
			if DisplayServer.get_name() != "headless":
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if get_value(key) else DisplayServer.WINDOW_MODE_WINDOWED)
		"ui_scale":
			if get_tree() and get_tree().root:
				get_tree().root.content_scale_factor = float(get_value(key))
