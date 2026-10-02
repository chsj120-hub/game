class_name CTBEngine
extends RefCounted
## CTB v2 전투 엔진(UI 비의존). tools/balance_sim.py Engine 과 1:1 미러.
##  게이지 0→1000 / AP(시작 3+속도 보너스, 턴당 +2, 최대 5) / AP 소모별 게이지 재시작
##  3~5 웨이브 연전 + 웨이브 간 정비 / 미니게임·기믹 / 도주(보스 0%) / 포획

signal event(text: String)

enum State { RUNNING, INTERMISSION, VICTORY, DEFEAT, FLED }

var state: int = State.RUNNING
var allies: Array = []
var enemies: Array = []
var waves: Array = []
var wave_index: int = 0
var hero_turns: int = 0
var defeated: Array = []     ## 격파·제압한 적 전투 스탯(보상 계산)
var captured: Array = []     ## 포획한 적 id
var items: Dictionary = {}   ## 전투 중 소모품 잔량 (id -> qty) — 종료 후 GameState 에 반영
var money_spent: int = 0
var minigame_effects: Dictionary = {}
var minigame_applies_to: String = "final_wave"
var minigame_boss_scale: float = 1.0
var instance_id: String = ""
var rng := RandomNumberGenerator.new()
var log_lines: PackedStringArray = []
var _uid := 0


func setup(ally_stats: Array, wave_list: Array, inventory: Dictionary, rng_seed: int = -1) -> void:
	if rng_seed >= 0:
		rng.seed = rng_seed
	else:
		rng.randomize()
	allies.clear()
	for s in ally_stats:
		var c := Combatant.from_stats(s, "ally")
		_uid += 1
		c.uid = _uid
		allies.append(c)
	items = inventory.duplicate()
	waves = wave_list
	wave_index = 0
	hero_turns = 0
	state = State.RUNNING
	_spawn_wave(0)


func set_minigame(effects: Dictionary, applies_to: String, boss_scale: float) -> void:
	minigame_effects = effects
	minigame_applies_to = applies_to
	minigame_boss_scale = boss_scale


func _emit(text: String) -> void:
	log_lines.append(text)
	event.emit(text)


func living(list: Array) -> Array:
	return list.filter(func(c): return c.is_alive())


func all_living() -> Array:
	return living(allies) + living(enemies)


func _spawn_wave(idx: int) -> void:
	enemies.clear()
	for eid in waves[idx]:
		var row := DataDB.get_row(String(eid))
		if row.is_empty():
			continue
		var c := Combatant.from_stats(Combatant.enemy_stats(row), "enemy")
		_uid += 1
		c.uid = _uid
		enemies.append(c)
	for a in allies:  # 웨이브 시작: 게이지·AP 초기화, HP 이월
		a.gauge = 0.0
		a.first_turn = true
	var names := PackedStringArray()
	for e in enemies:
		names.append(e.name)
	_emit("── 제 %d/%d 웨이브: %s" % [idx + 1, waves.size(), ", ".join(names)])
	var is_final := idx == waves.size() - 1
	if not minigame_effects.is_empty() and (minigame_applies_to == "all_waves" or (minigame_applies_to == "final_wave" and is_final) or (minigame_applies_to == "first_wave" and idx == 0)):
		_apply_minigame()


