"""File-backed storage for ReWord. Standard library only.

    documents/<name>/   one document: document.json, metadata.yaml, NN-section.md ...
    research/<id>.md    one research note
    library/citations/<tag>.md   one citation in the shared library

Notes and citations are Markdown files with a small header (JSON values, so they are valid
YAML too):

    ---
    type: "case"
    short: "*Smith*"
    ---
    *Smith v. Jones*, 123 F.3d 456 (8th Cir. 1999)

Everything is ordinary text, so git tracks it and nothing is locked inside the app.
"""
import datetime
import json
import os
import re
import time
from pathlib import Path

# Two roots. DATA holds everything you create (documents, research, library, build, outputs, settings).
# CODE holds the program's own files (templates, filters, scripts). Running from the project
# folder they're the same place; in the portable app, CODE is inside the app and DATA is the
# "ReWord Data" folder next to it (so your work travels on the USB drive).
ROOT = Path(__file__).resolve().parent.parent
CODE = ROOT

SECTION_RE = re.compile(r"^\d{2}-[a-z0-9][a-z0-9-]*\.md$")
META = "metadata.yaml"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
TAG_RE = SLUG_RE
import citeformat  # noqa: E402  (Bluebook / APA formatting of structured citations)
CITE_TYPES = list(citeformat.TYPES)


class StoreError(Exception):
    """A problem the user can understand (bad name, already exists...)."""

    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def set_root(path):
    global ROOT
    ROOT = Path(path).resolve()


def set_code(path):
    global CODE
    CODE = Path(path).resolve()


# ------------------------------------------------------------------ helpers

def slugify(text, fallback="untitled", limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].strip("-") or fallback


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def mtime_of(path):
    return str(path.stat().st_mtime_ns)


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def trash(path, folder):
    """Move a file or folder into <folder>/_trash/ with a timestamp, never delete it."""
    t = folder / "_trash"
    t.mkdir(parents=True, exist_ok=True)
    os.rename(path, t / (time.strftime("%Y%m%d-%H%M%S-") + path.name))


def unique(base, exists):
    s, i = base, 2
    while exists(s):
        s = "%s-%d" % (base, i)
        i += 1
    return s


