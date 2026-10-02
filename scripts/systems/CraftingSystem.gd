class_name CraftingSystem
extends RefCounted
## 제작 철칙: 전용 레시피북(비전서·조리서·의서·특산물 레시피북)이 인벤토리에 있어야 해금.
## 예외: [모작] — 해금된 단조법 + Rank + 원자재만으로 전국 어디서나 야외 단조.
## 공 지식: 재료 −3%/랭크(올림), 5랭크 '장인정신' 15% 2배 제작. 대장간 단조는 망치 미니게임(mg_forge) 품질 판정.


static func known_recipes() -> Array:
	var out := []
	var gs := GameState
	for f in DataDB.table("04_food_staples.json", "foods"):  # 섬 풀기(1섬 → 10말) — 비전서 불필요, 보유 시 표시
		if f.has("unpack") and gs.has_item(String(f["id"])):
			var to := String(f["unpack"]["to"])
			out.append({"id": "@unpack_" + String(f["id"]), "name": "섬 풀기: %s → %s ×%d" % [f["name"], DataDB.display_name(to), int(f["unpack"]["qty"])],
				"kind": "unpack", "output": to, "out_qty": int(f["unpack"]["qty"]), "materials": [{"id": f["id"], "qty": 1}],
				"book": "", "facility": "", "min_rank": 1})
	for bid in gs.owned_books():
		var book := DataDB.get_row(bid)
		if book.has("produces"):
			out.append({"id": bid, "name": String(book["name"]).replace("비전서", "제작"), "kind": "specialty",
				"output": book["produces"], "materials": book.get("materials", []), "book": bid,
				"facility": book.get("facility", "gongbang"), "min_rank": 1})
			continue
		for rid in book.get("unlocks", []):
			var rs := String(rid)
			if rs == "@capture_tools":
				for t in DataDB.table("08_capture_tools.json", "tools"):
					out.append({"id": t["id"], "name": t["name"], "kind": "capture", "output": t["id"],
						"materials": t["craft"]["materials"], "book": bid, "facility": "", "min_rank": int(t["tier"])})
				continue
			if rs == "@repair_life_gear":
				out.append({"id": "@repair", "name": "행장 수선", "kind": "repair", "output": "", "book": bid,
					"materials": DataDB.life_gear_repair.get("materials", []), "facility": "", "min_rank": 1})
				continue
			var r := DataDB.get_row(rs)
			if not r.is_empty():
				out.append(_card(r, bid))
	for mj in gs.mojak_unlocked:
		var m := DataDB.get_row(String(mj))
		if not m.is_empty():
			out.append({"id": m["id"], "name": m["name"], "kind": "mojak", "output": m["id"],
				"materials": m["materials"], "book": "", "facility": "", "min_rank": int(m["min_rank"])})
	return out


static func _card(r: Dictionary, bid: String) -> Dictionary:
	var c := {"id": r["id"], "name": r["name"], "output": r["id"], "book": bid, "min_rank": 1, "facility": ""}
	match String(r.get("_sheet", "")):
		"11_food_recipes.json:recipes":
			c["kind"] = "food"
			c["materials"] = r["ingredients"]
			c["cook_at"] = r.get("cook_at", ["jumak_gamasot"])
		"09_herbal_recipes.json:recipes":
			c["kind"] = "medicine"
			c["materials"] = r["ingredients"]
		"02_equipment.json:items":
			c["kind"] = "forge"
			c["materials"] = r.get("acquire", {}).get("materials", [])
			c["min_rank"] = int(r.get("acquire", {}).get("min_rank", 1))
			c["facility"] = "forge"
			c["minigame"] = "mg_forge"
		"06_life_gear.json:life_gear":
			c["kind"] = "tool"
			c["materials"] = r.get("craft", {}).get("materials", [])
			c["min_rank"] = int(r.get("min_rank", 1))
		_:
			c["kind"] = "etc"
			c["materials"] = []
	return c


static func material_mult() -> float:
	return maxf(0.5, 1.0 + GameState.life_effect("gong", "craft_material"))


static func _here_has(facility: String) -> bool:
	if facility == "":
		return true
	if facility == "forge":
		return DataDB.node_has(GameState.current_node, "forge") or DataDB.node_has(GameState.current_node, "forge_basic")
	return DataDB.node_has(GameState.current_node, facility)


static func _has_campfire() -> bool:
	var camp := String(GameState.life_gear.get("camp", ""))
	return camp != "" and String(DataDB.get_row(camp).get("unlock_cooking", "")) == "campfire"


