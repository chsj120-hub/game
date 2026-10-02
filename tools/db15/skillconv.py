"""DB-15 스킬 서술문 → 게임 14_skills 수치 스키마 변환.

원칙
- 게임 CTB(동료 통합 전투: 전장엔 주인공 1명, 동료 스킬은 주인공 목록에 합류)에 없는 개념은 가장 가까운 기존 효과로 치환한다.
- 등급별 상한(CAP)을 넘지 않는다 — 게임에 이미 튜닝된 스킬(14_skills.json)의 범위를 기준으로 잡았다.
- 치환 내역은 note 로 남긴다(보고서·변경이력에 그대로 노출).
"""
import re

ELEMENT_KW = [("fire", r"화염|불길|불꽃|여우불|화기|화약|총통|폭발|용암|삼매진화|화속"),
              ("holy", r"번개|벼락|낙뢰|뇌속|오뢰|신성|벽사|진언|성불|법계|만다라|금강"),
              ("water", r"수속성|강물|물살|해일|물벼락|수공|파도|침수|익사"),
              ("yin", r"암흑|저주|원한|원혼|망령|지옥|사령|흑마|흑뢰|그림자"),
              ("wood", r"독액|맹독|중독|옻|가시|초목"),
              ("metal", r"총|조총|쇠뇌|편전|사격|탄환|철퇴|쇠몽둥이|검|칼|베기|창")]
STATUS_KW = [("bleed", r"출혈|베기 상처"), ("poison", r"중독|맹독|독 피해|독액"), ("burn", r"화상"),
             ("fear", r"공포|위압|포효"), ("charm", r"혼란|환각|현혹|유혹|매혹|배신|조종|홀림"),
             ("curse", r"저주|쿨타임 무한|반전|봉인"), ("frost", r"동결|동상|냉기|한랭|빙")]
STUN_KW = r"기절|행동 ?불능|행동불능|수면|마비|스턴|행동 정지|넉백|낙마|속박|묶|침묵|스킬 불가|시전 불|영창 취소|발을 묶"
AOE_KW = r"적 전체|적 전원|전장의 모든|모든 적|광역|적진|전열|후열|부채꼴|적 [2-9]체|1열|적들|전장 전체|주변 적|8연속|난무"
ALLY_ALL_KW = r"아군 전원|아군 전체|파티 전원|아군 진형|아군 모두|동료 전원|쓰러진 아군 전원"
ALLY_ONE_KW = r"아군 1인|아군 1명|단일 대상의 체력|파티 단일|대상 1인"


def _pct(text, pat):
    m = re.search(pat, text)
    return int(m.group(1)) / 100 if m else None


def _cap(v, lo, hi):
    return max(lo, min(hi, v))


