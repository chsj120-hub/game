extends Node
## 플레이어 진행 상태 + 생존(피로/포만/신선도)·시간·날씨·지식·장비·동료·발견·도감·저장.
## 규칙 수치는 전부 DataDB.overview / 19 시트에서 읽는다.

signal stats_changed
signal rank_up(new_rank: int)
signal log_message(text: String)
signal node_changed(node_id: String)
signal day_passed(day: int)

const EQUIP_SLOTS := ["weapon", "armor", "shoes", "mount", "acc1", "acc2", "acc3"]
const ACC_SLOTS := ["acc1", "acc2", "acc3"]
const LIFE_SLOTS := ["nav", "carry", "camp", "record"]
const KNOWLEDGE_KEYS := ["yu", "bul", "seon", "sa", "nong", "gong", "sang"]
const MAX_PARTY := 3
const SAVE_PATH := "user://save.json"
const WEATHER_KO := {"clear": "맑음", "rain": "비", "storm": "폭풍우", "snow": "눈", "fog": "안개"}
const SOLAR_TERMS := ["입춘", "우수", "경칩", "춘분", "청명", "곡우", "입하", "소만", "망종", "하지", "소서", "대서",
	"입추", "처서", "백로", "추분", "한로", "상강", "입동", "소설", "대설", "동지", "소한", "대한"]

var class_id: String = "cls_eosa"
var reputation: int = 0
var money: int = 0
var rank: int = 1
var hp: float = 100.0
var fatigue: float = 0.0
var satiety: float = 80.0
var permanent_hp: int = 0
var current_region: String = "MAP_02"
var current_node: String = ""
var inside_node: bool = true        ## 거점 진입 상태(외곽 통과 시 false)
var minutes: int = 0                ## 누적 게임 시간(분)
var weather: String = "clear"
var inventory: Dictionary = {}      ## id -> qty
var freshness: Dictionary = {}      ## id -> 0~100 (perishable)
var equipped: Dictionary = {}       ## EQUIP_SLOTS -> id
var life_gear: Dictionary = {}      ## LIFE_SLOTS -> id
var gear_durability: Dictionary = {}
var mount_stamina: float = 100.0
var knowledge: Dictionary = {}      ## 본인 지식 랭크
var knowledge_xp: Dictionary = {}
var companions: Dictionary = {}     ## id -> {star, dupes, captured, hp}
var party: Array = []
var barracks: Array = []            ## 막사 대기 동료 id
var dispatch: Dictionary = {}       ## id -> {type, node, since}
var field_statuses: Dictionary = {} ## field status/buff id -> 만료 분
var discovered: Dictionary = {}     ## 은닉 노드 id -> true
var visited_nodes: Dictionary = {}
var lit_beacons: Dictionary = {}    ## region -> true
var heritage_state: Dictionary = {} ## her id -> pending|use|donate|sell
var investigate_retry: Dictionary = {} ## node -> 재시도 가능 분
var town_dev: Dictionary = {}
var active_quests: Dictionary = {}
var completed_quests: Array = []
var mojak_unlocked: Array = []
var trade_cargo: Dictionary = {}
var events_state: Dictionary = {}   ## event id -> {stage, started, status, chapter?}
var bounties: Array = []
var bounty_refresh_day: int = 0
var hwacheop: Dictionary = {}       ## scene id -> day
var takbon: Dictionary = {}         ## "첩번호" -> true
var seasonal_done: Dictionary = {}  ## "year:term" -> true
var codex: Dictionary = {}          ## entry id -> {cat, day}
var market_cycle: Dictionary = {}   ## node -> 갱신 주기 번호
var food_buff: Dictionary = {}
var walked_edges: Dictionary = {}  ## 지나 본 간선("a|b") — 익숙한 길 배율
var province_rep: Dictionary = {}  ## 도(道) id -> 도 명성(반복 원천 제외, 도시 발전 요건)
var ending_seen: bool = false
var auto_eat: bool = true
var substitute_mode: String = "confirm"  ## 상위 재료 대체: off | confirm | auto (00_overview.crafting.substitute_default)
var last_checkpoint: String = ""
var rng := RandomNumberGenerator.new()


func _ready() -> void:
	rng.randomize()
	new_game("cls_eosa")


func note(text: String) -> void:
	log_message.emit(text)


