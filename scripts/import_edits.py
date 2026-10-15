#!/usr/bin/env python3
"""Bring editors' tracked changes and comments from a .docx back to the Markdown.

  python3 scripts/import_edits.py edits/marked-up.docx            # report only
  python3 scripts/import_edits.py edits/marked-up.docx --apply    # also edit article/*.md

Writes edits/<name>-report.md listing every change and comment, each tied to a
file and line in article/ where it could be located.

With --apply, a change is written into the Markdown only when it is safe:
the original wording (plus a few words of context) appears exactly once in
article/, and the changed words contain no Markdown formatting. Everything else
is listed under "Apply by hand". Nothing is committed: review with `git diff`,
then commit, or `git checkout article/` to undo.
"""
import argparse, copy, difflib, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKUP = re.compile(r"[*_\[\]{}^\\`<>]")
MAX_CONTEXT = 8
PARA = "¶"  # paragraph boundary token; context never crosses it

# Characters Word "smartens" or Pandoc writes differently from the Markdown.
EQUIV = {
    "’": "['’]", "'": "['’]", "‘": "['‘]",
    "“": "[\"“]", "”": "[\"”]", '"': "[\"“”]",
    "–": "(?:–|--)", "—": "(?:—|---)", "…": "(?:…|\\.\\.\\.)",
    " ": "[  ]",
}
FMT = r"[*_]{0,3}"  # emphasis markers allowed around words in the source


# ------------------------------------------------------- reading the docx ----
def docx_ast(docx):
    out = subprocess.run(["pandoc", "--track-changes=all", "-t", "json", str(docx)],
                         check=True, capture_output=True, cwd=ROOT).stdout
    return json.loads(out)


def classes(node):
    return node["c"][0][1] if node.get("t") == "Span" else []


def resolve(node, accept):
    """Copy of the tree with tracked changes accepted (or rejected) and comments removed."""
    if isinstance(node, list):
        out = []
        for x in node:
            if isinstance(x, dict) and x.get("t") == "Span":
                cl = classes(x)
                if any(c.startswith("comment") for c in cl) or \
                   ("insertion" in cl and not accept) or ("deletion" in cl and accept):
                    continue
                if "insertion" in cl or "deletion" in cl or "paragraph-insertion" in cl:
                    out += resolve(x["c"][1], accept)
                    continue
            out.append(resolve(x, accept))
        return out
    if isinstance(node, dict):
        return {k: resolve(v, accept) for k, v in node.items()}
    return node


def plain(node, notes):
    """Text of a node; footnotes are pulled out into `notes`."""
    if isinstance(node, dict):
        t = node.get("t")
        if t == "Str": return node["c"]
        if t in ("Space", "SoftBreak", "LineBreak"): return " "
        if t == "Note":
            notes.append(node["c"])
            return " "
        if t == "Quoted":
            q = ("“", "”") if node["c"][0]["t"] == "DoubleQuote" else ("‘", "’")
            return q[0] + plain(node["c"][1], notes) + q[1]
        c = node.get("c")
        return plain(c, notes) if isinstance(c, (list, dict)) else ""
    if isinstance(node, list):
        return "".join(plain(x, notes) for x in node)
    return ""


def segments(blocks):
    """Body paragraphs, then each footnote, as separate text segments."""
    segs, notes = [], []

    def walk_blocks(bs, sink):
        for b in bs:
            t = b.get("t")
            if t in ("Para", "Plain"):
                sink.append(plain(b["c"], notes))
            elif t == "Header":
                sink.append(plain(b["c"][2], notes))
            elif t in ("BlockQuote",):
                walk_blocks(b["c"], sink)
            elif t == "Div":
                walk_blocks(b["c"][1], sink)
            elif t == "BulletList":
                for item in b["c"]: walk_blocks(item, sink)
            elif t == "OrderedList":
                for item in b["c"][1]: walk_blocks(item, sink)

    walk_blocks(blocks, segs)
    i = 0
    while i < len(notes):  # notes may be appended while walking
        walk_blocks(notes[i], segs)
        i += 1
    return segs


def words_of(segs):
    words = []
    for s in segs:
        if s.split():
            words += s.split() + [PARA]
    return words


def comments(blocks):
    found = []

    def walk(n, para):
        if isinstance(n, dict):
            if n.get("t") in ("Para", "Plain", "Header"):
                para = plain(resolve(n, True), [])
            if "comment-start" in classes(n):
                attrs = dict(n["c"][0][2])
                found.append({"author": attrs.get("author", "?"),
                              "comment": plain(n["c"][1], []).strip(),
                              "paragraph": " ".join(para.split())})
            for v in n.values():
                if isinstance(v, (list, dict)): walk(v, para)
        elif isinstance(n, list):
            for v in n: walk(v, para)

    walk(blocks, "")
    return found


# ------------------------------------------------- finding it in Markdown ----
def word_rx(word):
    return FMT + "".join(EQUIV.get(c, re.escape(c)) for c in word) + FMT


def words_rx(words):
    return r"\s+".join(word_rx(w) for w in words)


def bounded(words, i, step, k):
    """Up to k words from i going in `step` direction, stopping at a paragraph break."""
    out, j = [], i
    while len(out) < k and 0 <= j < len(words) and words[j] != PARA:
        out.append(words[j]); j += step
    return out[::-1] if step < 0 else out


