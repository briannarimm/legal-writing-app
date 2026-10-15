#!/usr/bin/env python3
"""Redline the current draft against an earlier git ref (tag, branch, or commit).

Produces two files:
  <out>.docx  Word file with real tracked changes (Review > Accept/Reject works)
  <out>.pdf   PDF with insertions in blue underline, deletions in red strikeout

How it works: both versions are parsed by Pandoc into its document tree, then
compared block by block and word by word. Footnotes are compared inside, so an
edited footnote shows the edit rather than a deleted and re-added note. Line
re-wrapping (one sentence per line) is ignored. Pandoc's docx writer turns the
marked spans into Word revisions.

Usage:  python3 scripts/redline.py --doc documents/my-memo --template templates/memo \
            --base v0.2 --base-dir documents/my-memo/.versions/v0.2 [--out build/my-memo/redline-vs-v0.2]

The earlier draft comes from a saved version folder (--base-dir), or from git (--git-ref REF,
with --repo pointing at the git working tree).
"""
import argparse, copy, datetime, difflib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = "documents/article-draft"     # set from --doc
TDIR = "templates/article"          # set from --template
LEGACY_DIR = "article"              # where drafts lived before documents/ existed
BASE_DIR = None                     # --base-dir: a saved version folder
REPO = ROOT                         # --repo: git working tree for --git-ref
CONTAINERS = {"Emph", "Strong", "SmallCaps", "Strikeout", "Underline",
              "Superscript", "Subscript"}
STATS = {"insertion": 0, "deletion": 0}


# ---------------------------------------------------------------- loading ----
def sh(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, cwd=ROOT, **kw).stdout


def git(*args):
    return subprocess.run(("git",) + args, check=True, capture_output=True, cwd=REPO).stdout


def files_at(ref):
    if BASE_DIR:
        return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(Path(BASE_DIR).glob("[0-9]*.md"))]
    # git: paths must be relative to the repository. Older versions of this project kept the
    # draft in article/; fall back to that.
    rel = os.path.relpath(str((ROOT / DOC).resolve()), str(Path(REPO).resolve()))
    for folder in (rel, LEGACY_DIR):
        names = git("ls-tree", "-r", "--name-only", ref, folder + "/").decode().split()
        rx = re.compile(r"^" + re.escape(folder) + r"/\d[^/]*\.md$")
        found = [(n, git("show", f"{ref}:{n}").decode()) for n in sorted(names) if rx.match(n)]
        if found:
            return found
    return []


def files_now():
    return [(p.name, p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / DOC).glob("[0-9]*.md"))]


def to_ast(files):
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, text in files:
            p = Path(tmp) / Path(name).name
            p.write_text(text)
            paths.append(str(p))
        out = sh("pandoc", "-f", "markdown+smart", "-t", "json",
                 "--metadata-file", f"{DOC}/metadata.yaml", *paths)
    return resolve_cites(json.loads(out))


def resolve_cites(doc):
    """Live citations ({.cite tag=…}) become their full (draft) text from the citation library, so both
    versions are compared as they read. Without the app's code (an old checkout) they stay as written."""
    try:
        sys.path.insert(0, str(ROOT / "app"))
        import cites  # noqa: E402
    except ImportError:
        return doc
    data = Path(os.environ.get("LT_DATA") or ROOT)
    tmpl = json.loads((ROOT / TDIR / "template.json").read_text(encoding="utf-8"))
    doc, _ = cites.resolve(doc, cites.load_library(data), **cites.options_for(tmpl, "draft", doc.get("meta", {})))
    return doc


# ---------------------------------------------------------------- helpers ----
def norm(x):
    """Comparison key: SoftBreak == Space so re-wrapping isn't a change."""
    if isinstance(x, dict):
        if x.get("t") == "SoftBreak":
            return {"t": "Space"}
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


def key(x):
    return json.dumps(norm(x), sort_keys=True)


