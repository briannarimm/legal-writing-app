"""Build a document with Pandoc and Tectonic directly: no Docker, no make, nothing installed.

This is what the portable app uses. (When these tools aren't available, as when working in the
project folder on a computer that has Docker, server.py falls back to the Docker/make route.)

Tools come from $LT_RUNTIME/bin (the portable app sets it) or from the PATH. Tectonic is a
self-contained TeX engine; its support files live in $LT_RUNTIME/tex-cache, filled in ahead of
time so nothing needs the internet.
"""
import json
import os
import tempfile
import re
import shutil
import subprocess
import sys
from pathlib import Path


class BuildError(Exception):
    """A build step failed; the message is meant for the person using the app."""


def runtime():
    d = os.environ.get("LT_RUNTIME")
    return Path(d) if d else None


def tool(name):
    rt = runtime()
    if rt and (rt / "bin" / name).is_file():
        return str(rt / "bin" / name)
    return shutil.which(name)


def native_ready():
    return bool(tool("pandoc") and tool("tectonic"))


def tool_env(data):
    e = dict(os.environ)
    rt = runtime()
    if rt:
        e["PATH"] = str(rt / "bin") + os.pathsep + e.get("PATH", "")
        e.setdefault("TECTONIC_CACHE_DIR", str(rt / "tex-cache"))
    e["LT_DATA"] = str(data)            # where documents/ and library/ are (used by filters and make_toa.py)
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    return e


def run(cmd, cwd, env, log, quiet=False):
    """Run a command, streaming its output to log(). Returns (returncode, last lines)."""
    if not quiet:
        log("$ " + " ".join(Path(cmd[0]).name if i == 0 else c for i, c in enumerate(cmd))[:200])
    p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    tail = []
    for line in p.stdout:
        line = line.rstrip("\n")
        tail = (tail + [line])[-25:]
        # Tectonic announces each support file it fetches on first use; keep the log readable
        if line.startswith("note: downloading") and not quiet:
            continue
        log(line)
    return p.wait(), tail


def must(cmd, cwd, env, log, what):
    rc, tail = run(cmd, cwd, env, log)
    if rc != 0:
        raise BuildError("%s failed. The last lines of the log above say why." % what)


def word_total(pandoc, code, ast_json, env):
    """Count words with the same filter `make wordcount` uses; returns (summary line, total)."""
    jf = Path(tempfile.gettempdir()) / ("lt-words-%d.json" % os.getpid())
    e = dict(env, WORDCOUNT_JSON=str(jf))
    p = subprocess.run([pandoc, "-f", "json", "--lua-filter", "filters/wordcount.lua", "-t", "plain", str(ast_json), "-o", os.devnull],
                       cwd=str(code), env=e, capture_output=True, text=True)
    line = next((l for l in (p.stdout + p.stderr).splitlines() if l.startswith("Words:")), "")
    total = 0
    try:
        total = json.loads(jf.read_text())["total"]
        jf.unlink()
    except (OSError, ValueError, KeyError):
        pass
    return line, total


def compile_tex(tex, cwd, env, log):
    """Tectonic reruns TeX itself until cross-references settle."""
    cmd = [tool("tectonic"), "--keep-intermediates", "--keep-logs"]
    if os.environ.get("LT_ONLY_CACHED"):         # never touch the network (used to prove offline builds work)
        cmd.append("--only-cached")
    must(cmd + [Path(tex).name], cwd, env, log, "Typesetting the PDF")


