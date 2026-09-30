class_name TravelSystem
extends RefCounted
## 노드 그래프 경로 탐색 (권역 내 도로·오솔길 / 국경 링크 / 나루터 뱃길 / 이벤트 우회로)
## 제약: 미발견 은닉 노드 통과 불가, 수계(water) 구간은 수상·비행 탈것 필요, 이벤트 봉쇄 노드 우회, 군사관문 검문.

const FERRY_COST_PER_DAY := 120.0  ## 경로 비용 환산(리)


static func leg_passable(leg: Dictionary, dest: String) -> String:
	var to := String(leg["to"])
	if not GameState.node_visible(to) and to != dest:
		return "미발견"
	if not GameState.node_visible(to) and to == dest:
		return "미발견"
	if String(leg["terrain"]) == "water" and String(leg["kind"]) != "ferry" and not GameState.has_water_mount():
		return "선박 필요"
	if to in EventSystem.blocked_nodes():
		return "봉쇄"
	if String(DataDB.get_row(to).get("type", "")) == "fort" and to != dest and checkpoint_block(to) != "":
		return "검문"
	return ""


static func checkpoint_block(node_id: String) -> String:
	var cp: Dictionary = DataDB.overview.get("facilities", {}).get("checkpoint", {})
	if not DataDB.node_has(node_id, "checkpoint"):
		return ""
	if GameState.rank >= int(cp.get("min_rank", 3)) or GameState.has_item(String(cp.get("pass_item", ""))):
		return ""
	return "군사관문 검문: 신분 Rank %d 이상 또는 통행증 필요" % int(cp.get("min_rank", 3))


static func _cost(leg: Dictionary) -> float:
	if String(leg["kind"]) == "ferry":
		return float(leg.get("days", 1)) * FERRY_COST_PER_DAY
	var t := float(DataDB.overview.get("movement", {}).get("terrain", {}).get(String(leg["terrain"]), 1.0))
	return float(leg["li"]) / maxf(0.3, t)


## Dijkstra → legs [{from, to, li, terrain, kind, fare, days, wind}] (실패 시 [])
static func find_path(from: String, to: String) -> Array:
	if from == to:
		return []
	var dist := {from: 0.0}
	var prev := {}
	var heap := [[0.0, from]]  # 이진 힙 [거리, 노드] — 노드 760여 곳에서 O(E log V)
	var done := {}
	while heap.size() > 0:
		var top: Array = _heap_pop(heap)
		var cur: String = top[1]
		if cur == to:
			break
		if done.has(cur):
			continue
		done[cur] = true
		for leg in DataDB.neighbors(cur):
			if leg_passable(leg, to) != "":
				continue
			var nx := String(leg["to"])
			var nd := float(dist[cur]) + _cost(leg)
			if not dist.has(nx) or nd < float(dist[nx]):
				dist[nx] = nd
				prev[nx] = {"from": cur, "leg": leg}
				_heap_push(heap, [nd, nx])
	if not prev.has(to):
		return []
	var legs := []
	var c := to
	while c != from:
		var p: Dictionary = prev[c]
		var leg: Dictionary = p["leg"].duplicate()
		leg["from"] = p["from"]
		legs.push_front(leg)
		c = String(p["from"])
	return legs


static func _heap_push(h: Array, item: Array) -> void:
	h.append(item)
	var i := h.size() - 1
	while i > 0:
		var p := (i - 1) >> 1
		if float(h[p][0]) <= float(h[i][0]):
			break
		var t = h[p]
		h[p] = h[i]
		h[i] = t
		i = p


static func _heap_pop(h: Array) -> Array:
	var top: Array = h[0]
	var last: Array = h.pop_back()
	if h.size() > 0:
		h[0] = last
		var i := 0
		var n := h.size()
		while true:
			var l := 2 * i + 1
			var r := l + 1
			var m := i
			if l < n and float(h[l][0]) < float(h[m][0]):
				m = l
			if r < n and float(h[r][0]) < float(h[m][0]):
				m = r
			if m == i:
				break
			var t = h[m]
			h[m] = h[i]
			h[i] = t
			i = m
	return top


static func path_li(legs: Array) -> float:
	var t := 0.0
	for l in legs:
		t += float(l.get("li", 0.0))
	return t


static func path_fare(legs: Array) -> int:
	var t := 0
	for l in legs:
		t += int(l.get("fare", 0))
	return t


## 예상 소요(분): 현재 조건 속도 기준 (뱃길은 days)
static func eta_minutes(legs: Array) -> int:
	var m := 0.0
	var per_sec := float(DataDB.overview.get("movement", {}).get("game_minutes_per_walk_second", 24))
	var ppl := float(DataDB.docs.get("regions.json", {}).get("px_per_li", 20.0))
	for l in legs:
		if String(l["kind"]) == "ferry":
			m += float(l.get("days", 1)) * 1440.0
		else:
			var v := SurvivalSystem.speed_now(String(l["terrain"]))
			m += (float(l["li"]) * ppl / maxf(v, 1.0)) * per_sec
	return int(m)


