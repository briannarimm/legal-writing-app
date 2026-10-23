"""ReSuite: how ReWord works with RePublish, RePDF and the ReSuite hub.

ReWord works on its own; this module only adds what it can do with the other apps when they are
installed. They meet through links in each app's URL scheme and JSON "hand-off" files in the
suite's shared folder (~/Library/Application Support/ReSuite, or RESUITE_SUPPORT_DIR), described in
docs/handoffs.md in briannarimm/resuite. The Swift apps read and write the same JSON (SuiteHandoff).

  outline(slug)            a document as an outline: title, authors, abstract, sections, references
  send_outline(slug, make) hand it to RePublish to make slides, a poster or a handout
  receive(path)            read a hand-off sent to ReWord (only from the Handoffs folder)
  receive_highlights(path) RePDF's highlights as a research note, once per hand-off
  note_from_highlights(h)  a research note quoting a PDF's highlights (from RePDF)
  launch(app) / open_files(app, paths) / open_link(app, action, query)

Nothing here writes to another app's files: ReWord writes only hand-offs, in the suite's folder.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

import store

APPS = {
    "hub": {"name": "ReSuite", "bundle": "com.briannarimm.ReSuite", "scheme": "resuite",
            "get": "https://github.com/briannarimm/resuite/releases/latest"},
    "reword": {"name": "ReWord", "bundle": "app.reword", "scheme": "reword",
               "get": "https://github.com/briannarimm/legal-writing-app/tree/main/distro"},
    "republish": {"name": "RePublish", "bundle": "com.briannarimm.RePublish", "scheme": "republish",
                  "get": "https://github.com/briannarimm/republisher/releases/latest"},
    "repdf": {"name": "RePDF", "bundle": "com.briannarimm.RePDF", "scheme": None,
              "get": "https://github.com/briannarimm/repdf#build-and-run"},
}
MAKES = ("slides", "poster", "handout")
MAX_HANDOFF = 4_000_000            # bytes; a hand-off is a few kilobytes of text
KEEP_HANDOFFS = 7 * 24 * 3600      # the next sender clears older ones away


class SuiteError(store.StoreError):
    pass


def available():
    """The other apps are Mac apps: links and hand-offs work only there."""
    return sys.platform == "darwin"


def support_dir():
    d = os.environ.get("RESUITE_SUPPORT_DIR")
    p = Path(d) if d else Path.home() / "Library" / "Application Support" / "ReSuite"
    return p


def handoffs_dir():
    p = support_dir() / "Handoffs"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ opening the other apps

def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 127


RUN = _run          # tests replace this to see the commands instead of running them


def _get(app):
    """The app isn't installed: open the page to get it."""
    RUN(["open", APPS[app]["get"]])
    return {"ok": True, "installed": False, "name": APPS[app]["name"]}


def launch(app):
    if app not in APPS:
        raise SuiteError("unknown app")
    if RUN(["open", "-b", APPS[app]["bundle"]]) != 0:
        return _get(app)
    return {"ok": True, "installed": True}


def open_files(app, paths):
    if app not in APPS:
        raise SuiteError("unknown app")
    if RUN(["open", "-b", APPS[app]["bundle"]] + [str(p) for p in paths]) != 0:
        return _get(app)
    return {"ok": True, "installed": True}


def link(app, action, query=None):
    q = urllib.parse.urlencode(sorted((query or {}).items()), quote_via=urllib.parse.quote)
    return "%s://%s%s" % (APPS[app]["scheme"], action, "?" + q if q else "")


def open_link(app, action, query=None):
    if app not in APPS or not APPS[app]["scheme"]:
        raise SuiteError("unknown app")
    if RUN(["open", link(app, action, query)]) != 0:
        return _get(app)
    return {"ok": True, "installed": True}


# ------------------------------------------------------------------ suite projects (read only)

