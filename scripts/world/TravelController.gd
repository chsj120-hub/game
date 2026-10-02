class_name TravelController
extends Node
## 실시간 행군: 경로(legs)를 최종 속도(px/s)로 이동, 10리(200px)마다 생존 틱·조우 판정,
## 거점 노드 5px 이내 도달 시 정지 → [거점 진입]/[외곽 통과] 분기. Space 긴급 정지(Main 에서 호출).
## 마스크맵(res://assets/maps/masks/map_nn_mask.png)이 있으면 픽셀 샘플링으로 지형·위험도 판정, 없으면 간선 속성 사용.

signal arrived(node_id: String, is_final: bool)
signal encounter(waves: Array, near_node: String)
signal stopped(reason: String)
signal progress_changed

const SETTLEMENT_TYPES := ["city", "town", "station", "temple", "spring", "fort"]

var legs: Array = []
var leg_i: int = 0
var leg_px: float = 0.0          ## 현재 구간 진행 px
var tick_acc: float = 0.0
var moving: bool = false
var fast_forward: float = 1.0
var pos: Vector2 = Vector2.ZERO  ## 권역 지도 좌표(국경 구간은 보간)
var walked_total: float = 0.0    ## 패럴랙스 스크롤용 누적 px
var speed_now: float = 0.0
var terrain_now: String = "road"
var danger_now: float = 0.0
var _mask_cache: Dictionary = {} ## region -> Image | null
var _minute_acc: float = 0.0


## 필드 행군 배율 (전투와 분리): 처음 길 ×field_pace_mult, 지나 본 간선 ×known_road_pace_mult
func pace_mult(leg: Dictionary) -> float:
	var mv: Dictionary = DataDB.overview.get("movement", {})
	var m := float(mv.get("field_pace_mult", 1.0)) * float(Settings.get_value("march_speed"))
	if GameState.walked_edges.has(_edge_key(leg)):
		m *= float(mv.get("known_road_pace_mult", 1.0))
	return m


func _edge_key(leg: Dictionary) -> String:
	var a := String(leg["from"])
	var b := String(leg["to"])
	return a + "|" + b if a < b else b + "|" + a


func px_per_li() -> float:
	return float(DataDB.docs.get("regions.json", {}).get("px_per_li", 20.0))


func start(path: Array) -> void:
	legs = path
	leg_i = 0
	leg_px = 0.0
	tick_acc = 0.0
	moving = not legs.is_empty()
	pos = DataDB.node_pos(GameState.current_node)
	GameState.inside_node = false
	if moving:
		GameState.note("행군 시작 — %s (%.0f리)" % [DataDB.display_name(String(legs[-1]["to"])), TravelSystem.path_li(legs)])
		_begin_leg()


func stop(reason: String = "user") -> void:
	if not moving:
		return
	moving = false
	if reason == "user":
		GameState.note("긴급 정지 — 현 위치(%s 부근)에서 멈췄습니다." % DataDB.display_name(String(legs[leg_i]["from"]) if leg_i < legs.size() else GameState.current_node))
	stopped.emit(reason)


func resume() -> void:
	if leg_i < legs.size():
		moving = true


func remaining_li() -> float:
	var t := 0.0
	for i in range(leg_i, legs.size()):
		t += float(legs[i].get("li", 0.0))
	return t - leg_px / px_per_li()


func _leg() -> Dictionary:
	return legs[leg_i]


## 뱃길 구간은 즉시 처리(요금·일수)
func _begin_leg() -> void:
	while leg_i < legs.size() and String(_leg()["kind"]) == "ferry":
		var err := TravelSystem.ferry(_leg())
		if err != "":
			GameState.note(err)
			stop("ferry")
			return
		var to := String(_leg()["to"])
		leg_i += 1
		TravelSystem.arrive(to, false)
		pos = DataDB.node_pos(to)
		if leg_i >= legs.size():
			moving = false
			arrived.emit(to, true)
			return


