extends Node
## 밸런스 공식 단일 창구. 상수는 전부 00_overview.json (DataDB.overview) 에서 읽는다.
## tools/balance_sim.py(전투) · tools/common.py + economy_sim.py(경제) 가 동일 공식을 미러링한다.


func _cfg(section: String) -> Dictionary:
	return DataDB.overview.get(section, {})


func curve(cfg: Dictionary, tier: int) -> float:
	return float(cfg.get("base", 0)) * pow(float(cfg.get("growth", 1.0)), float(tier - 1))


# ================================================================ 신분
func rank_table() -> Array:
	return _cfg("rank").get("table", [])


func max_rank() -> int:
	return rank_table().size()


func rank_threshold(rank: int) -> int:
	for r in rank_table():
		if int(r["rank"]) == rank:
			return int(r["threshold"])
	return 0


## 명성으로 '심사 가능한' 최고 신분 (실제 승급은 관아 심사)
func rank_for_reputation(reputation: int) -> int:
	var result := 1
	for r in rank_table():
		if reputation >= int(r["threshold"]):
			result = maxi(result, int(r["rank"]))
	return result


func rank_title(rank: int, class_id: String) -> String:
	for r in rank_table():
		if int(r["rank"]) == rank:
			return String(r.get("titles", {}).get(class_id, ""))
	return ""


## 참고 적합식 Threshold(L) ≈ a·(L−1)^k
func rank_formula_value(level: int) -> float:
	var f: Dictionary = _cfg("rank").get("formula", {})
	return 0.0 if level <= 1 else float(f.get("a", 0)) * pow(float(level - 1), float(f.get("k", 1)))


func rank_gift_money(new_rank: int) -> int:
	return int(round(curve(_cfg("rank").get("rank_gift", {}).get("money", {}), new_rank - 1)))


func donate_min_rank(tier: int) -> int:
	return int(_cfg("rank").get("donate_min_rank", {}).get(str(tier), 1))


# ================================================================ 경제 자동 공식
func _econ() -> Dictionary:
	return _cfg("economy")


func rank_gap_mult(tier: int, rank: int) -> float:
	var g: Dictionary = _econ().get("rank_gap", {})
	var gap := tier - rank
	if gap > 0:
		return 1.0 + float(g.get("above_bonus_per_tier", 0.1)) * gap
	return maxf(float(g.get("floor", 0.4)), 1.0 - float(g.get("below_penalty_per_tier", 0.15)) * -gap)


## 유산 보상. choice: discover(답사 명성, 선택 무관) | donate(기증 명성) | sell(매각 엽전)
##  명성 = base·growth^(t−1) × 카테고리 × 은닉 × 신분격차 × (1+0.01·사) × 몫(답사 35% / 기증 65%) × 시설(기증만) × (1±jitter)
##  엽전 = base·growth^(t−1) × 카테고리 × 은닉 × 시설 × (1+0.03·상) × (1±jitter)
func heritage_reward(her: Dictionary, choice: String, venue: String, rank: int, knowledge: Dictionary, rng: RandomNumberGenerator) -> int:
	var e := _econ()
	var key := "money" if choice == "sell" else "rep"
	var cfg: Dictionary = e.get("heritage_" + key, {})
	var tier := int(her.get("tier", 1))
	var v := curve(cfg, tier)
	v *= float(e.get("category_mult", {}).get(String(her.get("category", "")), {}).get(key, 1.0))
	if her.get("hidden", false):
		v *= float(e.get("hidden_mult", 1.0))
	var kb: Dictionary = e.get("knowledge_bonus", {})
	var share := float(e.get("heritage_discovery_share", 0.0))
	if key == "rep":
		v *= rank_gap_mult(tier, rank)
		v *= 1.0 + float(kb.get("sa_rep_per_rank", 0.0)) * int(knowledge.get("sa", 0))
		v *= share if choice == "discover" else 1.0 - share
	else:
		v *= 1.0 + float(kb.get("sang_money_per_rank", 0.0)) * int(knowledge.get("sang", 0))
	if choice != "discover":
		var vn: Dictionary = e.get("venue", {}).get(venue, {})
		var cats: Array = vn.get("categories", [])
		if cats.is_empty() or String(her.get("category", "")) in cats:
			v *= float(vn.get(key, 1.0))
	var j := float(cfg.get("jitter", 0.0))
	v *= rng.randf_range(1.0 - j, 1.0 + j) if rng else 1.0
	return int(round(v))


## 미리보기용 기대값 (jitter 없음)
func heritage_reward_expect(her: Dictionary, choice: String, venue: String, rank: int, knowledge: Dictionary) -> int:
	return heritage_reward(her, choice, venue, rank, knowledge, null)


# ================================================================ 도(道) 명성
func province_of_region(region_id: String) -> Dictionary:
	for p in DataDB.overview.get("provinces", []):
		if region_id in p.get("regions", []):
			return p
	return {}


func province_of_node(node_id: String) -> Dictionary:
	return province_of_region(DataDB.region_of_node(node_id))


