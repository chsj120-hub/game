#!/usr/bin/env python3
"""CTB v2 보스전 밸런스 시뮬레이터 — scripts/battle/CTBEngine.gd · Combatant.gd · autoload/Balance.gd ·
GameState.party_combat_stats() 를 1:1 미러링한다. (한쪽을 고치면 반드시 다른 쪽도 고칠 것)

전투 규칙(완전판 7장 + 초기 기획 3.2):
  게이지 G 0→1000, 충전율 = 전투속도×(1+보정)/10  → T = 10000/(Speed×(1+보정))
  행동 후 G 재시작: AP 소모 0:+300 1:+200 2:0 3:−150 4+:−300 / 매 턴 +2 AP(최대 5), 시작 AP 3 + 이동속도 20px/s 초과분당 +1
  대미지 = max(1, ATK×배율×(1+0.08×지식)×상성1.5×치명 × 100/(100+min(DEF×(1−관통),200)) × (1−저항) − 고정감소)
사용: python3 tools/balance_sim.py [--trials 300] [--tier 4|5|all] [--cls cls_eosa]
"""
import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parallel_map  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def load(n):
    return json.loads((DATA / n).read_text(encoding="utf-8"))


OV = load("00_overview.json")
B = OV["battle"]
IDX = {}
for fn, key in [("02_equipment.json", "items"), ("12_enemies.json", "enemies"), ("13_companions.json", "companions"),
                ("14_skills.json", "skills"), ("11_food_recipes.json", "recipes"), ("09_herbal_recipes.json", "recipes"),
                ("06_life_gear.json", "life_gear"), ("16_mojak_gear.json", "mojak"), ("07_mounts.json", "mounts")]:
    for r in load(fn)[key]:
        IDX[r["id"]] = r
CK = load("19_classes_knowledge.json")
CLASSES = {c["id"]: c for c in CK["classes"]}
STATUS = {s["id"]: s for s in load("18_status_effects.json")["battle"]}


# ------------------------------------------------------------ Balance.gd
def damage(raw, knowledge_rank, affinity_hit, bonus, crit, defense, def_ignore, resist, flat_red, aff_mult=None):
    d_eff = min(defense * max(0.0, 1.0 - def_ignore), B["def_cap"])
    r = max(-1.0, min(resist, B["resist_cap"]))
    k = 1.0 + B["knowledge_damage_per_rank"] * knowledge_rank
    a = (aff_mult if aff_mult is not None else B["affinity_mult"]) if affinity_hit else 1.0
    c = B["crit"]["mult"] if crit else 1.0
    v = raw * k * a * bonus * c * (100.0 / (100.0 + max(d_eff, 0.0))) * (1.0 - r) - flat_red
    return max(int(math.floor(v + 0.5)), B["min_damage"])


def restart_gauge(ap_spent):
    t = B["restart_gauge_by_ap"]
    return float(t[str(min(max(ap_spent, 0), max(int(k) for k in t)))])


