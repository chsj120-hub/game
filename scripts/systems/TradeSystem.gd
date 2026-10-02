class_name TradeSystem
extends RefCounted
## 상점·교역: 5일장/상설시장(원산지 매수 0.72× → 거리별 매도 0.60/0.95/1.15/1.35×), 권역 쌀 시세 35~80냥,
## 5일 주기 물량 갱신, 상 지식(매수 −2%/매도 +3% per rank), 1.8배 무역 퀘스트, 도시 발전도 명품 해금.


static func _t() -> Dictionary:
	return DataDB.overview.get("trade", {})


static func _fac() -> Array:
	return DataDB.get_row(GameState.current_node).get("facilities", [])


static func region_hops(a: String, b: String) -> int:
	if a == b:
		return 0
	var dist := {a: 0}
	var q := [a]
	while q.size() > 0:
		var cur: String = q.pop_front()
		for nb in DataDB.adjacent(cur):
			if not dist.has(nb):
				dist[nb] = int(dist[cur]) + 1
				if nb == b:
					return int(dist[nb])
				q.append(nb)
	return 3  # 섬(제주) 등 해로 연결


static func _sang_buy() -> float:
	return maxf(0.5, 1.0 + GameState.life_effect("sang", "buy_price") - Balance.dev_benefit("buy_discount", GameState.current_node))


static func _sang_sell() -> float:
	var m := 1.0 + GameState.life_effect("sang", "sell_price") + float(GameState.buff_totals().get("trade_price", 0.0)) + Balance.dev_benefit("sell_bonus", GameState.current_node)
	if GameState.has_life_passive("pas_sang"):
		m += 0.10
	return m * float(GameState.class_passive().get("sell_mult", 1.0))


static func buy_price(id: String) -> int:
	var r := DataDB.get_row(id)
	var reg := GameState.current_region
	if id == "food_rice":
		return int(round(Balance.regional_rice_price(reg) * _sang_buy()))
	if r.has("unit_of"):  # 조리용 '한 말' = 섬 시세 × 0.1 × 1.1(소매)
		return maxi(1, int(round(buy_price(String(r["unit_of"])) * float(r.get("unit_ratio", 0.1)) * 1.1)))
	if DataDB.sheet_of(id) == "03_specialties.json:specialties":
		var m := float(_t().get("buy_at_origin", 0.72)) if String(r.get("region", "")) == reg else float(_t().get("buy_elsewhere", 1.1))
		return maxi(1, int(round(float(r["base_price"]) * m * _sang_buy())))
	var p := 0
	if r.has("price") and typeof(r["price"]) != TYPE_STRING:
		p = int(r["price"])
	elif r.get("acquire", {}).has("price"):
		p = int(r["acquire"]["price"])
	else:
		p = Balance.price_formula(_price_cat(r), int(r.get("tier", 1)))
	return maxi(1, int(round(p * _sang_buy())))


static func _price_cat(r: Dictionary) -> String:
	var s := String(r.get("slot", ""))
	if s in ["weapon", "armor", "shoes", "accessory", "book"]:
		return s
	return "accessory"


static func sell_price(id: String) -> int:
	var r := DataDB.get_row(id)
	var reg := GameState.current_region
	if id == "food_rice":
		return int(round(Balance.regional_rice_price(reg) * float(_t().get("rice_sell_spread", 0.9)) * _sang_sell()))
	if r.has("unit_of"):
		return maxi(1, int(round(sell_price(String(r["unit_of"])) * float(r.get("unit_ratio", 0.1)))))
	if DataDB.sheet_of(id) == "03_specialties.json:specialties":
		var hops := region_hops(String(r.get("region", reg)), reg)
		var fresh := float(GameState.freshness.get(id, 100.0)) / 100.0 if r.get("perishable", false) else 1.0
		return maxi(1, int(round(float(r["base_price"]) * Balance.trade_sell_mult(hops) * fresh * _sang_sell() * seasonal_mult(id) * saturation_mult(id))))
	var base := 0
	if r.has("price") and typeof(r["price"]) != TYPE_STRING:
		base = int(r["price"])
	elif r.get("acquire", {}).has("price"):
		base = int(r["acquire"]["price"])
	else:
		base = Balance.price_formula(_price_cat(r), int(r.get("tier", 1)))
	return maxi(1, int(round(base * float(_t().get("sell_spread_general", 0.5)) * _sang_sell())))