# ------------------------------------------------------------ 미니게임 효과 (17 시트)
func _apply_minigame() -> void:
	var fx := minigame_effects
	var has_boss := false
	var leader: Combatant = null
	for e in enemies:
		has_boss = has_boss or e.is_boss()
		if leader == null or e.max_hp > leader.max_hp:
			leader = e
	var sc := minigame_boss_scale if has_boss else 1.0
	if fx.has("leader_def_break") and leader:
		leader.add_buff("def_pct", -float(fx["leader_def_break"]) * sc, 999)
		_emit("미니게임 성공! %s 방어구 파괴 (방어 −%d%%)" % [leader.name, int(float(fx["leader_def_break"]) * sc * 100)])
	if fx.has("leader_hp_cut") and leader:
		var cut: float = leader.max_hp * float(fx["leader_hp_cut"]) * sc
		leader.hp = maxf(1.0, leader.hp - cut)
		_emit("선제 저격! %s HP −%d" % [leader.name, int(cut)])
	if fx.get("dispel_enemy_buffs", false):
		for e in enemies:
			e.clear_positive_buffs()
		_emit("팔괘 진법 해제! 적 도술 버프 소멸")
	if fx.has("ally_magic_immune_turns"):
		for a in allies:
			a.magic_immune_turns = int(fx["ally_magic_immune_turns"])
		_emit("아군 도술 면역 %d턴" % int(fx["ally_magic_immune_turns"]))
	if fx.has("front_stun_turns"):
		var turns := maxi(1, int(round(float(fx["front_stun_turns"]) * sc)))
		for e in enemies:
			e.add_status("stun", turns)
		_emit("일기토 승리! 적 전열 기절 %d턴 (보스 면역)" % turns)
	if fx.has("formation_break_def"):
		for e in enemies:
			e.add_buff("def_pct", -float(fx["formation_break_def"]) * sc, 999)
		_emit("적 진형 붕괴")
	if fx.get("purify_non_boss_ghosts", false):
		for e in enemies:
			if e.kind == "ghost" and not e.is_boss():
				e.hp = 0.0
				defeated.append(e.row)
				_emit("%s 즉시 성불 (무혈 승리)" % e.name)
	if fx.has("enemy_atk_mult"):
		for e in living(enemies):
			e.atk_mult = 1.0 - (1.0 - float(fx["enemy_atk_mult"])) * sc
			e.atk_mult_turns = int(fx.get("atk_mult_turns", 0))
		_emit("벽사 진언! 적 공격력 약화")
	_check_end()


# ------------------------------------------------------------ 비전투 기믹
func apply_gimmick(target: Combatant, g: Dictionary, context: Dictionary) -> String:
	match String(g.get("type", "")):
		"bribe":
			if int(context.get("money", 0)) < int(g.get("money", 0)):
				return "뇌물 엽전 부족"
		"persuade":
			if int(context.get("rank", 1)) < int(g.get("min_rank", 1)) and not context.get("persuade_any_rank", false):
				return "신분이 낮아 설득 불가 (Rank %d 필요)" % int(g.get("min_rank", 1))
		"lure":
			if int(context.get("item_count", 0)) < int(g.get("qty", 1)):
				return "유인 먹이(%s) 부족" % DataDB.display_name(String(g.get("item", "")))
		"purify", "riddle", "debate":
			if g.has("requires_item") and not context.get("has_required_item", false):
				return "%s 필요" % DataDB.display_name(String(g["requires_item"]))
			if not context.get("minigame_success", false):
				return "미니게임 실패"
	if String(g.get("result", "")) == "surrender":
		if target.is_boss():
			target.hp = maxf(1.0, target.hp - target.max_hp * 0.5)
			_emit("%s 의 기세가 꺾였다! HP 50%% 감소" % target.name)
		else:
			target.hp = 0.0
			defeated.append(target.row)
			_emit("%s 제압 성공 (비전투)" % target.name)
	else:
		if g.has("atk_mult"):
			target.atk_mult *= float(g["atk_mult"])
		if g.has("def_mult"):
			target.base_def *= float(g["def_mult"])
		_emit("%s 약화 성공" % target.name)
	_check_end()
	return ""


# ------------------------------------------------------------ 타임라인
func _time_to_turn(c: Combatant) -> float:
	return maxf(0.0, (Balance.gauge_max() - c.gauge) / c.rate())