# ================================================================ 새 게임
func new_game(cls: String) -> void:
	var c := DataDB.class_row(cls)
	class_id = cls
	var t: Dictionary = DataDB.overview.get("time", {})
	minutes = (int(t.get("start_day", 1)) - 1) * 1440 + int(t.get("start_hour", 7)) * 60
	reputation = 0
	rank = 1
	money = int(c.get("start", {}).get("money", 300))
	inventory = c.get("start", {}).get("items", {}).duplicate()
	freshness = {}
	for id in inventory.keys():
		_init_fresh(id)
	knowledge = {}
	knowledge_xp = {}
	for k in KNOWLEDGE_KEYS:
		knowledge[k] = int(c.get("knowledge", {}).get(k, 0))
		knowledge_xp[k] = 0
	equipped = {"weapon": "eq_w1_mokgeom", "armor": "eq_a1_cheollik", "shoes": "eq_s1_jipsin", "acc1": "eq_c1_hopae"}
	life_gear = {"nav": "lg_yundo", "carry": "lg_botjim"}
	gear_durability = {}
	for id in life_gear.values():
		gear_durability[id] = int(DataDB.get_row(id).get("durability", 100))
	mount_stamina = 100.0
	permanent_hp = 0
	hp = hp_max()
	fatigue = 0.0
	satiety = 80.0
	companions = {}
	party = []
	barracks = []
	dispatch = {}
	field_statuses = {}
	discovered = {}
	visited_nodes = {}
	lit_beacons = {}
	heritage_state = {}
	investigate_retry = {}
	town_dev = {}
	active_quests = {}
	completed_quests = []
	mojak_unlocked = []
	trade_cargo = {}
	events_state = {}
	bounties = []
	bounty_refresh_day = 0
	hwacheop = {}
	takbon = {}
	seasonal_done = {}
	codex = {}
	substitute_mode = String(DataDB.overview.get("crafting", {}).get("substitute_default", "confirm"))
	market_cycle = {}
	food_buff = {}
	province_rep = {}
	walked_edges = {}
	ending_seen = false
	current_region = "MAP_02"
	current_node = String(DataDB.get_row("MAP_02").get("hub", ""))
	inside_node = true
	visited_nodes[current_node] = true
	last_checkpoint = current_node
	_roll_weather()
	stats_changed.emit()


# ================================================================ 인벤토리 · 무게 · 신선도
func count(id: String) -> int:
	return int(inventory.get(id, 0))


func has_item(id: String, qty: int = 1) -> bool:
	return id != "" and count(id) >= qty


func _perishable(id: String) -> bool:
	return DataDB.get_row(id).get("perishable", false)


func _init_fresh(id: String) -> void:
	if _perishable(id) and not freshness.has(id):
		freshness[id] = 100.0


func add_item(id: String, qty: int = 1) -> void:
	if qty <= 0:
		return
	var had := count(id)
	inventory[id] = had + qty
	if _perishable(id):  # 가중 평균 신선도
		freshness[id] = (float(freshness.get(id, 100.0)) * had + 100.0 * qty) / float(had + qty)
	if DataDB.get_row(id).has("real_name"):
		codex_add(id, "물산")
	stats_changed.emit()


func remove_item(id: String, qty: int = 1) -> bool:
	if count(id) < qty:
		return false
	inventory[id] = count(id) - qty
	if inventory[id] <= 0:
		inventory.erase(id)
		freshness.erase(id)
	stats_changed.emit()
	return true


# ---------------------------------------------------------------- 재료 계획(공용 재료군 · 상위 재료 대체)
func _craft_cfg() -> Dictionary:
	return DataDB.overview.get("crafting", {})


func _tier(id: String) -> int:
	return int(DataDB.get_row(id).get("tier", 1))


func material_label(m: Dictionary) -> String:
	if m.has("group"):
		return String(_craft_cfg().get("lines", {}).get(String(m["group"]), {}).get("name", m["group"]))
	return DataDB.display_name(String(m["id"]))


## 재료 1줄의 소모 후보 [id…] (우선순위 순) 과 기준 등급
func material_candidates(m: Dictionary) -> Dictionary:
	var cfg := _craft_cfg()
	var lines: Dictionary = cfg.get("lines", {})
	var nosub: Array = cfg.get("no_substitute", [])
	var exact := ""
	var pool := []
	var base_tier := 99
	if m.has("group"):
		for x in lines.get(String(m["group"]), {}).get("items", []):
			if not (x in nosub):
				pool.append(String(x))
				base_tier = mini(base_tier, _tier(String(x)))
	else:
		exact = String(m["id"])
		base_tier = _tier(exact)
		if substitute_mode != "off":
			for ln in lines.values():
				if exact in ln.get("items", []):
					for x in ln["items"]:
						var sx := String(x)
						if sx != exact and not (sx in nosub) and not (sx in pool) and _tier(sx) >= base_tier:
							pool.append(sx)
	pool.sort_custom(_candidate_before)
	if exact != "":
		pool.push_front(exact)
	return {"items": pool, "exact": exact, "base_tier": base_tier if base_tier < 99 else 1}


## 낮은 등급 먼저, 같은 등급이면 곧 상할 것(신선도 낮음) 먼저
func _candidate_before(a: String, b: String) -> bool:
	if _tier(a) != _tier(b):
		return _tier(a) < _tier(b)
	return float(freshness.get(a, 100.0)) < float(freshness.get(b, 100.0))