def parse_front(text):
    """Split '---\\nkey: json\\n---\\nbody' into ({key: value}, body)."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[4:end].split("\n"):
        k, sep, v = line.partition(":")
        if not sep:
            continue
        v = v.strip()
        try:
            meta[k.strip()] = json.loads(v)
        except ValueError:
            meta[k.strip()] = v
    return meta, text[end + 5:]


def dump_front(meta, body):
    head = "".join("%s: %s\n" % (k, json.dumps(v, ensure_ascii=False)) for k, v in meta.items())
    return "---\n" + head + "---\n" + body.strip("\n") + "\n"


# ------------------------------------------------------------------ templates

def templates():
    out = []
    for p in sorted((CODE / "templates").glob("*/template.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    order = ["article", "assignment", "journal-apa", "journal-chicago", "journal-chicago-ad", "bibliography", "memo",
             "brief-federal", "brief-missouri", "email"]
    out.sort(key=lambda t: order.index(t["id"]) if t["id"] in order else 99)
    return out


def template(tid):
    for t in templates():
        if t["id"] == tid:
            return t
    raise StoreError("Unknown template: %s" % tid)


# ------------------------------------------------------------------ documents

def docs_dir():
    return ROOT / "documents"


def doc_path(slug):
    if not SLUG_RE.match(slug or ""):
        raise StoreError("invalid document name")
    p = docs_dir() / slug
    if not (p / "document.json").exists():
        raise StoreError("no such document", 404)
    return p


def read_doc_info(p):
    try:
        info = json.loads((p / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    info["slug"] = p.name
    info.setdefault("title", p.name)
    info.setdefault("template", "article")
    files = [f for f in p.glob("*") if f.is_file()]
    info["updated"] = max((f.stat().st_mtime for f in files), default=0)
    return info


def documents():
    out = []
    if docs_dir().exists():
        for p in sorted(docs_dir().iterdir()):
            if p.is_dir() and not p.name.startswith("_") and (p / "document.json").exists():
                out.append(read_doc_info(p))
    return out


def create_document(tid, title, project=""):
    t = template(tid)
    proj = read_project(project) if project else None
    title = (title or "").strip() or "Untitled " + t["name"].lower()
    slug = unique(slugify(title, "document"), lambda s: (docs_dir() / s).exists())
    seed = CODE / "templates" / tid / "seed"
    if not seed.is_dir():
        raise StoreError("This template has no starter files.")
    dest = docs_dir() / slug
    dest.mkdir(parents=True)
    yaml_title = title.replace("\\", "\\\\").replace('"', '\\"')
    for f in sorted(seed.iterdir()):
        if f.is_file():
            text = f.read_text(encoding="utf-8").replace("{{title}}", yaml_title if f.suffix == ".yaml" else title)
            if proj and f.name == META and t.get("cite_style") == "document" and proj.get("citation_style"):
                text = re.sub(r"(?m)^citation-style:.*$", "citation-style: " + proj["citation_style"], text)
            write_atomic(dest / f.name, text)
    info = {"title": title, "template": tid, "created": now()}
    if proj:
        info["project"] = proj["id"]
    write_atomic(dest / "document.json", json.dumps(info, indent=2) + "\n")
    if proj:
        assign_document_citations(slug)
    return slug


def rename_document(slug, title):
    p = doc_path(slug)
    info = json.loads((p / "document.json").read_text(encoding="utf-8"))
    info["title"] = (title or "").strip() or info.get("title", slug)
    write_atomic(p / "document.json", json.dumps(info, indent=2) + "\n")
    return info["title"]


DOC_OPTIONS = {"final_draft": bool, "project": str}       # per-document settings kept in document.json


def set_doc_option(slug, key, value):
    if key not in DOC_OPTIONS:
        raise StoreError("unknown option")
    p = doc_path(slug)
    info = json.loads((p / "document.json").read_text(encoding="utf-8"))
    if key == "project":
        value = (value or "").strip()
        if value:
            read_project(value)                  # must exist
            info["project"] = value
        else:
            info.pop("project", None)
    else:
        info[key] = DOC_OPTIONS[key](value)
    write_atomic(p / "document.json", json.dumps(info, indent=2) + "\n")
    if key == "project" and value:
        assign_document_citations(slug)          # moving a document brings its sources along (add-only)
    return info


REFS_HEADING_RE = re.compile(r"^#\s+(References?|Bibliography|Works Cited)\s*(\{[^}]*\})?\s*$", re.I)


def _refs_section(slug):
    """The section that holds the reference list (its first line is a References/Bibliography heading)."""
    for f in section_paths(slug):
        first = next((ln for ln in f.read_text(encoding="utf-8").split("\n") if ln.strip()), "")
        if REFS_HEADING_RE.match(first):
            return f
    return None


def change_template(slug, tid):
    """Switch a document to another template, converting it: citations move between footnotes and the text
    as the new citation system needs (convert.py), the reference list is renamed, added or removed, and the
    details (metadata.yaml) are rebuilt from the new template with the title, authors and abstract carried
    over. The files as they were are copied to the document's _trash folder first. Returns a report."""
    import shutil
    import cites
    import convert
    p = doc_path(slug)
    info = json.loads((p / "document.json").read_text(encoding="utf-8"))
    old_t, new_t = template(info.get("template", "article")), template(tid)
    if old_t["id"] == new_t["id"]:
        return {"template": tid, "name": new_t["name"], "unchanged": True}
    if old_t.get("bibliography") or new_t.get("bibliography"):
        raise StoreError("An annotated bibliography is a list of sources rather than a paper, so it can't switch to or "
                         "from another template. Start a new document from the template you want instead.")
    old_style, new_style = cites.style_of(old_t)[0], cites.style_of(new_t)[0]
    src, dst = convert.placement(old_t, old_style), convert.placement(new_t, new_style)

    # 1. keep a copy of everything as it was
    backup = p / "_trash" / (time.strftime("%Y%m%d-%H%M%S-") + "before-" + tid)
    backup.mkdir(parents=True, exist_ok=True)
    for f in section_paths(slug) + [p / META, p / "document.json"]:
        if f.exists():
            shutil.copy2(f, backup / f.name)

    # 2. citations: footnotes <-> text
    lib = {c["tag"]: c for c in citations()}
    author_year = citeformat.chicago_ad_author_year if old_style == "chicago-ad" else citeformat.apa_author_year

    def names_for(tag):
        c = lib.get(tag)
        return citeformat.to_md(author_year(c, True)[0]) if c else tag
    sections = [(f.name, f.read_text(encoding="utf-8")) for f in section_paths(slug)]
    converted, report = convert.convert_sections(sections, src, dst, names_for)
    for (name, before), (_, after) in zip(sections, converted):
        if after != before:
            write_atomic(p / name, after)

    # 3. the reference list
    heading = cites.REF_HEADING.get(new_style)
    refs = _refs_section(slug)
    report["references"] = ""
    seed_refs = None
    for f in sorted((CODE / "templates" / tid / "seed").glob("[0-9]*.md")):
        first = next((ln for ln in f.read_text(encoding="utf-8").split("\n") if ln.strip()), "")
        if REFS_HEADING_RE.match(first):
            seed_refs = f
    if heading and refs:
        lines = refs.read_text(encoding="utf-8").split("\n")
        k = next(i for i, ln in enumerate(lines) if ln.strip())
        m = REFS_HEADING_RE.match(lines[k])
        typed = re.sub(r"<!--.*?-->", "", "\n".join(lines[k + 1:]), flags=re.S).strip()
        if not typed and seed_refs:              # only the heading and its note: take the new template's
            if refs.read_text(encoding="utf-8") != seed_refs.read_text(encoding="utf-8"):
                write_atomic(refs, seed_refs.read_text(encoding="utf-8"))
        elif m.group(1) != heading:
            lines[k] = "# " + heading + (" " + m.group(2) if m.group(2) else "")
            write_atomic(refs, "\n".join(lines))
        if m.group(1) != heading:
            report["references"] = "renamed"
    elif heading and seed_refs:
        n = max([int(x.name[:2]) for x in section_paths(slug)] + [0]) + 1
        if n <= 99:
            write_atomic(p / ("%02d-%s" % (n, seed_refs.name[3:])), seed_refs.read_text(encoding="utf-8"))
            report["references"] = "added"
    elif refs:
        body = refs.read_text(encoding="utf-8").split("\n", 1)[1:]
        rest = re.sub(r"<!--.*?-->", "", body[0] if body else "", flags=re.S).strip()
        if rest:
            report["references"] = "kept"
        else:
            trash(refs, p)
            report["references"] = "removed"

    # 4. the details: the new template's starter file, with what carries over
    seed_meta = CODE / "templates" / tid / "seed" / META
    old_meta = (p / META).read_text(encoding="utf-8") if (p / META).exists() else ""
    if seed_meta.exists():
        write_atomic(p / META, convert.convert_metadata(old_meta, seed_meta.read_text(encoding="utf-8"),
                                                         info.get("title", slug), old_t["name"]))
    info["template"] = tid
    write_atomic(p / "document.json", json.dumps(info, indent=2) + "\n")

    # 5. sources Chicago would like more details for (they still format without them)
    gaps = []
    if new_style.startswith("chicago"):
        tags = set()
        for f in section_paths(slug):
            tags |= cited_tags(f.read_text(encoding="utf-8"))
        for t in sorted(tags):
            if t in lib:
                missing = citeformat.chicago_gaps(lib[t])
                if missing:
                    gaps.append({"tag": t, "missing": missing})
    report.update({"template": tid, "name": new_t["name"], "from": old_t["name"], "gaps": gaps,
                   "backup": str(backup.relative_to(ROOT)) if backup.is_relative_to(ROOT) else str(backup)})
    return report


def delete_document(slug):
    p = doc_path(slug)
    trash(p, docs_dir())
    b = ROOT / "build" / slug
    if b.exists():
        import shutil
        shutil.rmtree(b, ignore_errors=True)


def section_paths(slug):
    return sorted(p for p in doc_path(slug).glob("[0-9]*.md") if SECTION_RE.match(p.name))


def doc_files(slug):
    p = doc_path(slug)
    files = []
    meta = p / META
    files.append({"file": META, "kind": "meta", "md": meta.read_text(encoding="utf-8") if meta.exists() else "",
                  "mtime": mtime_of(meta) if meta.exists() else "0"})
    for s in section_paths(slug):
        files.append({"file": s.name, "kind": "section", "md": s.read_text(encoding="utf-8"), "mtime": mtime_of(s)})
    return files


def resolve_doc_file(slug, name):
    if name != META and not SECTION_RE.match(name or ""):
        raise StoreError("invalid file name")
    return doc_path(slug) / name