## 5일장 주기(물량 갱신) 표시용
static func market_cycle_id() -> int:
	return int((GameState.day() - 1) / int(_t().get("restock_days", 5)))


## 특산물 물량은 trade.stock_scope="region" 이면 원산지 권역 전체가 공유(장터 순회로 물량이 불어나지 않음)
static func _stock_key(id: String) -> String:
	var where := GameState.current_node
	if DataDB.sheet_of(id) == "03_specialties.json:specialties" and String(_t().get("stock_scope", "node")) == "region":
		where = GameState.current_region
	return "%s:%d:%s" % [where, market_cycle_id(), id]


static func stock_left(id: String) -> int:
	var r := DataDB.get_row(id)
	var base := 20 if DataDB.sheet_of(id) == "03_specialties.json:specialties" else 99
	if r.has("stock"):  # 품목별 물량(예: 의주 자초피 5)
		base = int(r["stock"])
	elif r.has("grade") and DataDB.sheet_of(id) == "03_specialties.json:specialties":  # 기본 20 / 상품 8 / 진상품 3
		var sb: Array = _t().get("stock_by_grade", [20, 8, 3])
		base = int(sb[clampi(int(r["grade"]), 0, sb.size() - 1)])
	elif String(r.get("kind", "")) == "premium":
		base = 6
	return base - int(GameState.market_cycle.get(_stock_key(id), 0))


static func _take_stock(id: String, qty: int) -> void:
	var key := _stock_key(id)
	GameState.market_cycle[key] = int(GameState.market_cycle.get(key, 0)) + qty


## 판매 포화: 같은 장터에서 같은 특산물을 이번 장(5일)에 판 개수만큼 개당 −per_unit, 하한 floor
static func _sold_key(id: String) -> String:
	return "sold:%s:%d:%s" % [GameState.current_node, market_cycle_id(), id]


static func saturation_mult(id: String, extra := 0) -> float:
	if DataDB.sheet_of(id) != "03_specialties.json:specialties":
		return 1.0
	var sat: Dictionary = _t().get("sell_saturation", {})
	if sat.is_empty():
		return 1.0
	var n := int(GameState.market_cycle.get(_sold_key(id), 0)) + extra
	return maxf(float(sat.get("floor", 0.6)), 1.0 - float(sat.get("per_unit", 0.02)) * n)


## 계절 교역(예: 겨울 동지사 사행 때 의주 매도가 +20%)
static func seasonal_mult(id: String) -> float:
	if DataDB.sheet_of(id) != "03_specialties.json:specialties":
		return 1.0
	var m := 1.0
	for b in _t().get("seasonal_sell_bonus", []):
		if String(b["region"]) == GameState.current_region and int(b["season"]) == GameState.season():
			m *= float(b["mult"])
	return m