## mats [{id|group, qty}] → {ok, take{id:qty}, subs[{need, used, qty, gap}], missing[{label, have, need}]}
func material_plan(mats: Array, mult: float = 1.0) -> Dictionary:
	var take := {}
	var subs := []
	var missing := []
	for m in mats:
		var need := maxi(1, int(ceil(int(m["qty"]) * mult)))
		var c := material_candidates(m)
		var left := need
		for xv in c["items"]:
			var x := String(xv)
			if left <= 0:
				break
			var use := mini(count(x) - int(take.get(x, 0)), left)
			if use <= 0:
				continue
			take[x] = int(take.get(x, 0)) + use
			left -= use
			var gap := _tier(x) - int(c["base_tier"])
			if (c["exact"] != "" and x != c["exact"]) or (c["exact"] == "" and gap > 0):
				subs.append({"need": material_label(m), "used": x, "qty": use, "gap": gap})
		if left > 0:
			missing.append({"label": material_label(m), "have": need - left, "need": need})
	return {"ok": missing.is_empty(), "take": take, "subs": subs, "missing": missing}


## '확인' 모드에서 요구보다 confirm_tier_gap 등급 이상 높은 재료가 쓰이면 true
func needs_substitute_confirm(plan: Dictionary) -> bool:
	if substitute_mode != "confirm":
		return false
	var gap_min := int(_craft_cfg().get("confirm_tier_gap", 2))
	for s in plan.get("subs", []):
		if int(s["gap"]) >= gap_min:
			return true
	return false


func has_materials(mats: Array, mult: float = 1.0) -> bool:
	return material_plan(mats, mult)["ok"]


func consume_materials(mats: Array, mult: float = 1.0) -> bool:
	var plan := material_plan(mats, mult)
	if not plan["ok"]:
		return false
	for id in plan["take"].keys():
		remove_item(String(id), int(plan["take"][id]))
	return true


func item_weight(id: String) -> float:
	return float(DataDB.get_row(id).get("weight", 0.5))


func carry_weight() -> float:
	var w := 0.0
	for q in DataDB.table("03_specialties.json", "trade_quests"):  # 보부상 위탁 짐
		if q.get("consign", false) and String(trade_cargo.get(q["id"], "")) == "accepted":
			w += item_weight(String(q["item"])) * int(q["qty"])
	var worn := equipped.values() + life_gear.values()
	for id in inventory.keys():
		var q := count(id) - (1 if id in worn else 0)
		w += item_weight(id) * maxi(0, q)
	return w


func carry_capacity() -> float:
	var cap := float(DataDB.overview.get("movement", {}).get("carry_base", 30.0))
	cap += float(buff_totals().get("carry_capacity", 0.0))
	cap += companion_carry()
	var m := String(equipped.get("mount", ""))
	if m != "" and mount_stamina > 0:
		cap += float(DataDB.get_row(m).get("carry_capacity", 0))
	return cap


func weight_ratio() -> float:
	return carry_weight() / maxf(1.0, carry_capacity())


## 노드 이동 1회: 부패성 물품 신선도 −5%(농 지식 감쇠), 0% 폐기
func decay_freshness() -> void:
	var loss := float(DataDB.overview.get("survival", {}).get("freshness_loss_per_node", 5.0))
	loss *= 1.0 + life_effect("nong", "freshness_decay") + float(buff_totals().get("food_decay", 0.0))
	for id in freshness.keys():
		freshness[id] = float(freshness[id]) - maxf(0.5, loss)
		if float(freshness[id]) <= 0.0:
			note("%s 이(가) 상해 버렸습니다(신선도 0%%)." % DataDB.display_name(id))
			inventory.erase(id)
			freshness.erase(id)


func owned_books() -> Array:
	var out := []
	for id in inventory.keys():
		var sh := DataDB.sheet_of(id)
		if sh == "15_recipe_books.json:books" or sh == "03_specialties.json:specialty_recipes":
			out.append(id)
	return out


# ================================================================ 엽전 · 명성 · 신분
func add_money(amount: int) -> void:
	money += amount
	stats_changed.emit()


func spend_money(amount: int) -> bool:
	if money < amount:
		note("엽전이 부족합니다 (필요 %d냥 / 보유 %d냥)" % [amount, money])
		return false
	money -= amount
	stats_changed.emit()
	return true


## region: 명성이 발생한 권역(도 명성 적립). repeatable=true 인 원천(수배·공문·세시·일반 처치·투자)은 전국 명성만.
func add_reputation(amount: int, region: String = "", repeatable: bool = false) -> int:
	var gained := int(round(amount * (1.0 + float(buff_totals().get("reputation_gain", 0.0))))) if amount > 0 else amount
	reputation = maxi(0, reputation + gained)
	if not repeatable and region != "" and gained > 0:
		var pv := Balance.province_of_region(region)
		if not pv.is_empty():
			var pg := int(round(gained * Balance.province_rep_mult(region)))
			province_rep[pv["id"]] = int(province_rep.get(pv["id"], 0)) + pg
	if promotion_available():
		note("명성이 신분 Rank %d 심사 기준에 도달했습니다 — 관아에서 승급 심사를 받으세요." % (rank + 1))
	stats_changed.emit()
	return gained