def save_file(path, content, mtime=None, force=False):
    if not isinstance(content, str):
        raise StoreError("no content")
    if path.exists() and not force and mtime not in (None, mtime_of(path)):
        raise StoreError("changed on disk", 409, mtime=mtime_of(path))
    write_atomic(path, content)
    return mtime_of(path)


def new_section(slug, title, heading="#"):
    sections = section_paths(slug)
    n = (max(int(p.name[:2]) for p in sections) + 1) if sections else 1
    if n > 99:
        raise StoreError("too many sections")
    title = (title or "").strip() or "New section"
    path = doc_path(slug) / ("%02d-%s.md" % (n, slugify(title, "section")))
    write_atomic(path, "%s %s\n\n" % (heading, title.replace("#", "").strip()))
    return path.name


def move_section(slug, name, direction):
    files = section_paths(slug)
    names = [p.name for p in files]
    if name not in names:
        raise StoreError("no such section")
    i = names.index(name)
    j = i - 1 if direction == "up" else i + 1
    if j < 0 or j >= len(files):
        return name
    a, c = files[i], files[j]
    new_a = c.parent / (c.name[:2] + a.name[2:])
    new_c = a.parent / (a.name[:2] + c.name[2:])
    tmp = a.parent / (a.name + ".swap")
    os.rename(a, tmp)
    os.rename(c, new_c)
    os.rename(tmp, new_a)
    return new_a.name


def delete_section(slug, name):
    path = resolve_doc_file(slug, name)
    if name == META or not path.exists():
        raise StoreError("can't delete that")
    trash(path, doc_path(slug))


# ------------------------------------------------------------------ versions
# A "version" is a named snapshot of a document's text, kept inside the document folder
# (documents/<name>/.versions/<version>/). Redlines compare against the newest one. This works
# anywhere, with or without git installed; git tags are an optional extra on top.

VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")


def versions_dir(slug):
    return doc_path(slug) / ".versions"


def version_path(slug, name):
    if not VERSION_RE.match(name or ""):
        raise StoreError("Version names can use letters, numbers, dots and dashes (for example v0.2).")
    return versions_dir(slug) / name


def list_versions(slug):
    vd = versions_dir(slug)
    out = []
    if vd.is_dir():
        for p in vd.iterdir():
            if p.is_dir() and VERSION_RE.match(p.name):
                try:
                    created = json.loads((p / "_version.json").read_text(encoding="utf-8")).get("created", "")
                except (OSError, ValueError):
                    created = ""
                out.append({"name": p.name, "created": created or time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))})
    out.sort(key=lambda v: v["created"])
    return out


def last_version(slug):
    v = list_versions(slug)
    return v[-1] if v else None


