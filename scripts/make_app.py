#!/usr/bin/env python3
"""Build the stand-alone "ReWord" for Apple Silicon Macs.

    python3 scripts/make_app.py [--out FOLDER] [--import-data PROJECT_FOLDER]
    python3 scripts/make_app.py --dist      # also make distro/ReWord-<version>-mac-arm64.zip

The result is one folder you can copy to a USB drive (or anywhere):

    ReWord/
        ReWord.app      the program: its own window, Python, Pandoc and TeX engine
        ReWord Data/    your documents, research, citations and finished files
        READ ME FIRST.txt

Nothing else needs to be installed on the computer you plug it into: no Python, no Docker, no
Chrome, no LaTeX, no internet. (Only GitHub features need git, if you use them there.)

What this script does:
  1. downloads Pandoc, Tectonic (a self-contained TeX engine) and a portable Python from their
     official releases into ~/Library/Caches/ReWord Build (once; checksums recorded),
  2. typesets a sample of every template so Tectonic's support files are cached for offline use,
  3. compiles the native window (app/mac/main.swift) and draws the icon,
  4. assembles and ad-hoc signs ReWord.app.

Needs: a Mac with the Xcode command line tools (swiftc, codesign) and an internet connection the
first time. The finished app needs none of that.
"""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path.home() / "Library" / "Caches" / "ReWord Build"
VERSION = "1.1.1"          # also the name of the download in distro/
DIST = ROOT / "distro"

# Pinned versions. Pandoc matches the Docker image, so output is the same either way.
PANDOC = ("3.9.0.2", "https://github.com/jgm/pandoc/releases/download/3.9.0.2/pandoc-3.9.0.2-arm64-macOS.zip", None)
TECTONIC = ("0.17.0", "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/"
            "tectonic-0.17.0-aarch64-apple-darwin.tar.gz", None)
PYTHON = ("3.12.15", "https://github.com/astral-sh/python-build-standalone/releases/download/20261009/"
          "cpython-3.12.15%2B20261009-aarch64-apple-darwin-install_only_stripped.tar.gz",
          "233f8e15255b3e1d1fd47ea5dd5230dfed803f371138e896e54d98c60ae19f6f")


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name, spec, filename):
    version, url, want = spec
    dest = CACHE / filename
    if not dest.exists():
        print("Downloading %s %s ..." % (name, version))
        CACHE.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, str(dest) + ".part")
        os.replace(str(dest) + ".part", dest)
    got = sha256(dest)
    if want and got != want:
        dest.unlink()
        sys.exit("The %s download doesn't match its published checksum. Try again." % name)
    return dest, got


def prepare_runtime():
    """Unpack the three tools into CACHE/runtime and slim them down. Returns {name: (version, sha256)}."""
    rt = CACHE / "runtime"
    info = {}
    py, info["python"] = fetch("Python", PYTHON, "python.tar.gz")
    pz, info["pandoc"] = fetch("Pandoc", PANDOC, "pandoc.zip")
    tt, info["tectonic"] = fetch("Tectonic", TECTONIC, "tectonic.tar.gz")
    info = {"python": (PYTHON[0], info["python"]), "pandoc": (PANDOC[0], info["pandoc"]), "tectonic": (TECTONIC[0], info["tectonic"])}
    if (rt / "bin" / "pandoc").exists() and (rt / "bin" / "tectonic").exists() and (rt / "python" / "bin" / "python3").exists():
        return rt, info
    shutil.rmtree(rt, ignore_errors=True)
    (rt / "bin").mkdir(parents=True)
    with tarfile.open(py) as t:
        t.extractall(rt)
    with tarfile.open(tt) as t:
        t.extractall(rt / "bin")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(pz) as z:
            z.extractall(tmp)
        exe = next(Path(tmp).rglob("pandoc"))
        shutil.copy2(exe, rt / "bin" / "pandoc")
    for b in ("pandoc", "tectonic"):
        (rt / "bin" / b).chmod(0o755)
    # Python: drop what this program never uses (tests, GUI toolkit, installers, editors)
    lib = rt / "python" / "lib"
    for rel in ("python3.12/test", "python3.12/idlelib", "python3.12/tkinter", "python3.12/turtledemo", "python3.12/ensurepip",
                "python3.12/lib2to3", "python3.12/site-packages", "tcl9", "tcl9.0", "tk9.0", "itcl4.3.8", "thread3.0.6",
                "libtcl9.0.dylib", "libtcl9tk9.0.dylib"):
        p = lib / rel
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    for p in (rt / "python").rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    (rt / "python" / "share").exists() and shutil.rmtree(rt / "python" / "share", ignore_errors=True)
    return rt, info