func promotion_available() -> bool:
	return rank < Balance.max_rank() and reputation >= Balance.rank_threshold(rank + 1)


## 관아 '신분 승급 심사' (완전판 5장)
func promote() -> bool:
	if not promotion_available():
		return false
	if not DataDB.node_has(current_node, String(DataDB.overview.get("rank", {}).get("promotion", {}).get("requires_facility", "gwana"))):
		note("승급 심사는 관아에서만 받을 수 있습니다.")
		return false
	rank += 1
	var gift := Balance.rank_gift_money(rank)
	money += gift
	hp = minf(hp + float(DataDB.classes_doc.get("rank_growth", {}).get("hp", 15)), hp_max())
	note("신분 승급! Rank %d — %s (하사품 %d냥)" % [rank, Balance.rank_title(rank, class_id), gift])
	rank_up.emit(rank)
	stats_changed.emit()
	return true


func next_rank_progress() -> Vector2i:
	if rank >= Balance.max_rank():
		return Vector2i(reputation, reputation)
	return Vector2i(reputation, Balance.rank_threshold(rank + 1))


# ================================================================ 지식
func add_knowledge_xp(k: String, xp: int) -> void:
	if not (k in KNOWLEDGE_KEYS) or xp <= 0:
		return
	var mx := int(DataDB.classes_doc.get("knowledge", {}).get("max", 10))
	knowledge_xp[k] = int(knowledge_xp.get(k, 0)) + xp
	while int(knowledge.get(k, 0)) < mx and int(knowledge_xp[k]) >= Balance.knowledge_xp_to_next(maxi(1, int(knowledge.get(k, 0)))):
		knowledge_xp[k] = int(knowledge_xp[k]) - Balance.knowledge_xp_to_next(maxi(1, int(knowledge.get(k, 0))))
		knowledge[k] = int(knowledge.get(k, 0)) + 1
		note("지식 상승: %s %d랭크" % [DataDB.classes_doc.get("knowledge", {}).get("names", {}).get(k, k), knowledge[k]])
	stats_changed.emit()


## 파티 지식 = 본인 + 서책 패시브 + 동행 동료 knowledge_add (상한 10) — 완전판 8장 '100% 합산'
func party_knowledge() -> Dictionary:
	var out := knowledge.duplicate()
	for slot in ACC_SLOTS:
		var ps := String(DataDB.get_row(String(equipped.get(slot, ""))).get("passive_skill", ""))
		for k in DataDB.skill(ps).get("effects", {}).get("passive", {}).get("knowledge", {}).keys():
			out[k] = int(out.get(k, 0)) + int(DataDB.skill(ps)["effects"]["passive"]["knowledge"][k])
	for cid in party:
		var add := CompanionSystem.knowledge_of(String(cid))  # 승급할수록 대표 지식 +1
		for k in add.keys():
			out[k] = int(out.get(k, 0)) + int(add[k])
	var cap := int(DataDB.classes_doc.get("knowledge", {}).get("party_sum", {}).get("cap", 10))
	for k in out.keys():
		out[k] = mini(cap, int(out[k]))
	return out


func life_effect(k: String, key: String) -> float:
	return float(DataDB.classes_doc.get("life_effects", {}).get(k, {}).get(key, 0.0)) * int(party_knowledge().get(k, 0))


func has_life_passive(pid: String) -> bool:
	for p in DataDB.classes_doc.get("four_passives", []):
		if p["id"] == pid:
			for k in p["req"].keys():
				if int(party_knowledge().get(k, 0)) < int(p["req"][k]):
					return false
			return true
	return false


func class_passive() -> Dictionary:
	return DataDB.class_row(class_id).get("passive", {}).get("effects", {})


# ================================================================ 장비 · 행장 · 탈것
func can_equip(id: String, slot: String = "") -> String:
	var row := DataDB.get_row(id)
	if row.is_empty():
		return "알 수 없는 아이템"
	if not has_item(id):
		return "보유하지 않음"
	var need := int(row.get("min_rank", row.get("acquire", {}).get("min_rank", 1)))
	if DataDB.sheet_of(id) == "02_equipment.json:items" and int(row.get("tier", 1)) >= 4:
		need = maxi(need, int(row.get("tier", 1)) - 1)
	if rank < need:
		return "신분 Rank %d 이상 필요" % need
	var cr: Array = row.get("class_restriction", [])
	if not cr.is_empty() and not (class_id in cr):
		return "%s 전용" % "/".join(PackedStringArray(cr.map(func(c): return DataDB.display_name(String(c)))))
	var rk: Dictionary = row.get("req_knowledge", {})
	for k in rk.keys():
		if int(party_knowledge().get(k, 0)) < int(rk[k]):
			return "지식 %s %d 필요" % [k, int(rk[k])]
	return ""