def create_version(slug, name):
    dest = version_path(slug, name)
    if dest.exists():
        raise StoreError("A version named %s already exists for this document." % name)
    dest.mkdir(parents=True)
    src = doc_path(slug)
    for f in section_paths(slug) + [src / META]:
        if f.exists():
            (dest / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (dest / "_version.json").write_text(json.dumps({"created": now()}) + "\n", encoding="utf-8")
    return dest


# ------------------------------------------------------------------ citations

def cite_dir():
    return ROOT / "library" / "citations"


def cite_path(tag):
    if not TAG_RE.match(tag or ""):
        raise StoreError("A tag can use lowercase letters, numbers and dashes (for example smith-v-jones).")
    return cite_dir() / (tag + ".md")


def read_citation(p):
    """A citation file: front matter (type, fields as JSON, dates) + the practitioner Bluebook form as the body.
    The body and the "short"/"toa" keys are generated from the fields; older tools (the table of
    authorities) read them, so they are always rewritten on save. Files from before structured citations
    (no "fields") are treated as type "other" with the old text."""
    meta, body = parse_front(p.read_text(encoding="utf-8"))
    ctype = meta.get("type", "other")
    fields = meta.get("fields")
    if not isinstance(fields, dict) or ctype not in citeformat.TYPES:
        ctype, fields = "other", {"text": body.strip(), "short": meta.get("short", ""), "url": meta.get("url", "")}
    c = {"tag": p.stem, "type": ctype, "fields": fields}
    c.update({"cite": body.strip(), "short": meta.get("short", ""), "url": fields.get("url", "") if isinstance(fields.get("url", ""), str) else "",
              "created": meta.get("created", ""), "updated": meta.get("updated", ""), "mtime": mtime_of(p),
              "projects": [x for x in (meta.get("projects") or []) if isinstance(x, str)],
              "projects_auto": [x for x in (meta.get("projects_auto") or []) if isinstance(x, str)],
              "forms": citeformat.describe(c), "missing": citeformat.warnings(c), "chicago_missing": citeformat.chicago_gaps(c)})
    return c


def citations():
    if not cite_dir().exists():
        return []
    out = [read_citation(p) for p in sorted(cite_dir().glob("*.md")) if TAG_RE.match(p.stem)]
    out.sort(key=lambda c: c["tag"])
    return out


def clean_fields(ctype, fields):
    """Keep only the fields this type has (plus manual overrides), with tidy values."""
    spec = {f["key"]: f for f in citeformat.TYPES[ctype]["fields"]}
    out = {}
    for k, v in (fields or {}).items():
        if k in ("_override_bluebook", "_override_short", "_override_apa"):
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
            continue
        f = spec.get(k)
        if not f:
            continue
        if f["kind"] == "authors":
            people = []
            for x in (v if isinstance(v, list) else []):
                if not isinstance(x, dict):
                    continue
                y = {kk: str(x.get(kk, "")).strip() for kk in ("given", "family", "suffix", "literal") if str(x.get(kk, "")).strip()}
                if y:
                    people.append(y)
            if people:
                out[k] = people
        elif f["kind"] == "bool":
            out[k] = bool(v)
        elif f["kind"] == "date" and isinstance(v, str) and v.strip():
            out[k] = citeformat.normalize_date(v)
        elif isinstance(v, str) and v.strip():
            out[k] = re.sub(r"\s+", " ", v.strip())
    return out


def write_citation(tag, data, mtime=None, force=False, create=False):
    p = cite_path(tag)
    if create and p.exists():
        raise StoreError('A citation with the tag "%s" already exists.' % tag, 409, exists=True)
    if not create:
        if not p.exists():
            raise StoreError("no such citation", 404)
        if not force and mtime not in (None, mtime_of(p)):
            raise StoreError("changed on disk", 409, mtime=mtime_of(p))
    ctype = data.get("type") if data.get("type") in citeformat.TYPES else "other"
    fields = clean_fields(ctype, data.get("fields"))
    if ctype == "other" and not fields.get("text") and data.get("cite"):      # the old shape {type, cite, short}
        fields = clean_fields("other", {"text": data.get("cite"), "short": data.get("short", ""), "url": data.get("url", "")})
    old = read_citation(p) if p.exists() else {}
    c = {"type": ctype, "fields": fields}
    full = citeformat.to_md(citeformat.bluebook(c, "practitioner"))
    # projects: kept as they are unless the request sets them ("projects" = the full list chosen by hand)
    projects, auto = old.get("projects", []), old.get("projects_auto", [])
    if isinstance(data.get("projects"), list):
        known = {x["id"] for x in projects_list()}
        projects = [x for x in dict.fromkeys(data["projects"]) if isinstance(x, str) and x in known]
        auto = [x for x in auto if x in projects and x not in (data.get("projects_manual") or [])]
    meta = {"type": ctype, "toa": citeformat.TOA_GROUP.get(ctype, "other"), "fields": fields,
            "short": citeformat.to_md(citeformat.bluebook_short(c, "practitioner")),
            "created": old.get("created") or now(), "updated": now()}
    if projects:
        meta["projects"] = projects
        if auto:
            meta["projects_auto"] = auto
    write_atomic(p, dump_front(meta, full))
    return read_citation(p)


def preview_citation(data):
    """Formatted forms for a citation that hasn't been saved (the form's live preview)."""
    ctype = data.get("type") if data.get("type") in citeformat.TYPES else "other"
    c = {"type": ctype, "fields": clean_fields(ctype, data.get("fields"))}
    return {"forms": citeformat.describe(c, (data.get("pin") or "").strip()), "missing": citeformat.warnings(c),
            "chicago_missing": citeformat.chicago_gaps(c)}


def delete_citation(tag):
    p = cite_path(tag)
    if not p.exists():
        raise StoreError("no such citation", 404)
    trash(p, ROOT / "library" / "citations")


# ------------------------------------------------------------------ attachments and annotations
# library/files/<tag>/<file>                     PDFs and other files attached to a citation
# library/files/<tag>/<file>.annotations.json    highlights and comments made in ReWord (the PDF is never changed)
# library/files/<tag>/<stem>-annotated.pdf       an exported copy with the annotations written in

FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()&,'-]{0,120}$")
MAX_ATTACH = 200_000_000


def files_dir(tag):
    cite_path(tag)                       # validates the tag
    return ROOT / "library" / "files" / tag


def safe_file_name(name):
    import unicodedata
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    name = re.sub(r"[/\\:\x00-\x1f]", "-", (name or "").strip()).lstrip(".-_ ")
    name = re.sub(r"\s+", " ", name)[:120] or "file.pdf"
    if not FILE_RE.match(name) or name.endswith(".annotations.json"):
        raise StoreError("That file name can't be used. Rename the file (letters, numbers, spaces, dashes).")
    return name


def attachment_path(tag, name):
    p = files_dir(tag) / safe_file_name(name)
    if p.parent.resolve() != files_dir(tag).resolve():
        raise StoreError("bad file name")
    return p


def list_attachments(tag):
    d = files_dir(tag)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if not p.is_file() or p.name.endswith(".annotations.json") or p.name.startswith("."):
            continue
        ann = d / (p.name + ".annotations.json")
        count = 0
        if ann.exists():
            try:
                count = len(json.loads(ann.read_text(encoding="utf-8")).get("annotations", []))
            except ValueError:
                count = 0
        out.append({"name": p.name, "size": p.stat().st_size, "mtime": mtime_of(p), "annotations": count,
                    "kind": "pdf" if p.suffix.lower() == ".pdf" else p.suffix.lower().lstrip("."),
                    "snapshot": p.name.startswith("snapshot"), "annotated": p.stem.endswith("-annotated")})
    return out


def save_attachment(tag, name, data, replace=False):
    if len(data) > MAX_ATTACH:
        raise StoreError("That file is larger than 200 MB, too big to keep in a GitHub repository.", 413)
    p = attachment_path(tag, name)
    if p.exists() and not replace:
        stem, ext = p.stem, p.suffix
        p = p.with_name(unique(stem, lambda s: (p.parent / (s + ext)).exists()) + ext)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)
    return p.name


def delete_attachment(tag, name):
    p = attachment_path(tag, name)
    if not p.exists():
        raise StoreError("no such file", 404)
    ann = p.with_name(p.name + ".annotations.json")
    trash(p, files_dir(tag))
    if ann.exists():
        trash(ann, files_dir(tag))


def read_annotations(tag, name):
    p = attachment_path(tag, name)
    a = p.with_name(p.name + ".annotations.json")
    if not a.exists():
        return {"file": p.name, "annotations": [], "mtime": None}
    d = json.loads(a.read_text(encoding="utf-8"))
    d["mtime"] = mtime_of(a)
    return d


def write_annotations(tag, name, annotations, mtime=None, force=False):
    p = attachment_path(tag, name)
    if not p.exists():
        raise StoreError("no such file", 404)
    a = p.with_name(p.name + ".annotations.json")
    if a.exists() and not force and mtime not in (None, mtime_of(a)):
        raise StoreError("changed on disk", 409, mtime=mtime_of(a))
    clean = []
    for x in annotations if isinstance(annotations, list) else []:
        if not isinstance(x, dict):
            continue
        rects = [[round(float(v), 5) for v in r[:4]] for r in (x.get("rects") or []) if isinstance(r, list) and len(r) >= 4]
        clean.append({"id": str(x.get("id") or "")[:40], "page": int(x.get("page") or 1), "rects": rects,
                      "text": str(x.get("text") or "")[:5000], "comment": str(x.get("comment") or "")[:20000],
                      "color": x.get("color") if x.get("color") in HIGHLIGHT_IDS else "yellow",
                      "created": x.get("created") or now(), "updated": now() if x.get("dirty") else (x.get("updated") or now())})
    clean.sort(key=lambda x: (x["page"], (x["rects"] or [[0, 0]])[0][1], (x["rects"] or [[0, 0]])[0][0]))
    write_atomic(a, json.dumps({"file": p.name, "annotations": clean}, indent=1, ensure_ascii=False) + "\n")
    return {"mtime": mtime_of(a), "count": len(clean)}


# ------------------------------------------------------------------ projects
# projects/<id>.json: {id, name, color, description, default_template, citation_style, created}
# Documents and notes record one project ("project"); citations a list ("projects", plus "projects_auto"
# for the ones added because they were cited in that project). Assignment is add-only.