def stage_code(dest):
    """The program's own files: the server, web pages, templates, filters and scripts."""
    dest.mkdir(parents=True)
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "mac")
    shutil.copytree(ROOT / "app", dest / "app", ignore=skip)
    for d in ("templates", "filters", "defaults"):
        shutil.copytree(ROOT / d, dest / d, ignore=skip)
    (dest / "scripts").mkdir()
    for f in ("redline.py", "make_toa.py", "import_edits.py", "make_reference_docx.py"):
        shutil.copy2(ROOT / "scripts" / f, dest / "scripts" / f)


def warm_tex_cache(code, rt, cache):
    """Typeset a sample of every template (and a redline) so Tectonic downloads each support file once, now."""
    print("Preparing the offline TeX cache (typesets every template once; the first time takes a few minutes) ...")
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["LT_RUNTIME"] = str(rt)
    os.environ["TECTONIC_CACHE_DIR"] = str(cache)
    os.environ.pop("LT_ONLY_CACHED", None)
    sys.path.insert(0, str(code / "app"))
    import store, builder  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        store.set_root(data)
        store.set_code(code)
        store.write_citation("sample-case", {"type": "case", "fields": {"name": "Smith v. Jones", "volume": "123", "reporter": "F.3d",
                                                                       "first_page": "456", "court": "8th Cir.", "date": "1999"}}, create=True)
        store.write_citation("sample-article", {"type": "journal", "fields": {"authors": [{"given": "Jane", "family": "Scholar"}],
                                                                             "title": "An Article", "journal": "Harvard Law Review",
                                                                             "volume": "100", "first_page": "1", "date": "2020"}}, create=True)
        for t in store.templates():
            slug = store.create_document(t["id"], "Warm up " + t["id"])
            if t.get("toa"):
                last = sorted(store.section_paths(slug))[-1]
                last.write_text(last.read_text() + '\nSee [*Smith v. Jones*, 123 F.3d 456 (8th Cir. 1999)]{.auth tag="sample-case"}.\n')
            print("  " + t["name"])
            builder.build(code, data, slug, lambda line: None)
            if t.get("redline"):
                store.create_version(slug, "v0.1")
                first = sorted(store.section_paths(slug))[0]
                first.write_text(first.read_text() + "\nOne more sentence.\n")
                base = ("dir", str(store.version_path(slug, "v0.1")), "v0.1")
                if not builder.redline(code, data, slug, base, lambda line: None):
                    sys.exit("The warm-up redline for %s failed." % t["name"])
    # prove the cache is complete: the same builds again, with the network forbidden
    os.environ["LT_ONLY_CACHED"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        store.set_root(data)
        store.write_citation("sample-case", {"type": "case", "fields": {"name": "Smith v. Jones", "volume": "123", "reporter": "F.3d",
                                                                       "first_page": "456", "date": "1999"}}, create=True)
        for t in store.templates():
            slug = store.create_document(t["id"], "Offline check " + t["id"])
            builder.build(code, data, slug, lambda line: None)
    os.environ.pop("LT_ONLY_CACHED", None)
    print("  offline check passed")


def build_rwpdf(work):
    """The PDF helper (web snapshots, annotated copies): app/mac/rwpdf.swift, macOS frameworks only."""
    exe = work / "rwpdf"
    sh(["swiftc", "-O", "-target", "arm64-apple-macos12.0", "-framework", "AppKit", "-framework", "WebKit", "-framework", "PDFKit",
        str(ROOT / "app" / "mac" / "rwpdf.swift"), "-o", str(exe)])
    return exe


def build_shell(work):
    exe = work / "ReWord"
    sh(["swiftc", "-O", "-target", "arm64-apple-macos12.0", "-framework", "AppKit", "-framework", "WebKit",
        str(ROOT / "app" / "mac" / "main.swift"), "-o", str(exe)])
    return exe


def build_icon(dest_icns, work):
    exe, big = work / "make_icon", work / "icon-1024.png"
    sh(["swiftc", "-O", str(ROOT / "scripts" / "make_icon.swift"), "-o", str(exe)])
    sh([str(exe), str(big)])
    iconset = work / "AppIcon.iconset"
    iconset.mkdir()
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = base * scale
            name = "icon_%dx%d%s.png" % (base, base, "@2x" if scale == 2 else "")
            sh(["sips", "-z", str(px), str(px), str(big), "--out", str(iconset / name)], capture_output=True)
    sh(["iconutil", "-c", "icns", str(iconset), "-o", str(dest_icns)])


README = """REWORD
================

Double-click "ReWord.app" to start. Nothing else needs to be installed.

* Your work is in the "ReWord Data" folder next to the app: documents, research notes,
  your citation library, and the finished PDF and Word files. Keep the two together, and
  your work goes wherever the drive goes. This drive is the only copy until you back it up
  (the Publish tab can push a copy to GitHub).
* It runs on Apple Silicon Macs (M1 or newer).
* The first time on a new computer, macOS may ask permission to use files on this drive: choose
  Allow. If macOS says it can't verify the app, right-click the app, choose Open, then Open.
* Eject the drive from Finder when you are done, after quitting ReWord (Command-Q).
* For a drive you will use only on Macs, format it as "APFS" or "Mac OS Extended" in Disk Utility.
  exFAT also works for this app, but older Macs and some tools handle it less gracefully.
"""


NOTICE = """ReWord {version}: third-party software in ReWord.app
=============================================================

ReWord itself is MIT-licensed (code) and CC BY 4.0 (documentation). See LICENSE in the source
repository. ReWord.app also contains these programs, unchanged, under their own licenses:

{tools}
Source code for these programs:
  * Pandoc (GNU GPL v2 or later): https://github.com/jgm/pandoc/tree/{pandoc}
    Source archive: https://github.com/jgm/pandoc/archive/refs/tags/{pandoc}.tar.gz
  * Tectonic (MIT; TeX support files under the LaTeX Project Public License, SIL OFL and others):
    https://github.com/tectonic-typesetting/tectonic/tree/tectonic%40{tectonic}
  * Python (PSF License 2.0), built by python-build-standalone:
    https://github.com/astral-sh/python-build-standalone
  * PDF.js (Apache 2.0): https://github.com/mozilla/pdf.js (license in
    ReWord.app/Contents/Resources/code/app/static/vendor/pdfjs/LICENSE)

The sha256 values above are of the archives downloaded from each project's official release page.
"""


def make_dist(app, versions):
    """Zip a clean copy for others: the app, an empty data folder, the read-me and the license notice."""
    DIST.mkdir(exist_ok=True)
    name = "ReWord-%s-mac-arm64" % VERSION
    with tempfile.TemporaryDirectory() as tmp:
        top = Path(tmp) / "ReWord"
        top.mkdir()
        sh(["ditto", str(app), str(top / "ReWord.app")])            # ditto keeps the signature and symlinks
        (top / "ReWord Data").mkdir()                                # empty: the app fills it on first start
        (top / "READ ME FIRST.txt").write_text(README, encoding="utf-8")
        tools = "".join("  * %-9s %-9s sha256 %s\n" % (n, v, h) for n, (v, h) in versions.items())
        (top / "THIRD-PARTY NOTICES.txt").write_text(
            NOTICE.format(version=VERSION, tools=tools, pandoc=versions["pandoc"][0], tectonic=versions["tectonic"][0]),
            encoding="utf-8")
        shutil.copy2(ROOT / "LICENSE", top / "LICENSE.txt")
        zp = DIST / (name + ".zip")
        zp.unlink(missing_ok=True)
        print("Zipping %s ..." % zp)
        sh(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(top), str(zp)])
    digest = sha256(zp)
    (DIST / (name + ".zip.sha256")).write_text("%s  %s\n" % (digest, zp.name), encoding="utf-8")
    print("  %s (%.0f MB)\n  sha256 %s" % (zp, zp.stat().st_size / 1e6, digest))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path.home() / "ReWord"), help="folder to create (default: ~/ReWord)")
    ap.add_argument("--import-data", help="copy the documents, research, library and settings from this project folder into the data folder")
    ap.add_argument("--dist", action="store_true",
                    help="also zip the app with an empty data folder into distro/ for others to download (never includes your data)")
    ap.add_argument("--skip-warm", action="store_true", help="reuse the existing TeX cache without re-checking every template")
    a = ap.parse_args()
    if sys.platform != "darwin" or os.uname().machine != "arm64":
        sys.exit("Run this on an Apple Silicon Mac: it builds an Apple Silicon app.")

    out = Path(a.out).expanduser()
    app = out / "ReWord.app"
    work = Path(tempfile.mkdtemp())
    try:
        rt, versions = prepare_runtime()
        cache = CACHE / "tex-cache"
        stage = work / "code"
        stage_code(stage)
        if not a.skip_warm or not cache.exists():
            warm_tex_cache(stage, rt, cache)

        print("Building the window ...")
        shell = build_shell(work)
        rwpdf = build_rwpdf(work)
        shutil.copy2(rwpdf, rt / "bin" / "rwpdf")          # the developer route finds it here too
        icns = work / "AppIcon.icns"
        build_icon(icns, work)

        print("Assembling %s ..." % app)
        out.mkdir(parents=True, exist_ok=True)
        if app.exists():
            shutil.rmtree(app)
        res = app / "Contents" / "Resources"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        res.mkdir(parents=True)
        shutil.copy2(shell, app / "Contents" / "MacOS" / "ReWord")
        shutil.copy2(icns, res / "AppIcon.icns")
        shutil.copytree(stage, res / "code")
        # runtime/tex-cache is the developer route's working cache; the app uses tex-cache-seed instead
        shutil.copytree(rt, res / "runtime", symlinks=True,
                        ignore=lambda d, names: ["tex-cache"] if Path(d) == rt else [])
        shutil.copytree(cache, res / "runtime" / "tex-cache-seed")
        (res / "MANIFEST.txt").write_text(
            "ReWord runtime\n" + "".join("%s %s  sha256 %s\n" % (n, v, h) for n, (v, h) in versions.items()), encoding="utf-8")
        usage = "ReWord reads and saves your documents."
        plist = {
            "CFBundleName": "ReWord", "CFBundleDisplayName": "ReWord",
            "CFBundleIdentifier": "app.reword", "CFBundleExecutable": "ReWord",
            "CFBundleIconFile": "AppIcon", "CFBundlePackageType": "APPL", "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION, "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True, "NSAllowsArbitraryLoadsInWebContent": True},
            "NSRemovableVolumesUsageDescription": usage, "NSDocumentsFolderUsageDescription": usage,
            "NSDesktopFolderUsageDescription": usage, "NSDownloadsFolderUsageDescription": usage,
            "NSNetworkVolumesUsageDescription": usage,
        }
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump(plist, f)

        subprocess.run(["xattr", "-cr", str(app)], check=False)
        sh(["codesign", "--force", "--deep", "-s", "-", str(app)], capture_output=True)
        sh(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True)

        data = out / "ReWord Data"
        data.mkdir(exist_ok=True)
        (out / "READ ME FIRST.txt").write_text(README, encoding="utf-8")
        if a.import_data:
            src = Path(a.import_data).expanduser()
            for name in ("documents", "research", "library"):
                if (src / name).is_dir() and not (data / name).exists():
                    shutil.copytree(src / name, data / name, ignore=shutil.ignore_patterns(".DS_Store", "_trash", ".gitkeep"))
                    print("  copied %s" % name)
        if a.dist:
            make_dist(app, versions)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file()) / 1e6
    print("\nBuilt %s (%.0f MB)" % (app, size))
    print("Copy the whole \"%s\" folder to your USB drive. Double-click ReWord.app to open it." % out.name)


if __name__ == "__main__":
    main()