func slot_for(id: String) -> String:
	var row := DataDB.get_row(id)
	if DataDB.sheet_of(id) == "07_mounts.json:mounts":
		return "mount"
	var s := String(row.get("slot", ""))
	if s in ["accessory", "book"]:
		for a in ACC_SLOTS:
			if String(equipped.get(a, "")) == "":
				return a
		return "acc1"
	return s


func equip(id: String, slot: String = "") -> bool:
	if slot == "":
		slot = slot_for(id)
	var err := can_equip(id, slot)
	if err == "" and not (slot in EQUIP_SLOTS or slot in LIFE_SLOTS):
		err = "장착 불가 아이템"
	if err != "":
		note("장착 실패: " + err)
		return false
	for s in equipped.keys():  # 같은 아이템 중복 장착 방지
		if equipped[s] == id:
			equipped.erase(s)
	if slot in EQUIP_SLOTS:
		equipped[slot] = id
	else:
		life_gear[slot] = id
		if not gear_durability.has(id):
			gear_durability[id] = int(DataDB.get_row(id).get("durability", 999))
	note("%s 장착" % DataDB.display_name(id))
	hp = minf(hp, hp_max())
	stats_changed.emit()
	return true


func unequip(slot: String) -> void:
	equipped.erase(slot)
	life_gear.erase(slot)
	hp = minf(hp, hp_max())
	stats_changed.emit()


## 동행 동료의 짐 무게 가산 (동료는 스킬·지식·무게만 기여, 스탯은 합산하지 않음)
func companion_carry() -> float:
	var t := 0.0
	for cid in party:
		var row := DataDB.get_row(String(cid))
		if companions.get(cid, {}).get("captured", false):
			t += float(row.get("capture_profile", {}).get("companion_bonuses", {}).get("carry", 0))
		else:
			t += float(row.get("carry_bonus", 0))
	return t


func mounted() -> bool:
	return String(equipped.get("mount", "")) != "" and mount_stamina > 0.0


## 수계 통과 허가: 수상/비행 탈것 보유
func has_water_mount() -> bool:
	for id in inventory.keys():
		if DataDB.sheet_of(id) == "07_mounts.json:mounts" and String(DataDB.get_row(id).get("terrain", "")) in ["water", "air"]:
			return true
	return false


## 행장·서책 패시브·음식·필드 버프 전역 합산
func buff_totals() -> Dictionary:
	var total := {}
	for id in life_gear.values():
		if int(gear_durability.get(id, 1)) <= 0:
			continue
		_merge(total, DataDB.get_row(id).get("buffs", {}))
	for slot in ACC_SLOTS:
		var ps := String(DataDB.get_row(String(equipped.get(slot, ""))).get("passive_skill", ""))
		var eff: Dictionary = DataDB.skill(ps).get("effects", {})
		_merge(total, eff.get("passive", {}))
		if eff.has("field_reputation_gain"):
			_merge(total, {"reputation_gain": eff["field_reputation_gain"]})
	if not food_buff.is_empty():
		_merge(total, food_buff.get("buff", {}))
	for sid in field_statuses.keys():
		var r: Dictionary = DataDB.field_buffs.get(sid, DataDB.status_field.get(sid, {}))
		_merge(total, r)
	return total


func _merge(total: Dictionary, add: Dictionary) -> void:
	for k in add.keys():
		if typeof(add[k]) in [TYPE_INT, TYPE_FLOAT] and not (k in ["duration_battles", "days"]):
			if k.ends_with("_mult"):
				total[k] = float(total.get(k, 1.0)) * float(add[k])
			else:
				total[k] = float(total.get(k, 0.0)) + float(add[k])


# ================================================================ HP · 전투 스탯 (balance_sim.py hero_stats 미러)
func hp_max() -> float:
	var cd := DataDB.classes_doc
	var c := DataDB.class_row(class_id)
	var v := float(c.get("base", {}).get("hp", 100)) + (rank - 1) * float(cd.get("rank_growth", {}).get("hp", 15)) + permanent_hp
	for slot in EQUIP_SLOTS:
		v += float(DataDB.get_row(String(equipped.get(slot, ""))).get("stats", {}).get("hp", 0))
	v *= 1.0 + float(buff_totals().get("hp_pct", 0.0))
	return minf(v, float(cd.get("hp_cap", 250)))


func is_night() -> bool:
	var h := hour()
	var dh: Array = DataDB.overview.get("time", {}).get("day_hours", [5, 19])
	return h < int(dh[0]) or h >= int(dh[1])


func fatigue_stage() -> Dictionary:
	for s in DataDB.overview.get("survival", {}).get("fatigue_stages", []):
		if fatigue >= float(s["min"]) and fatigue <= float(s["max"]):
			return s
	return {}