## 다음 행동자 결정 + 전원 게이지 진행 (동시 도달 시 아군 우선)
func _advance_to_next() -> Combatant:
	var best: Combatant = null
	var bt := 1.0e18
	for c in all_living():
		var t := _time_to_turn(c)
		if t < bt - 1e-9 or (absf(t - bt) < 1e-9 and c.side == "ally" and best.side == "enemy"):
			best = c
			bt = t
	if best == null:
		return null
	for c in all_living():
		c.gauge += c.rate() * bt
	best.gauge = Balance.gauge_max()
	return best


## 향후 n턴 예측 (완전판 1.1: 우측 상단 7턴 깃발 타임라인)
func preview(n: int) -> Array:
	var g := {}
	var pool := all_living()
	for c in pool:
		g[c.uid] = c.gauge
	var out := []
	for i in n:
		var best: Combatant = null
		var bt := 1.0e18
		for c in pool:
			var t: float = maxf(0.0, (Balance.gauge_max() - float(g[c.uid])) / c.rate())
			if t < bt:
				best = c
				bt = t
		if best == null:
			break
		for c in pool:
			g[c.uid] = float(g[c.uid]) + c.rate() * bt
		out.append(best)
		g[best.uid] = Balance.restart_gauge(1)  # 예측은 일반 공격(1AP) 가정
	return out


## 다음 행동자에게 차례를 넘김. AP 충전·지속 피해·기절/홀림 처리 후 행동 가능한 자를 반환.
func begin_next_turn() -> Combatant:
	while state == State.RUNNING:
		var c := _advance_to_next()
		if c == null:
			return null
		if not c.first_turn:
			c.ap = mini(c.ap_max, c.ap + c.ap_regen)
		c.first_turn = false
		c.spent = 0
		c.used_comp = {}
		c.used_basic = {}
		for sid in c.statuses.keys():
			var dot := float(DataDB.status_battle.get(sid, {}).get("dot", 0.0))
			if dot > 0.0:
				var d: float = c.max_hp * dot
				c.take_damage(d)
				c.min_ratio = minf(c.min_ratio, c.hp_ratio())
				_emit("%s %s 피해 −%d" % [c.name, DataDB.status_battle[sid].get("name", sid), int(d)])
		if not c.is_alive():
			if c.side == "enemy":
				defeated.append(c.row)
			_check_end()
			continue
		if c.statuses.has("stun"):
			_emit("%s 기절 — 행동 불가" % c.name)
			_finish(c)
			continue
		if c.statuses.has("charm") and rng.randf() < float(DataDB.status_battle.get("charm", {}).get("skip_chance", 0.5)):
			_emit("%s 홀림 — 멍하니 서 있다" % c.name)
			_finish(c)
			continue
		return c
	return null


## 턴 종료: 이번 턴에 쓴 AP 총합으로 게이지 재시작 (+ 자기 게이지 보너스)
func _finish(c: Combatant, _unused: int = 0) -> void:
	c.end_turn()
	c.gauge = Balance.restart_gauge(c.spent) + c.pending_gauge
	c.pending_gauge = 0.0
	if c.id == "hero":
		hero_turns += 1


## 주인공(동료 통합) 턴을 플레이어가 끝낼 때
func end_ally_turn(actor: Combatant) -> void:
	if actor.spent == 0:
		defend(actor)
		return
	_emit("%s 턴 종료 (AP %d 사용 → 다음 턴 지연 %d)" % [actor.name, actor.spent, int(-Balance.restart_gauge(actor.spent))])
	_finish(actor)


# ------------------------------------------------------------ 행동
func skill_row(sid: String) -> Dictionary:
	var sk := DataDB.skill(sid)
	if sk.is_empty():
		return {"id": "basic", "name": "공격", "target": "enemy", "element": "weapon", "affinity": "weapon", "power": 1.0, "ap_cost": 1, "cooldown": 0}
	return sk