def suite_projects():
    out = []
    folder = support_dir() / "Projects"
    if not folder.is_dir():
        return out
    for f in sorted(folder.glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(p, dict) and isinstance(p.get("id"), str):
            out.append(p)
    return out


def suite_project_for(slug="", project=""):
    """The suite project that holds a document, or the ReWord project it is in."""
    best = None
    for p in suite_projects():
        for it in p.get("items") or []:
            if not isinstance(it, dict):
                continue
            if slug and it.get("kind") == "rewordDocument" and it.get("path") == slug:
                return p
            if project and it.get("kind") == "rewordProject" and it.get("path") == project:
                best = best or p
    return best


def suite_project_summary(p):
    if not p:
        return None
    return {"id": p["id"], "name": (p.get("name") or "").strip() or (p.get("details") or {}).get("title") or "Untitled Project",
            "color": p.get("color") or "#3B6FD4"}


# ------------------------------------------------------------------ a document as an outline

def read_meta(text):
    """The few metadata.yaml keys an outline needs: plain `key: value` lines, `key: |` blocks and an
    author list (`- name: …`). Comments and anything else are skipped; this is not a YAML parser."""
    meta, lines, i = {}, text.replace("\r\n", "\n").split("\n"), 0

    def scalar(v):
        v = v.split(" #")[0].strip() if not v.strip().startswith(('"', "'")) else v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\") if v[0] == '"' else v[1:-1].replace("''", "'")
        return v.strip()

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        i += 1
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest in ("|", ">", "|-", ">-"):
            block = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                block.append(lines[i].strip())
                i += 1
            joined = "\n".join(block).strip()
            meta[key] = re.sub(r"(?<!\n)\n(?!\n)", " ", joined) if rest.startswith(">") or key == "abstract" else joined
        elif rest == "":
            items = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                s = lines[i].strip()
                i += 1
                named = re.match(r"^(?:-\s+)?name:\s*(.+)$", s)
                plain = re.match(r"^-\s+(.+)$", s)
                if named:
                    items.append(scalar(named.group(1)))
                elif plain and not re.match(r"^[\w-]+:(\s|$)", plain.group(1)):
                    items.append(scalar(plain.group(1)))
            if items:
                meta[key] = items
        else:
            meta[key] = scalar(rest)
    return meta


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*(\{[^}]*\})?\s*#*\s*$")
LIST_RE = re.compile(r"^\s{0,3}(?:[-+*]|\d+[.)])\s+(.*)$")
FN_DEF_RE = re.compile(r"^\[\^[^\]\s]+\]:")
PLACEHOLDER_RE = re.compile(r"replace this placeholder|^state the problem|^describe the doctrine", re.I)


def _plain(md):
    return store.md_plain(md).strip()


def _clip(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + "…").strip()


def _blocks(md):
    """A section file's Markdown as (kind, level, text) blocks: headings, list items and paragraphs.
    Footnote definitions, comments, tables, code and raw blocks are left out."""
    md = re.sub(r"<!--.*?-->", "", md.replace("\r\n", "\n"), flags=re.S)
    out, para, skip = [], [], False

    def flush():
        if para:
            out.append(("p", 0, " ".join(para)))
            para.clear()

    in_fence = False
    for line in md.split("\n"):
        if line.strip().startswith(("```", "~~~", ":::")):
            flush()
            in_fence = not in_fence if line.strip().startswith(("```", "~~~")) else in_fence
            continue
        if in_fence:
            continue
        if FN_DEF_RE.match(line):
            flush()
            skip = True
            continue
        if skip:
            if line.startswith(("    ", "\t")) or not line.strip():
                continue
            skip = False
        if line.lstrip().startswith("|") or line.lstrip().startswith("<"):
            flush()
            continue
        h = HEADING_RE.match(line)
        if h:
            flush()
            out.append(("h", len(h.group(1)), h.group(2)))
            continue
        li = LIST_RE.match(line)
        if li:
            flush()
            out.append(("li", 0, li.group(1)))
            continue
        if not line.strip():
            flush()
        elif out and out[-1][0] == "li" and not para and line.startswith((" ", "\t")):
            out[-1] = ("li", 0, out[-1][2] + " " + line.strip())
        else:
            para.append(line.strip())
    flush()
    return out