func hero_combat_stats() -> Dictionary:
	var cd := DataDB.classes_doc
	var c := DataDB.class_row(class_id)
	var g: Dictionary = cd.get("rank_growth", {})
	var lv := rank - 1
	var s := {"id": "hero", "name": String(c.get("name", "주인공")), "kind": "human",
		"hp": hp_max(), "hp_now": hp, "atk": float(c["base"]["atk"]) + lv * float(g.get("atk", 3)),
		"def": float(c["base"]["def"]) + lv * float(g.get("def", 2)), "res": 0.0, "element": "none",
		"aff": String(c.get("affinity", "none")), "skills": c.get("skills", []).duplicate(),
		"crit": float(DataDB.overview.get("battle", {}).get("crit", {}).get("base_rate", 0.05)), "def_ignore": 0.0, "flat_red": 0.0,
		"damage_vs": class_passive().get("damage_vs", {}).duplicate(), "affinity_bonus": {}}
	var shoe_v := 0.0
	for slot in EQUIP_SLOTS:
		var id := String(equipped.get(slot, ""))
		if id == "" or slot == "mount":
			continue
		var it := DataDB.get_row(id)
		var st: Dictionary = it.get("stats", {})
		for k in ["atk", "def", "res", "crit", "def_ignore", "flat_red"]:
			s[k] = float(s.get(k, 0.0)) + float(st.get(k, 0.0))
		if slot == "shoes":
			shoe_v = float(st.get("spd", 0))
		if slot == "weapon":
			s["element"] = String(it.get("element", "none"))
			if String(it.get("affinity", "none")) != "none":
				s["aff"] = String(it["affinity"])
			for k in it.get("affinity_bonus", {}).keys():
				s["affinity_bonus"][k] = float(s["affinity_bonus"].get(k, 0.0)) + float(it["affinity_bonus"][k])
			var gsk: Dictionary = it.get("granted_skills", {})
			if gsk.has("active") and not (gsk["active"] in s["skills"]):
				s["skills"].append(gsk["active"])
		var ps := String(it.get("passive_skill", it.get("granted_skills", {}).get("passive", "")))
		for k in DataDB.skill(ps).get("effects", {}).get("passive", {}).get("damage_vs", {}).keys():
			s["damage_vs"][k] = float(s["damage_vs"].get(k, 0.0)) + float(DataDB.skill(ps)["effects"]["passive"]["damage_vs"][k])
	var b := buff_totals()
	var mid := String(equipped.get("mount", ""))
	var v_mount := float(DataDB.get_row(mid).get("v_mount", 0)) if mounted() else shoe_v
	var fs := fatigue_stage()
	var env := Balance.combat_env(weather, is_night())
	var mv := (float(DataDB.overview.get("movement", {}).get("v_base", 80.0)) + v_mount) * env
	var scale := float(DataDB.overview.get("battle", {}).get("hero_combat_scale", 1.25))
	s["move_speed"] = mv
	s["combat_speed"] = mv * scale
	s["shoe_combat_speed"] = 0.0 if mounted() else shoe_v * env * scale
	s["speed_bonus"] = (float(DataDB.get_row(mid).get("spd_bonus", 0.0)) if mounted() else 0.0) + float(b.get("spd_bonus", 0.0))
	s["gauge_rate_mod"] = float(fs.get("gauge_rate", 0.0))
	s["ap_penalty"] = -int(fs.get("start_ap", 0))
	s["knowledge"] = party_knowledge()
	s["atk"] = float(s["atk"]) * (1.0 + float(b.get("atk_pct", 0.0))) * (float(DataDB.overview.get("survival", {}).get("starve_atk_mult", 0.5)) if satiety <= 0.0 else 1.0)
	s["def"] = float(s["def"]) * (1.0 + float(b.get("def_pct", 0.0)) + float(fs.get("def_pct", 0.0)))
	s["res"] = float(s["res"]) + float(b.get("res_all", 0.0))
	return s


## (구) 동료 개별 전투원 스탯 — 동료 통합 전투 전환 후 사용하지 않음. 도감·정보 표시용으로만 유지
func companion_combat_stats(cid: String) -> Dictionary:
	var info: Dictionary = companions.get(cid, {})
	var row := DataDB.get_row(cid)
	var star := int(info.get("star", 1))
	var sm := 1.0 + float(DataDB.overview.get("barracks", {}).get("star_stat_per_level", 0.08)) * (star - 1)
	var env := Balance.combat_env(weather, is_night())
	var s: Dictionary
	if info.get("captured", false):  # 포획 몬스터 동료
		var e := Combatant.enemy_stats(row)
		var ratio := float(DataDB.overview.get("capture", {}).get("captured_stat_ratio", 0.8))
		s = {"id": cid, "name": String(row.get("name", cid)), "kind": e["kind"], "aff": e["aff"], "element": e["element"],
			"hp": float(e["hp"]) * ratio * sm, "atk": float(e["atk"]) * ratio * sm, "def": float(e["def"]) * ratio * sm, "res": 0.0,
			"skills": e["skills"], "knowledge": {}, "move_speed": float(row.get("speed", 90)) * env,
			"combat_speed": float(row.get("speed", 90)) * env * float(DataDB.overview.get("battle", {}).get("companion_combat_scale", 1.2))}
	else:
		s = {"id": cid, "name": String(row.get("name", cid)), "kind": "human", "aff": String(row.get("yu_bul_seon_type", "none")),
			"element": String(row.get("element", "none")), "hp": float(row.get("hp", 100)) * sm, "atk": float(row.get("atk", 15)) * sm,
			"def": float(row.get("def", 10)) * sm, "res": float(row.get("res", 0.0)), "skills": row.get("skills", []),
			"knowledge": row.get("knowledge", {}).duplicate(), "move_speed": float(row.get("speed", 88)) * env,
			"combat_speed": float(row.get("speed", 88)) * env * float(DataDB.overview.get("battle", {}).get("companion_combat_scale", 1.2))}
	var b := buff_totals()
	s["hp"] = float(s["hp"]) * (1.0 + float(b.get("hp_pct", 0.0)))
	if info.has("hp"):
		s["hp_now"] = minf(float(info["hp"]), float(s["hp"]))
	s["atk"] = float(s["atk"]) * (1.0 + float(b.get("atk_pct", 0.0)))
	s["def"] = float(s["def"]) * (1.0 + float(b.get("def_pct", 0.0)))
	s["res"] = float(s["res"]) + float(b.get("res_all", 0.0))
	return s