## 현재 노드 상점 [{id, name, price, facility, lock, stock}]
static func shop_list() -> Array:
	var gs := GameState
	var fac := _fac()
	var reg := gs.current_region
	var out := []
	_pushed = {}
	var market := "market" in fac or "market5" in fac
	if market:
		for f in DataDB.table("04_food_staples.json", "foods"):
			var fk := String(f["kind"])
			if fk in ["staple", "ration", "grain", "ingredient"] or (fk == "meat" and "market" in fac):  # 쇠고기는 도회 장터만
				_push(out, f["id"], "market", "")
		for m in DataDB.table("05_materials.json", "materials"):
			if int(m["tier"]) <= 2:
				_push(out, m["id"], "market", "")
		for s in DataDB.table("03_specialties.json", "specialties"):
			if String(s["region"]) != reg or String(s["kind"]) == "crafted":
				continue
			var lv := int(gs.town_dev.get(String(s.get("node", "")), 0))
			var lock := "" if lv >= int(s["dev_level"]) else "도시 발전도 %d 필요" % int(s["dev_level"])
			if lock == "" and int(s.get("grade", 0)) > 0 and _t().get("grade_rank_gate", true) and gs.rank < int(s["tier"]):
				lock = "Rank %d 필요" % int(s["tier"])
			_push(out, s["id"], "market", lock)
		for t in DataDB.table("08_capture_tools.json", "tools"):
			_push(out, t["id"], "market", "" if gs.rank >= int(t["tier"]) else "Rank %d 필요" % int(t["tier"]))
		for g in DataDB.table("06_life_gear.json", "life_gear"):
			if g.has("price"):
				var need := int(g.get("min_rank", 1))
				_push(out, g["id"], "market", "" if gs.rank >= need else "Rank %d 필요" % need)
	if "yakbang" in fac or "yakryeongsi" in fac or "hyeminseo" in fac:
		for h in DataDB.table("10_herbs.json", "herbs"):
			if String(h["source"]) == "yakbang":
				_push(out, h["id"], "yakbang", "")
	for e in DataDB.table("02_equipment.json", "items"):
		var a: Dictionary = e.get("acquire", {})
		var f := String(a.get("facility", ""))
		if a.get("type", "") == "shop" and (f in fac or (f == "market5" and "market" in fac) or (f == "forge" and "forge_basic" in fac and int(e["tier"]) <= 1)):
			var need2 := int(a.get("min_rank", e["tier"]))
			_push(out, e["id"], f, "" if gs.rank >= need2 else "Rank %d 필요" % need2)
	if "yeokcham" in fac:
		for m2 in DataDB.table("07_mounts.json", "mounts"):
			if m2.get("acquire", {}).get("type", "") == "shop":
				var need3 := int(m2.get("min_rank", 1))
				_push(out, m2["id"], "yeokcham", "" if gs.rank >= need3 else "Rank %d 필요" % need3)
	for b in DataDB.table("15_recipe_books.json", "books"):
		var sa: Dictionary = b.get("sold_at", {})
		var bf := String(sa.get("facility", ""))
		if sa.is_empty() or not (bf in fac or (bf == "market5" and "market" in fac)):
			continue
		var regs: Array = sa.get("regions", [])
		if not ("*" in regs or reg in regs):
			continue
		var need4 := int(b.get("min_rank", 1))
		_push(out, b["id"], bf, "" if gs.rank >= need4 else "Rank %d 필요" % need4)
	if "checkpoint" in fac or "gwana" in fac:
		_push(out, "item_tonghaengjeung", "gwana", "")
	return out


static var _pushed: Dictionary = {}  ## shop_list 중복 방지(목록 선형 검색 대신)


static func _push(out: Array, id: String, facility: String, lock: String) -> void:
	if _pushed.has(id):
		return
	_pushed[id] = true
	var st := stock_left(id)
	out.append({"id": id, "name": DataDB.display_name(id), "price": buy_price(id), "facility": facility,
		"lock": lock if st > 0 else "이번 장(5일) 물량 소진", "stock": st})


static func buy(entry: Dictionary, qty: int = 1) -> bool:
	var gs := GameState
	if String(entry.get("lock", "")) != "":
		gs.note("구매 불가: " + String(entry["lock"]))
		return false
	qty = mini(qty, int(entry.get("stock", 99)))
	var total := int(entry["price"]) * qty
	if not gs.spend_money(total):
		return false
	var id := String(entry["id"])
	gs.add_item(id, qty)
	_take_stock(id, qty)
	if DataDB.sheet_of(id) == "07_mounts.json:mounts":
		gs.equip(id, "mount")
		gs.mount_stamina = 100.0
	gs.note("구매: %s ×%d (−%d냥)" % [entry["name"], qty, total])
	gs.bump("buy")
	return true