def convert(text, owner, tier, affinity="none", is_boss=False, ap_hint=None):
    """returns (skill_dict_without_id_name, notes[])"""
    t = str(text)
    notes = []
    tier = int(tier or 1)
    k = max(0, tier - 2)
    eff = {}
    element = next((e for e, kw in ELEMENT_KW if re.search(kw, t)), "weapon")
    aoe = bool(re.search(AOE_KW, t))
    ally_all = bool(re.search(ALLY_ALL_KW, t))
    ally_one = bool(re.search(ALLY_ONE_KW, t))
    heal = _pct(t, r"체력(?:을|의)? ?(?:을 )?(\d+)% ?(?:즉시 |완전 )?(?:회복|충전)") or (1.0 if re.search(r"체력.{0,6}100%|완전 회복|완치", t) else None)
    revive = bool(re.search(r"부활|소생|환생|저승 문턱", t))
    kill = bool(re.search(r"즉사", t))
    invul = bool(re.search(r"무적|완전 방어|모든 공격 완전|피해.{0,8}(?:흡수|무효|반감)|방벽|결계", t))
    buff, debuff = {}, {}
    for key, pat_up, pat_dn in [("atk_pct", r"공격력 ?(\d+)% ?(?:증가|상승|증폭|버프|가산|폭증)", r"공격력 ?(\d+)% ?(?:감소|약화|차감|흡수)|공격력을 ?(\d+)% ?깎"),
                                ("def_pct", r"방어력 ?(\d+)% ?(?:증가|상승|폭증|버프)", r"방어력 ?(\d+)% ?(?:감소|무효|저하|약화)|받는 피해를 ?(\d+)% ?증가"),
                                ("res_all", r"저항(?:력)? ?(\d+)% ?(?:증가|부여|상승)?", None),
                                ("speed_pct", r"(?:이동)?속도 ?(\d+)% ?(?:증가|가속|상승)", None)]:
        up = _pct(t, pat_up) if pat_up else None
        if up:
            buff[key] = up
        if pat_dn:
            m = re.search(pat_dn, t)
            if m:
                debuff[key] = -int(next(g for g in m.groups() if g)) / 100
    crit = _pct(t, r"치명타(?:율| 확률)? ?\+?(\d+)%")
    dodge = _pct(t, r"회피율 ?\+?(\d+)%")
    if crit and not buff.get("atk_pct"):
        buff["atk_pct"] = crit * 0.5
        notes.append("치명타율 → 공격력 버프(½) 환산")
    if dodge and not buff.get("def_pct"):
        buff["def_pct"] = dodge * 0.5
        notes.append("회피율 → 방어력 버프(½) 환산(게임에 회피 판정 없음)")
    if re.search(r"은신", t) and not buff:
        buff["def_pct"] = 0.2
        notes.append("은신 → 방어력 버프로 치환(게임에 은신 판정 없음)")
    dmg_pct = _pct(t, r"(\d{3})% ?(?:의 )?(?:물리|관통|피해|배후|신성|확정|치명)")
    def_ign = _pct(t, r"방어력 ?(\d+)%를? 무시") or (0.3 if re.search(r"방어 ?무시|관통|방어구 (?:분쇄|파괴|해체)|방패를 부수", t) else None)
    stun = bool(re.search(STUN_KW, t))
    status = next((s for s, kw in STATUS_KW if re.search(kw, t)), None)
    gauge = bool(re.search(r"AP|행동력|선제 행동|첫 턴", t))
    summon = bool(re.search(r"소환|분신|화신|관군|승병|군단|증원", t))
    cleanse = bool(re.search(r"해제|정화|해독|지혈|소멸|복원", t)) and (ally_all or ally_one or heal)
    money = re.search(r"엽전 ?(\d+)냥 ?소모", t)

    # ---- 대상
    if heal or revive or (buff and not debuff and not dmg_pct) or invul and not debuff:
        target = "allies" if (ally_all or not ally_one) else "ally"
        if re.search(r"자신|본체|자기", t) and not ally_all:
            target = "self"
    else:
        target = "enemies" if aoe else "enemy"
    if owner == "enemy":  # 적 스킬: target=enemy 는 '상대 진영(주인공)' — 게임 규약
        target = "enemies" if (aoe or re.search(r"아군 전체|아군 전원|전장", t)) else ("self" if (buff and not debuff and not dmg_pct) else "enemy")

    offensive = target in ("enemy", "enemies")
    ap, power, cd = 2, 0.0, 1
    if offensive:
        if target == "enemies":
            base, cap = (0.8 + 0.1 * k, 1.15) if owner != "enemy" else ((0.75 if is_boss else 0.65), 0.85)
            ap, cd = 3, 2 if owner != "enemy" else (1 if is_boss else 0)
        else:
            heavy = bool(dmg_pct and dmg_pct >= 2.0) or kill or re.search(r"강력|필살|일격|강타|분쇄", t)
            if owner == "enemy":
                base, cap = (1.3, 1.6) if heavy else (1.05, 1.3)
                ap, cd = (3, 3) if (heavy and is_boss) else (2, 0)
            else:
                base, cap = (1.7 + 0.1 * k, 2.1) if heavy else (1.3 + 0.1 * k, 1.8)
                ap, cd = (3, 2) if heavy else (2, 1)
        power = _cap(base, 0, cap)
        pure_ctrl = not re.search(r"피해|타격|공격|베기|사격|찌르|강타|분쇄|투척|후려|물어|돌진|난타|연사|발사|포격|브레스|폭발|벼락|번개|마법", t)
        if pure_ctrl and (stun or status or debuff):
            power = 0.0 if owner != "enemy" else _cap(power * 0.6, 0.4, 0.8)
            ap, cd = (2, 3) if owner != "enemy" else (ap, max(cd, 2))
    else:
        ap, cd = (3, 3) if target == "allies" else (2, 2)

    # ---- 효과
    if heal:
        if target == "allies":
            eff["heal_pct"] = round(_cap(heal, 0.1, min(0.22, 0.12 + 0.03 * k)), 2)
        else:
            eff["heal_pct"] = round(_cap(heal, 0.15, min(0.35, 0.2 + 0.04 * k)), 2)
        if heal > eff["heal_pct"] + 0.001:
            notes.append(f"회복 {int(heal*100)}% → {int(eff['heal_pct']*100)}% (등급 상한)")
    if revive:
        eff["heal_pct"] = max(eff.get("heal_pct", 0), round(min(0.3, 0.18 + 0.03 * k), 2))
        cd = max(cd, 5)
        notes.append("부활/소생 → 대량 회복으로 치환(동료 통합 전투라 쓰러질 아군이 주인공뿐)")
    if cleanse:
        eff["cleanse"] = True
    if invul:
        buff["def_pct"] = max(buff.get("def_pct", 0), 0.25)
        buff["res_all"] = max(buff.get("res_all", 0), 0.1)
        notes.append("무적/피해 흡수·무효 → 방어·저항 버프(상한 25%/10%)")
        cd = max(cd, 4)
    caps = {"atk_pct": min(0.15, 0.08 + 0.02 * k), "def_pct": min(0.3, 0.12 + 0.04 * k),
            "res_all": min(0.2, 0.1 + 0.03 * k), "speed_pct": min(0.2, 0.1 + 0.03 * k)}
    if owner == "enemy":
        caps = {"atk_pct": 0.3 if is_boss else 0.25, "def_pct": 0.3, "res_all": 0.2, "speed_pct": 0.2}
    for key, v in list(buff.items()):
        nv = round(min(v, caps[key]), 2)
        if nv < v - 0.001:
            notes.append(f"버프 {key} {int(v*100)}% → {int(nv*100)}%")
        buff[key] = nv
    for key, v in list(debuff.items()):
        cap = 0.3 if owner == "enemy" else min(0.25, 0.12 + 0.03 * k)
        nv = round(max(v, -cap), 2)
        if nv > v + 0.001:
            notes.append(f"약화 {key} {int(v*100)}% → {int(nv*100)}%")
        debuff[key] = nv
    if buff:
        eff["buff"] = buff
        eff["buff_turns"] = 3 if owner != "enemy" else 2
    if debuff:
        eff["debuff"] = debuff
        eff["buff_turns"] = eff.get("buff_turns", 2)
    if stun:
        eff["stun_turns"] = 1
        cd = max(cd, 3 if owner != "enemy" else 2)
        if re.search(r"2턴간 (?:행동|침수 기절|수면)", t):
            notes.append("행동 불능 2턴 → 1턴(보스 면역·연속 기절 방지)")
    if status and status in ("bleed", "poison", "burn", "fear", "charm", "curse", "frost"):
        chance = 0.35 if owner != "enemy" else (0.4 if is_boss else 0.3)
        m = re.search(r"(\d+)% ?확률", t)
        if m:
            chance = min(chance + 0.2, int(m.group(1)) / 100)
        eff["status"] = {"id": status, "turns": 2, "chance": round(chance, 2)}
    if def_ign:
        eff["def_ignore"] = round(min(def_ign, 0.4 if owner != "enemy" else 0.3), 2)
    if gauge and owner != "enemy":
        eff["gauge_boost"] = 150
        notes.append("AP/행동력 추가 → 게이지 +150(AP 상한은 동료 수로만 증가)")
    if money:
        eff["money_cost"] = int(money.group(1))
    if kill:
        notes.append("즉사 → 고위력 단일기(보스 포함 즉사 없음)")
    if summon:
        notes.append("소환/분신 → 광역 타격으로 치환(전장 1인 구조)")
    if re.search(r"영구", t) and owner in ("hero", "companion"):
        notes.append("'영구' 효과 → 전투 한정")
    if ap_hint:
        ap = int(ap_hint)
    ap = _cap(ap, 1, 4)
    if owner in ("companion", "hero") and power == 0 and not eff:
        eff["buff"] = {"atk_pct": caps["atk_pct"]}
        eff["buff_turns"] = 2
        notes.append("수치화할 효과 없음 → 소폭 공격 버프")
    aff = affinity if element != "weapon" or owner == "enemy" else "weapon"
    return {"owner": owner, "target": target, "ap_cost": ap, "power": round(power, 2), "element": element,
            "affinity": aff if element != "weapon" else "weapon", "cooldown": cd, "effects": eff}, notes