PROJECT_COLORS = ["#3b6fd4", "#2e9e6b", "#c2412d", "#9b51c9", "#d4932b", "#1f8fa6", "#c23b7a", "#6b7280"]
CITATION_STYLES = ["", "apa", "bluebook", "bluebook-lawreview", "chicago", "chicago-author-date"]


def projects_dir():
    return ROOT / "projects"


def project_path(pid):
    if not SLUG_RE.match(pid or ""):
        raise StoreError("invalid project")
    return projects_dir() / (pid + ".json")


def project_exists(pid):
    return bool(pid) and SLUG_RE.match(pid) is not None and project_path(pid).exists()


def read_project(pid):
    p = project_path(pid)
    if not p.exists():
        raise StoreError("There's no project “%s”." % pid, 404)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["id"] = pid
    return d


def projects_list():
    d = projects_dir()
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        if SLUG_RE.match(p.stem):
            try:
                x = json.loads(p.read_text(encoding="utf-8")); x["id"] = p.stem; out.append(x)
            except ValueError:
                continue
    out.sort(key=lambda x: x.get("name", x["id"]).lower())
    return out


def _project_fields(data, old=None):
    old = old or {}
    name = (data.get("name", old.get("name", "")) or "").strip()
    if not name:
        raise StoreError("Give the project a name.")
    color = data.get("color", old.get("color", "")) or ""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = PROJECT_COLORS[len(projects_list()) % len(PROJECT_COLORS)]
    tid = data.get("default_template", old.get("default_template", "")) or ""
    if tid and tid not in {t["id"] for t in templates()}:
        tid = ""
    style = data.get("citation_style", old.get("citation_style", "")) or ""
    if style not in CITATION_STYLES:
        style = ""
    return {"name": name[:80], "color": color, "description": (data.get("description", old.get("description", "")) or "").strip()[:2000],
            "default_template": tid, "citation_style": style, "created": old.get("created") or now()}


