#!/usr/bin/env python3
"""Generate the Word style sheets (reference.docx) the templates use. Standard library only.

You normally don't need this: the generated files are committed. To tweak a template's Word
look, the easy route is to open templates/<id>/reference.docx in Word, change the *styles*
(not the text), and save. To regenerate from scratch (it needs Pandoc, so run it in the
build image):

    docker run --rm --platform linux/amd64 -v "$PWD":/data -w /data lawreview-build:latest \\
        python3 scripts/make_reference_docx.py memo templates/memo/reference.docx

Profiles: memo, apa (APA 7th student paper), bib (annotated bibliography), brief13 (Missouri), brief14 (federal). The profile `footer` leaves an existing
file's styles alone and only adds page numbers (used once for the article template).
"""
import re, subprocess, sys, zipfile
from pathlib import Path

FONT = "Times New Roman"

PROFILES = {
    # size in points; line: 240 = single, 480 = double; indent = first-line indent (twips)
    "memo":    dict(size=12, line=240, after=160, indent=0,   fn=10,   headings="memo"),
    "apa":     dict(size=12, line=480, after=0,   indent=720, fn=10,   headings="apa"),
    "bib":     dict(size=12, line=480, after=0,   indent=720, fn=10,   headings="apa", annotation=True),
    "brief13": dict(size=13, line=480, after=0,   indent=720, fn=13,   headings="brief"),
    "brief14": dict(size=14, line=480, after=0,   indent=720, fn=14,   headings="brief"),
}


def rfonts():
    return f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" w:cs="{FONT}"/>'


def rpr(size, bold=False, italic=False, caps=False, smallcaps=False):
    out = rfonts()
    if bold: out += "<w:b/><w:bCs/>"
    if italic: out += "<w:i/><w:iCs/>"
    if caps: out += "<w:caps/>"
    if smallcaps: out += "<w:smallCaps/>"
    out += '<w:color w:val="000000"/>'
    out += f'<w:sz w:val="{int(size * 2)}"/><w:szCs w:val="{int(size * 2)}"/>'
    return out


def ppr(line=240, before=0, after=0, left=None, right=None, first=None, hanging=None, jc=None, keep=False, outline=None):
    out = ""
    if keep: out += "<w:keepNext/><w:keepLines/>"
    out += f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>'
    if any(v is not None for v in (left, right, first, hanging)):
        out += "<w:ind"
        if left is not None: out += f' w:left="{left}"'
        if right is not None: out += f' w:right="{right}"'
        if first is not None: out += f' w:firstLine="{first}"'
        if hanging is not None: out += f' w:hanging="{hanging}"'
        out += "/>"
    if jc: out += f'<w:jc w:val="{jc}"/>'
    if outline is not None: out += f'<w:outlineLvl w:val="{outline}"/>'
    return out


def restyle(xml, sid, p="", r=""):
    """Replace a style's paragraph/run properties, keeping its name and inheritance."""
    pat = re.compile(r'(<w:style [^>]*w:styleId="%s"[^>]*>)(.*?)(</w:style>)' % re.escape(sid), re.S)
    m = pat.search(xml)
    if not m:
        raise SystemExit(f"style {sid} not found in the base reference.docx")
    head = re.split(r"<w:pPr>|<w:rPr>|<w:tblPr>", m.group(2), 1)[0]
    new = m.group(1) + head + (f"<w:pPr>{p}</w:pPr>" if p else "") + (f"<w:rPr>{r}</w:rPr>" if r else "") + m.group(3)
    return xml[:m.start()] + new + xml[m.end():]


def add_style(xml, sid, name, based, p, r):
    style = (f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{sid}"><w:name w:val="{name}"/>'
             f'<w:basedOn w:val="{based}"/><w:qFormat/><w:pPr>{p}</w:pPr><w:rPr>{r}</w:rPr></w:style>')
    return xml.replace("</w:styles>", style + "</w:styles>")


