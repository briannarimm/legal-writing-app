#!/usr/bin/env python3
"""Pandoc JSON filter: live citations for the make / Docker route (the app does the same in app/builder.py).

    pandoc ... --filter scripts/cites_filter.py ...
    CITES_TEMPLATE=templates/<id>/template.json  CITES_MODE=draft|final  (LT_DATA: folder with library/)

Replaces each [..]{.cite tag=…} with its formatted citation from library/citations (see app/cites.py).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import cites  # noqa: E402

fmt = sys.argv[1] if len(sys.argv) > 1 else "latex"
tpath = os.environ.get("CITES_TEMPLATE")
tmpl = json.loads(Path(tpath).read_text(encoding="utf-8")) if tpath and Path(tpath).exists() else {}
mode = os.environ.get("CITES_MODE", "draft")
data = os.environ.get("LT_DATA") or str(ROOT)
out, report = cites.resolve_json_text(sys.stdin.read(), cites.load_library(data), tmpl, mode, "docx" if fmt == "docx" else "latex")
if report["missing"]:
    sys.stderr.write("Citations not in the library: %s\n" % ", ".join(report["missing"]))
sys.stdout.write(out)