def create_project(data):
    pid = unique(slugify((data.get("name") or "").strip() or "project", "project"), lambda s: project_path(s).exists())
    d = _project_fields(data)
    write_atomic(project_path(pid), json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    return read_project(pid)


def update_project(pid, data):
    old = read_project(pid)
    d = _project_fields(data, old)
    write_atomic(project_path(pid), json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    return read_project(pid)


def delete_project(pid):
    """Everything in the project stays, with no project; the project's file goes to projects/_trash."""
    p = project_path(pid)
    if not p.exists():
        raise StoreError("no such project", 404)
    for info in documents():
        if info.get("project") == pid:
            set_doc_option(info["slug"], "project", "")
    if notes_dir().exists():
        for q in notes_dir().glob("*.md"):
            meta, body = parse_front(q.read_text(encoding="utf-8"))
            if meta.get("project") == pid:
                meta.pop("project", None)
                write_atomic(q, dump_front(meta, body))
    if cite_dir().exists():
        for q in cite_dir().glob("*.md"):
            _edit_citation_projects(q, lambda pr, au: ([x for x in pr if x != pid], [x for x in au if x != pid]))
    v = verification_path(pid)
    if v.exists():
        trash(v, v.parent)
    trash(p, projects_dir())


CITED_RE = re.compile(r'\{\.(?:cite|auth)\b[^}]*?\btag="([a-z0-9][a-z0-9-]*)"')


def cited_tags(md):
    """Library tags used in Markdown: live citations ({.cite tag=…}) and older table-of-authorities marks."""
    return set(CITED_RE.findall(md or ""))


# ------------------------------------------------------------------ where a source is cited ("Cited in")

SPAN_END_RE = re.compile(r'\]\{\.(cite|auth)\b((?:\s+[a-z]+="(?:\\.|[^"\\])*")*)\s*\}')
SPAN_ATTR_RE = re.compile(r'([a-z]+)="((?:\\.|[^"\\])*)"')
FN_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:")
FN_MORE_RE = re.compile(r"^( {4}|\t)\S")
FN_REF_RE = re.compile(r"\[\^([^\]\s]+)\]")


def _escaped(s, i):
    n, j = 0, i - 1
    while j >= 0 and s[j] == "\\":
        n, j = n + 1, j - 1
    return n % 2 == 1


def _md_regions(md):
    """The file split the way the editor reads it (md.js parse): footnote definitions [(start, end, label)] and
    everything else (label None), in file order."""
    lines = md.split("\n")
    offs, pos = [], 0
    for ln in lines:
        offs.append(pos)
        pos += len(ln) + 1
    regions, body_from, i = [], 0, 0
    while i < len(lines):
        m = FN_DEF_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines):
            if FN_MORE_RE.match(lines[j]):
                j += 1
                continue
            if not lines[j].strip():
                k = j
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k < len(lines) and FN_MORE_RE.match(lines[k]):
                    j = k
                    continue
            break
        if offs[i] > body_from:
            regions.append((body_from, offs[i], None))
        end = offs[j] if j < len(lines) else len(md)
        regions.append((offs[i], end, m.group(1)))
        body_from, i = end, j
    if body_from < len(md):
        regions.append((body_from, len(md), None))
    return regions


def _ref_order(md):
    """Footnote labels in the order the text refers to them (md.js countRefs): numbering across sections."""
    out = []
    for ln in md.split("\n"):
        if FN_DEF_RE.match(ln) or FN_MORE_RE.match(ln) or ln.startswith(("    ", "\t")):
            continue
        for lab in FN_REF_RE.findall(ln):
            if lab not in out:
                out.append(lab)
    return out


def _cite_spans(md):
    """Every [text]{.cite …} / [text]{.auth tag=…} in a file: (start, end, kind, attrs, inner)."""
    out = []
    for m in SPAN_END_RE.finditer(md):
        depth, i = 0, m.start()
        while i >= 0:
            if md[i] in "[]" and not _escaped(md, i):
                depth += 1 if md[i] == "]" else -1
                if depth == 0:
                    break
            i -= 1
        if i < 0:
            continue
        attrs = {k: re.sub(r"\\(.)", r"\1", v) for k, v in SPAN_ATTR_RE.findall(m.group(2))}
        if attrs.get("tag"):
            out.append((i, m.end(), m.group(1), attrs, md[i + 1:m.start()]))
    return out


def md_plain(md):
    """Inline Markdown as plain words, for a short quotation around a citation."""
    s = FN_REF_RE.sub("", md or "")
    for _ in range(3):                                       # spans can nest: [*Name*, [Harv.]{.smallcaps}]{.cite}
        s = re.sub(r"\[([^\[\]]*)\]\{[^}]*\}", r"\1", s)
    s = re.sub(r"\[([^\[\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\\(.)", r"\1", s)
    s = re.sub(r"(?<!\w)[*_]+|[*_]+(?!\w)|`", "", s)
    s = re.sub(r"^\s*(#{1,6}|>|[-+*]|\d+[.)])\s+", "", s, flags=re.M)
    return re.sub(r"\s+", " ", s).strip()


def _context(md, region, start, end):
    """A few words before and after a citation, inside its paragraph (or its footnote)."""
    lo, hi = region[0], region[1]
    if region[2] is None:
        a = md.rfind("\n\n", lo, start)
        b = md.find("\n\n", end, hi)
        lo, hi = (a + 2 if a >= 0 else lo), (b if b >= 0 else hi)
    else:
        lo = lo + len(FN_DEF_RE.match(md[lo:hi]).group(0))
    before, after = md_plain(md[lo:start]), md_plain(md[end:hi])
    if len(before) > 110:
        before = "…" + before[-110:].split(" ", 1)[-1]
    if len(after) > 90:
        after = after[:90].rsplit(" ", 1)[0] + "…"
    return before, after


def _uses_in(md, tag, refs_before=0, render=None):
    """The places one file cites `tag`. k = which match this is inside its body or footnote, the way the editor
    finds the chip again; start/end = where it is in the file, for the Markdown editor. render(attrs, in_note)
    gives the citation as the editor's chip shows it now: (text, html)."""
    regions, order = _md_regions(md), _ref_order(md)
    seen, out = {}, []
    for start, end, kind, attrs, inner in _cite_spans(md):
        if attrs["tag"] != tag:
            continue
        reg = next((r for r in regions if r[0] <= start < r[1]), (0, len(md), None))
        label = reg[2]
        k = seen.get(label, 0)
        seen[label] = k + 1
        before, after = _context(md, reg, start, end)
        text, html = render(attrs, bool(label)) if render and kind == "cite" else (md_plain(inner), "")
        u = {"where": "footnote" if label else "text", "k": k, "start": start, "end": end, "kind": kind,
             "text": text, "html": html, "before": before, "after": after}
        if label:
            u["label"] = label
            u["number"] = refs_before + order.index(label) + 1 if label in order else None
        out.append(u)
    return out


def _section_title(md, name):
    m = re.search(r"^#\s+(.*?)\s*(?:\{[^}]*\})?\s*$", md, re.M)
    t = md_plain(m.group(1)) if m else ""
    return t or re.sub(r"^\d+-|\.md$", "", name).replace("-", " ")


def citation_uses(tag=None):
    """Where library sources are cited: live citations ({.cite tag=…}) and table-of-authorities marks
    ({.auth tag=…}) in every document's sections and in research notes, in reading order.
    With a tag: {documents: [{slug, title, …, uses: [{section, where, number, before, text, after, …}]}], notes: […], total}.
    Without: {counts: {tag: number of places}}."""
    if tag is None:
        counts = {}
        texts = []
        for info in documents():
            texts += [f.read_text(encoding="utf-8") for f in section_paths(info["slug"])]
        if notes_dir().exists():
            texts += [parse_front(p.read_text(encoding="utf-8"))[1] for p in notes_dir().glob("*.md") if SLUG_RE.match(p.stem)]
        for md in texts:
            for _, _, _, attrs, _ in _cite_spans(md):
                counts[attrs["tag"]] = counts.get(attrs["tag"], 0) + 1
        return {"counts": counts}
    import cites
    p = cite_path(tag)                                       # validates the tag
    c = read_citation(p) if p.exists() else None
    entry = {"type": c["type"], "fields": c["fields"], "tag": tag} if c else None

    def renderer(style, typeface):
        def render(attrs, in_note):
            runs = cites.chip_text(entry, attrs, typeface, style, in_note or typeface != "lawreview")
            return md_plain(citeformat.to_md(runs)), citeformat.to_html(runs)
        return render
    tmpls = {t["id"]: t for t in templates()}
    docs, total = [], 0
    for info in sorted(documents(), key=lambda d: -d["updated"]):
        t = tmpls.get(info.get("template", ""), {})
        meta = {}
        mp = doc_path(info["slug"]) / META
        m = re.search(r'(?m)^citation-style:\s*"?([\w-]+)', mp.read_text(encoding="utf-8")) if mp.exists() else None
        if m:
            meta["citation-style"] = {"t": "MetaString", "c": m.group(1)}
        render = renderer(*cites.style_of(t, meta))
        uses, refs = [], 0
        for f in section_paths(info["slug"]):
            md = f.read_text(encoding="utf-8")
            for u in _uses_in(md, tag, refs, render):
                u.update({"file": f.name, "section": _section_title(md, f.name)})
                uses.append(u)
            refs += len(_ref_order(md))
        if uses:
            total += len(uses)
            docs.append({"slug": info["slug"], "title": info.get("title", info["slug"]), "template": info.get("template", ""),
                         "template_name": t.get("name", ""), "project": info.get("project", ""), "uses": uses})
    note_styles = {"apa": ("apa", "practitioner"), "bluebook-lawreview": ("bluebook", "lawreview"), "chicago": ("chicago", "practitioner"),
                   "chicago-author-date": ("chicago-ad", "practitioner")}       # a note takes its project's style (research.js)
    proj_style = {x["id"]: x.get("citation_style", "") for x in projects_list()}
    found = []
    if notes_dir().exists():
        for q in notes_dir().glob("*.md"):
            if not SLUG_RE.match(q.stem):
                continue
            n = read_note(q)
            style = note_styles.get(proj_style.get(n["project"], ""), ("bluebook", "practitioner"))
            uses = _uses_in(n["body"], tag, 0, renderer(*style))
            if uses:
                total += len(uses)
                found.append({"id": n["id"], "title": n["title"], "project": n["project"], "updated": n["updated"], "uses": uses})
    found.sort(key=lambda n: n["updated"] or "", reverse=True)
    return {"tag": tag, "documents": docs, "notes": found, "total": total}


# ------------------------------------------------------------------ verification (the Verify tab)
# projects/verification/<project>.json: {"results": {key: {status, reason, at, sig, tag, doc}}}
# Every citation in a project's documents, one card each, checked against its source. A key names one place:
# document, source, pinpoint and which time that (source, pinpoint) appears in the document, so results stay
# put when other citations are added. sig fingerprints the citation and the words before it: when either
# changes, an approval no longer counts (a citation sent back stays sent back, marked as edited since).

VERIFY_STATUSES = ("approved", "failed")


def verification_path(pid):
    project_path(pid)                                        # validates the id
    return projects_dir() / "verification" / (pid + ".json")


def _read_verification(pid):
    p = verification_path(pid)
    if not p.exists():
        return {"results": {}}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {"results": {}}
    if not isinstance(d.get("results"), dict):
        d["results"] = {}
    return d


def _para_plain(md, region, start, end):
    """The whole paragraph (or footnote) around a citation, as plain words before and after it."""
    lo, hi = region[0], region[1]
    if region[2] is None:
        a = md.rfind("\n\n", lo, start)
        b = md.find("\n\n", end, hi)
        lo, hi = (a + 2 if a >= 0 else lo), (b if b >= 0 else hi)
    else:
        lo = lo + len(FN_DEF_RE.match(md[lo:hi]).group(0))
    return md_plain(md[lo:start]), md_plain(md[end:hi])


def _note_anchor(md, label):
    """For a footnote: the paragraph of the text that points to it, split at the footnote mark (what the note supports)."""
    for lo, hi, lab in _md_regions(md):
        if lab is not None:
            continue
        m = re.search(r"\[\^" + re.escape(label) + r"\]", md[lo:hi])
        if not m:
            continue
        at = lo + m.start()
        a = md.rfind("\n\n", lo, at)
        b = md.find("\n\n", at, hi)
        plo, phi = (a + 2 if a >= 0 else lo), (b if b >= 0 else hi)
        return md_plain(md[plo:at]), md_plain(md[lo + m.end():phi])
    return None


def verification(pid, slug=None):
    """Every citation in the project's documents (or one of them), in reading order, with its result so far."""
    import cites
    import hashlib
    read_project(pid)
    tmpls = {t["id"]: t for t in templates()}
    entries = {}
    results = _read_verification(pid)["results"]
    items = []
    all_docs = sorted((d for d in documents() if d.get("project") == pid), key=lambda d: (d.get("title") or d["slug"]).lower())
    for info in (d for d in all_docs if not slug or d["slug"] == slug):
        t = tmpls.get(info.get("template", ""), {})
        meta = {}
        mp = doc_path(info["slug"]) / META
        m = re.search(r'(?m)^citation-style:\s*"?([\w-]+)', mp.read_text(encoding="utf-8")) if mp.exists() else None
        if m:
            meta["citation-style"] = {"t": "MetaString", "c": m.group(1)}
        style, typeface = cites.style_of(t, meta)
        seen, refs = {}, 0
        for f in section_paths(info["slug"]):
            md = f.read_text(encoding="utf-8")
            regions, order = _md_regions(md), _ref_order(md)
            section = _section_title(md, f.name)
            nth = {}
            for start, end, kind, attrs, inner in _cite_spans(md):
                tag = attrs["tag"]
                reg = next((r for r in regions if r[0] <= start < r[1]), (0, len(md), None))
                label = reg[2]
                k = nth.get((tag, label), 0)                  # which match in its body or footnote (writing.reveal)
                nth[(tag, label)] = k + 1
                if tag not in entries:
                    q = cite_path(tag) if TAG_RE.match(tag) else None
                    c = read_citation(q) if q and q.exists() else None
                    entries[tag] = {"type": c["type"], "fields": c["fields"], "tag": tag} if c else None
                if kind == "cite":
                    runs = cites.chip_text(entries[tag], attrs, typeface, style, bool(label) or typeface != "lawreview")
                    text, html = md_plain(citeformat.to_md(runs)), citeformat.to_html(runs)
                else:
                    text, html = md_plain(inner), ""
                before, after = _para_plain(md, reg, start, end)
                pin = (attrs.get("pin") or "").strip()
                n = seen.get((tag, pin), 0)
                seen[(tag, pin)] = n + 1
                key = "%s:%s:%s:%d" % (info["slug"], tag, pin, n)
                near = before[-160:]
                sig = hashlib.sha1((text + "\x00" + near).encode("utf-8")).hexdigest()[:12]
                it = {"key": key, "sig": sig, "slug": info["slug"], "doc": info.get("title", info["slug"]), "file": f.name,
                      "section": section, "tag": tag, "missing": entries[tag] is None, "kind": kind, "where": "footnote" if label else "text",
                      "k": k, "start": start, "end": end, "text": text, "html": html, "before": before, "after": after,
                      "pin": pin, "signal": (attrs.get("signal") or "").strip(), "paren": md_plain(attrs.get("paren") or "")}
                if label:
                    it["label"] = label
                    it["number"] = refs + order.index(label) + 1 if label in order else None
                    anchor = _note_anchor(md, label)
                    if anchor:
                        it["supports"] = list(anchor)
                r = results.get(key)
                if r:
                    edited = r.get("sig") != sig
                    if r.get("status") == "approved" and edited:
                        it["was"] = "approved"                # approved, then the citation or its sentence changed
                    else:
                        it.update({"status": r.get("status"), "edited": edited})
                    it.update({"reason": r.get("reason", ""), "at": r.get("at", "")})
                items.append(it)
            refs += len(order)
    return {"project": pid, "documents": [{"slug": d["slug"], "title": d.get("title", d["slug"])} for d in all_docs], "items": items}


def set_verification(pid, key, status, reason="", sig="", tag="", doc=""):
    """Record one card's result (status "" clears it)."""
    if status and status not in VERIFY_STATUSES:
        raise StoreError("unknown result")
    if not isinstance(key, str) or not key or len(key) > 300:
        raise StoreError("invalid key")
    d = _read_verification(pid)
    if status:
        d["results"][key] = {"status": status, "reason": (reason or "").strip()[:4000], "at": now(), "sig": sig or "",
                             "tag": tag or "", "doc": doc or ""}
    else:
        d["results"].pop(key, None)
    p = verification_path(pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return d["results"].get(key)


def reset_verification(pid, slug=None):
    """Start over: forget every result (or one document's)."""
    d = _read_verification(pid)
    d["results"] = {k: v for k, v in d["results"].items() if slug and not k.startswith(slug + ":")}
    p = verification_path(pid)
    if p.exists() or d["results"]:
        p.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(p, json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return {"ok": True}


def _edit_citation_projects(p, change):
    """Rewrite a citation's project lists without changing its timestamp, so a copy open in the editor
    doesn't think the file was edited underneath it (its next save keeps these lists)."""
    text = p.read_text(encoding="utf-8")
    meta, body = parse_front(text)
    pr = [x for x in (meta.get("projects") or []) if isinstance(x, str)]
    au = [x for x in (meta.get("projects_auto") or []) if isinstance(x, str)]
    npr, nau = change(pr, au)
    if npr == pr and nau == au:
        return False
    st = p.stat()
    meta.pop("projects", None); meta.pop("projects_auto", None)
    if npr:
        meta["projects"] = npr
        if nau:
            meta["projects_auto"] = nau
    write_atomic(p, dump_front(meta, body))
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    return True


def assign_citations(tags, project):
    """Add-only: each cited source joins the project (marked as added automatically)."""
    if not project or not project_exists(project):
        return []
    added = []
    for t in sorted(tags):
        if not TAG_RE.match(t):
            continue
        q = cite_path(t)
        if q.exists() and _edit_citation_projects(q, lambda pr, au: (pr, au) if project in pr else (pr + [project], au + [project])):
            added.append(t)
    return added


def assign_document_citations(slug):
    info = read_doc_info(doc_path(slug))
    if not info.get("project"):
        return []
    tags = set()
    for f in doc_path(slug).glob("[0-9]*.md"):
        tags |= cited_tags(f.read_text(encoding="utf-8"))
    return assign_citations(tags, info["project"])


def assign_note(nid, project):
    p = note_path(nid)
    if not p.exists():
        raise StoreError("no such note", 404)
    if project and not project_exists(project):
        raise StoreError("There's no project “%s”." % project, 404)
    st = p.stat()
    meta, body = parse_front(p.read_text(encoding="utf-8"))
    if project:
        meta["project"] = project
    else:
        meta.pop("project", None)
    write_atomic(p, dump_front(meta, body))
    if project:
        assign_citations(cited_tags(body) | ({meta["citation"]} if meta.get("citation") else set()), project)
    return read_note(p)


# ------------------------------------------------------------------ research notes

def notes_dir():
    return ROOT / "research"


def note_path(nid):
    if not SLUG_RE.match(nid or ""):
        raise StoreError("invalid note id")
    return notes_dir() / (nid + ".md")


def read_note(p, with_body=True):
    meta, body = parse_front(p.read_text(encoding="utf-8"))
    out = {"id": p.stem, "title": meta.get("title") or p.stem, "topic": meta.get("topic", ""),
           "citation": meta.get("citation", ""), "project": meta.get("project", ""), "created": meta.get("created", ""),
           "updated": meta.get("updated", ""), "mtime": mtime_of(p)}
    if with_body:
        out["body"] = body.strip("\n") + "\n" if body.strip() else ""
    else:
        out["snippet"] = re.sub(r"[#*_\[\]>`^\\]+|\{[^}]*\}", "", body)[:160].strip().replace("\n", " ")
    return out


def notes():
    if not notes_dir().exists():
        return []
    out = [read_note(p, False) for p in notes_dir().glob("*.md") if SLUG_RE.match(p.stem)]
    out.sort(key=lambda n: n["updated"] or "", reverse=True)
    return out


def create_note(title, topic="", citation="", body="", project=""):
    title = (title or "").strip() or "Untitled note"
    nid = unique(slugify(title, "note", 50), lambda s: note_path(s).exists())
    project = project if project and project_exists(project) else ""
    meta = {"title": title, "topic": (topic or "").strip(), "citation": citation or "", "created": now(), "updated": now()}
    if project:
        meta["project"] = project
    write_atomic(note_path(nid), dump_front(meta, body or ""))
    if project:
        assign_citations(cited_tags(body or "") | ({citation} if citation else set()), project)
    return read_note(note_path(nid))


def write_note(nid, data, mtime=None, force=False):
    p = note_path(nid)
    if not p.exists():
        raise StoreError("no such note", 404)
    if not force and mtime not in (None, mtime_of(p)):
        raise StoreError("changed on disk", 409, mtime=mtime_of(p))
    old = read_note(p)
    project = data.get("project", old.get("project", "")) or ""
    if project and not project_exists(project):
        project = ""
    meta = {"title": (data.get("title") or old["title"]).strip(),
            "topic": (data.get("topic", old["topic"]) or "").strip(),
            "citation": data.get("citation", old["citation"]) or "",
            "created": old["created"] or now(), "updated": now()}
    if project:
        meta["project"] = project
    body = data.get("body", old["body"]) or ""
    write_atomic(p, dump_front(meta, body))
    if project:          # sources cited in the note, and the note's own source, join its project
        assign_citations(cited_tags(body) | ({meta["citation"]} if meta["citation"] else set()), project)
    return read_note(p)


def delete_note(nid):
    p = note_path(nid)
    if not p.exists():
        raise StoreError("no such note", 404)
    trash(p, notes_dir())

# ---------------------------------------------------------------- highlight colors and their labels
# Twelve colors; you name what each one means (Holding, Dicta, Quote…). The names live in
# library/highlights.json, so every project, note and source shares them and they sync with the library.
HIGHLIGHT_COLORS = [('yellow', '#ffd60a'), ('green', '#5fcf7a'), ('blue', '#6aaeff'), ('pink', '#ff7fbf'), ('orange', '#ffa043'), ('red', '#ff6161'), ('purple', '#a98bff'), ('teal', '#2fc7bf'), ('lime', '#b5e655'), ('brown', '#c79a6b'), ('gray', '#a7b0ba'), ('indigo', '#6f86ff')]
HIGHLIGHT_IDS = tuple(c for c, _ in HIGHLIGHT_COLORS)


def highlights_path():
    return ROOT / "library" / "highlights.json"


def read_highlights():
    try:
        labels = json.loads(highlights_path().read_text(encoding="utf-8")).get("labels", {})
    except (OSError, ValueError, AttributeError):
        labels = {}
    return [{"id": c, "hex": h, "label": str(labels.get(c) or "")[:40]} for c, h in HIGHLIGHT_COLORS]


def write_highlights(labels):
    if not isinstance(labels, dict):
        raise StoreError("labels must be an object")
    clean = {c: " ".join(str(labels.get(c) or "").split())[:40] for c in HIGHLIGHT_IDS}
    highlights_path().parent.mkdir(parents=True, exist_ok=True)
    write_atomic(highlights_path(), json.dumps({"labels": clean}, indent=2, ensure_ascii=False) + "\n")
    return read_highlights()