def locate(old, i1, i2, sources):
    core = old[i1:i2]
    last = None
    for k in range(2, MAX_CONTEXT + 1):
        before, after = bounded(old, i1 - 1, -1, k), bounded(old, i2, 1, k)
        if (before, after) == last:
            break  # context can't grow any further
        last = (before, after)
        if not before and not after:
            return None, "no surrounding words to anchor the change"
        mid = words_rx(core) if core else ""
        rx = ""
        if before:
            rx += f"(?P<before>{words_rx(before)})"
            rx += r"(?P<mid>\s+" + mid + (r"\s+)" if after and mid else ")")
        else:
            rx += "(?P<mid>" + mid + (r"\s+)" if mid else ")")
        if after:
            rx += f"(?P<after>{words_rx(after)})"
        hits = [(p, m) for p, text in sources.items() for m in re.finditer(rx, text)]
        if len(hits) == 1:
            return hits[0], None
        if not hits:
            return None, ("original wording not found in article/ (it may cross formatting "
                          "or a footnote marker, or the draft has changed since)")
    return None, "wording appears more than once in article/"


def splice(mid, new, has_before, has_after):
    """Replacement for the matched middle, keeping the source's own whitespace
    (so one-sentence-per-line breaks survive)."""
    if not mid.strip():  # pure insertion
        if has_before and has_after:
            return mid + new + " "
        return (" " + new) if has_before else (new + " ")
    lead = mid[:len(mid) - len(mid.lstrip())]
    trail = mid[len(mid.rstrip()):]
    if new:
        return lead + new + trail
    return lead if (lead and trail) else ""


# ------------------------------------------------------------------- main ----
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--doc", default="documents/article-draft", help="document folder, e.g. documents/my-memo")
    ap.add_argument("--apply", action="store_true", help="write safe changes into the document's section files")
    args = ap.parse_args()
    docx = args.docx.resolve()

    ast = docx_ast(docx)
    old = words_of(segments(resolve(ast["blocks"], accept=False)))
    new = words_of(segments(resolve(ast["blocks"], accept=True)))
    sources = {str(p.relative_to(ROOT)): p.read_text()
               for p in sorted((ROOT / args.doc).glob("[0-9]*.md"))}

    applied, todo, edits = [], [], {}
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        e = {"old": " ".join(old[i1:i2]), "new": " ".join(new[j1:j2]),
             "before": " ".join(bounded(old, i1 - 1, -1, 8)),
             "after": " ".join(bounded(old, i2, 1, 8))}
        if PARA in old[i1:i2] or PARA in new[j1:j2]:
            e["why"] = "paragraphs were split or merged"
            todo.append(e); continue
        hit, why = locate(old, i1, i2, sources)
        e["why"] = why
        if hit:
            path, m = hit
            e["where"] = f"{path}:{sources[path].count(chr(10), 0, m.start('mid')) + 1}"
            if MARKUP.search(m.group("mid")) or MARKUP.search(e["new"]):
                e["why"] = "the changed words touch Markdown formatting"
            elif args.apply:
                gd = m.groupdict()
                rep = splice(m.group("mid"), e["new"], gd.get("before") is not None,
                             gd.get("after") is not None)
                edits.setdefault(path, []).append((m.start("mid"), m.end("mid"), rep))
                applied.append(e); continue
        todo.append(e)

    for path, changes in edits.items():
        text, floor = sources[path], None
        for s, end, rep in sorted(changes, reverse=True):
            if floor is not None and end > floor:
                continue  # overlaps an edit already made; a second run will catch it
            text, floor = text[:s] + rep + text[end:], s
        (ROOT / path).write_text(text)

    notes = comments(ast["blocks"])
    report = ROOT / "edits" / f"{docx.stem}-report.md"
    report.parent.mkdir(exist_ok=True)

    def show(e):
        old_s = f"~~{e['old']}~~" if e["old"] else "*(insert)*"
        new_s = f"**{e['new']}**" if e["new"] else "*(delete)*"
        out = [f"- `{e.get('where', 'location not found')}` {old_s} → {new_s}",
               f"  - …{e['before']} [{e['old'] or '^'}] {e['after']}…"]
        if e.get("why") and (args.apply or "where" not in e):
            out.append(f"  - {'not applied: ' if args.apply else ''}{e['why']}")
        return out

    lines = [f"# Edits from {docx.name}", "",
             f"{len(applied) + len(todo)} changes, {len(notes)} comments. " +
             (f"{len(applied)} applied to article/; review with `git diff`." if args.apply
              else "Report only. Run with APPLY=1 to write the safe ones into article/."), ""]
    if applied:
        lines += ["## Applied", ""] + sum(map(show, applied), []) + [""]
    if todo:
        lines += ["## Apply by hand" if args.apply else "## Changes", ""] + sum(map(show, todo), []) + [""]
    if notes:
        lines += ["## Comments", ""]
        for c in notes:
            para = c["paragraph"]
            lines += [f"- **{c['author']}:** {c['comment']}",
                      f"  - on: “{para[:200]}{'…' if len(para) > 200 else ''}”"]
    report.write_text("\n".join(lines) + "\n")
    print(f"{len(applied)} applied, {len(todo)} {'to do by hand' if args.apply else 'found'}, "
          f"{len(notes)} comments -> {report.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"pandoc failed:\n{e.stderr.decode()}")