func can_use(actor: Combatant, sid: String) -> bool:
	var sk := skill_row(sid)
	var pm := Balance.party_merge()
	if actor.comp_skills.has(sid) and pm.get("companion_skill_once_per_turn", true) and actor.used_comp.has(String(actor.comp_skills[sid]["cid"])):
		return false
	if actor.side == "ally" and pm.get("basic_skill_once_per_turn", false) and int(sk.get("ap_cost", 1)) == 1 and actor.used_basic.has(sid):
		return false
	if sk.get("effects", {}).has("money_cost") and int(sk["effects"]["money_cost"]) > GameState.money - money_spent and actor.side == "ally":
		return false
	return actor.skill_ready(sid) and actor.ap >= int(sk.get("ap_cost", 1))


func _hit(actor: Combatant, t: Combatant, sk: Dictionary, power: float) -> int:
	var b: Dictionary = DataDB.overview.get("battle", {})
	var elem := actor.element if String(sk.get("element", "weapon")) == "weapon" else String(sk.get("element", "none"))
	var a := actor.aff if String(sk.get("affinity", "weapon")) == "weapon" else String(sk.get("affinity", "none"))
	var krank := 0
	var neutral := 1.0
	if a in ["yu", "bul", "seon"]:
		krank = int(actor.knowledge.get(a, 0))
	else:  # 무 상성: 생활 지식 최고 랭크 + 고정 배율
		for k in ["sa", "nong", "gong", "sang"]:
			krank = maxi(krank, int(actor.knowledge.get(k, 0)))
		neutral = float(b.get("neutral_affinity_mult", 1.2))
	var hit_aff := Balance.affinity_beats(a, t.aff)
	var bonus := (1.0 + float(actor.affinity_bonus.get(t.aff, 0.0)) + float(actor.damage_vs.get(t.kind, 0.0))) * neutral
	if actor.side == "enemy":
		bonus *= float(b.get("enemy_damage_mult", 1.0))
	var crit := rng.randf() < actor.crit
	var di := actor.def_ignore + float(sk.get("effects", {}).get("def_ignore", 0.0))
	var am := float(b.get("affinity_mult_enemy", b.get("affinity_mult", 1.5))) if actor.side == "enemy" else float(b.get("affinity_mult", 1.5))
	return Balance.damage(actor.atk() * power, krank, hit_aff, bonus, crit, t.defense(), di, t.resist(elem), t.flat_red, am)