def build_styles(xml, prof):
    s, line, after, ind = prof["size"], prof["line"], prof["after"], prof["indent"]
    xml = re.sub(r"<w:rPrDefault>.*?</w:rPrDefault>",
                 f"<w:rPrDefault><w:rPr>{rfonts()}<w:sz w:val=\"{s * 2}\"/><w:szCs w:val=\"{s * 2}\"/>"
                 f"<w:lang w:val=\"en-US\"/></w:rPr></w:rPrDefault>", xml, flags=re.S)
    xml = restyle(xml, "Normal", ppr(line=line, after=after), rpr(s))
    xml = restyle(xml, "BodyText", ppr(line=line, before=0, after=after, first=ind or None))
    xml = restyle(xml, "FirstParagraph", ppr(line=line, before=0, after=after, first=ind or None))
    xml = restyle(xml, "Compact", ppr(line=240, before=0, after=after if prof["headings"] == "memo" else 0))
    if prof["headings"] == "apa":
        xml = restyle(xml, "BlockText", ppr(line=line, after=0, left=720, first=0))
    else:
        xml = restyle(xml, "BlockText", ppr(line=240, after=240, left=720, right=720, first=0))
    xml = restyle(xml, "FootnoteText", ppr(line=240, after=60), rpr(prof["fn"]))
    for sid in ("Title", "Subtitle", "Author", "Date"):
        xml = restyle(xml, sid, ppr(line=240, after=120, jc="center"), rpr(s + 2 if sid == "Title" else s, bold=sid == "Title"))
    if prof["headings"] == "apa":
        # APA 7 levels: centered bold / flush-left bold / flush-left bold italic / indented bold / indented bold italic
        h = [("Heading1", dict(bold=True), dict(jc="center")),
             ("Heading2", dict(bold=True), dict()),
             ("Heading3", dict(bold=True, italic=True), dict()),
             ("Heading4", dict(bold=True), dict(left=720)),
             ("Heading5", dict(bold=True, italic=True), dict(left=720))]
    elif prof["headings"] == "memo":
        h = [("Heading1", dict(bold=True, caps=True), dict(jc="center", before=240, after=120)),
             ("Heading2", dict(bold=True), dict(before=160, after=80)),
             ("Heading3", dict(bold=True, italic=True), dict(before=120, after=60)),
             ("Heading4", dict(italic=True), dict(before=120, after=60))]
    else:
        h = [("Heading1", dict(bold=True, caps=True), dict(jc="center", before=240, after=240)),
             ("Heading2", dict(bold=True), dict(before=120, after=240)),
             ("Heading3", dict(bold=True), dict(before=120, after=240, left=720)),
             ("Heading4", dict(bold=True), dict(before=120, after=240, left=1440))]
    for i, (sid, rp, pp) in enumerate(h):
        xml = restyle(xml, sid, ppr(line=line if prof["headings"] == "apa" else 240, keep=True, outline=i, **pp), rpr(s, **rp))
    if prof["headings"] == "apa":
        # reference list entries: hanging indent (filters/apa.lua puts them in this style)
        pr = ppr(line=line, after=0, left=720, hanging=720)
        if 'w:styleId="Bibliography"' in xml:
            xml = restyle(xml, "Bibliography", pr)
        else:
            xml = add_style(xml, "Bibliography", "Bibliography", "Normal", pr, "")
    if prof.get("annotation"):
        # annotated bibliography: the annotation under each entry, indented as a block
        xml = add_style(xml, "Annotation", "Annotation", "Normal", ppr(line=line, after=120, left=720, first=720), "")
    xml = add_style(xml, "Centered", "Centered", "Normal", ppr(line=240, after=120, jc="center"), "")
    return xml


FOOTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
          '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
          '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
          '</w:p></w:ftr>')


def add_footer(files, top_right=False):
    """Centered page numbers at the bottom (or, for APA, at the top right), plus 1-inch margins on letter paper."""
    doc = files["word/document.xml"].decode("utf8")
    if "footerReference" in doc or "headerReference" in doc:
        return
    kind = "header" if top_right else "footer"
    part = FOOTER.replace("w:ftr", "w:hdr").replace('<w:jc w:val="center"/>', '<w:jc w:val="right"/>') if top_right else FOOTER
    files["word/%s1.xml" % kind] = part.encode("utf8")
    ct = files["[Content_Types].xml"].decode("utf8")
    files["[Content_Types].xml"] = ct.replace(
        "</Types>", '<Override PartName="/word/%s1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.%s+xml"/></Types>' % (kind, kind)).encode("utf8")
    rels = files["word/_rels/document.xml.rels"].decode("utf8")
    files["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>", '<Relationship Id="rId%s1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/%s" Target="%s1.xml"/></Relationships>' % (kind.title(), kind, kind)).encode("utf8")
    page = ('<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
            'w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>')
    sect = re.search(r"<w:sectPr[^>]*>(.*?)</w:sectPr>", doc, re.S)
    inner = sect.group(1)
    inner = re.sub(r"<w:pgSz[^>]*/>|<w:pgMar[^>]*/>", "", inner)
    # schema order: header/footer references, footnotePr, ..., pgSz, pgMar
    if "</w:footnotePr>" in inner:
        inner = inner.replace("</w:footnotePr>", "</w:footnotePr>" + page, 1)
    else:
        inner = inner + page
    inner = '<w:%sReference w:type="default" r:id="rId%s1"/>' % (kind, kind.title()) + inner
    open_tag = re.search(r"<w:sectPr[^>]*>", doc).group(0)
    doc = doc[:sect.start()] + open_tag + inner + "</w:sectPr>" + doc[sect.end():]
    if "xmlns:r=" not in doc[:2000]:
        doc = doc.replace("<w:document ", '<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    files["word/document.xml"] = doc.encode("utf8")


def read_zip(path_or_bytes):
    import io
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    with zipfile.ZipFile(src) as z:
        return {n: z.read(n) for n in z.namelist()}, [i for i in z.infolist()]


def main():
    if len(sys.argv) != 3 or (sys.argv[1] not in PROFILES and sys.argv[1] != "footer"):
        sys.exit(__doc__)
    profile, out = sys.argv[1], Path(sys.argv[2])
    if profile == "footer":
        files, _ = read_zip(str(out))
    else:
        raw = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True, check=True).stdout
        files, _ = read_zip(raw)
        files["word/styles.xml"] = build_styles(files["word/styles.xml"].decode("utf8"), PROFILES[profile]).encode("utf8")
    add_footer(files, top_right=profile in ("apa", "bib"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml first, as Word expects
        for name in sorted(files, key=lambda n: (n != "[Content_Types].xml", n)):
            z.writestr(name, files[name])
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
