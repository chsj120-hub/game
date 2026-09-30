extends Node
## 데이터 드리븐 파이프라인: res://data/*.json (시트 00~22 + regions) 로드 → id 인덱스 · 도로 그래프 제공.
## 수치·콘텐츠는 JSON 에서만 수정한다(월드는 data_src → tools/build_world.py).

const DATA_DIR := "res://data/"

const SHEETS := {
	"regions.json": ["regions", "nodes"],
	"01_heritage.json": ["heritage"],
	"02_equipment.json": ["items"],
	"03_specialties.json": ["specialties", "specialty_recipes", "trade_quests"],
	"04_food_staples.json": ["foods"],
	"05_materials.json": ["materials"],
	"06_life_gear.json": ["life_gear"],
	"07_mounts.json": ["mounts"],
	"08_capture_tools.json": ["tools"],
	"09_herbal_recipes.json": ["recipes"],
	"10_herbs.json": ["herbs"],
	"11_food_recipes.json": ["recipes"],
	"12_enemies.json": ["enemies"],
	"13_companions.json": ["companions"],
	"14_skills.json": ["skills"],
	"15_recipe_books.json": ["books"],
	"16_mojak_gear.json": ["mojak"],
	"17_instances.json": ["instances"],
	"19_classes_knowledge.json": ["classes"],
	"20_events.json": ["events", "main_scenarios"],
	"21_minigames.json": ["minigames"],
	"23_tutorial.json": ["scenarios", "steps", "help"],
}

var overview: Dictionary = {}
var tables: Dictionary = {}          ## "file:key" -> Array
var by_id: Dictionary = {}           ## id -> row (row["_sheet"] = "file:key")
var docs: Dictionary = {}            ## file -> 원본 문서
var battle_minigames: Dictionary = {}## 17 시트 전투 미니게임(archery/bagua/ssireum/rhythm)
var classes_doc: Dictionary = {}
var status_battle: Dictionary = {}
var status_field: Dictionary = {}
var field_buffs: Dictionary = {}
var side_doc: Dictionary = {}
var category_reward_map: Dictionary = {}
var life_gear_repair: Dictionary = {}
var graph: Dictionary = {}           ## node id -> Array[{to, li, terrain, kind, fare?, days?, wind?}]
var load_errors: PackedStringArray = []


func _ready() -> void:
	reload()


func reload() -> void:
	tables.clear()
	by_id.clear()
	docs.clear()
	load_errors.clear()
	overview = _read_json(DATA_DIR + "00_overview.json")
	for file_name in SHEETS.keys():
		var doc := _read_json(DATA_DIR + file_name)
		docs[file_name] = doc
		for key in SHEETS[file_name]:
			var rows: Array = doc.get(key, [])
			var tk := "%s:%s" % [file_name, key]
			tables[tk] = rows
			for row in rows:
				if typeof(row) != TYPE_DICTIONARY or not row.has("id"):
					continue
				if by_id.has(row["id"]):
					load_errors.append("중복 id: %s (%s)" % [row["id"], file_name])
				row["_sheet"] = tk
				by_id[row["id"]] = row
	battle_minigames = docs.get("17_instances.json", {}).get("minigames", {})
	classes_doc = docs.get("19_classes_knowledge.json", {})
	category_reward_map = docs.get("01_heritage.json", {}).get("category_reward_map", {})
	life_gear_repair = _read_json(DATA_DIR + "06_life_gear.json").get("repair", {})
	var st := _read_json(DATA_DIR + "18_status_effects.json")
	docs["18_status_effects.json"] = st
	for s in st.get("battle", []):
		status_battle[s["id"]] = s
	for s in st.get("field", []):
		status_field[s["id"]] = s
	for s in st.get("field_buffs", []):
		field_buffs[s["id"]] = s
	side_doc = _read_json(DATA_DIR + "22_side_systems.json")
	_build_graph()
	for e in load_errors:
		push_warning(e)
	print("[DataDB] %d 레코드 · 노드 %d · 간선 그래프 %d 로드" % [by_id.size(), nodes().size(), graph.size()])


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		load_errors.append("파일 없음: " + path)
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(parsed) != TYPE_DICTIONARY:
		load_errors.append("JSON 파싱 실패: " + path)
		return {}
	return parsed