static func can_sell_here() -> bool:
	var fac := _fac()
	return "market" in fac or "market5" in fac or "antique" in fac or "black_market" in fac


static func sell(id: String, qty: int = 1) -> bool:
	var gs := GameState
	if not can_sell_here():
		gs.note("이 고을에는 장터/골동상이 없습니다.")
		return false
	if gs.count(id) < qty:
		return false
	var total := 0
	for k in qty:  # 포화: 한 개 팔 때마다 다음 값이 내려감
		total += sell_price(id)
		if DataDB.sheet_of(id) == "03_specialties.json:specialties":
			var sk := _sold_key(id)
			gs.market_cycle[sk] = int(gs.market_cycle.get(sk, 0)) + 1
	gs.remove_item(id, qty)
	gs.add_money(total)
	gs.note("매각: %s ×%d (+%d냥)" % [DataDB.display_name(id), qty, total])
	gs.bump("sell")
	var mj := String(DataDB.get_row(id).get("mojak_recipe", ""))
	if mj != "" and not (mj in gs.mojak_unlocked):
		gs.mojak_unlocked.append(mj)
		gs.note("%s 단조법 해금 (전국 어디서나 야외 단조)" % DataDB.display_name(mj))
	return true


# ------------------------------------------------------------ 무역 퀘스트 (1.8배 + 명성)
## 상태: "" 수락 가능 / accepted 진행 중 / done 완료. 반복 의뢰(repeat)는 다음 장(5일)에 다시 "".
static func quest_state(q: Dictionary) -> String:
	var st := String(GameState.trade_cargo.get(q["id"], ""))
	if st.begins_with("done@"):
		return "" if q.get("repeat", false) and int(st.substr(5)) != market_cycle_id() else "done"
	return st


static func trade_quests_here() -> Array:
	return DataDB.table("03_specialties.json", "trade_quests").filter(
		func(q): return (q["from"] == GameState.current_node and int(q.get("tier", 1)) <= GameState.rank + 1) or q["to"] == GameState.current_node or quest_state(q) == "accepted")


static func accept_trade(q: Dictionary) -> bool:
	var gs := GameState
	if gs.current_node != q["from"]:
		gs.note("출발지(%s)에서만 수락할 수 있습니다." % DataDB.display_name(String(q["from"])))
		return false
	if quest_state(q) != "":
		return false
	gs.trade_cargo[q["id"]] = "accepted"
	gs.bump("trade_accept")
	if q.get("consign", false):  # 보부상 위탁: 화주가 짐을 맡김(배낭 무게에 포함, 되팔 수 없음)
		gs.note("위탁 짐 인수: %s ×%d (무게 %.1f)" % [DataDB.display_name(String(q["item"])), int(q["qty"]), gs.item_weight(String(q["item"])) * int(q["qty"])])
	gs.note("무역 수락: %s — %s ×%d → %s" % [q["name"], DataDB.display_name(String(q["item"])), int(q["qty"]), DataDB.display_name(String(q["to"]))])
	gs.stats_changed.emit()
	return true