func use_skill(actor: Combatant, sid: String, target: Combatant) -> void:
	var sk := skill_row(sid)
	var eff: Dictionary = sk.get("effects", {})
	var cost := int(sk.get("ap_cost", 1))
	actor.ap -= cost
	actor.spent += cost
	if cost == 1:
		actor.used_basic[sid] = true
	var mult := 1.0
	var by_name := ""
	if actor.comp_skills.has(sid):
		actor.used_comp[String(actor.comp_skills[sid]["cid"])] = true
		mult = float(actor.comp_skills[sid].get("mult", 1.0))
		by_name = "[%s] " % actor.comp_skills[sid].get("name", "")
	if eff.has("money_cost") and actor.side == "ally":
		money_spent += int(eff["money_cost"])
	var foes := living(enemies) if actor.side == "ally" else living(allies)
	var friends := living(allies) if actor.side == "ally" else living(enemies)
	var targets := []
	match String(sk.get("target", "enemy")):
		"enemy":
			targets = [target if target and target.is_alive() and target.side != actor.side else _auto_target(actor, foes)]
		"enemies":
			targets = foes
		"ally":
			targets = [target if target and target.is_alive() and target.side == actor.side else _lowest_hp(friends)]
		"allies":
			targets = friends
		_:
			targets = [actor]
	var power := float(sk.get("power", 0.0)) * mult
	var magic := not (String(sk.get("element", "weapon")) in ["weapon", "none"])
	var parts := PackedStringArray()
	for t in targets:
		if t == null:
			continue
		if power > 0.0 and t.side != actor.side:
			if magic and t.magic_immune_turns > 0:
				parts.append("%s 도술 면역" % t.name)
			else:
				var dmg := _hit(actor, t, sk, power)
				var warded := t.has_death_ward() and dmg >= t.hp
				t.take_damage(dmg)
				t.min_ratio = minf(t.min_ratio, t.hp_ratio())
				parts.append("%s −%d%s" % [t.name, dmg, " (불사: HP 1 로 버팀)" if warded else ""])
			if not t.is_alive():
				parts.append("%s 쓰러짐" % t.name)
				if t.side == "enemy":
					defeated.append(t.row)
			elif t.is_boss() and not t.enraged and not t.enrage.is_empty() and t.hp_ratio() <= float(t.enrage.get("hp_ratio", 0.3)):
				t.enraged = true
				parts.append("%s 격노!" % t.name)
		if eff.has("heal_pct") and t.side == actor.side:
			parts.append("%s +%d" % [t.name, int(t.heal(float(eff["heal_pct"]) * mult))])
		if eff.get("cleanse", false) and t.side == actor.side:
			t.cleanse()
		if t.side != actor.side and t.is_alive():
			if eff.has("stun_turns"):
				var kinds: Array = eff.get("stun_kinds", [])
				if kinds.is_empty() or t.kind in kinds:
					t.add_status("stun", int(eff["stun_turns"]))
			if eff.has("status") and rng.randf() < float(eff["status"].get("chance", 1.0)):
				t.add_status(String(eff["status"]["id"]), int(eff["status"]["turns"]))
				parts.append("%s %s" % [t.name, DataDB.status_battle.get(String(eff["status"]["id"]), {}).get("name", "")])
			if eff.has("gauge_push"):
				t.gauge = maxf(0.0, t.gauge - float(eff["gauge_push"]))
			if eff.has("debuff"):
				for k in eff["debuff"].keys():
					t.add_buff(k, float(eff["debuff"][k]), int(eff.get("buff_turns", 2)), sid)
		if eff.has("buff"):
			var bt: Combatant = t if t.side == actor.side else actor
			for k in eff["buff"].keys():
				bt.add_buff(k, float(eff["buff"][k]) * mult, int(eff.get("buff_turns", 2)), sid)
	if eff.has("gauge_boost") and actor.side == "ally" and Balance.party_merge().get("gauge_boost_to_self", true):
		actor.pending_gauge += float(eff["gauge_boost"])
	if eff.has("taunt_turns"):
		actor.taunt_turns = int(eff["taunt_turns"])
	if eff.has("party_heal_pct"):
		for f in friends:
			f.heal(float(eff["party_heal_pct"]) * mult)
	if int(sk.get("cooldown", 0)) > 0:
		actor.cooldowns[sid] = int(sk["cooldown"]) + 1  # 사용한 턴 종료 시 1 감소 → 이후 자기 턴 N번 재사용 불가
	_emit("%s%s 「%s」(%dAP · 남은 %d) %s" % [by_name, actor.name, sk.get("name", sid), cost, actor.ap, ", ".join(parts)])
	if actor.side == "enemy":
		_finish(actor)
	_check_end()


## 소모품(09 한방약·11 음식) — 1 AP
func use_item(actor: Combatant, item_id: String, target: Combatant, free: bool = false) -> void:
	var row := DataDB.get_row(item_id)
	var effect: Dictionary = row.get("effect", {})
	var t: Combatant = target if target else actor
	if effect.has("death_ward") and t.is_alive():  # 선단 불사환: 3턴 즉사 방지
		var dw: Dictionary = effect["death_ward"]
		t.add_status("death_ward", int(dw.get("turns", 3)))
		_emit("%s 불사(不死) — %d턴 동안 HP 가 1 아래로 내려가지 않음" % [t.name, int(dw.get("turns", 3))])
	if effect.has("heal_pct") and t.is_alive():
		t.heal(float(effect["heal_pct"]) * (1.0 + float(DataDB.classes_doc.get("life_effects", {}).get("nong", {}).get("herbal_heal", 0.0)) * int(GameState.party_knowledge().get("nong", 0))))
	if effect.has("cure"):
		t.cleanse()
	if effect.has("buff"):
		for k in effect["buff"].keys():
			t.add_buff(k, float(effect["buff"][k]), 3)
	items[item_id] = int(items.get(item_id, 0)) - 1
	_emit("%s → %s 에게 %s 사용" % [actor.name, t.name, row.get("name", item_id)])
	if not free and state == State.RUNNING:  # 1AP, 턴은 계속
		actor.ap -= 1
		actor.spent += 1