def describe(sk):
    """게임 수치 → 한국어 요약(수정본 effect_game 열)."""
    tg = {"enemy": "단일 적", "enemies": "적 전체", "ally": "아군 1", "allies": "아군 전체", "self": "자신", "field": "필드"}[sk["target"]]
    parts = [f"{tg}"]
    if sk["power"]:
        parts.append(f"위력 {sk['power']}")
    e = sk.get("effects", {})
    if "heal_pct" in e:
        parts.append(f"HP {int(e['heal_pct']*100)}% 회복")
    if e.get("cleanse"):
        parts.append("해로운 효과 해제")
    for k, lab in (("buff", "강화"), ("debuff", "약화")):
        if k in e:
            parts.append(lab + " " + ", ".join(f"{a} {int(v*100):+d}%" for a, v in e[k].items()) + f" {e.get('buff_turns', 2)}턴")
    if "stun_turns" in e:
        parts.append(f"기절 {e['stun_turns']}턴")
    if "status" in e:
        parts.append(f"{e['status']['id']} {e['status']['turns']}턴 {int(e['status']['chance']*100)}%")
    if "def_ignore" in e:
        parts.append(f"방어 {int(e['def_ignore']*100)}% 무시")
    if "gauge_boost" in e:
        parts.append(f"게이지 +{e['gauge_boost']}")
    if "money_cost" in e:
        parts.append(f"엽전 {e['money_cost']}냥")
    parts.append(f"AP {sk['ap_cost']} · 재사용 {sk['cooldown']}턴 · 원소 {sk['element']}")
    return " · ".join(parts)