## 역참 간 쾌속 이동(경유지 이벤트 스킵, 엽전·시간 소모)
static func station_fast_travel(to_station: String) -> String:
	var gs := GameState
	if not DataDB.node_has(gs.current_node, "yeokcham") or not DataDB.node_has(to_station, "yeokcham"):
		return "역참 간에만 쾌속 이동 가능"
	var legs := find_path(gs.current_node, to_station)
	if legs.is_empty():
		return "경로 없음"
	for l in legs:
		if String(l["kind"]) == "ferry":
			return "뱃길이 포함된 경로는 쾌속 이동 불가"
	var cfg: Dictionary = DataDB.overview.get("movement", {}).get("station_fast_travel", {})
	var li := path_li(legs)
	var cost := int(ceil(li * float(cfg.get("money_per_li", 0.4)) * maxf(0.2, 1.0 - Balance.dev_benefit("fast_travel_discount", gs.current_node))))
	if not gs.spend_money(cost):
		return "역마 삯 부족"
	gs.advance_minutes(int(eta_minutes(legs) * float(cfg.get("time_ratio", 0.3))))
	gs.fatigue = minf(100.0, gs.fatigue + li * 0.05)
	arrive(to_station, true)
	gs.note("역마 쾌속 이동 %.0f리 (−%d냥)" % [li, cost])
	return ""


## 나루터 뱃길 (풍향: 폭풍우면 결항, 비면 요금 1.5배)
static func ferry(leg: Dictionary) -> String:
	var gs := GameState
	var f: Dictionary = DataDB.overview.get("facilities", {}).get("ferry", {})
	if leg.get("wind", false) and gs.weather in f.get("wind_cancel_weather", ["storm"]):
		return "풍랑으로 결항 — 날씨가 개면 다시 오세요"
	var fare := int(leg.get("fare", 0))
	if gs.weather == "rain":
		fare = int(fare * float(f.get("fare_mult_rain", 1.5)))
	var per_sang := float(f.get("sang_discount_per_rank", 0.0))  # 상(商) 지식 랭크당 뱃삯 할인(제주 등 원거리 해로)
	if per_sang > 0.0:
		fare = int(fare * maxf(0.5, 1.0 - per_sang * float(gs.knowledge.get("sang", 0))))
	if not gs.spend_money(fare):
		return "뱃삯 부족"
	gs.advance_minutes(int(leg.get("days", 1)) * 1440)
	gs.note("뱃길 %d일 (−%d냥)" % [int(leg.get("days", 1)), fare])
	return ""


## 노드 도착 처리 (권역 변경·신선도·동선 큐·이벤트·화첩 트리거)
static func arrive(node_id: String, enter: bool) -> void:
	var gs := GameState
	var prev_region := gs.current_region
	gs.current_node = node_id
	gs.current_region = DataDB.region_of_node(node_id)
	gs.inside_node = enter
	gs.decay_freshness()
	if not gs.visited_nodes.has(node_id):
		gs.visited_nodes[node_id] = true
	if gs.current_region != prev_region:
		gs.note("%s 권역에 들어섰습니다." % DataDB.display_name(gs.current_region))
	RouteQueue.on_node_visited(node_id)
	EventSystem.on_node(node_id)
	gs.node_changed.emit(node_id)
	gs.stats_changed.emit()


## 조우 확률 (10리당)
static func encounter_chance(terrain: String, danger_mask: float, at_hazard: bool) -> float:
	var e: Dictionary = DataDB.overview.get("movement", {}).get("encounter", {})
	var c := float(e.get("base_per_10li", 0.04))
	if terrain == "mountain":
		c += float(e.get("mountain_add", 0.15))
	if GameState.is_night():
		c += float(e.get("night_add", 0.05))
	c += danger_mask * float(e.get("mask_danger_max_add", 0.1))
	if at_hazard:
		c += float(e.get("hazard_node_add", 0.25))
	return clampf(c, 0.0, 0.8)


## 출현 조건(권역·지형·시간·절기·노드) 에 맞는 일반 적 웨이브 생성
static func roll_encounter(terrain: String, near_node: String) -> Array:
	var gs := GameState
	var pool := []
	for e in DataDB.table("12_enemies.json", "enemies"):
		if int(e.get("boss_tier", 0)) > 0:
			continue
		if absi(int(e["tier"]) - gs.rank) > 1:
			continue
		var sc: Dictionary = e.get("spawn_conditions", {})
		var regs: Array = sc.get("regions", ["*"])
		if not ("*" in regs or gs.current_region in regs):
			continue
		var nodes: Array = sc.get("nodes", [])
		if not nodes.is_empty() and not (near_node in nodes):
			continue
		var terrs: Array = sc.get("terrains", [])
		if not terrs.is_empty() and not (terrain in terrs) and not ("village_outskirt" in terrs and terrain == "road"):
			continue
		var t := String(sc.get("allowed_time", "ANY"))
		if t == "NIGHT_ONLY" and not gs.is_night():
			continue
		var st: Array = sc.get("seasonal_trigger", [])
		if not st.is_empty() and not (gs.solar_term() in st):
			continue
		pool.append(e["id"])
	if pool.is_empty():
		return []
	var wave := []
	for i in gs.rng.randi_range(1, 3):
		wave.append(pool[gs.rng.randi_range(0, pool.size() - 1)])
	return [wave]