## 감영(도 수부) 발전 단계 — 도 전역 혜택의 기준
func capital_level(region_id: String) -> int:
	var pv := province_of_region(region_id)
	return int(GameState.town_dev.get(String(pv.get("capital", "")), 0)) if not pv.is_empty() else 0


## 도시 발전 혜택: 감영 단계 × 도 전역 + 해당 도시 단계 × 국지(감영 자신은 국지 혜택도 받음)
func dev_benefit(key: String, node_id: String) -> float:
	var b: Dictionary = DataDB.overview.get("town_dev", {}).get("benefits", {})
	var region := DataDB.region_of_node(node_id)
	var v := float(b.get("capital_per_level", {}).get("province_" + key, 0.0)) * capital_level(region)
	v += float(b.get("city_per_level", {}).get("local_" + key, 0.0)) * int(GameState.town_dev.get(node_id, 0))
	return v


func province_rep_mult(region_id: String) -> float:
	var b: Dictionary = DataDB.overview.get("town_dev", {}).get("benefits", {}).get("capital_level5", {})
	return 1.0 + float(b.get("province_rep_bonus", 0.0)) if capital_level(region_id) >= 5 else 1.0


## 도시 발전 L단계(1~5)에 필요한 도 명성
func standing_required(province: Dictionary, level: int) -> int:
	var req: Array = province.get("standing_req", [])
	return int(req[clampi(level, 1, req.size()) - 1]) if req.size() > 0 else 0


func quest_reward(tier: int, qtype: String, key: String) -> int:
	var e := _econ()
	var m := float(e.get("quest_type_mult", {}).get(qtype, {}).get(key, 1.0))
	return int(round(curve(e.get("quest_" + key, {}), tier) * m))


func enemy_reward(row: Dictionary, key: String) -> int:
	var e := _econ()
	var v := curve(e.get("enemy_" + key, {}), int(row.get("tier", 1)))
	if int(row.get("boss_tier", 0)) > 0:
		v *= float(e.get("boss_mult", {}).get(key, 1.0))
	return int(round(v))


func price_formula(cat: String, tier: int) -> int:
	var p: Dictionary = _econ().get("price", {})
	return maxi(5, int(round(float(p.get("base", {}).get(cat, 50)) * pow(float(p.get("growth", 3.0)), tier - 1) / 5.0)) * 5)


func wage_per_day(tier: int) -> int:
	return int(round(curve(_econ().get("wage_per_day", {}), tier)))


func town_dev_cost(level: int) -> int:
	var t := _cfg("town_dev")
	return int(round(float(t.get("cost_base", 800)) * pow(float(t.get("cost_growth", 1.6)), level)))


# ================================================================ 무역
func regional_rice_price(region_id: String) -> int:
	return int(DataDB.get_row(region_id).get("rice_price", 50))


func trade_sell_mult(hops: int) -> float:
	var arr: Array = _cfg("trade").get("sell_by_hops", [0.6, 0.95, 1.15, 1.35])
	return float(arr[clampi(hops, 0, arr.size() - 1)])


func trade_quest_payout(base_price: float, qty: int, margin: float) -> int:
	return int(round(base_price * qty * margin))


# ================================================================ 이동 (완전판 4.1)
func move_speed(v_mount: float, terrain: String, weather: String, night: bool, torch: bool, weight_ratio: float, fatigue_mult: float) -> float:
	var mv := _cfg("movement")
	var mt := float(mv.get("terrain", {}).get(terrain, 1.0))
	var mw := float(mv.get("weather", {}).get(weather, 1.0))
	var tm: Dictionary = mv.get("time", {})
	var mtime := float(tm.get("day", 1.0))
	if night:
		mtime = float(tm.get("night_torch", 0.9)) if torch else float(tm.get("night", 0.75))
	var v := (float(mv.get("v_base", 80.0)) + v_mount) * mt * mw * mtime * weight_mult(weight_ratio) * fatigue_mult
	return maxf(v, float(mv.get("v_min", 15.0)))


func weight_mult(ratio: float) -> float:
	for w in _cfg("movement").get("weight", []):
		if ratio < float(w["max"]):
			return float(w["mult"])
	return maxf(0.2, 1.0 - 0.5 * (ratio - 0.7))


## 전투용 환경 배율 = sqrt(M_weather × M_time)
func combat_env(weather: String, night: bool) -> float:
	var mv := _cfg("movement")
	var w := float(mv.get("weather", {}).get(weather, 1.0))
	var t := float(mv.get("time", {}).get("night" if night else "day", 1.0))
	return sqrt(w * t)


# ================================================================ CTB 전투 (완전판 7장)
func _b() -> Dictionary:
	return _cfg("battle")


func gauge_max() -> float:
	return float(_b().get("gauge_max", 1000))


## 게이지 충전율 (초기 기획 T = 10000/(Speed×(1+보정)) 과 동일)
func gauge_rate(speed: float, bonus: float, rate_mod: float) -> float:
	return maxf(1.0, speed * (1.0 + bonus) * maxf(0.1, 1.0 + rate_mod) / float(_b().get("gauge_rate_divisor", 10)))


