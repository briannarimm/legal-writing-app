#!/usr/bin/env python3
"""Build the table of authorities for a brief.

Usage:  python3 scripts/make_toa.py <build-dir> <job-name>

Reads <build-dir>/<job>.toa-raw (one \\toaraw{category}{tag}{page} per marked cite, written by
LaTeX), looks each tag up in library/citations/, and writes <build-dir>/<job>.toa.tex with the
entries grouped by category, alphabetized, and with their pages. Run before the final LaTeX pass.
"""
import os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = [  # library type -> heading, in the order briefs list them
    ("case", "Cases"),
    ("constitution", "Constitutional Provisions"),
    ("statute", "Statutes"),
    ("rule", "Rules"),
    ("regulation", "Regulations"),
    ("other", "Other Authorities"),
]
KNOWN = {k for k, _ in CATEGORIES}


def read_entry(tag):
    p = Path(os.environ.get("LT_DATA") or ROOT) / "library" / "citations" / f"{tag}.md"
    if not p.exists():
        return None
    parts = p.read_text(encoding="utf-8").split("\n---\n", 1)
    body = parts[1] if len(parts) == 2 else parts[0]
    body = body.replace("\r", "")
    return body.strip()


def to_latex(markdown_cites):
    """Convert cites (Markdown with *italics* and [small caps]{.smallcaps}) to LaTeX in one Pandoc call."""
    if not markdown_cites:
        return []
    src = "\n\n".join(c.replace("\n", " ") for c in markdown_cites)
    out = subprocess.run(["pandoc", "-f", "markdown+smart", "-t", "latex", "--wrap=none"],
                         input=src, capture_output=True, text=True, check=True).stdout
    paras = [p.strip() for p in re.split(r"\n\s*\n", out.strip())]
    if len(paras) != len(markdown_cites):
        raise SystemExit("make_toa: Pandoc returned an unexpected number of paragraphs")
    return paras


def pages_text(pages):
    nums = sorted({int(p) for p in pages})
    if len(nums) > 5:
        return "\\textit{passim}"
    return ", ".join(str(n) for n in nums)


def main():
    build, job = Path(sys.argv[1]), sys.argv[2]
    raw = build / f"{job}.toa-raw"
    uses = {}  # tag -> (category, set of pages)
    if raw.exists():
        for m in re.finditer(r"\\toaraw\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}", raw.read_text()):
            cat, tag, page = m.groups()
            uses.setdefault(tag, (cat, set()))[1].add(page)
    entries, missing = [], []
    for tag, (cat, pages) in uses.items():
        md = read_entry(tag)
        if md is None:
            missing.append(tag)
            md = f"[{tag}: not found in the citation library]"
            cat = "other"
        entries.append((cat if cat in KNOWN else "other", md, pages))

    latex = to_latex([e[1] for e in entries])
    lines = []
    for key, heading in CATEGORIES:
        group = sorted(((re.sub(r"[^a-z0-9 ]", "", e[1].lower()), latex[i], e[2])
                        for i, e in enumerate(entries) if e[0] == key), key=lambda t: t[0])
        if not group:
            continue
        lines.append(f"\\toacat{{{heading}}}")
        for _, text, pages in group:
            lines.append(f"\\toaentry{{{text}}}{{{pages_text(pages)}}}")
    if not lines:
        lines = ["\\par\\textit{No authorities are marked yet. Insert citations with the Cite button in "
                 "ReWord and they will be listed here.}"]
    (build / f"{job}.toa.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"table of authorities: {len(entries)} authorities" + (f"; NOT in library: {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