func defend(actor: Combatant) -> void:
	actor.add_buff("def_pct", 0.5, 1, "defend")
	_emit("%s 방어 태세 (턴 종료)" % actor.name)
	_finish(actor)


func try_flee(actor: Combatant) -> bool:
	var rows := []
	for e in living(enemies):
		rows.append(e.row)
	var chance := Balance.flee_chance(rows)
	if rng.randf() < chance:
		state = State.FLED
		_emit("도주 성공 (%.0f%%) — 안전하게 복귀합니다." % (chance * 100))
		return true
	_emit("도주 실패 (%.0f%%) — 턴 종료" % (chance * 100))
	actor.spent += 1
	_finish(actor)
	return false


func try_capture(actor: Combatant, tool_row: Dictionary, target: Combatant, bonus: float) -> bool:
	var chance := Balance.capture_chance(tool_row, target.row, target.hp_ratio(), bonus)
	var ok := chance > 0.0 and rng.randf() < chance
	actor.ap -= 2
	actor.spent += 2
	if ok:
		target.hp = 0.0
		captured.append(target.id)
		_emit("%s %s 성공! (%.0f%%)" % [target.name, tool_row.get("method", "포획"), chance * 100])
	elif chance <= 0.0:
		_emit("포획 불가 — %s" % ("보스는 포획할 수 없음" if target.is_boss() else "빈사(HP 30% 이하) 상태가 아님"))
	else:
		_emit("%s 포획 실패 (%.0f%%)" % [target.name, chance * 100])
	_check_end()
	return ok


# ------------------------------------------------------------ AI (balance_sim.py 와 동일 규칙)
func enemy_act(actor: Combatant) -> void:
	var sid := ""
	for s in actor.skills:
		if can_use(actor, String(s)) and rng.randf() < 0.6:
			sid = String(s)
			break
	if sid == "":
		if actor.ap >= 1:
			sid = "basic"
		else:
			defend(actor)
			return
	use_skill(actor, sid, _auto_target(actor, living(allies)))


