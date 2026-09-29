class_name Combatant
extends RefCounted
## CTB v2 전투 참가자. tools/balance_sim.py class C 와 1:1 대응.

var uid: int = 0
var id: String = ""
var name: String = ""
var side: String = "ally"      ## ally | enemy
var kind: String = "human"     ## human|ghost|yokai|beast|dragon
var aff: String = "none"       ## 유불선 상성 yu|bul|seon|none
var tier: int = 1
var boss_tier: int = 0
var max_hp: float = 100.0
var hp: float = 100.0
var base_atk: float = 10.0
var base_def: float = 5.0
var speed: float = 100.0       ## 전투 속도(= 이동속도 × 환경 × combat_scale)
var speed_bonus: float = 0.0   ## (1+보정) 의 보정
var shoe_speed: float = 0.0    ## 신발 몫(야광귀 '신발 훔치기' 로 제거)
var gauge_rate_mod: float = 0.0
var res_all: float = 0.0
var res_map: Dictionary = {}
var element: String = "none"
var skills: Array = []
var knowledge: Dictionary = {}
var crit: float = 0.05
var def_ignore: float = 0.0
var flat_red: float = 0.0
var damage_vs: Dictionary = {}
var affinity_bonus: Dictionary = {}
var enrage: Dictionary = {}
var enraged: bool = false
var ap: int = 3
var ap_max: int = 5
var ap_regen: int = 2
var comp_skills: Dictionary = {}  ## 동료 통합: sid -> {cid, name, mult}
var used_comp: Dictionary = {}    ## 이번 턴에 스킬을 쓴 동료 id
var used_basic: Dictionary = {}   ## 이번 턴에 쓴 1AP 기본기
var spent: int = 0                ## 이번 턴에 쓴 AP 총합(게이지 재시작 산정)
var pending_gauge: float = 0.0
var min_ratio: float = 1.0
var gauge: float = 0.0
var first_turn: bool = true
var cooldowns: Dictionary = {}
var buffs: Array = []          ## [{stat, val, turns}]
var statuses: Dictionary = {}  ## status id -> 남은 턴
var taunt_turns: int = 0
var magic_immune_turns: int = 0
var atk_mult: float = 1.0
var atk_mult_turns: int = 0
var row: Dictionary = {}


static func from_stats(s: Dictionary, side_: String) -> Combatant:
	var c := Combatant.new()
	c.side = side_
	c.id = String(s.get("id", ""))
	c.name = String(s.get("name", c.id))
	c.kind = String(s.get("kind", "human"))
	c.aff = String(s.get("aff", "none"))
	c.tier = int(s.get("tier", 1))
	c.boss_tier = int(s.get("boss_tier", 0))
	c.max_hp = float(s.get("hp", 100))
	c.hp = float(s.get("hp_now", c.max_hp))
	c.base_atk = float(s.get("atk", 10))
	c.base_def = float(s.get("def", 5))
	c.speed = float(s.get("combat_speed", 100))
	c.speed_bonus = float(s.get("speed_bonus", 0.0))
	c.shoe_speed = float(s.get("shoe_combat_speed", 0.0))
	c.gauge_rate_mod = float(s.get("gauge_rate_mod", 0.0))
	c.res_all = float(s.get("res", 0.0))
	c.res_map = s.get("res_map", {}).duplicate()
	c.element = String(s.get("element", "none"))
	c.skills = s.get("skills", []).duplicate()
	c.knowledge = s.get("knowledge", {}).duplicate()
	c.crit = float(s.get("crit", DataDB.overview.get("battle", {}).get("crit", {}).get("base_rate", 0.05)))
	c.def_ignore = float(s.get("def_ignore", 0.0))
	c.flat_red = float(s.get("flat_red", 0.0))
	c.damage_vs = s.get("damage_vs", {}).duplicate()
	c.affinity_bonus = s.get("affinity_bonus", {}).duplicate()
	c.enrage = s.get("enrage", {})
	var pm := Balance.party_merge()
	var a: Dictionary = DataDB.overview.get("battle", {}).get("ap", {})
	var n := int(s.get("n_companions", 0))
	c.ap_max = int(a.get("max", 5)) + int(pm.get("ap_max_per_companion", 1)) * n
	c.ap_regen = int(a.get("per_turn", 2)) + int(pm.get("ap_regen_per_companion", 1)) * n
	c.comp_skills = s.get("comp_skills", {}).duplicate()
	if side_ == "ally":
		c.ap = mini(c.ap_max, Balance.start_ap(float(s.get("move_speed", 80)), int(s.get("ap_penalty", 0))) + int(pm.get("ap_start_per_companion", 0)) * n)
	else:
		c.ap = int(s.get("base_ap", 3))
	c.row = s
	return c