func _build_graph() -> void:
	graph.clear()
	var w: Dictionary = docs.get("regions.json", {})
	for e in w.get("edges", []) + w.get("border_links", []):
		_link(String(e["a"]), String(e["b"]), {"li": float(e["li"]), "terrain": String(e["terrain"]), "kind": String(e["kind"])})
	for s in w.get("sea_routes", []):
		_link(String(s["a"]), String(s["b"]), {"li": 0.0, "terrain": "water", "kind": "ferry", "fare": int(s["fare"]), "days": int(s["days"]), "wind": s.get("wind_sensitive", false)})


func _link(a: String, b: String, attr: Dictionary) -> void:
	var ab := attr.duplicate()
	ab["to"] = b
	var ba := attr.duplicate()
	ba["to"] = a
	if not graph.has(a):
		graph[a] = []
	if not graph.has(b):
		graph[b] = []
	graph[a].append(ab)
	graph[b].append(ba)


## 이벤트 우회로 등 런타임 임시 간선
func add_runtime_link(a: String, b: String, attr: Dictionary) -> void:
	_link(a, b, attr)


# ---------------------------------------------------------------- 조회 API
func get_row(id: String) -> Dictionary:
	return by_id.get(id, {})


func has(id: String) -> bool:
	return by_id.has(id)


func table(file_name: String, key: String) -> Array:
	return tables.get("%s:%s" % [file_name, key], [])


func sheet_of(id: String) -> String:
	return String(get_row(id).get("_sheet", ""))


func display_name(id: String) -> String:
	return String(get_row(id).get("name", id))


func skill(id: String) -> Dictionary:
	return get_row(id)


func regions() -> Array:
	return table("regions.json", "regions")


func nodes() -> Array:
	return table("regions.json", "nodes")


func is_node(id: String) -> bool:
	return sheet_of(id) == "regions.json:nodes"


func nodes_in(region_id: String) -> Array:
	return nodes().filter(func(n): return n["region"] == region_id)


func heritage_list() -> Array:
	return table("01_heritage.json", "heritage")


func heritage_at(node_id: String) -> Dictionary:
	var hid := String(get_row(node_id).get("heritage", ""))
	return get_row(hid) if hid != "" else {}


func instances() -> Array:
	return table("17_instances.json", "instances")


func adjacent(region_id: String) -> Array:
	return get_row(region_id).get("adjacent", [])


## 뱃길(sea_routes)로 이어진 다른 권역 — 동선 큐 인접 판정에 육로 인접과 함께 사용(제주 등 뱃길 전용 권역)
func sea_adjacent(region_id: String) -> Array:
	var out := []
	for s in docs.get("regions.json", {}).get("sea_routes", []):
		var ra := region_of_node(String(s["a"]))
		var rb := region_of_node(String(s["b"]))
		if ra == region_id and rb != region_id and not (rb in out):
			out.append(rb)
		elif rb == region_id and ra != region_id and not (ra in out):
			out.append(ra)
	return out


func neighbors(node_id: String) -> Array:
	return graph.get(node_id, [])


## 동선 큐 노드(노드·유산) → 권역
func region_of_node(id: String) -> String:
	var row := get_row(id)
	return String(row.get("region", ""))


## 유산 id 를 노드 id 로 (동선 큐가 유산을 가리킬 때)
func node_of(id: String) -> String:
	if is_node(id):
		return id
	return String(get_row(id).get("node", ""))


func node_pos(node_id: String) -> Vector2:
	var p: Array = get_row(node_id).get("pos", [0, 0])
	return Vector2(float(p[0]), float(p[1]))


func node_has(node_id: String, facility: String) -> bool:
	return facility in get_row(node_id).get("facilities", [])


func class_row(class_id: String) -> Dictionary:
	return get_row(class_id)


func minigame(id: String) -> Dictionary:
	return get_row(id)


func events() -> Array:
	return table("20_events.json", "events")


func main_scenarios() -> Array:
	return table("20_events.json", "main_scenarios")