## 동료 통합 전투: 전장에는 주인공 1명. 동행 동료의 스킬을 주인공 목록에 합치고(숙련 보정), 동료 수만큼 AP 상한·충전 가산.
## 동료가 기여하는 것은 ①스킬 ②지식(party_knowledge) ③짐 무게(companion_carry) 뿐이며 스탯은 합산하지 않는다.
func party_combat_stats() -> Array:
	var s := hero_combat_stats()
	var pm := Balance.party_merge()
	var excl: Array = pm.get("exclude_companion_skills", ["sk_basic_strike"])
	var comp := {}
	for cid in party:
		var c := String(cid)
		var row := DataDB.get_row(c)
		var info: Dictionary = companions.get(c, {})
		var mult := Balance.companion_skill_mult(CompanionSystem.tier_of(c), int(info.get("star", 1)))  # 현재(승급) 등급
		for sid in row.get("skills", []):
			var sk := String(sid)
			if sk in excl or sk in s["skills"]:
				continue
			s["skills"].append(sk)
			comp[sk] = {"cid": c, "name": String(row.get("name", c)), "mult": mult}
	s["comp_skills"] = comp
	s["n_companions"] = party.size()
	return [s]


## 전투 종료 후 HP 반영
func sync_after_battle(engine: CTBEngine) -> void:
	for c in engine.allies:
		if c.id == "hero":
			hp = maxf(1.0, c.hp)
	for id in engine.items.keys():
		var used := count(id) - int(engine.items[id])
		if used > 0:
			remove_item(id, used)
	if engine.money_spent > 0:
		money = maxi(0, money - engine.money_spent)
	stats_changed.emit()


# ================================================================ 음식 도핑
func apply_food_buff(buff: Dictionary) -> void:
	food_buff = {"buff": buff.duplicate(), "battles": int(buff.get("duration_battles", 1))}
	stats_changed.emit()


func tick_battle_buffs() -> void:
	if food_buff.is_empty():
		return
	food_buff["battles"] = int(food_buff["battles"]) - 1
	if int(food_buff["battles"]) <= 0:
		food_buff = {}
		note("음식 도핑 효과가 사라졌습니다.")
	stats_changed.emit()


# ================================================================ 시간 · 날씨 · 절기
func day() -> int:
	return int(minutes / 1440) + 1


func hour() -> int:
	return int((minutes % 1440) / 60)


func clock_text() -> String:
	return "%d일차 %02d:%02d" % [day(), hour(), minutes % 60]


func solar_term_index() -> int:
	var per := int(DataDB.overview.get("time", {}).get("days_per_term", 15))
	return int((day() - 1) / per) % 24


func solar_term() -> String:
	return SOLAR_TERMS[solar_term_index()]


func season() -> int:  ## 0 봄 1 여름 2 가을 3 겨울 (입춘 시작)
	return int(solar_term_index() / 6)


func year() -> int:
	var per := int(DataDB.overview.get("time", {}).get("days_per_term", 15))
	return int((day() - 1) / (per * 24)) + 1


## 시간 경과 — 날이 바뀌면 일일 처리(날씨·일급·파견·상태 만료·이벤트 기한 등)
func advance_minutes(m: int) -> void:
	var d0 := day()
	minutes += maxi(0, m)
	for sid in field_statuses.keys():
		if int(field_statuses[sid]) <= minutes:
			field_statuses.erase(sid)
			note("%s 상태가 풀렸습니다." % DataDB.field_buffs.get(sid, DataDB.status_field.get(sid, {})).get("name", sid))
	for d in range(d0 + 1, day() + 1):
		_on_new_day(d)
	stats_changed.emit()