## 12 시트 적 행 → 전투 스탯
static func enemy_stats(e: Dictionary) -> Dictionary:
	var nm: Dictionary = {"atk": 1.0, "hp": 1.0}
	if int(e.get("boss_tier", 0)) == 0:  # 동료 통합 전투: 다수 일반 적이 주인공 1명을 노리므로 보정
		nm = DataDB.overview.get("battle", {}).get("normal_enemy_mult", nm)
	return {"id": e["id"], "name": e.get("name", e["id"]), "hp": float(e.get("hp", 50)) * float(nm.get("hp", 1.0)), "atk": float(e.get("atk", 10)) * float(nm.get("atk", 1.0)), "def": e.get("def", 5),
		"kind": e.get("kind", "human"), "aff": e.get("yu_bul_seon_type", "none"), "tier": e.get("tier", 1),
		"boss_tier": e.get("boss_tier", 0), "element": e.get("element", "none"), "res_map": e.get("res", {}),
		"skills": e.get("skills", []), "enrage": e.get("enrage", {}), "base_ap": e.get("base_ap", 3),
		"combat_speed": float(e.get("speed", 90)) * float(e.get("combat_scale", 1.0)),
		"capturable": e.get("capturable", false), "flee_rate": e.get("flee_rate", 0.9),
		"money_reward": Balance.enemy_reward(e, "money"), "rep_reward": Balance.enemy_reward(e, "rep"), "drops": e.get("drops", []),
		"gimmicks": e.get("gimmicks", []), "capture_profile": e.get("capture_profile", {})}


func is_alive() -> bool:
	return hp > 0.0


func is_boss() -> bool:
	return boss_tier > 0


func hp_ratio() -> float:
	return hp / maxf(max_hp, 1.0)


func _status_row(sid: String) -> Dictionary:
	return DataDB.status_battle.get(sid, {})


func bsum(stat: String) -> float:
	var v := 0.0
	for b in buffs:
		if b["stat"] == stat:
			v += float(b["val"])
	for sid in statuses.keys():
		v += float(_status_row(sid).get(stat, 0.0))
	return v


func atk() -> float:
	var m := atk_mult
	if enraged:
		m *= float(enrage.get("atk_mult", 1.0))
	return base_atk * maxf(0.1, 1.0 + bsum("atk_pct")) * m


func defense() -> float:
	return base_def * maxf(0.1, 1.0 + bsum("def_pct"))


func resist(elem: String) -> float:
	return res_all + float(res_map.get(elem, 0.0)) + bsum("res_all")


func rate() -> float:
	var sp := speed * (1.0 + bsum("speed_pct"))
	if statuses.has("shoeless"):
		sp -= shoe_speed
	return Balance.gauge_rate(sp, speed_bonus, gauge_rate_mod + bsum("gauge_rate"))


func heal_mult() -> float:
	var m := 1.0
	for sid in statuses.keys():
		m *= float(_status_row(sid).get("heal_mult", 1.0))
	return m


func heal(pct: float) -> float:
	var before := hp
	hp = minf(max_hp, hp + max_hp * pct * heal_mult())
	return hp - before


func add_status(sid: String, turns: int) -> void:
	if sid == "stun" and is_boss():
		return
	statuses[sid] = maxi(int(statuses.get(sid, 0)), turns)


func add_buff(stat: String, val: float, turns: int, src: String = "") -> void:
	buffs.append({"stat": stat, "val": val, "turns": turns, "src": src})


func has_buff_from(src: String) -> bool:
	for b in buffs:
		if String(b.get("src", "")) == src:
			return true
	return false


func clear_positive_buffs() -> void:
	buffs = buffs.filter(func(b): return float(b["val"]) < 0.0)


## 해로운 상태만 해제(불사 death_ward 같은 이로운 상태는 유지)
func cleanse() -> void:
	var kept := {}
	for sid in statuses.keys():
		if String(DataDB.status_battle.get(sid, {}).get("type", "debuff")) == "buff":
			kept[sid] = statuses[sid]
	statuses = kept


## 피해 적용 — 선단 불사환(death_ward) 중이면 HP 가 1 아래로 내려가지 않음(치명타를 맞아도 1 로 버팀)
func take_damage(d: float) -> float:
	var before := hp
	if statuses.has("death_ward"):
		hp = maxf(minf(hp, 1.0), hp - d)
	else:
		hp = maxf(0.0, hp - d)
	return before - hp


func has_death_ward() -> bool:
	return statuses.has("death_ward")


func skill_ready(sid: String) -> bool:
	return int(cooldowns.get(sid, 0)) <= 0


func end_turn() -> void:
	for k in cooldowns.keys():
		cooldowns[k] = maxi(0, int(cooldowns[k]) - 1)
	var kept := []
	for b in buffs:
		b["turns"] = int(b["turns"]) - 1
		if int(b["turns"]) > 0:
			kept.append(b)
	buffs = kept
	var st := {}
	for sid in statuses.keys():
		if int(statuses[sid]) - 1 > 0:
			st[sid] = int(statuses[sid]) - 1
	statuses = st
	taunt_turns = maxi(0, taunt_turns - 1)
	magic_immune_turns = maxi(0, magic_immune_turns - 1)
	if atk_mult_turns > 0:
		atk_mult_turns -= 1
		if atk_mult_turns == 0:
			atk_mult = 1.0