def text_of(x):
    out = []
    def walk(n):
        if isinstance(n, dict):
            if n.get("t") == "Str": out.append(n["c"])
            elif n.get("t") in ("Space", "SoftBreak"): out.append(" ")
            else: walk(n.get("c"))
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(x)
    return "".join(out)


def similar(a, b):
    return difflib.SequenceMatcher(None, text_of(a).split(), text_of(b).split()).ratio()


def is_space(tok):
    return tok.get("t") in ("Space", "SoftBreak")


# ---------------------------------------------------------------- marking ----
def span(inlines, kind):
    if not inlines or all(is_space(i) for i in inlines):
        return list(inlines)
    STATS[kind] += 1
    return [{"t": "Span", "c": [["", [kind], [["author", AUTHOR], ["date", DATE]]],
                                mark_notes(inlines, kind)]}]


def mark_notes(inlines, kind):
    """Inside a marked run, also mark the text of any footnotes it contains."""
    out = []
    for el in inlines:
        el = copy.deepcopy(el)
        if el.get("t") == "Note":
            el["c"] = mark_blocks(el["c"], kind, count=False)
        out.append(el)
    return out


def mark_blocks(blocks, kind, count=True):
    out = []
    for b in copy.deepcopy(blocks):
        t = b.get("t")
        if t in ("Para", "Plain"):
            b["c"] = span(b["c"], kind) if count else _quiet_span(b["c"], kind)
        elif t == "Header":
            b["c"][2] = span(b["c"][2], kind) if count else _quiet_span(b["c"][2], kind)
        elif t == "BlockQuote":
            b["c"] = mark_blocks(b["c"], kind, count)
        elif t == "Div":
            b["c"][1] = mark_blocks(b["c"][1], kind, count)
        elif t == "BulletList":
            b["c"] = [mark_blocks(item, kind, count) for item in b["c"]]
        elif t == "OrderedList":
            b["c"][1] = [mark_blocks(item, kind, count) for item in b["c"][1]]
        out.append(b)
    return out


def _quiet_span(inlines, kind):
    before = STATS[kind]
    r = span(inlines, kind)
    STATS[kind] = before
    return r