static func deliver_trade(q: Dictionary) -> bool:
	var gs := GameState
	if gs.trade_cargo.get(q["id"], "") != "accepted":
		return false
	if gs.current_node != q["to"]:
		gs.note("도착지(%s)에서 납품하세요." % DataDB.display_name(String(q["to"])))
		return false
	if not q.get("consign", false) and not gs.remove_item(String(q["item"]), int(q["qty"])):
		gs.note("납품 물량 부족 (%d 필요)" % int(q["qty"]))
		return false
	var base := float(DataDB.get_row(String(q["item"])).get("base_price", 0))
	var pay := Balance.trade_quest_payout(base, int(q["qty"]), float(q.get("margin", 1.8)))
	pay = int(pay * (1.0 + GameState.life_effect("sang", "trade_money")))
	gs.add_money(pay)
	var rep := gs.add_reputation(Balance.quest_reward(int(q.get("tier", 1)), "trade", "rep"), DataDB.region_of_node(String(q["to"])))
	gs.add_knowledge_xp("sang", int(DataDB.classes_doc.get("knowledge", {}).get("xp_sources", {}).get("trade_complete_sang", 30)))
	gs.trade_cargo[q["id"]] = "done@%d" % market_cycle_id()
	gs.bump("trade_done")
	gs.note("무역 완료: +%d냥, 명성 +%d" % [pay, rep])
	var rw := String(q.get("reward_item", ""))
	if rw != "" and not gs.has_item(rw):
		gs.add_item(rw)
		gs.note("보상: %s" % DataDB.display_name(rw))
	return true


# ------------------------------------------------------------ 도시 발전도 (최대 5단계)
## 다음 단계 요건: 엽전 + 해당 도(道) 명성. 도 명성은 그 도에서 얻은 1회성 명성만 쌓인다.
static func invest_block(node_id: String) -> String:
	var gs := GameState
	if not DataDB.overview.get("town_dev", {}).get("standing_required", false):
		return ""
	var pv := Balance.province_of_node(node_id)
	if pv.is_empty():
		return ""
	var nxt := int(gs.town_dev.get(node_id, 0)) + 1
	var need := Balance.standing_required(pv, nxt)
	var have := int(gs.province_rep.get(pv["id"], 0))
	if have < need:
		return "%s 명성 부족 — %d단계에는 도 명성 %d 필요(현재 %d). 이 도의 유산·퀘스트를 더 찾아보세요." % [pv["name"], nxt, need, have]
	return ""


static func invest_hint(node_id: String) -> String:
	var pv := Balance.province_of_node(node_id)
	var lv := int(GameState.town_dev.get(node_id, 0))
	if lv >= int(DataDB.overview.get("town_dev", {}).get("max", 5)):
		return "최대"
	return "%d/5단계 · 다음 %d냥 · %s 명성 %d/%d" % [lv, Balance.town_dev_cost(lv), pv.get("name", ""), int(GameState.province_rep.get(pv.get("id", ""), 0)), Balance.standing_required(pv, lv + 1)]
static func invest_town() -> bool:
	var gs := GameState
	var t := gs.current_node
	if String(DataDB.get_row(t).get("type", "")) != "city":
		gs.note("발전기금 투자는 대도시(감영·유수부)에서만 가능합니다.")
		return false
	var td: Dictionary = DataDB.overview.get("town_dev", {})
	var lv := int(gs.town_dev.get(t, 0))
	if lv >= int(td.get("max", 5)):
		gs.note("이미 최대 발전도입니다.")
		return false
	var err := invest_block(t)
	if err != "":
		gs.note(err)
		return false
	var cost := Balance.town_dev_cost(lv)
	if not gs.spend_money(cost):
		return false
	gs.town_dev[t] = lv + 1
	var pv := Balance.province_of_node(t)
	if String(pv.get("capital", "")) == t:
		gs.note("【%s 감영】 도 전역 혜택: 매입 −%d%% · 숙박 −%d%% · 역마 −%d%%%s" % [pv["name"], int(Balance.dev_benefit("buy_discount", t) * 100),
			int(Balance.dev_benefit("inn_discount", t) * 100), int(Balance.dev_benefit("fast_travel_discount", t) * 100), " · 감영 중흥(도 명성 +10%)" if lv + 1 >= 5 else ""])
	var rep := gs.add_reputation(int(cost * float(td.get("rep_ratio", 0.08))), "", true)
	gs.note("%s 발전도 %d → %d (명성 +%d)" % [DataDB.display_name(t), lv, lv + 1, rep])
	return true