func turn_time(speed: float, bonus: float) -> float:
	return gauge_max() / gauge_rate(speed, bonus, 0.0)


## 턴 동안 쓴 AP 총합 → 다음 게이지 시작값 (표의 최대 키에서 클램프)
func restart_gauge(ap_spent: int) -> float:
	var t: Dictionary = _b().get("restart_gauge_by_ap", {})
	var mx := 0
	for k in t.keys():
		mx = maxi(mx, int(k))
	return float(t.get(str(clampi(ap_spent, 0, mx)), 0))


func party_merge() -> Dictionary:
	return _b().get("party_merge", {})


## 동료 스킬 숙련 보정 = base + per_tier·(등급−3) + per_star·(성−1)
func companion_skill_mult(tier: int, star: int) -> float:
	var m: Dictionary = party_merge().get("companion_skill_mult", {})
	return float(m.get("base", 1.0)) + float(m.get("per_tier_from_3", 0.06)) * (tier - 3) + float(m.get("per_star", 0.04)) * (star - 1)


func start_ap(move_speed_value: float, penalty: int) -> int:
	var a: Dictionary = _b().get("ap", {})
	var bonus := int(maxf(0.0, move_speed_value - float(a.get("speed_bonus_base", 80))) / float(a.get("speed_bonus_step", 20)))
	return clampi(int(a.get("start", 3)) + bonus - penalty, 0, int(a.get("max", 5)))


## 대미지 = max(1, ATK×배율×(1+0.08×지식)×상성×보너스×치명 × 100/(100+min(DEF×(1−관통),200)) × (1−저항) − 고정감소)
func damage(raw: float, knowledge_rank: int, affinity_hit: bool, bonus: float, crit: bool, defense: float, def_ignore: float, resist: float, flat_red: float, aff_mult: float = -1.0) -> int:
	var b := _b()
	var d_eff := minf(defense * maxf(0.0, 1.0 - def_ignore), float(b.get("def_cap", 200)))
	var r := clampf(resist, -1.0, float(b.get("resist_cap", 0.9)))
	var k := 1.0 + float(b.get("knowledge_damage_per_rank", 0.08)) * knowledge_rank
	var am := aff_mult if aff_mult >= 0.0 else float(b.get("affinity_mult", 1.5))
	var a := am if affinity_hit else 1.0
	var c := float(b.get("crit", {}).get("mult", 1.5)) if crit else 1.0
	var v := raw * k * a * bonus * c * (100.0 / (100.0 + maxf(d_eff, 0.0))) * (1.0 - r) - flat_red
	return maxi(int(floor(v + 0.5)), int(b.get("min_damage", 1)))


func affinity_beats(attacker: String, defender: String) -> bool:
	return String(_b().get("affinity_beats", {}).get(attacker, "")) == defender


func dying_ratio() -> float:
	return float(_b().get("dying_hp_ratio", 0.3))


## 일반 적: 전장 적 flee_rate 최소값(75~95%로 클램프). 보스 포함 시 0%.
func flee_chance(enemy_rows: Array) -> float:
	var b := _b()
	var rng_range: Array = b.get("flee_normal", [0.75, 0.95])
	var chance := 1.0
	for e in enemy_rows:
		if int(e.get("boss_tier", 0)) > 0:
			return float(b.get("flee_boss", 0.0))
		chance = minf(chance, float(e.get("flee_rate", rng_range[0])))
	return clampf(chance, float(rng_range[0]), float(rng_range[1]))


# ================================================================ 포획
## 빈사 필수·보스 불가. 계통(method.target_kind) 일치 ×1.5, 도구 등급 미달 ×0.4, 지식·클래스·미끼 보너스
func capture_chance(tool_row: Dictionary, enemy_row: Dictionary, hp_ratio: float, bonus: float) -> float:
	if not enemy_row.get("capturable", false):
		return 0.0
	var dying := dying_ratio()
	if hp_ratio > dying:
		return 0.0
	var c := _cfg("capture")
	var chance := float(tool_row.get("base_rate", 0.3))
	chance *= 1.0 + (dying - hp_ratio) * float(c.get("dying_bonus_per_missing_ratio", 2.0))
	if String(tool_row.get("target_kind", "")) == String(enemy_row.get("kind", "")):
		chance *= float(c.get("family_match_mult", 1.5))
	if int(tool_row.get("tier", 1)) < int(enemy_row.get("tier", 1)):
		chance *= float(c.get("underleveled_tool_mult", 0.4))
	chance *= 1.0 + bonus
	return clampf(chance, 0.0, float(c.get("max_chance", 0.95)))


# ================================================================ 지식
func knowledge_xp_to_next(rank: int) -> int:
	var x: Dictionary = DataDB.classes_doc.get("knowledge", {}).get("xp_to_next", {})
	return int(round(float(x.get("base", 100)) * pow(float(x.get("growth", 1.35)), rank - 1)))