# ---------------------------------------------------------------- diffing ----
def diff_blocks(old, new):
    sm = difflib.SequenceMatcher(None, [key(b) for b in old], [key(b) for b in new],
                                 autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out += new[j1:j2]
        elif op == "delete":
            out += mark_blocks(old[i1:i2], "deletion")
        elif op == "insert":
            out += mark_blocks(new[j1:j2], "insertion")
        else:
            out += pair_blocks(old[i1:i2], new[j1:j2])
    return out


def pair_blocks(old, new):
    """Match edited blocks to their new versions by similarity, in order."""
    out, j = [], 0
    for a in old:
        match = next((k for k in range(j, len(new))
                      if new[k].get("t") == a.get("t") and similar(a, new[k]) >= 0.4), None)
        if match is None:
            out += mark_blocks([a], "deletion")
            continue
        out += mark_blocks(new[j:match], "insertion")
        out += diff_block_pair(a, new[match])
        j = match + 1
    out += mark_blocks(new[j:], "insertion")
    return out


def diff_block_pair(a, b):
    t = a.get("t")
    if key(a) == key(b):
        return [b]
    if t in ("Para", "Plain"):
        return [{"t": t, "c": diff_inlines(a["c"], b["c"])}]
    if t == "Header" and a["c"][0] == b["c"][0]:
        return [{"t": t, "c": [b["c"][0], b["c"][1], diff_inlines(a["c"][2], b["c"][2])]}]
    if t == "BlockQuote":
        return [{"t": t, "c": diff_blocks(a["c"], b["c"])}]
    if t == "Div":
        return [{"t": t, "c": [b["c"][0], diff_blocks(a["c"][1], b["c"][1])]}]
    if t == "BulletList" and len(a["c"]) == len(b["c"]):
        return [{"t": t, "c": [diff_blocks(x, y) for x, y in zip(a["c"], b["c"])]}]
    if t == "OrderedList" and len(a["c"][1]) == len(b["c"][1]):
        return [{"t": t, "c": [b["c"][0], [diff_blocks(x, y) for x, y in zip(a["c"][1], b["c"][1])]]}]
    return mark_blocks([a], "deletion") + mark_blocks([b], "insertion")


def coalesced_opcodes(a, b):
    """Opcodes where change runs separated only by spaces merge into one change,
    so a rewritten phrase reads as one deletion + one insertion."""
    ops = difflib.SequenceMatcher(None, [key(x) for x in a], [key(x) for x in b],
                                  autojunk=False).get_opcodes()
    merged = []
    for op in ops:
        tag, i1, i2, j1, j2 = op
        if (tag == "equal" and merged and merged[-1][0] != "equal"
                and all(is_space(x) for x in a[i1:i2])):
            tag = "replace"
        if merged and tag != "equal" and merged[-1][0] != "equal":
            p = merged[-1]
            merged[-1] = ("replace", p[1], i2, p[3], j2)
        else:
            merged.append((tag, i1, i2, j1, j2))
    # A trailing space-only "replace" absorbed nothing new; harmless.
    return merged


def diff_inlines(a, b):
    out = []
    for op, i1, i2, j1, j2 in coalesced_opcodes(a, b):
        if op == "equal":
            out += b[j1:j2]
        elif op == "delete":
            out += span(a[i1:i2], "deletion")
        elif op == "insert":
            out += span(b[j1:j2], "insertion")
        else:
            out += diff_region(a[i1:i2], b[j1:j2])
    return out


def diff_region(a, b):
    """A changed run. If both sides hold the same number of footnotes, split
    around them so footnote edits are shown inside the footnote."""
    na = [i for i, x in enumerate(a) if x.get("t") == "Note"]
    nb = [i for i, x in enumerate(b) if x.get("t") == "Note"]
    if na and len(na) == len(nb):
        out, pa, pb = [], 0, 0
        for ia, ib in zip(na, nb):
            out += diff_inlines(a[pa:ia], b[pb:ib])
            out.append({"t": "Note", "c": diff_blocks(a[ia]["c"], b[ib]["c"])})
            pa, pb = ia + 1, ib + 1
        return out + diff_inlines(a[pa:], b[pb:])
    if len(a) == len(b) and all(x.get("t") == y.get("t") and x.get("t") != "Str"
                                for x, y in zip(a, b)):
        out = []
        for x, y in zip(a, b):
            out += diff_inline_pair(x, y)
        return out
    return span(a, "deletion") + span(b, "insertion")


def diff_inline_pair(x, y):
    t = x.get("t")
    if key(x) == key(y):
        return [y]
    if t in CONTAINERS:
        return [{"t": t, "c": diff_inlines(x["c"], y["c"])}]
    if t == "Span" and key(x["c"][0]) == key(y["c"][0]):
        return [{"t": t, "c": [y["c"][0], diff_inlines(x["c"][1], y["c"][1])]}]
    if t == "Quoted" and x["c"][0] == y["c"][0]:
        return [{"t": t, "c": [y["c"][0], diff_inlines(x["c"][1], y["c"][1])]}]
    if t == "Link" and x["c"][2] == y["c"][2]:
        return [{"t": t, "c": [y["c"][0], diff_inlines(x["c"][1], y["c"][1]), y["c"][2]]}]
    if t == "Note":
        return [{"t": t, "c": diff_blocks(x["c"], y["c"])}]
    return span([x], "deletion") + span([y], "insertion")


def unique_revision_ids(docx):
    """Pandoc numbers insertions and deletions separately, so ids repeat.
    Word expects every revision id to be unique; renumber them."""
    import zipfile
    counter = iter(range(100000, 10**9))
    tmp = docx.with_name(docx.name + ".tmp")
    with zipfile.ZipFile(docx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in ("word/document.xml", "word/footnotes.xml"):
                data = re.sub(rb'(<w:(?:ins|del) w:id=")\d+(")',
                              lambda m: m.group(1) + str(next(counter)).encode() + m.group(2), data)
            zout.writestr(item, data)
    tmp.replace(docx)


# ------------------------------------------------------------------- main ----
def main():
    global AUTHOR, DATE, DOC, TDIR, BASE_DIR, REPO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", default=DOC, help="document folder, e.g. documents/my-memo")
    ap.add_argument("--template", default=TDIR, help="template folder, e.g. templates/memo")
    ap.add_argument("--base", required=True, help="name of the earlier version (for the title and file name)")
    ap.add_argument("--base-dir", help="folder holding the earlier version's section files")
    ap.add_argument("--git-ref", help="git tag/branch/commit to compare against instead of --base-dir")
    ap.add_argument("--repo", help="git working tree to read --git-ref from")
    ap.add_argument("--out", help="output path without extension")
    ap.add_argument("--author", help="name shown on tracked changes in Word")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    DOC, TDIR = args.doc.rstrip("/"), args.template.rstrip("/")
    BASE_DIR = args.base_dir
    if args.repo:
        REPO = Path(args.repo)
    ref = args.git_ref or args.base

    name = ""
    if args.git_ref:        # only ask git when we're already using it
        try:
            name = git("config", "user.name").decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            name = ""
    AUTHOR = args.author or name or os.environ.get("LT_AUTHOR") or "Author"
    DATE = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = Path(DOC).name
    out = Path(args.out or f"build/{slug}/redline-vs-{args.base.replace('/', '-')}")
    out.parent.mkdir(parents=True, exist_ok=True)

    old_files = files_at(ref)
    if not old_files:
        sys.exit(f"No section files for {DOC} found at {ref}")
    old, new = to_ast(old_files), to_ast(files_now())
    new["blocks"] = diff_blocks(old["blocks"], new["blocks"])
    meta = new.setdefault("meta", {})
    meta["redline-note"] = {"t": "MetaString", "c": f"Redline against {args.base}"}

    ast = Path(f"{out}.json")
    ast.write_text(json.dumps(new))
    sh("pandoc", "-f", "json", str(ast), "-d", f"{TDIR}/docx.yaml", "-o", str(Path(f"{out}.docx")))
    unique_revision_ids(Path(f"{out}.docx"))
    if not args.no_pdf:
        tectonic = shutil.which("tectonic") or (str(Path(os.environ["LT_RUNTIME"]) / "bin" / "tectonic")
                                                if os.environ.get("LT_RUNTIME") else None)
        if tectonic and Path(tectonic).exists():
            # portable build: Pandoc writes the TeX, Tectonic typesets it
            tex = Path(f"{out}.tex")
            sh("pandoc", "-f", "json", str(ast), "-d", f"{TDIR}/pdf.yaml", "-V", "singlespace=true", "-s", "-o", str(tex))
            flags = ["--only-cached"] if os.environ.get("LT_ONLY_CACHED") else []
            r = subprocess.run([tectonic] + flags + [tex.name], cwd=tex.parent, capture_output=True, text=True)
            tex.unlink()
            if r.returncode != 0:
                sys.exit("Typesetting the redline PDF failed:\n" + (r.stdout + r.stderr)[-1500:])
        else:
            sh("pandoc", "-f", "json", str(ast), "-d", f"{TDIR}/pdf.yaml",
               "-V", "singlespace=true", "-o", str(Path(f"{out}.pdf")))
    ast.unlink()
    print(f"Redline vs {args.base}: {STATS['insertion']} insertions, "
          f"{STATS['deletion']} deletions -> {out}.docx"
          + ("" if args.no_pdf else f", {out}.pdf"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"Command failed: {' '.join(e.cmd)}\n{e.stderr.decode()}")
