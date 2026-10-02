class_name TutorialSystem
extends RefCounted
## 23 시트 튜토리얼: 시나리오가 지정한 묶음(tutorial)의 단계를 순서대로 안내한다.
## 단계 조건(cond)이 충족되면 자동으로 다음 단계로 넘어간다. ack 단계는 [다음] 버튼으로 넘긴다.
## 진행도는 GameState.tutorial_step(세이브 포함), 표시 여부는 Settings.tutorial.


static func steps(tid: String) -> Array:
	return DataDB.tutorial_steps(tid)


static func active() -> bool:
	return GameState.tutorial_id != "" and GameState.tutorial_step < steps(GameState.tutorial_id).size()


static func current() -> Dictionary:
	if not active():
		return {}
	return steps(GameState.tutorial_id)[GameState.tutorial_step]


## 조건 충족 여부
static func met(cond: Dictionary) -> bool:
	var gs := GameState
	match String(cond.get("type", "ack")):
		"ack":
			return false
		"counter":
			return int(gs.counters.get(String(cond["key"]), 0)) >= int(cond.get("n", 1))
		"visited":
			return gs.visited_nodes.size() >= int(cond.get("n", 1))
		"at_node":
			return gs.current_node == String(cond["node"])
		"has_item":
			return gs.count(String(cond["item"])) >= int(cond.get("n", 1))
		"event_progress":
			var st: Dictionary = gs.events_state.get(String(cond["event"]), {})
			var done := int(st.get("stage", 0))
			if int(st.get("chapter", 0)) > 0 or String(st.get("status", "")) == "done":
				done = 999
			return done >= int(cond.get("n", 1))
	return false


## 현재 단계 조건을 확인해 넘길 수 있는 만큼 넘긴다. 넘겼으면 true
static func check() -> bool:
	var moved := false
	while active() and met(current().get("cond", {})):
		advance()
		moved = true
	return moved


static func advance() -> void:
	var gs := GameState
	var st := current()
	if st.is_empty():
		return
	gs.tutorial_step += 1
	gs.note("【안내 완료】 %s" % st.get("title", ""))
	if not active():
		gs.note("튜토리얼을 모두 마쳤습니다. [도움말]에서 언제든 다시 볼 수 있습니다.")


static func skip_all() -> void:
	GameState.tutorial_step = steps(GameState.tutorial_id).size()
	GameState.note("튜토리얼을 건너뛰었습니다. [도움말]에서 설명을 볼 수 있습니다.")


static func restart() -> void:
	if GameState.tutorial_id == "":
		GameState.tutorial_id = "tut_jeju"
	GameState.tutorial_step = 0


static func progress_text() -> String:
	if not active():
		return ""
	return "%d / %d" % [GameState.tutorial_step + 1, steps(GameState.tutorial_id).size()]