static func check(card: Dictionary) -> String:
	var gs := GameState
	if card["kind"] != "mojak" and String(card.get("book", "")) != "" and not gs.has_item(String(card["book"])):
		return "비전서 미보유"
	if gs.rank < int(card.get("min_rank", 1)):
		return "신분 Rank %d 이상 필요" % int(card["min_rank"])
	if card["kind"] == "food":
		var ok := false
		for place in card.get("cook_at", []):
			if place == "jumak_gamasot" and _here_has("jumak"):
				ok = true
			elif place == "campfire" and _has_campfire():
				ok = true
		if not ok:
			return "주막 가마솥 또는 야영 모닥불(무쇠 노구솥) 필요"
	elif not _here_has(String(card.get("facility", ""))):
		return "%s 이(가) 있는 곳에서만 제작" % card["facility"]
	if not gs.has_materials(card.get("materials", []), material_mult()):
		return "재료 부족: " + materials_text(card.get("materials", []))
	return ""


## quality: 대장간 미니게임 결과(0~1). 1.0 이상이면 명품(스탯 +10% 는 표시만, 추후 품질 시스템)
static func craft(card: Dictionary, quality: float = 1.0) -> String:
	var gs := GameState
	var err := check(card)
	if err != "":
		gs.note("제작 불가 (%s): %s" % [card["name"], err])
		return err
	var mult := 1.0 if card["kind"] == "unpack" else material_mult()
	gs.consume_materials(card.get("materials", []), mult)
	if card["kind"] == "unpack":
		gs.add_item(String(card["output"]), int(card["out_qty"]))
		gs.note("%s 완료" % card["name"])
		gs.advance_minutes(10)
		gs.bump("unpack")
		return ""
	if card["kind"] == "repair":
		var cost := int(float(DataDB.life_gear_repair.get("money", 20)) * (1.0 + gs.life_effect("gong", "repair_cost")))
		if not gs.spend_money(cost):
			return "엽전 부족"
		for id in gs.life_gear.values():
			gs.gear_durability[id] = int(DataDB.get_row(id).get("durability", 100))
		gs.note("행장 수선 완료 (−%d냥)" % cost)
		return ""
	if quality <= 0.0:
		gs.note("단조 실패 — 재료가 상했습니다.")
		return "실패"
	var qty := 2 if gs.has_life_passive("pas_gong") and gs.rng.randf() < 0.15 else 1
	gs.add_item(String(card["output"]), qty)
	gs.add_knowledge_xp("gong", int(DataDB.classes_doc.get("knowledge", {}).get("xp_sources", {}).get("craft_gong", 15)))
	gs.note("%s 완료: %s%s" % ["야외 단조" if card["kind"] == "mojak" else "제작", DataDB.display_name(String(card["output"])), " ×2 (장인정신)" if qty == 2 else ""])
	gs.advance_minutes(60)
	gs.bump("craft")
	return ""


## "무쇠 10/10, 곡물(한 말) 1/1 · 대체: 정련 사철괴 ×4→무쇠" — 공용 재료군은 군 이름, 보유량은 대체 가능 품목 합계
static func materials_text(materials: Array) -> String:
	var gs := GameState
	var parts := PackedStringArray()
	var mm := material_mult()
	for m in materials:
		var have := 0
		for x in gs.material_candidates(m)["items"]:
			have += gs.count(String(x))
		parts.append("%s %d/%d" % [gs.material_label(m), have, maxi(1, int(ceil(int(m["qty"]) * mm)))])
	var txt := ", ".join(parts)
	var plan := gs.material_plan(materials, mm)
	if plan["ok"] and not plan["subs"].is_empty():
		var sp := PackedStringArray()
		for su in plan["subs"]:
			sp.append("%s ×%d→%s" % [DataDB.display_name(String(su["used"])), int(su["qty"]), su["need"]])
		txt += " · 대체: " + ", ".join(sp)
	return txt


static func use_consumable(id: String) -> String:
	var gs := GameState
	var r := DataDB.get_row(id)
	var eff: Dictionary = r.get("effect", {})
	if r.has("satiety") or eff.has("satiety"):
		return "" if SurvivalSystem.eat(id) else "먹을 수 없음"
	if eff.is_empty():
		return "사용할 수 없는 아이템"
	if not gs.remove_item(id):
		return "보유하지 않음"
	if eff.has("heal_pct"):
		gs.hp = minf(gs.hp_max(), gs.hp + gs.hp_max() * float(eff["heal_pct"]))
	var cured := []  # 18 시트 field.cure_by 에 이 처방 id 가 있으면 필드 질병 치료
	for sid in gs.diseases():
		if id in DataDB.status_field.get(sid, {}).get("cure_by", []):
			cured.append(sid)
	gs.cure_field(cured)
	if eff.has("buff"):
		var b: Dictionary = eff["buff"].duplicate()
		b["duration_battles"] = 1
		gs.apply_food_buff(b)
	gs.note("%s 복용" % r["name"])
	gs.stats_changed.emit()
	return ""
