extends Node
## 선택적 에셋 로더. 파일이 없으면 null 을 돌려주고 호출 측이 절차적 그리기로 대체한다.
## 경로·규격은 README.md '에셋 삽입 사양' 과 assets/ASSET_MANIFEST.json(tools/gen_asset_manifest.py) 참조.

const ROOT := "res://assets/"
var _cache: Dictionary = {}

## 폰트: UI 고운돋움 · 본문/굵게 고운바탕 · 한자 대체 Noto Serif KR (모두 SIL OFL, assets/fonts/OFL_*.txt)
const FONT_UI := "res://assets/fonts/GowunDodum-Regular.ttf"
const FONT_TEXT := "res://assets/fonts/GowunBatang-Regular.ttf"
const FONT_BOLD := "res://assets/fonts/GowunBatang-Bold.ttf"
const FONT_HANJA := "res://assets/fonts/NotoSerifKR-Regular.otf"
var font_ui: Font
var font_text: Font
var font_bold: Font


func _ready() -> void:
	_apply_fonts()


func _load_font(path: String, fallback: Font) -> Font:
	if not ResourceLoader.exists(path):
		return null
	var f := load(path) as FontFile
	if f == null:
		return null
	if fallback != null:
		f.fallbacks = [fallback]  # 고운 계열에 없는 한자(不可殺伊·鶴翼陣 등)는 Noto Serif KR 로
	return f


## 창 전체에 기본 테마 적용 — 모든 Control 이 상속. 폰트 파일이 없으면 엔진 기본 폰트 유지
func _apply_fonts() -> void:
	var hanja := _load_font(FONT_HANJA, null)
	font_ui = _load_font(FONT_UI, hanja)
	font_text = _load_font(FONT_TEXT, hanja)
	font_bold = _load_font(FONT_BOLD, hanja)
	if font_ui == null:
		return
	var th := Theme.new()
	th.default_font = font_ui
	th.default_font_size = 16
	if font_text:
		th.set_font("normal_font", "RichTextLabel", font_text)
	if font_bold:
		th.set_font("bold_font", "RichTextLabel", font_bold)
	get_tree().root.theme = th


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
