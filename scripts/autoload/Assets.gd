extends Node
## 선택적 에셋 로더. 파일이 없으면 null 을 돌려주고 호출 측이 절차적 그리기로 대체한다.
## 경로·규격은 README.md '에셋 삽입 사양' 과 assets/ASSET_MANIFEST.json(tools/gen_asset_manifest.py) 참조.

const ROOT := "res://assets/"
var _cache: Dictionary = {}


func tex(path: String) -> Texture2D:
	if _cache.has(path):
		return _cache[path]
	var t: Texture2D = null
	if path != "" and ResourceLoader.exists(path):
		t = load(path)
	_cache[path] = t
	return t


func item_icon(id: String) -> Texture2D:
	var row := DataDB.get_row(id)
	if row.has("icon"):
		var t := tex(ROOT + "icons/common/" + String(row["icon"]))
		if t:
			return t
	return tex(ROOT + "icons/items/%s.png" % id)


func heritage_icon(her_id: String) -> Texture2D:
	return tex(ROOT + "icons/heritage/%s.png" % her_id)


func node_marker(node_type: String) -> Texture2D:
	return tex(ROOT + "ui/markers/%s.png" % node_type)


func portrait(id: String) -> Texture2D:
	return tex(ROOT + "portraits/%s.png" % id)


func class_icon(class_id: String) -> Texture2D:
	return tex(ROOT + "ui/class/%s.png" % class_id)


func status_icon(sid: String) -> Texture2D:
	return tex(ROOT + "ui/status/%s.png" % sid)


func region_map(region_id: String) -> Texture2D:
	return tex(String(DataDB.get_row(region_id).get("map_texture", "")))


func parallax(region_id: String, layer: String) -> Texture2D:
	return tex(String(DataDB.get_row(region_id).get("parallax_dir", "")) + layer + ".png")


func sprite_sheet(id: String, anim: String) -> Texture2D:
	return tex(ROOT + "characters/%s/%s.png" % [id, anim])


func overworld() -> Texture2D:
	return tex(ROOT + "maps/overworld.png")


## 9-패치 패널 (없으면 StyleBoxFlat 대체)
func panel_style(name: String, fallback_bg: Color, border: Color) -> StyleBox:
	var t := tex(ROOT + "ui/panels/%s.png" % name)
	if t:
		var sb := StyleBoxTexture.new()
		sb.texture = t
		sb.set_texture_margin_all(24)
		sb.set_content_margin_all(14)
		return sb
	var f := StyleBoxFlat.new()
	f.bg_color = fallback_bg
	f.border_color = border
	f.set_border_width_all(3)
	f.set_content_margin_all(14)
	return f
