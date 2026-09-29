"""표준 라이브러리만으로 xlsx 읽기/쓰기 (openpyxl 없이 동작).

read(path)  -> {시트명: [[셀, ...], ...]}   (첫 행 = 헤더)
write(path, sheets, widths=None)            sheets = [(시트명, rows)] — 첫 행은 굵게·틀 고정·자동 필터
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_M = "{%s}" % NS["m"]


def _col_idx(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _col_name(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _num(v):
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() else f


def read(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(_M + "t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for s in wb.find("m:sheets", NS):
        target = rels[s.get("{%s}id" % NS["r"])].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter(_M + "row"):
            vals = {}
            for c in row.findall("m:c", NS):
                t, v = c.get("t"), c.find("m:v", NS)
                if t == "s":
                    val = shared[int(v.text)] if v is not None else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(_M + "t"))
                elif t == "b":
                    val = v is not None and v.text == "1"
                elif v is not None:
                    val = _num(v.text)
                else:
                    val = ""
                vals[_col_idx(c.get("r"))] = val
            if vals:
                rows.append([vals.get(i, "") for i in range(max(vals) + 1)])
        width = max((len(r) for r in rows), default=0)
        out[s.get("name")] = [r + [""] * (width - len(r)) for r in rows]
    return out


def _cell(ref, v, style):
    st = f' s="{style}"' if style else ""
    if isinstance(v, bool):
        return f'<c r="{ref}" t="b"{st}><v>{int(v)}</v></c>'
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{st}><v>{v}</v></c>'
    if v is None or v == "":
        return ""
    txt = escape(str(v)).replace("\n", "&#10;")
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{txt}</t></is></c>'


def _sheet_xml(rows, widths, changed=frozenset(), added_from=None):
    ncol = max((len(r) for r in rows), default=1)
    cols = "".join(f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths[:ncol]))
    body = []
    for ri, r in enumerate(rows, 1):
        cells = []
        for ci, v in enumerate(r):
            if ri == 1:
                style = 4 if (added_from is not None and ci >= added_from) else 1
            else:
                style = 3 if (ri - 1, ci) in changed else 2
            cells.append(_cell(f"{_col_name(ci)}{ri}", v, style))
        cells = "".join(cells)
        body.append(f'<row r="{ri}">{cells}</row>')
    last = f"{_col_name(ncol - 1)}{max(len(rows), 1)}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{NS["m"]}" xmlns:r="{NS["r"]}">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData>'
            f'<autoFilter ref="A1:{last}"/></worksheet>')


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          f'<styleSheet xmlns="{NS["m"]}">'
          '<fonts count="2"><font><sz val="10"/><name val="맑은 고딕"/></font><font><b/><sz val="10"/><name val="맑은 고딕"/></font></fonts>'
          '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
          '<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/></patternFill></fill>'
          '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2A8"/></patternFill></fill>'
          '<fill><patternFill patternType="solid"><fgColor rgb="FFE2EFDA"/></patternFill></fill></fills>'
          '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
          '<cellXfs count="5"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"/>'
          '<xf applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
          '<xf fillId="3" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
          '<xf fontId="1" fillId="4" applyFont="1" applyFill="1"/></cellXfs></styleSheet>')


def _auto_widths(rows):
    ncol = max((len(r) for r in rows), default=1)
    w = []
    for c in range(ncol):
        m = max((len(str(r[c])) if c < len(r) else 0) for r in rows[:200])
        w.append(max(8, min(60, int(m * 1.4) + 2)))
    return w


def write(path, sheets, widths=None, marks=None):
    """marks = {시트명: {"changed": {(행, 열)}, "added_from": 열번호}} — 수정 셀 노랑, 추가 열 헤더 초록."""
    widths = widths or {}
    z = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
    ov = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                 for i in range(1, len(sheets) + 1))
    z.writestr("[Content_Types].xml",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
               '<Default Extension="xml" ContentType="application/xml"/>'
               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
               '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
               f'{ov}</Types>')
    z.writestr("_rels/.rels",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
               '</Relationships>')
    sh = "".join(f'<sheet name="{escape(n[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(sheets, 1))
    dn = "".join(f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">\'{escape(n[:31])}\'!$A$1:${_col_name(max(len(r) for r in rows) - 1)}${len(rows)}</definedName>'
                 for i, (n, rows) in enumerate(sheets) if rows)
    z.writestr("xl/workbook.xml",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               f'<workbook xmlns="{NS["m"]}" xmlns:r="{NS["r"]}"><sheets>{sh}</sheets><definedNames>{dn}</definedNames></workbook>')
    rel = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                  for i in range(1, len(sheets) + 1))
    rel += f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    z.writestr("xl/_rels/workbook.xml.rels",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rel}</Relationships>')
    z.writestr("xl/styles.xml", STYLES)
    for i, (name, rows) in enumerate(sheets, 1):
        meta = marks.get(name, {}) if marks else {}
        z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows, widths.get(name) or _auto_widths(rows),
                                                              meta.get("changed", frozenset()), meta.get("added_from")))
    z.close()