def _name_of(path):
    return re.sub(r"^\d{2}-", "", path.stem).replace("-", " ").strip().capitalize()


def outline(slug):
    p = store.doc_path(slug)
    info = store.read_doc_info(p)
    meta_file = p / store.META
    meta = read_meta(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    title = (info.get("title") or meta.get("title") or slug).strip()
    authors = meta.get("author") or meta.get("from") or []
    if isinstance(authors, str):
        authors = [authors]
    details = {"title": title, "subtitle": meta.get("subtitle", ""), "presenter": ", ".join(a for a in authors if a),
               "date": meta.get("date", "")}
    abstract = _plain(meta.get("abstract", ""))
    if PLACEHOLDER_RE.search(abstract):
        abstract = ""

    sections, references, cur, in_refs = [], [], None, False
    for f in store.section_paths(slug):
        blocks = _blocks(f.read_text(encoding="utf-8"))
        if blocks and blocks[0][0] != "h":
            blocks.insert(0, ("h", 1, _name_of(f)))
        for kind, level, text in blocks:
            if kind == "h" and level == 1:
                in_refs = bool(store.REFS_HEADING_RE.match("# " + text))
                cur = None if in_refs else {"heading": _plain(text), "text": "", "bullets": [], "_paras": []}
                if cur is not None:
                    sections.append(cur)
                continue
            if in_refs:
                if kind in ("li", "p") and _plain(text):
                    references.append(_plain(text))
                continue
            if cur is None:
                continue
            t = _plain(text)
            if not t or PLACEHOLDER_RE.search(t):
                continue
            if kind == "h":
                cur["bullets"].append(t)
            elif kind == "li":
                cur["bullets"].append(_clip(t, 200))
            else:
                cur["_paras"].append(t)

    for s in sections:
        s["text"] = _clip(" ".join(s.pop("_paras")[:2]), 700)
        s["bullets"] = s["bullets"][:8]
    sections = [s for s in sections if s["heading"] and (s["text"] or s["bullets"])] or \
        [s for s in sections if s["heading"]]

    if not references:
        seen = []
        for f in store.section_paths(slug):
            for t in store.cited_tags(f.read_text(encoding="utf-8")):
                if t not in seen:
                    seen.append(t)
        for t in seen[:40]:
            try:
                c = store.read_citation(store.cite_path(t))
            except (store.StoreError, OSError):
                continue
            if c.get("cite"):
                references.append(_plain(c["cite"]))

    h = {"version": 1, "kind": "outline", "from": "reword", "created": _now(), "title": title,
         "subtitle": details["subtitle"], "details": {k: v for k, v in details.items() if v},
         "abstract": abstract, "sections": sections, "references": references[:40], "source": str(p)}
    sp = suite_project_for(slug, info.get("project", ""))
    if sp:
        h["suiteProject"] = sp["id"]
    return h


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_handoff(h):
    folder = handoffs_dir()
    f = folder / (str(uuid.uuid4()).upper() + ".json")
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(h, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)
    prune()
    return f


def prune():
    old = time.time() - KEEP_HANDOFFS
    for f in handoffs_dir().iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < old:
                f.unlink()
        except OSError:
            pass


def send_outline(slug, make):
    if make not in MAKES:
        raise SuiteError("RePublish can make slides, a poster or a handout.")
    h = outline(slug)
    if not h["sections"] and not h["abstract"]:
        raise SuiteError("This document has no text to make %s from yet." % ("slides" if make == "slides" else "a " + make))
    f = write_handoff(h)
    r = open_link("republish", "handoff", {"file": str(f), "make": make})
    r["sections"] = len(h["sections"])
    return r


# ------------------------------------------------------------------ hand-offs sent to ReWord

def receive(path):
    """The hand-off at `path`, if it is a JSON file directly inside the Handoffs folder (after
    resolving links), so a link from anywhere can't make ReWord read any other file."""
    if not isinstance(path, str) or not path:
        raise SuiteError("no hand-off")
    f = Path(path).expanduser().resolve()
    if f.parent != handoffs_dir().resolve() or f.suffix != ".json" or not f.is_file():
        raise SuiteError("ReWord only reads hand-offs from the ReSuite folder.", 403)
    if f.stat().st_size > MAX_HANDOFF:
        raise SuiteError("That hand-off is too large.")
    try:
        h = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SuiteError("That hand-off couldn't be read.")
    if not isinstance(h, dict) or h.get("kind") not in ("outline", "highlights", "details"):
        raise SuiteError("That hand-off couldn't be read.")
    return h


def _source_tag(source):
    """The citation a PDF belongs to, when it is one of the library's files (library/files/<tag>/…)."""
    if not isinstance(source, str) or not source:
        return ""
    try:
        f = Path(source).expanduser().resolve()
        files = (store.ROOT / "library" / "files").resolve()
    except OSError:
        return ""
    if files in f.parents and f.parent.parent == files and store.TAG_RE.match(f.parent.name):
        return f.parent.name if store.cite_path(f.parent.name).exists() else ""
    return ""


def _reword_project(h):
    sp = h.get("suiteProject")
    if not isinstance(sp, str):
        return ""
    for p in suite_projects():
        if p.get("id", "").upper() == sp.upper():
            for it in p.get("items") or []:
                if isinstance(it, dict) and it.get("kind") == "rewordProject" and store.project_exists(it.get("path") or ""):
                    return it["path"]
    return ""


def _quote(text):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return re.sub(r"([\\`*_\[\]{}<>#|])", r"\\\1", t)


def note_from_highlights(h, project=""):
    """A research note quoting a PDF's highlights in page order, each with its page and comment."""
    items = [x for x in (h.get("highlights") or []) if isinstance(x, dict) and (str(x.get("text") or "").strip() or str(x.get("note") or "").strip())]
    if not items:
        raise SuiteError("There are no highlights to make a note from.")
    items.sort(key=lambda x: x.get("page") if isinstance(x.get("page"), int) and not isinstance(x.get("page"), bool) else 0)
    source = h.get("source") if isinstance(h.get("source"), str) else ""
    name = (str(h.get("title") or "").strip() or (Path(source).stem if source else "") or "a PDF")
    parts = []
    for x in items:
        page = x.get("page") if isinstance(x.get("page"), int) and not isinstance(x.get("page"), bool) and x.get("page") > 0 else None
        # RePDF sends the page's printed label too ("iv", "A-3"), which is what a cite uses.
        shown = str(x.get("pageLabel") or "").strip()[:20] if isinstance(x.get("pageLabel"), str) else ""
        shown = _quote(shown) or (str(page) if page else "")
        text, note = _quote(x.get("text")), str(x.get("note") or "").strip()
        label = _quote(x.get("label"))
        if text:
            parts.append("> " + text + (" (p. %s)" % shown if shown else ""))
        elif shown:
            parts.append("*p. %s*" % shown)
        if label:
            parts.append("**" + label + "**")
        if note:
            parts.append(note)
    tag = _source_tag(source)
    body = "\n\n".join(parts)
    project = project or _reword_project(h)
    return store.create_note("Highlights: " + name, topic="From RePDF", body=body, project=project,
                             citations=[tag] if tag else [])


_notes_made = {}       # hand-off file -> the note made from it, so a link opened twice makes one note


def receive_highlights(path, project=""):
    h = receive(path)
    if h.get("kind") != "highlights":
        raise SuiteError("ReWord makes research notes from highlights. Open this in RePublish instead.")
    key = str(Path(path).expanduser().resolve())
    nid = _notes_made.get(key)
    if nid and store.note_path(nid).exists():
        return store.read_note(store.note_path(nid))
    note = note_from_highlights(h, project)
    _notes_made[key] = note["id"]
    return note