def build(code, data, slug, log, final=None):
    """Build every output the template makes. Live citations are resolved first (app/cites.py): the draft
    (slug.pdf, slug.docx …) has every citation in full; with the document's Final draft switch on, a
    second set (slug-final.pdf …) has Id., short forms and supra worked out. Returns the word-count line."""
    sys.path.insert(0, str(Path(code) / "app"))
    import cites  # noqa: E402
    code, data = Path(code), Path(data)
    docdir = data / "documents" / slug
    info = json.loads((docdir / "document.json").read_text(encoding="utf-8"))
    tid = info["template"]
    tmpl = json.loads((code / "templates" / tid / "template.json").read_text(encoding="utf-8"))
    sections = sorted(p for p in docdir.glob("[0-9]*.md"))
    if not sections:
        raise BuildError("This document has no sections to build.")
    meta = docdir / "metadata.yaml"
    out = data / "build" / slug
    out.mkdir(parents=True, exist_ok=True)
    env = tool_env(data)
    pandoc = tool("pandoc")
    rel = lambda name: "templates/%s/%s" % (tid, name)      # noqa: E731 - relative to the code folder
    if final is None:
        final = bool(info.get("final_draft"))

    # 1. read the document once
    source = out / (slug + ".source.json")
    must([pandoc, "-d", "defaults/common.yaml", "--metadata-file", str(meta)] + [str(s) for s in sections] +
         ["-t", "json", "-o", str(source)], code, env, log, "Reading the document")
    doc_text = source.read_text(encoding="utf-8")
    library = cites.load_library(data)

    summary = ""
    for mode in (["draft", "final"] if final else ["draft"]):
        stem = slug if mode == "draft" else slug + "-final"
        if mode == "final":
            log("Final draft: short forms, Id. and supra")

        def resolved(fmt):
            text, report = cites.resolve_json_text(doc_text, library, tmpl, mode, fmt)
            if report["missing"]:
                log("Citations not in the library: " + ", ".join(report["missing"]))
            p = out / ("%s.%s.json" % (stem, fmt))
            p.write_text(text, encoding="utf-8")
            return p

        latex_ast = resolved("latex")
        line, total = word_total(pandoc, code, latex_ast, env)
        if mode == "draft" or not summary:
            summary = line
        for fmt in tmpl["outputs"]:
            target = out / ("%s.%s" % (stem, fmt))
            ast = latex_ast if fmt in ("pdf", "html", "txt") else resolved(fmt)
            if fmt == "pdf":
                tex = out / ("%s.tex" % stem)
                extra = []
                if tmpl.get("pdf_builder") == "toa":
                    extra = ["-M", "words=%s" % "{:,}".format(total)]       # for the certificate of compliance
                must([pandoc, "-f", "json", str(ast), "-d", rel("pdf.yaml")] + extra + ["-s", "-o", str(tex)],
                     code, env, log, "Preparing the PDF")
                compile_tex(tex, out, env, log)
                if tmpl.get("pdf_builder") == "toa":
                    # first pass told us which page each authority landed on; build the table, then typeset again
                    must([sys.executable, str(code / "scripts" / "make_toa.py"), str(out), stem], code, env, log, "Building the table of authorities")
                    compile_tex(tex, out, env, log)
            elif fmt in ("docx", "html", "txt"):
                must([pandoc, "-f", "json", str(ast), "-d", rel(fmt + ".yaml"), "-o", str(target)],
                     code, env, log, "Building the %s file" % fmt.upper())
            else:
                raise BuildError("Don't know how to build a .%s file." % fmt)
    if summary:
        log(summary)
    return summary


def redline(code, data, slug, base, log):
    """base = ("dir", path, label) for a saved version, or ("git", ref, label) for an older git tag."""
    code, data = Path(code), Path(data)
    info = json.loads((data / "documents" / slug / "document.json").read_text(encoding="utf-8"))
    kind, where, label = base
    out = data / "build" / slug / ("redline-vs-" + label.replace("/", "-"))
    cmd = [sys.executable, str(code / "scripts" / "redline.py"), "--doc", str(data / "documents" / slug),
           "--template", "templates/" + info["template"], "--base", label, "--out", str(out)]
    cmd += ["--base-dir", where] if kind == "dir" else ["--git-ref", where, "--repo", str(data)]
    rc, tail = run(cmd, code, tool_env(data), log)
    return rc == 0