def start_ap(move_speed, ap_penalty=0):
    a = B["ap"]
    bonus = int(max(0.0, move_speed - a["speed_bonus_base"]) // a["speed_bonus_step"])
    return max(0, min(a["max"], a["start"] + bonus - ap_penalty))


PM = B["party_merge"]


# ------------------------------------------------------------ Combatant.gd
class C:
    def __init__(self, s, side):
        self.id, self.name, self.side = s["id"], s["name"], side
        self.kind = s.get("kind", "human")
        self.aff = s.get("aff", "none")
        self.boss_tier = int(s.get("boss_tier", 0))
        self.max_hp = self.hp = float(s["hp"])
        self.base_atk, self.base_def = float(s["atk"]), float(s["def"])
        self.speed = float(s["combat_speed"])
        self.speed_bonus = float(s.get("speed_bonus", 0.0))
        self.shoe_speed = float(s.get("shoe_combat_speed", 0.0))
        self.res_all = float(s.get("res", 0.0))
        self.res_map = dict(s.get("res_map", {}))
        self.element = s.get("element", "none")
        self.skills = list(s.get("skills", []))
        self.comp_skills = dict(s.get("comp_skills", {}))  # sid -> {"cid", "mult"}
        self.knowledge = dict(s.get("knowledge", {}))
        self.crit = float(s.get("crit", B["crit"]["base_rate"]))
        self.def_ignore = float(s.get("def_ignore", 0.0))
        self.flat_red = float(s.get("flat_red", 0.0))
        self.damage_vs = dict(s.get("damage_vs", {}))
        self.affinity_bonus = dict(s.get("affinity_bonus", {}))
        self.enrage = s.get("enrage", {})
        self.enraged = False
        n = int(s.get("n_companions", 0))
        self.ap_max = B["ap"]["max"] + PM["ap_max_per_companion"] * n
        self.ap_regen = B["ap"]["per_turn"] + PM["ap_regen_per_companion"] * n
        if side == "ally":
            self.ap = min(self.ap_max, start_ap(float(s.get("move_speed", 80)), int(s.get("ap_penalty", 0))) + PM["ap_start_per_companion"] * n)
        else:
            self.ap = int(s.get("base_ap", 3))
        self.gauge = 0.0
        self.gauge_rate_mod = float(s.get("gauge_rate_mod", 0.0))
        self.cooldowns, self.buffs, self.statuses = {}, [], {}
        self.taunt = 0
        self.first_turn = True
        self.spent = 0
        self.pending_gauge = 0.0
        self.used_comp = set()
        self.used_basic = set()
        self.min_ratio = 1.0

    alive = property(lambda s: s.hp > 0)
    ratio = property(lambda s: s.hp / max(s.max_hp, 1))

    def bsum(self, st):
        v = 0
        for b in self.buffs:
            if b[0] == st:
                v += b[1]
        for sid in self.statuses:
            v += STATUS[sid].get(st, 0.0)
        return v

    def has_buff_from(self, src):
        return any(b[3] == src for b in self.buffs)

    def atk(self):
        m = self.enrage.get("atk_mult", 1.0) if self.enraged else 1.0
        return self.base_atk * max(0.1, 1 + self.bsum("atk_pct")) * m

    def defense(self):
        return self.base_def * max(0.1, 1 + self.bsum("def_pct"))

    def resist(self, e):
        return self.res_all + self.res_map.get(e, 0.0) + self.bsum("res_all")

    def rate(self):
        sp = self.speed * (1 + self.bsum("speed_pct"))
        if "shoeless" in self.statuses:
            sp -= self.shoe_speed
        mod = 1 + self.gauge_rate_mod + self.bsum("gauge_rate")
        return max(1.0, sp * (1 + self.speed_bonus) * max(0.1, mod) / B["gauge_rate_divisor"])

    def heal_mult(self):
        m = 1.0
        for sid in self.statuses:
            m *= STATUS[sid].get("heal_mult", 1.0)
        return m

    def heal(self, pct):
        self.hp = min(self.max_hp, self.hp + self.max_hp * pct * self.heal_mult())

    def take(self, d):
        """Combatant.take_damage 미러 — 불사(death_ward) 중이면 HP 1 아래로 내려가지 않음."""
        self.hp = max(min(self.hp, 1.0), self.hp - d) if "death_ward" in self.statuses else max(0.0, self.hp - d)

    def add_status(self, sid, turns):
        if sid == "stun" and self.boss_tier:
            return
        self.statuses[sid] = max(self.statuses.get(sid, 0), turns)

    def end_turn(self):
        for k in self.cooldowns:
            self.cooldowns[k] = max(0, self.cooldowns[k] - 1)
        self.buffs = [[s, v, t - 1, src] for s, v, t, src in self.buffs if t - 1 > 0]
        self.statuses = {k: v - 1 for k, v in self.statuses.items() if v - 1 > 0}
        self.taunt = max(0, self.taunt - 1)


BASIC_SKILL = {"id": "basic", "name": "공격", "target": "enemy", "element": "weapon", "affinity": "weapon", "power": 1.0, "ap_cost": 1, "cooldown": 0}


# ------------------------------------------------------------ CTBEngine.gd
class Engine:
    def __init__(self, allies, enemies, items, rng):
        self.allies, self.enemies, self.items, self.rng = allies, enemies, dict(items), rng
        self.hero_turns, self.state = 0, "run"

    def living(self, l):
        return [c for c in l if c.alive]

    def all_living(self):
        return self.living(self.allies) + self.living(self.enemies)

    def next_actor(self):
        best, bt = None, 1e18
        live = self.all_living()
        rates = [c.rate() for c in live]      # 한 번만 계산(같은 순간의 속도 — 결과 동일)
        gmax = B["gauge_max"]
        for c, rt in zip(live, rates):
            t = max(0.0, (gmax - c.gauge) / rt)
            if t < bt - 1e-9 or (abs(t - bt) < 1e-9 and c.side == "ally" and best.side == "enemy"):
                best, bt = c, t
        for c, rt in zip(live, rates):
            c.gauge += rt * bt
        best.gauge = B["gauge_max"]
        return best

    def begin_turn(self, c):
        if not c.first_turn:
            c.ap = min(c.ap_max, c.ap + c.ap_regen)
        c.first_turn = False
        c.spent = 0
        c.used_comp = set()
        c.used_basic = set()
        for sid in list(c.statuses):
            dot = STATUS[sid].get("dot", 0.0)
            if dot:
                c.take(c.max_hp * dot)
                c.min_ratio = min(c.min_ratio, c.ratio)
        if not c.alive:
            self.check()
            return False
        if "stun" in c.statuses or ("charm" in c.statuses and self.rng.random() < STATUS["charm"]["skip_chance"]):
            self.finish(c)
            return False
        return True

    def finish(self, c):
        """턴 종료: 쓴 AP 총합으로 게이지 재시작(+ 자기 게이지 보너스)."""
        c.end_turn()
        c.gauge = restart_gauge(c.spent) + c.pending_gauge
        c.pending_gauge = 0.0
        if c.id == "hero":
            self.hero_turns += 1

    def lowest(self, l):
        l = [c for c in l if c.alive]
        return min(l, key=lambda c: c.ratio) if l else None

    def auto_target(self, actor, foes):
        if not foes:
            return None
        if actor.side == "enemy":
            t = [f for f in foes if f.taunt > 0]
            return t[0] if t else foes[self.rng.randint(0, len(foes) - 1)]
        return self.lowest(foes)

    def skill(self, sid):
        return IDX.get(sid) or BASIC_SKILL

    def can_use(self, actor, sid):
        sk = self.skill(sid)
        if sid in actor.comp_skills and PM["companion_skill_once_per_turn"] and actor.comp_skills[sid]["cid"] in actor.used_comp:
            return False
        if actor.side == "ally" and PM.get("basic_skill_once_per_turn") and int(sk.get("ap_cost", 1)) == 1 and sid in actor.used_basic:
            return False
        return actor.cooldowns.get(sid, 0) <= 0 and actor.ap >= sk.get("ap_cost", 1)

    def hit(self, actor, t, sk, power):
        elem = actor.element if sk.get("element", "weapon") == "weapon" else sk["element"]
        aff = actor.aff if sk.get("affinity", "weapon") == "weapon" else sk.get("affinity", "none")
        if aff in ("yu", "bul", "seon"):
            krank, neutral = actor.knowledge.get(aff, 0), 1.0
        else:
            krank = max([actor.knowledge.get(k, 0) for k in ("sa", "nong", "gong", "sang")] + [0])
            neutral = B["neutral_affinity_mult"]
        aff_hit = aff in B["affinity_beats"] and B["affinity_beats"][aff] == t.aff
        bonus = (1.0 + actor.affinity_bonus.get(t.aff, 0.0) + actor.damage_vs.get(t.kind, 0.0)) * neutral
        if actor.side == "enemy":
            bonus *= B["enemy_damage_mult"]
        crit = self.rng.random() < actor.crit
        di = actor.def_ignore + sk.get("effects", {}).get("def_ignore", 0.0)
        am = B["affinity_mult_enemy"] if actor.side == "enemy" else B["affinity_mult"]
        return damage(actor.atk() * power, krank, aff_hit, bonus, crit, t.defense(), di, t.resist(elem), t.flat_red, am)

    def use_skill(self, actor, sid, target):
        """효과만 적용(턴은 끝내지 않음). 적은 호출 뒤 finish."""
        sk = self.skill(sid)
        eff = sk.get("effects", {})
        cost = int(sk.get("ap_cost", 1))
        actor.ap -= cost
        actor.spent += cost
        mult = 1.0
        if cost == 1:
            actor.used_basic.add(sid)
        if sid in actor.comp_skills:
            actor.used_comp.add(actor.comp_skills[sid]["cid"])
            mult = actor.comp_skills[sid]["mult"]
        foes = self.living(self.enemies if actor.side == "ally" else self.allies)
        friends = self.living(self.allies if actor.side == "ally" else self.enemies)
        mode = sk.get("target", "enemy")
        if mode == "enemy":
            targets = [target if target and target.alive and target.side != actor.side else self.auto_target(actor, foes)]
        elif mode == "enemies":
            targets = foes
        elif mode == "ally":
            targets = [target if target and target.alive and target.side == actor.side else self.lowest(friends)]
        elif mode == "allies":
            targets = friends
        else:
            targets = [actor]
        power = float(sk.get("power", 0.0)) * mult
        for t in targets:
            if t is None:
                continue
            if power > 0 and t.side != actor.side:
                t.take(self.hit(actor, t, sk, power))
                t.min_ratio = min(t.min_ratio, t.ratio)
                if t.alive and t.boss_tier and not t.enraged and t.enrage and t.ratio <= t.enrage.get("hp_ratio", 0.3):
                    t.enraged = True
            if "heal_pct" in eff and t.side == actor.side:
                t.heal(eff["heal_pct"] * mult)
            if eff.get("cleanse") and t.side == actor.side:
                t.statuses = {k: v for k, v in t.statuses.items() if STATUS.get(k, {}).get("type") == "buff"}
            if t.side != actor.side and t.alive:
                if "stun_turns" in eff and (not eff.get("stun_kinds") or t.kind in eff["stun_kinds"]):
                    t.add_status("stun", eff["stun_turns"])
                st = eff.get("status")
                if st and self.rng.random() < st.get("chance", 1.0):
                    t.add_status(st["id"], st["turns"])
                if "gauge_push" in eff:
                    t.gauge = max(0.0, t.gauge - eff["gauge_push"])
                if "debuff" in eff:
                    for k, v in eff["debuff"].items():
                        t.buffs.append([k, v, eff.get("buff_turns", 2), sid])
            if "buff" in eff:
                bt = t if t.side == actor.side else actor
                for k, v in eff["buff"].items():
                    bt.buffs.append([k, v * mult, eff.get("buff_turns", 2), sid])
        if "gauge_boost" in eff and actor.side == "ally" and PM["gauge_boost_to_self"]:
            actor.pending_gauge += eff["gauge_boost"]
        if "taunt_turns" in eff:
            actor.taunt = eff["taunt_turns"]
        if "party_heal_pct" in eff:
            for f in friends:
                f.heal(eff["party_heal_pct"] * mult)
        if sk.get("cooldown", 0) > 0:
            actor.cooldowns[sid] = sk["cooldown"] + 1  # 사용한 턴 종료 시 1 감소 → 이후 자기 턴 N번 동안 재사용 불가
        self.check()

    def use_item(self, actor, iid, t):
        eff = IDX[iid]["effect"]
        actor.ap -= 1
        actor.spent += 1
        if "heal_pct" in eff and t.alive:
            t.heal(eff["heal_pct"])
        if "cure" in eff:
            t.statuses = {k: v for k, v in t.statuses.items() if STATUS.get(k, {}).get("type") == "buff"}
        if "death_ward" in eff and t.alive:  # 선단 불사환: 자기 턴 N회 동안 HP 1 아래로 내려가지 않음
            t.add_status("death_ward", eff["death_ward"].get("turns", 3))
        self.items[iid] -= 1

    def defend(self, actor):
        actor.buffs.append(["def_pct", 0.5, 1, "defend"])
        self.finish(actor)

    def enemy_act(self, a):
        opts = [s for s in a.skills if self.can_use(a, s)]
        sid = None
        for s in opts:
            if self.rng.random() < 0.6:
                sid = s
                break
        if sid is None:
            if a.ap >= 1:
                sid = "basic"
            else:
                return self.defend(a)
        self.use_skill(a, sid, self.auto_target(a, self.living(self.allies)))
        self.finish(a)

    # ---------------- 주인공(동료 통합) 자동 턴: AP 소진형 연속 행동
    def choose(self, a):
        foes = self.living(self.enemies)
        if not foes:
            return None
        boss = next((e for e in foes if e.boss_tier), None)
        focus = boss or self.lowest(foes)
        usable = [s for s in a.skills if self.can_use(a, s)]
        if a.ratio < 0.30 and self.items.get("hr_sipjeon", 0) > 0 and a.ap >= 1:
            return ("item", "hr_sipjeon", a)
        heals = [s for s in usable if "heal_pct" in self.skill(s).get("effects", {}) and self.skill(s).get("target") in ("ally", "allies", "self")]
        if heals and a.ratio < 0.55:
            return ("skill", max(heals, key=lambda s: self.skill(s)["effects"]["heal_pct"]), a)
        for s in usable:
            sk = self.skill(s)
            eff = sk.get("effects", {})
            if sk.get("target") in ("self", "allies", "ally") and "buff" in eff and "heal_pct" not in eff and not a.has_buff_from(s):
                return ("skill", s, a)
        for s in usable:
            sk = self.skill(s)
            eff = sk.get("effects", {})
            if sk.get("target") in ("enemy", "enemies") and float(sk.get("power", 0)) <= 1.0 and int(sk.get("ap_cost", 1)) <= 2 \
                    and ("debuff" in eff or "status" in eff) and not focus.has_buff_from(s) and not (focus.boss_tier and eff.get("status", {}).get("id") == "stun"):
                return ("skill", s, focus)
        best, bs = None, 0.0
        for s in usable:
            sk = self.skill(s)
            if sk.get("target") not in ("enemy", "enemies") or float(sk.get("power", 0)) <= 0:
                continue
            elem = a.element if sk.get("element", "weapon") == "weapon" else sk.get("element", "none")
            if focus.resist(elem) >= 0.5:
                continue
            n = len(foes) if sk["target"] == "enemies" else 1
            mult = a.comp_skills[s]["mult"] if s in a.comp_skills else 1.0
            score = float(sk["power"]) * mult * n * (1 - focus.resist(elem)) / max(1, sk.get("ap_cost", 1))
            if score > bs:
                best, bs = s, score
        if best:
            return ("skill", best, focus)
        if a.ap >= 1 and self.can_use(a, "basic"):
            return ("skill", "basic", focus)
        return None

    def ally_turn(self, a):
        acted = 0
        while self.state == "run" and a.alive and acted < 12:
            c = self.choose(a)
            if c is None:
                break
            kind, x, tgt = c
            (self.use_item(a, x, tgt) if kind == "item" else self.use_skill(a, x, tgt))
            acted += 1
        if acted == 0:
            return self.defend(a)
        self.finish(a)

    def check(self):
        if self.state != "run":
            return
        if not self.living(self.allies):
            self.state = "defeat"
        elif not self.living(self.enemies):
            self.state = "victory"

    def run(self, max_actions=3000):
        n = 0
        while self.state == "run" and n < max_actions:
            c = self.next_actor()
            n += 1
            if not self.begin_turn(c):
                continue
            (self.enemy_act if c.side == "enemy" else self.ally_turn)(c)
        return self


# ------------------------------------------------------------ GameState.party_combat_stats 미러
def env_mult(weather="clear", night=False):
    mv = OV["movement"]
    w = mv["weather"][weather]
    t = mv["time"]["night"] if night else mv["time"]["day"]
    return math.sqrt(w * t)


def global_buffs(lo):
    tot = {}

    def add(d):
        for k, v in d.items():
            if isinstance(v, (int, float)) and k != "duration_battles":
                tot[k] = tot.get(k, 0.0) + v
    if lo.get("food"):
        add(IDX[lo["food"]]["effect"].get("battle_buff", {}))
    for lg in lo.get("life_gear", []):
        add(IDX[lg].get("buffs", {}))
    return tot


def apply_buffs(s, b):
    s["hp"] = s["hp"] * (1 + b.get("hp_pct", 0))
    s["atk"] *= 1 + b.get("atk_pct", 0)
    s["def"] *= 1 + b.get("def_pct", 0)
    s["res"] = s.get("res", 0) + b.get("res_all", 0)
    s["speed_bonus"] = s.get("speed_bonus", 0) + b.get("spd_bonus", 0)
    return s


def party_knowledge(lo):
    cls = CLASSES[lo["cls"]]
    k = dict(cls["knowledge"])
    for sl in ("acc1", "acc2", "acc3"):
        iid = lo["gear"].get(sl)
        if iid and IDX[iid].get("passive_skill"):
            for kk, v in IDX[IDX[iid]["passive_skill"]].get("effects", {}).get("passive", {}).get("knowledge", {}).items():
                k[kk] = k.get(kk, 0) + v
    for cid in lo["party"]:
        for kk, v in companion_knowledge(cid, lo).items():
            k[kk] = k.get(kk, 0) + v
    cap = CK["knowledge"]["party_sum"]["cap"]
    return {kk: min(cap, v) for kk, v in k.items()}


def hero_stats(lo):
    cls = CLASSES[lo["cls"]]
    g = CK["rank_growth"]
    lv = lo["rank"] - 1
    s = {"id": "hero", "name": cls["name"], "hp": cls["base"]["hp"] + lv * g["hp"] + lo.get("perm_hp", 0),
         "atk": cls["base"]["atk"] + lv * g["atk"], "def": cls["base"]["def"] + lv * g["def"], "res": 0.0,
         "element": "none", "aff": cls["affinity"], "skills": cls["skills"], "crit": B["crit"]["base_rate"],
         "def_ignore": 0.0, "flat_red": 0.0, "damage_vs": dict(cls["passive"]["effects"].get("damage_vs", {})), "affinity_bonus": {}}
    pas = {}
    shoe_v = 0
    for slot, iid in lo["gear"].items():
        it = IDX[iid]
        st = it.get("stats", {})
        for k in ("hp", "atk", "def", "res", "crit", "def_ignore", "flat_red"):
            s[k] = s.get(k, 0) + st.get(k, 0)
        if slot == "shoes":
            shoe_v = st.get("spd", 0)
        if slot == "weapon":
            s["element"] = it.get("element", "none")
            if it.get("affinity", "none") != "none":
                s["aff"] = it["affinity"]
            for k, v in it.get("affinity_bonus", {}).items():
                s["affinity_bonus"][k] = s["affinity_bonus"].get(k, 0) + v
        if it.get("passive_skill"):
            for k, v in IDX[it["passive_skill"]].get("effects", {}).get("passive", {}).items():
                if k == "damage_vs":
                    for kk, vv in v.items():
                        s["damage_vs"][kk] = s["damage_vs"].get(kk, 0) + vv
                elif isinstance(v, (int, float)):
                    pas[k] = pas.get(k, 0) + v
    mount = lo.get("mount")
    v_mount = IDX[mount]["v_mount"] if mount else shoe_v
    move = OV["movement"]["v_base"] + v_mount
    env = env_mult(lo.get("weather", "clear"), lo.get("night", False))
    s["move_speed"] = move * env
    s["combat_speed"] = move * env * B["hero_combat_scale"]
    s["shoe_combat_speed"] = 0 if mount else shoe_v * env * B["hero_combat_scale"]
    s["speed_bonus"] = IDX[mount].get("spd_bonus", 0) if mount else 0.0
    s["knowledge"] = party_knowledge(lo)
    b = global_buffs(lo)
    for k, v in pas.items():
        b[k] = b.get(k, 0) + v
    s = apply_buffs(s, b)
    s["hp"] = min(CK["hp_cap"], s["hp"])
    merge_companions(s, lo)
    return s


def companion_tier(cid, lo=None):
    """CompanionSystem.tier_of 미러. 시나리오 기본값: 신분 Rank 까지 승급 완료(승급 t 는 Rank ≥ t) — lo['comp_tiers'] 로 개별 지정 가능."""
    c = IDX[cid]
    start = c.get("start_tier", c.get("tier", 3))
    if lo is None:
        return start
    if cid in lo.get("comp_tiers", {}):
        return lo["comp_tiers"][cid]
    return max(start, min(lo.get("rank", start), c.get("max_tier", 5)))


def companion_knowledge(cid, lo=None):
    """CompanionSystem.knowledge_of 미러: 시작 지식 + 승급당 대표 지식 +1."""
    c = IDX[cid]
    out = dict(c.get("knowledge_add", {}))
    ups = companion_tier(cid, lo) - c.get("start_tier", c.get("tier", 3))
    for kk, v in c.get("knowledge_per_promotion", {}).items():
        out[kk] = out.get(kk, 0) + v * max(0, ups)
    return out


def companion_skill_mult(cid, star=1, lo=None):
    m = PM["companion_skill_mult"]
    return m["base"] + m["per_tier_from_3"] * (companion_tier(cid, lo) - 3) + m["per_star"] * (star - 1)


def merge_companions(s, lo):
    """동행 동료 스킬을 주인공 목록에 합치고(동료 숙련 보정), AP 가산용 동료 수 기록."""
    s["skills"] = list(s["skills"])
    s["comp_skills"] = {}
    for cid in lo["party"]:
        for sid in IDX[cid]["skills"]:
            if sid in PM["exclude_companion_skills"] or sid in s["skills"]:
                continue
            s["skills"].append(sid)
            s["comp_skills"][sid] = {"cid": cid, "mult": companion_skill_mult(cid, 1, lo)}
    s["n_companions"] = len(lo["party"])


def companion_stats(cid, lo):
    c = IDX[cid]
    env = env_mult(lo.get("weather", "clear"), lo.get("night", False))
    s = {"id": cid, "name": c["name"], "hp": c["hp"], "atk": c["atk"], "def": c["def"], "res": c.get("res", 0),
         "element": c.get("element", "none"), "aff": c.get("yu_bul_seon_type", "none"), "skills": c["skills"],
         "knowledge": dict(c.get("knowledge", {})), "move_speed": c["speed"] * env,
         "combat_speed": c["speed"] * env * B["companion_combat_scale"]}
    return apply_buffs(s, global_buffs(lo))


def enemy_stats(eid, scale=None):
    e = dict(IDX[eid])
    if scale:
        e.update(scale)
    nm = B.get("normal_enemy_mult", {"atk": 1.0, "hp": 1.0}) if not e.get("boss_tier") else {"atk": 1.0, "hp": 1.0}
    return {"id": e["id"], "name": e["name"], "hp": e["hp"] * nm["hp"], "atk": e["atk"] * nm["atk"], "def": e["def"], "kind": e["kind"],
            "aff": e.get("yu_bul_seon_type", "none"), "boss_tier": e.get("boss_tier", 0), "element": e.get("element", "none"),
            "res_map": e.get("res", {}), "skills": e["skills"], "enrage": e.get("enrage", {}), "base_ap": e.get("base_ap", 3),
            "combat_speed": e["speed"] * e.get("combat_scale", 1.0)}


# ------------------------------------------------------------ 시나리오
T3_ACC = {"acc1": "eq_c3_byeoksa", "acc2": "eq_c3_gaya_crown", "acc3": "eq_b3_muyedobo"}
T3 = dict(armor="eq_a3_gyeongbeon", shoes="eq_s3_mokhwa", **T3_ACC)
T2 = dict(weapon="eq_w2_hwando", armor="eq_a2_dujeonggap", shoes="eq_s2_bidan_jipsin", acc1="eq_c2_yeongdeung", acc2="eq_c2_ssitgim", acc3="eq_c1_hopae")
CLASS_FAMILY = {"cls_eosa": "yu", "cls_merchant": "yu", "cls_dosa": "seon"}


def fam_set(prefix, fam, tier, book):
    return dict(weapon=f"{prefix}_{fam}_weapon_{tier}", armor=f"{prefix}_{fam}_armor_{tier}", shoes=f"{prefix}_{fam}_shoes_{tier}",
                acc1=f"{prefix}_{fam}_accessory_{tier}", acc2="eq_c3_byeoksa", acc3=book)


def pick_family(cls, boss):
    """클래스 선호 계열 무기 원소가 보스에게 50% 이상 저항되면 가장 덜 저항되는 계열로 교체(플레이어의 장비 교체를 가정)."""
    res = IDX[boss]["res"] if boss else {}
    pref = CLASS_FAMILY[cls]
    el = lambda f: IDX[f"eq_{f}_weapon_5"]["element"]
    if res.get(el(pref), 0) < 0.5:
        return pref
    return min(("yu", "bul", "seon"), key=lambda f: res.get(el(f), 0))


def T4(cls, boss=None):
    return fam_set("eq", pick_family(cls, boss), 4, "eq_b3_muyedobo")


def T5(cls, boss=None):
    return fam_set("eq", pick_family(cls, boss), 5, "eq_b5_hunminjeongeum")


def M5(cls, boss=None):
    return fam_set("mj", pick_family(cls, boss), 5, "eq_b5_hunminjeongeum")
PARTY4 = ["cp_heojun", "cp_samyeong", "cp_jeonuchi"]
PARTY5 = ["cp_yisunsin", "cp_samyeong", "cp_heojun"]


def best_weapon(boss, cls):
    e = IDX[boss]
    cands = ["eq_w3_byeolungeom", "eq_w3_hwaseon"]
    return max(cands, key=lambda w: IDX[w]["stats"]["atk"] * (1 - e["res"].get(IDX[w]["element"], 0)))


def scenarios(boss, cls):
    t3 = dict(T3, weapon=best_weapon(boss, cls))
    base = dict(cls=cls, rank=3, mount="mt_junma", party=PARTY4)
    return {
        "A 클러치 세팅 (T3 풀세트+준마+명물음식+동료3+십전대보탕×3)": dict(base, gear=t3, food="fr_jeonju_bibimbap", items={"hr_sipjeon": 3}),
        "B T3 풀세트, 음식·탕약 없음": dict(base, gear=t3, food=None, items={}),
        "C T3 풀세트+음식, 탕약 없음": dict(base, gear=t3, food="fr_jeonju_bibimbap", items={}),
        "D T2 장비 + 음식 + 탕약×3": dict(base, gear=T2, food="fr_jeonju_bibimbap", items={"hr_sipjeon": 3}),
        "E (참고) T4 장비 + 음식 + 탕약×3 (Rank4)": dict(base, rank=4, gear=T4(cls, boss), food="fr_jeonju_bibimbap", items={"hr_sipjeon": 3}),
    }


def scenarios_t5(boss, cls):
    base = dict(cls=cls, rank=5, mount="mt_junma", food="fr_sinseollo", party=PARTY5, items={"hr_sipjeon": 3}, perm_hp=15)
    return {
        "F 5등급 원본 풀세트 + 신선로 + 동료3 + 탕약×3": dict(base, gear=T5(cls, boss)),
        "G [모작] 5등급 풀세트 (원본 75%)": dict(base, gear=M5(cls, boss)),
        "H 4등급 풀세트로 신화보스 도전": dict(base, gear=T4(cls, boss)),
    }


def simulate(boss, sc, trials, seed=7, boss_override=None):
    rng = random.Random(seed)
    wins, turns, hp_left, deaths = 0, [], [], []
    for _ in range(trials):
        allies = [C(hero_stats(sc), "ally")]
        eng = Engine(allies, [C(enemy_stats(boss, boss_override), "enemy")], sc["items"], rng).run()
        if eng.state == "victory":
            wins += 1
            turns.append(eng.hero_turns)
            hp_left.append(allies[0].min_ratio)  # 전투 중 최저 HP 비율(아슬아슬 지표)
            deaths.append(sum(1 for a in allies if not a.alive))
    return wins / trials, turns, hp_left, deaths


def simulate_instance(inst_id, sc, trials, seed=11):
    inst = next(i for i in load("17_instances.json")["instances"] if i["id"] == inst_id)
    rng = random.Random(seed)
    clears = 0
    for _ in range(trials):
        allies = [C(hero_stats(sc), "ally")]
        items = dict(sc["items"])
        ok = True
        for wave in inst["waves"]:
            for a in allies:  # 웨이브 간: 게이지/AP 초기화, HP 이월
                a.gauge, a.first_turn = 0.0, True
            eng = Engine(allies, [C(enemy_stats(e), "enemy") for e in wave], items, rng)
            eng.run()
            items = eng.items
            if eng.state != "victory":
                ok = False
                break
        clears += ok
    return clears / trials


FIELD_CASES = [
    ("R1 단독·1등급", 1, dict(weapon="eq_w1_mokgeom", armor="eq_a1_cheollik", shoes="eq_s1_jipsin", acc1="eq_c1_hopae"), [],
     [["en_bandit"], ["en_bandit", "en_bandit"], ["en_bandit", "en_wolf", "en_bandit"]]),
    ("R2 동료1·2등급", 2, dict(weapon="eq_w2_hwando", armor="eq_a2_dujeonggap", shoes="eq_s2_bidan_jipsin", acc1="eq_c2_yeongdeung"), ["cp_chakho"],
     [["en_tiger"], ["en_dokkaebi", "en_ghost"], ["en_pirate", "en_pirate", "en_bandit"]]),
    ("R3 동료2·3등급", 3, dict(T3, weapon="eq_w3_byeolungeom"), ["cp_heojun", "cp_jeonuchi"],
     [["en_gumiho"], ["en_cultist", "en_cultist"], ["en_cultist", "en_cultist", "en_spirit_minion"]]),
]


def field_check(trials):
    """일반 조우(보스 아님) — 다수 적이 주인공 1명을 노리는 상황의 체감 난도. 목표: 3마리 조우 50~90%, 1~2마리 ≥85%."""
    ok = True
    print("\n══ 일반 조우 (보스 아님, 음식·탕약 없음, 3클래스 평균)")
    for label, rank, gear, party, waves in FIELD_CASES:
        row = []
        for w in waves:
            rates = []
            for cls in CLASSES:
                sc = dict(cls=cls, rank=rank, gear=gear, party=party, items={}, mount=None)
                rng = random.Random(3)
                wins = sum(Engine([C(hero_stats(sc), "ally")], [C(enemy_stats(e), "enemy") for e in w], {}, rng).run().state == "victory" for _ in range(trials))
                rates.append(wins / trials)
            r = sum(rates) / 3
            good = (0.5 <= r <= 0.9) if len(w) >= 3 else r >= 0.85
            ok &= good
            row.append(f"{'+'.join(IDX[e]['name'] for e in w)} {r*100:3.0f}%{'' if good else '✗'}")
        print(f"  {label:<14} " + " | ".join(row))
    return ok


def report(name, wr, turns, hp, dth):
    if turns:
        st = sorted(turns)
        line = f"승률 {wr*100:5.1f}%  턴 중앙값 {statistics.median(turns):4.1f} (p10 {st[len(st)//10]} ~ p90 {st[len(st)*9//10]})  최저HP {statistics.mean(hp)*100:4.1f}%"
    else:
        line = f"승률 {wr*100:5.1f}%"
    print(f"  {name:<44} {line}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--tier", default="all", choices=["4", "5", "all"])
    args = ap.parse_args()
    tgt = B["clutch_target_turns"]
    ok_all = True
    groups = []
    if args.tier in ("4", "all"):
        groups.append(("4등급 권역보스 — 클러치 빅토리 (Rank 3)", ["en_bulgasari", "en_imugi", "en_jirisan_sanshin"], scenarios, "A", ("B", "D")))
    if args.tier in ("5", "all"):
        groups.append(("5등급 신화보스 (Rank 5)", ["en_arang", "en_heukryong", "en_yeokcheon"], scenarios_t5, "F", ("H",)))
    for title, bosses, fn, main_key, fail_keys in groups:
        print(f"\n══ {title}   (판정: 3클래스 평균 — 개별 클래스 편차는 상성 카운터로 허용)")
        jobs, keys = [], []
        for boss in bosses:
            for cls in CLASSES:
                for name, sc in fn(boss, cls).items():
                    jobs.append((boss, sc, args.trials))
                    keys.append((boss, cls, name))
        results = dict(zip(keys, parallel_map(simulate, jobs)))
        for boss in bosses:
            e = IDX[boss]
            print(f"■ {e['name']} [{e['yu_bul_seon_type']}] (HP {e['hp']}, ATK {e['atk']}, DEF {e['def']}, 전투속도 {e['speed']*e['combat_scale']:.0f})")
            agg = {}
            for cls in CLASSES:
                for name, sc in fn(boss, cls).items():
                    wr, turns, hp, dth = results[(boss, cls, name)]
                    agg.setdefault(name[0], []).append((wr, statistics.median(turns) if turns else None, statistics.mean(hp) if hp else 0))
                    report(f"[{CLASSES[cls]['name']}] {name}", wr, turns, hp, dth)
            m = agg[main_key]
            wr_avg = sum(x[0] for x in m) / 3
            meds = [x[1] for x in m if x[1] is not None]
            med_avg = sum(meds) / len(meds) if meds else 0
            hp_avg = sum(x[2] for x in m) / 3
            if main_key == "A":
                good = wr_avg >= 0.6 and tgt[0] - 0.5 <= med_avg <= tgt[1] + 0.5 and hp_avg < 0.4
                print(f"    → 클러치 목표(평균 승률≥60%, 턴 {tgt[0]}~{tgt[1]}, 승리 시 전투 중 최저HP<40%): 승률 {wr_avg*100:.0f}% · 턴 {med_avg:.1f} · 최저HP {hp_avg*100:.0f}% {'충족' if good else '미충족'}")
            else:
                good = wr_avg >= 0.6
                print(f"    → 원본 풀세트 공략 가능(평균 승률≥60%): {wr_avg*100:.0f}% {'충족' if good else '미충족'}")
            ok_all &= good
            for fk in fail_keys:
                f = sum(x[0] for x in agg[fk]) / 3
                g = f <= 0.35
                ok_all &= g
                print(f"    → 세팅 [{fk}] 패배 유도(평균 승률≤35%): {f*100:.0f}% {'충족' if g else '미충족'}")
        if main_key == "A":
            for inst_id, boss in [("WAVE_004", "en_jirisan_sanshin"), ("WAVE_005", "en_bulgasari")]:
                vals = []
                for cls in CLASSES:
                    sc = scenarios(boss, cls)["A 클러치 세팅 (T3 풀세트+준마+명물음식+동료3+십전대보탕×3)"]
                    vals.append(simulate_instance(inst_id, sc, max(40, args.trials // 4)))
                print(f"  (참고) {inst_id} 풀코스 클리어율(미니게임·기믹·정비 미사용, 3클래스 평균): {sum(vals)/3*100:5.1f}%")
    ok_all &= field_check(max(30, args.trials // 3))
    print("\n결과:", "PASS" if ok_all else "TUNING NEEDED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