func _process(delta: float) -> void:
	if not moving or leg_i >= legs.size():
		return
	var leg := _leg()
	var from_p := DataDB.node_pos(String(leg["from"]))
	var to_p := DataDB.node_pos(String(leg["to"]))
	var length := float(leg["li"]) * px_per_li()
	_sample_mask(String(leg["kind"]))
	terrain_now = terrain_now if terrain_now != "" else String(leg["terrain"])
	speed_now = SurvivalSystem.speed_now(terrain_now)
	if speed_now <= 0.0:
		stop("exhausted")
		return
	var step := speed_now * delta * fast_forward * pace_mult(leg)
	leg_px += step
	walked_total += step
	tick_acc += step
	# 게임 시간은 '실제 속도'(배율 제외) 기준 거리로 계산 — 화면 배율을 바꿔도 하루 이동 거리는 동일
	_minute_acc += step / speed_now * float(DataDB.overview.get("movement", {}).get("game_minutes_per_walk_second", 24))
	if _minute_acc >= 1.0:
		GameState.advance_minutes(int(_minute_acc))
		_minute_acc -= float(int(_minute_acc))
	if String(leg["kind"]) == "border":
		pos = from_p.lerp(to_p, clampf(leg_px / maxf(length, 1.0), 0.0, 1.0)) if DataDB.region_of_node(String(leg["from"])) == DataDB.region_of_node(String(leg["to"])) else from_p
	else:
		pos = from_p.lerp(to_p, clampf(leg_px / maxf(length, 1.0), 0.0, 1.0))
	var tick_px := float(DataDB.overview.get("survival", {}).get("tick_li", 10)) * px_per_li()
	while tick_acc >= tick_px and moving:
		tick_acc -= tick_px
		_on_tick(String(leg["from"]))
	progress_changed.emit()
	if not moving:
		return
	var arrive_px := float(DataDB.overview.get("movement", {}).get("arrive_distance_px", 5.0))
	if length - leg_px <= arrive_px:
		_reach_node(String(leg["to"]))


func _on_tick(near: String) -> void:
	var r := SurvivalSystem.tick(terrain_now)
	if r["stop"]:
		stop(String(r["reason"]))
		return
	_rumor()
	var hazard := String(DataDB.get_row(near).get("type", "")) == "hazard"
	if GameState.rng.randf() < TravelSystem.encounter_chance(terrain_now, danger_now, hazard):
		var waves := TravelSystem.roll_encounter(terrain_now, near)
		if not waves.is_empty():
			moving = false
			encounter.emit(waves, near)


func _reach_node(node_id: String) -> void:
	GameState.walked_edges[_edge_key(legs[leg_i])] = true
	leg_i += 1
	leg_px = 0.0
	pos = DataDB.node_pos(node_id)
	var final := leg_i >= legs.size()
	var t := String(DataDB.get_row(node_id).get("type", ""))
	TravelSystem.arrive(node_id, false)
	if final or t in SETTLEMENT_TYPES:
		moving = false
		arrived.emit(node_id, final)
		return
	_begin_leg()


## 행군 중 소문: 주변 은닉지를 탐색 없이 가끔 발견
func _rumor() -> void:
	var r: Dictionary = DataDB.overview.get("facilities", {}).get("rumor", {})
	var sa := int(GameState.party_knowledge().get("sa", 0))
	var rad := (float(r.get("radius_li", 8)) + float(r.get("radius_li_per_sa", 1)) * sa) * px_per_li()
	var ch := float(r.get("chance_per_tick", 0.12)) + float(r.get("chance_per_sa", 0.02)) * sa
	for n in DataDB.nodes_in(GameState.current_region):
		if n.get("hidden", false) and not GameState.discovered.has(n["id"]) and pos.distance_to(DataDB.node_pos(n["id"])) <= rad:
			if GameState.rng.randf() < ch:
				GameState.note("길손들의 소문 — 근처에 「%s」 이(가) 있다고 한다." % n["name"])
				GameState.discover(n["id"])
			return


## 외곽 통과 선택 시 계속
func continue_march() -> void:
	if leg_i < legs.size():
		moving = true
		_begin_leg()


# ------------------------------------------------------------ 마스크맵 (완전판 2.2 → 채널 인코딩 보정안)
## R: 0–31 통행불가 · 32–95 수계 · 96–191 산악 · 192–255 평지/관로  |  G: 위험도(0~255)  |  B: ≥128 나루·도하 지점
func _sample_mask(kind: String) -> void:
	terrain_now = ""
	danger_now = 0.0
	if kind == "border" or kind == "ferry":
		return
	var reg := GameState.current_region
	if not _mask_cache.has(reg):
		var path := String(DataDB.get_row(reg).get("mask_texture", ""))
		var img: Image = null
		if path != "" and ResourceLoader.exists(path):
			var tex: Texture2D = load(path)
			img = tex.get_image()
		_mask_cache[reg] = img
	var im = _mask_cache[reg]
	if im == null:
		return
	var ms: Array = DataDB.docs.get("regions.json", {}).get("map_size", [3840, 2160])
	var x := clampi(int(pos.x / float(ms[0]) * im.get_width()), 0, im.get_width() - 1)
	var y := clampi(int(pos.y / float(ms[1]) * im.get_height()), 0, im.get_height() - 1)
	var c: Color = im.get_pixel(x, y)
	var r := int(c.r8)
	if r < 32:
		terrain_now = "mountain"  # 통행불가 픽셀 위 간선은 험로로 취급(데이터 간선 우선)
	elif r < 96:
		terrain_now = "water"
	elif r < 192:
		terrain_now = "mountain"
	else:
		terrain_now = "road"
	danger_now = c.g