## 자동 전투 한 수 선택 (balance_sim.py Engine.choose 와 동일 우선순위). 반환 {kind, id, target} 또는 {}
func choose(a: Combatant) -> Dictionary:
	var foes := living(enemies)
	if foes.is_empty():
		return {}
	var boss: Combatant = null
	for e in foes:
		if e.is_boss():
			boss = e
	var focus: Combatant = boss if boss else _lowest_hp(foes)
	var usable := []
	for s in a.skills:
		if can_use(a, String(s)):
			usable.append(String(s))
	if a.hp_ratio() < 0.30 and int(items.get("hr_sipjeon", 0)) > 0 and a.ap >= 1:
		return {"kind": "item", "id": "hr_sipjeon", "target": a}
	var best_heal := ""
	var best_h := 0.0
	for s in usable:
		var sk := skill_row(s)
		var e: Dictionary = sk.get("effects", {})
		if e.has("heal_pct") and String(sk.get("target", "")) in ["ally", "allies", "self"] and float(e["heal_pct"]) > best_h:
			best_h = float(e["heal_pct"])
			best_heal = s
	if best_heal != "" and a.hp_ratio() < 0.55:
		return {"kind": "skill", "id": best_heal, "target": a}
	for s in usable:
		var sk2 := skill_row(s)
		var e2: Dictionary = sk2.get("effects", {})
		if String(sk2.get("target", "")) in ["self", "allies", "ally"] and e2.has("buff") and not e2.has("heal_pct") and not a.has_buff_from(s):
			return {"kind": "skill", "id": s, "target": a}
	for s in usable:
		var sk3 := skill_row(s)
		var e3: Dictionary = sk3.get("effects", {})
		var is_stun: bool = String(e3.get("status", {}).get("id", "")) == "stun"
		if String(sk3.get("target", "")) in ["enemy", "enemies"] and float(sk3.get("power", 0.0)) <= 1.0 and int(sk3.get("ap_cost", 1)) <= 2 \
				and (e3.has("debuff") or e3.has("status")) and not focus.has_buff_from(s) and not (focus.is_boss() and is_stun):
			return {"kind": "skill", "id": s, "target": focus}
	var best := ""
	var bs := 0.0
	for s in usable:
		var sk4 := skill_row(s)
		if not (String(sk4.get("target", "")) in ["enemy", "enemies"]) or float(sk4.get("power", 0.0)) <= 0.0:
			continue
		var elem := a.element if String(sk4.get("element", "weapon")) == "weapon" else String(sk4.get("element", "none"))
		if focus.resist(elem) >= 0.5:
			continue
		var n := foes.size() if String(sk4["target"]) == "enemies" else 1
		var mult := float(a.comp_skills[s].get("mult", 1.0)) if a.comp_skills.has(s) else 1.0
		var score := float(sk4["power"]) * mult * n * (1.0 - focus.resist(elem)) / maxf(1.0, float(sk4.get("ap_cost", 1)))
		if score > bs:
			bs = score
			best = s
	if best != "":
		return {"kind": "skill", "id": best, "target": focus}
	if a.ap >= 1 and can_use(a, "basic"):
		return {"kind": "skill", "id": "basic", "target": focus}
	return {}


## 자동 턴: AP 가 남는 동안 연속 행동 후 턴 종료
func auto_ally_turn(actor: Combatant) -> void:
	var acted := 0
	while state == State.RUNNING and actor.is_alive() and acted < 12:
		var c := choose(actor)
		if c.is_empty():
			break
		if c["kind"] == "item":
			use_item(actor, String(c["id"]), c["target"])
		else:
			use_skill(actor, String(c["id"]), c["target"])
		acted += 1
	if state != State.RUNNING and state != State.INTERMISSION:
		return
	if acted == 0:
		defend(actor)
	else:
		_finish(actor)


func _auto_target(actor: Combatant, foes: Array) -> Combatant:
	if foes.is_empty():
		return null
	if actor.side == "enemy":
		var taunters := foes.filter(func(f): return f.taunt_turns > 0)
		if taunters.size() > 0:
			return taunters[0]
		return foes[rng.randi_range(0, foes.size() - 1)]
	return _lowest_hp(foes)


func _lowest_hp(list: Array) -> Combatant:
	var best: Combatant = null
	for c in list:
		if c.is_alive() and (best == null or c.hp_ratio() < best.hp_ratio()):
			best = c
	return best


# ------------------------------------------------------------ 종료/웨이브
func _check_end() -> void:
	if state != State.RUNNING:
		return
	if living(allies).is_empty():
		state = State.DEFEAT
		_emit("아군 전멸… 패배")
	elif living(enemies).is_empty():
		if wave_index < waves.size() - 1:
			state = State.INTERMISSION
			_emit("웨이브 돌파! 간이 정비 — 음식/약 복용 후 다음 웨이브로")
		else:
			state = State.VICTORY
			_emit("승리! (주인공 %d턴)" % hero_turns)


func next_wave() -> void:
	if state != State.INTERMISSION:
		return
	wave_index += 1
	state = State.RUNNING
	_spawn_wave(wave_index)


func is_over() -> bool:
	return state in [State.VICTORY, State.DEFEAT, State.FLED]