func _on_new_day(d: int) -> void:
	_roll_weather()
	CompanionSystem.daily(d)
	EventSystem.daily(d)
	SideSystems.daily(d)
	day_passed.emit(d)


func _roll_weather() -> void:
	var clim := String(DataDB.get_row(current_region).get("climate", "temperate"))
	var table: Array = DataDB.overview.get("weather_table", {}).get(clim, [])
	if table.is_empty():
		weather = "clear"
		return
	var probs: Dictionary = table[season()]
	var r := rng.randf()
	var acc := 0.0
	weather = "clear"
	for k in probs.keys():
		acc += float(probs[k])
		if r <= acc:
			weather = String(k)
			break


func add_field_status(sid: String, days: float) -> void:
	field_statuses[sid] = minutes + int(days * 1440)
	var r: Dictionary = DataDB.field_buffs.get(sid, DataDB.status_field.get(sid, {}))
	note("%s 상태 (%.0f일)" % [r.get("name", sid), days])
	stats_changed.emit()


func cure_field(ids: Array) -> void:
	for sid in ids:
		if field_statuses.has(sid) and DataDB.status_field.has(sid):
			field_statuses.erase(sid)
			note("%s 완치" % DataDB.status_field[sid].get("name", sid))
	stats_changed.emit()


func diseases() -> Array:
	return field_statuses.keys().filter(func(k): return DataDB.status_field.has(k))


# ================================================================ 발견 · 도감
func node_visible(node_id: String) -> bool:
	var n := DataDB.get_row(node_id)
	return not n.get("hidden", false) or discovered.has(node_id) or lit_beacons.has(String(n.get("region", "")))


func discover(node_id: String) -> void:
	if discovered.has(node_id):
		return
	discovered[node_id] = true
	note("숨은 장소 발견: %s" % DataDB.display_name(node_id))
	stats_changed.emit()


## 도감 3중 분류 [역사]/[설화]/[창작]
func codex_add(entry_id: String, lore: String) -> void:
	if codex.has(entry_id):
		return
	var cat := "역사"
	if lore == "물산":
		cat = "물산"
	elif "설화" in lore:
		cat = "설화"
	elif "창작" in lore:
		cat = "창작"
	codex[entry_id] = {"cat": cat, "day": day()}
	note("도감 등록 [%s] %s" % [cat, DataDB.display_name(entry_id)])


# ================================================================ 동료 편성(세부는 CompanionSystem)
func recruit(cid: String, captured := false) -> void:
	CompanionSystem.add_companion(cid, captured)


# ================================================================ 저장/불러오기 (도시 주막 전용)
func can_save_here() -> String:
	if not DataDB.overview.get("save", {}).get("city_inn_only", true):
		return ""
	var n := DataDB.get_row(current_node)
	if String(n.get("type", "")) != "city" or not ("jumak" in n.get("facilities", [])) or not inside_node:
		return "여정 기록은 대도시 주막(온돌방)에서만 가능합니다."
	return ""


const SAVE_FIELDS := ["class_id", "reputation", "money", "rank", "hp", "fatigue", "satiety", "permanent_hp", "current_region",
	"current_node", "inside_node", "minutes", "weather", "inventory", "freshness", "equipped", "life_gear", "gear_durability",
	"mount_stamina", "knowledge", "knowledge_xp", "companions", "party", "barracks", "dispatch", "field_statuses", "discovered",
	"visited_nodes", "lit_beacons", "heritage_state", "investigate_retry", "town_dev", "active_quests", "completed_quests",
	"mojak_unlocked", "trade_cargo", "events_state", "bounties", "bounty_refresh_day", "hwacheop", "takbon", "seasonal_done",
	"codex", "market_cycle", "food_buff", "auto_eat", "substitute_mode", "last_checkpoint", "province_rep", "ending_seen", "walked_edges"]
const INT_FIELDS := ["reputation", "money", "rank", "permanent_hp", "minutes", "bounty_refresh_day"]


func save_game(checkpoint := false) -> bool:
	var err := can_save_here()
	if err != "":
		note(err)
		return false
	last_checkpoint = current_node
	var d := {}
	for k in SAVE_FIELDS:
		d[k] = get(k)
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	f.store_string(JSON.stringify(d, "\t"))
	note("여정 기록 완료%s" % (" (자동 체크포인트)" if checkpoint else ""))
	return true


func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH)


func load_game() -> bool:
	if not has_save():
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	for k in d.keys():
		if k in INT_FIELDS:
			set(k, int(d[k]))
		elif k in SAVE_FIELDS:
			set(k, d[k])
	# JSON 은 정수를 float 로 복원하므로 수량 정규화
	for id in inventory.keys():
		inventory[id] = int(inventory[id])
	current_node = last_checkpoint if last_checkpoint != "" else current_node
	current_region = DataDB.region_of_node(current_node)
	inside_node = true
	stats_changed.emit()
	node_changed.emit(current_node)
	note("여정을 불러왔습니다 — %s 주막" % DataDB.display_name(current_node))
	return true
