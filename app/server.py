#!/usr/bin/env python3
"""Local server for ReWord. Standard library only; nothing to install.

    python3 app/server.py            (or double-click start.command, or `make app`)

It serves the editor (app/static/), reads and writes documents, research notes and the
citation library (app/store.py), and runs the same git + make steps you would otherwise
type. It listens on 127.0.0.1 only.
"""
import argparse
import http.server
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import datetime
import urllib.parse
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
import store  # noqa: E402
import builder  # noqa: E402
import citeformat  # noqa: E402
import cites  # noqa: E402
import lookup  # noqa: E402

STATIC = APP_DIR / "static"
IMAGE = "lawreview-build:latest"
TAG_SUFFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")

PORT = 8765


# ---------------------------------------------------------------- helpers

def root():
    return store.ROOT


def env():
    e = dict(os.environ)
    extra = "/opt/homebrew/bin:/usr/local/bin"
    rt = os.environ.get("LT_RUNTIME")
    if rt:
        extra = rt + "/bin:" + extra
    e["PATH"] = extra + ":" + e.get("PATH", "")
    return e


_GIT = "unset"


def find_git():
    """Path to a working git, or None. Never runs /usr/bin/git unless the Xcode command line tools
    are installed: on a Mac without them that file is a stub that pops up an installer window."""
    global _GIT
    if os.environ.get("LT_NO_GIT"):           # for testing how the app behaves where git isn't installed
        return None
    if _GIT != "unset":
        return _GIT
    found = next((c for c in ("/opt/homebrew/bin/git", "/usr/local/bin/git") if os.access(c, os.X_OK)), None)
    if not found:
        if sys.platform == "darwin":
            try:
                ok = subprocess.run(["/usr/bin/xcode-select", "-p"], capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
            found = "/usr/bin/git" if ok and os.access("/usr/bin/git", os.X_OK) else None
        else:
            found = shutil.which("git")
    _GIT = found
    return found


def need_git():
    if not find_git():
        raise store.StoreError("This needs git, which isn't installed on this computer. Everything else in ReWord "
                               "works without it; to use GitHub here, install git (xcode-select --install in Terminal).")


def run_quiet(cmd, timeout=60):
    """Run a command, return (returncode, combined output). Never raises."""
    if cmd and cmd[0] == "git":
        g = find_git()
        if not g:
            return 127, "git is not available on this computer"
        cmd = [g] + list(cmd[1:])
    try:
        p = subprocess.run(cmd, cwd=root(), env=env(), capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "command not found: " + cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "timed out: " + " ".join(cmd)


def is_repo():
    return run_quiet(["git", "rev-parse", "--is-inside-work-tree"])[0] == 0


def last_tag(slug):
    """Newest saved version of a document: a snapshot name like "v0.2" (works everywhere), or,
    for documents versioned before snapshots existed, a git tag like "my-memo/v0.2"."""
    try:
        v = store.last_version(slug)
    except store.StoreError:
        v = None
    if v:
        return v["name"]
    rc, out = run_quiet(["git", "describe", "--tags", "--abbrev=0", "--match", slug + "/v*"])
    return out if rc == 0 else None


def redline_base(slug):
    """What to redline against: ("dir", folder, name) for a snapshot, ("git", ref, name) for an old git tag."""
    try:
        v = store.last_version(slug)
    except store.StoreError:
        v = None
    if v:
        return ("dir", str(store.version_path(slug, v["name"])), v["name"])
    rc, out = run_quiet(["git", "describe", "--tags", "--abbrev=0", "--match", slug + "/v*"])
    return ("git", out, out.split("/", 1)[-1]) if rc == 0 else None


def next_tag(slug, current):
    m = re.match(r"^v(\d+)\.(\d+)$", (current or "").split("/", 1)[-1])
    return ("v%s.%d" % (m.group(1), int(m.group(2)) + 1)) if m else "v0.1"


def dirty_count():
    rc, out = run_quiet(["git", "status", "--porcelain"])
    return len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0


def commit_all(label=""):
    """Commit everything git doesn't ignore. Returns a short description."""
    if not is_repo():
        return "not a git repository"
    run_quiet(["git", "add", "-A"])
    if run_quiet(["git", "diff", "--cached", "--quiet"])[0] == 0:
        return "nothing new to commit"
    msg = "Draft saved " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + (" (%s)" % label if label else "")
    rc, out = run_quiet(["git", "commit", "-q", "-m", msg])
    if rc != 0:
        raise RuntimeError("git commit failed: " + out)
    return "committed (%s)" % msg


def status(slug=None):
    repo = is_repo()
    tag = last_tag(slug) if slug else None
    return {"repo": repo, "gitAvailable": bool(find_git()), "lastTag": tag.split("/", 1)[-1] if tag else None,
            "nextTag": next_tag(slug, tag), "dirty": dirty_count() if repo else 0, "running": JOB.running}


def list_outputs(slug, tid, tag):
    """Built files for a document: the draft in each format the template makes, plus the redline."""
    out = []
    b = root() / "build" / slug
    if not b.exists():
        return out
    try:
        formats = store.template(tid)["outputs"]
    except store.StoreError:
        formats = []

    def add(name, label):
        p = b / name
        if p.exists():
            out.append({"name": slug + "/" + name, "label": label, "kind": p.suffix[1:], "mtime": p.stat().st_mtime})
    for ext in formats:
        add("%s.%s" % (slug, ext), "Draft")
    for ext in formats:
        add("%s-final.%s" % (slug, ext), "Final")
    if tag:
        stem = "redline-vs-" + tag.split("/", 1)[-1].replace("/", "-")
        add(stem + ".pdf", "Redline vs " + tag.split("/", 1)[-1])
        add(stem + ".docx", "Redline vs " + tag.split("/", 1)[-1])
    return out


# ---------------------------------------------------------------- settings, outputs, GitHub

SETTINGS_NAME = "settings.local.json"     # per-machine, git-ignored
GITHUB_URL_RE = re.compile(r"^(https://github\.com/[\w.-]+/[\w.-]+?(\.git)?|git@github\.com:[\w.-]+/[\w.-]+?(\.git)?)$")
REPO_NAME_RE = re.compile(r"^[\w.-]{1,100}$")


def get_settings():
    d = {"outputDir": "", "autoPush": False}
    try:
        d.update(json.loads((root() / SETTINGS_NAME).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return d


def save_settings(d):
    store.write_atomic(root() / SETTINGS_NAME, json.dumps(d, indent=2) + "\n")


def output_dir():
    s = get_settings()
    return Path(s["outputDir"]).expanduser() if s["outputDir"] else root() / "outputs"


def check_output_dir(text):
    """An output folder must be an absolute path that doesn't contain or sit inside the project's .git."""
    p = Path(text).expanduser()
    if not p.is_absolute():
        raise store.StoreError("Use a full path, for example /Users/you/Documents/ReWord Outputs.")
    r, here = p.resolve(), root().resolve()
    if r == here or r in here.parents:
        raise store.StoreError("The output folder can't be the project folder or one that contains it.")
    if ".git" in r.parts:
        raise store.StoreError("The output folder can't be inside a .git folder.")
    return p


def repo_path(which):
    if which == "outputs":
        return output_dir()
    if which == "project":
        return root()
    raise store.StoreError("unknown repository")


def git_in(path, *args, timeout=120, noninteractive=False):
    e = env()
    if noninteractive:
        e["GIT_TERMINAL_PROMPT"] = "0"       # never hang waiting for a password
        e["GCM_INTERACTIVE"] = "never"
    try:
        g = find_git()
        if not g:
            return 127, "git is not available on this computer"
        p = subprocess.run([g, "-C", str(path)] + list(args), env=e, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "git is not installed"
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ds: git %s" % (timeout, " ".join(args))


def project_identity():
    out = {}
    for k in ("user.name", "user.email"):
        rc, v = git_in(root(), "config", k)
        if rc == 0 and v:
            out[k] = v
    return out


def ensure_output_repo():
    """Make the output folder, and (when git is available) turn it into its own git repository."""
    d = output_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not find_git():
        return d
    if not (d / ".git").exists():
        rc, out = git_in(d, "init", "-q", "-b", "main")
        if rc != 0:
            raise RuntimeError("Couldn't set up the output folder as a git repository: " + out)
        (d / "README.md").write_text(
            "# ReWord outputs\n\nFinished files from ReWord: one folder per document, "
            "with its PDF, Word, HTML or text files and a `redlines/` folder.\n", encoding="utf-8")
    for k, v in project_identity().items():           # commits need a name and email
        if not git_in(d, "config", k)[1]:
            git_in(d, "config", k, v)
    for k, v in (("user.name", "ReWord"), ("user.email", "noreply@reword.local")):
        if not git_in(d, "config", k)[1]:             # nobody configured git on this computer
            git_in(d, "config", k, v)
    return d


# ---------------------------------------------------------------- the work repo (documents, research, library)

WORK_GITIGNORE = """# ReWord work repository: documents, research notes, citations, attached files and annotations.
# Finished files go to the separate outputs repository.
build/
outputs/
.tex-cache/
settings.local.json
_trash/
.DS_Store
*.tmp
"""


def ensure_work_repo():
    """The data folder as a git repository (it already is one when working in the project folder)."""
    need_git()
    d = root()
    if not (d / ".git").exists():
        rc, out = git_in(d, "init", "-q", "-b", "main")
        if rc != 0:
            raise store.StoreError("Couldn't set up the work folder as a git repository: " + out)
        if not (d / ".gitignore").exists():
            (d / ".gitignore").write_text(WORK_GITIGNORE, encoding="utf-8")
        if not (d / "README.md").exists():
            (d / "README.md").write_text("# ReWord work\n\nDocuments, research notes, the citation library and its attached "
                                         "files, kept by ReWord. Open the folder with ReWord to work on it.\n", encoding="utf-8")
    for k, v in project_identity().items():
        if not git_in(d, "config", k)[1]:
            git_in(d, "config", k, v)
    for k, v in (("user.name", "ReWord"), ("user.email", "noreply@reword.local")):
        if not git_in(d, "config", k)[1]:
            git_in(d, "config", k, v)
    return d


def sync_work(reason="sync", log=None):
    """Save everything, then bring the work repository and GitHub in step: commit, fetch, rebase onto
    GitHub's version (if the same lines changed on both sides: merge, keeping this computer's lines;
    GitHub's version stays in the history), push. Never asks for a password; never raises."""
    say = log or (lambda line: None)
    if not find_git():
        return {"ok": False, "offline": True, "message": "Working offline: this computer has no git, so syncing waits until you're back on a Mac set up for GitHub."}
    d = root()
    if not (d / ".git").exists():
        return {"ok": False, "setup": True, "message": "Your work isn't connected to GitHub yet (Publish → Connect…)."}
    host = os.uname().nodename.split(".")[0]
    for k, v in (("user.name", "ReWord"), ("user.email", "noreply@reword.local")):
        if not git_in(d, "config", k)[1]:             # a borrowed Mac where nobody set up git
            git_in(d, "config", k, v)
    try:
        commit_repo(d, "Sync from %s %s (%s)" % (host, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), reason))
    except RuntimeError as e:
        say(str(e))
        return {"ok": False, "message": "Couldn't save a snapshot for syncing: %s" % e}
    st = git_status("project")
    if not st.get("remote"):
        return {"ok": True, "message": "Saved on this computer (no GitHub repository connected)."}
    branch = st.get("branch") or "main"
    rc, out = git_in(d, "fetch", "origin", noninteractive=True, timeout=90)
    if rc != 0:
        msg = friendly_push_error(out) if any(h in out for h in AUTH_HINTS) else "Couldn't reach GitHub (offline?). Your work is saved here and will sync later."
        say(msg)
        return {"ok": False, "offline": True, "message": msg}
    pulled = 0
    note = ""
    has_remote_branch = git_in(d, "rev-parse", "--verify", "-q", "origin/" + branch)[0] == 0
    if has_remote_branch:
        rc, cnt = git_in(d, "rev-list", "--count", "HEAD..origin/" + branch)
        pulled = int(cnt) if rc == 0 and cnt.isdigit() else 0
        if pulled:
            rc, out = git_in(d, "rebase", "origin/" + branch)
            if rc != 0:
                git_in(d, "rebase", "--abort")
                rc, out = git_in(d, "merge", "-X", "ours", "--no-edit", "-m", "Sync: merge GitHub changes (%s)" % host, "origin/" + branch)
                if rc != 0:
                    git_in(d, "merge", "--abort")
                    say(out)
                    return {"ok": False, "message": "GitHub and this computer changed the same files in a way ReWord can't combine. "
                                                    "Nothing was lost; open the folder in GitHub Desktop or Terminal to finish (git status)."}
                note = " Some lines were changed both here and on GitHub; this computer's version was kept (GitHub's is in the history)."
    rc, ahead = git_in(d, "rev-list", "--count", ("origin/" + branch + "..HEAD") if has_remote_branch else "HEAD")
    pushed = int(ahead) if rc == 0 and ahead.isdigit() else 0
    if pushed:
        rc, out = git_in(d, "push", "-u", "origin", "HEAD", noninteractive=True, timeout=180)
        if rc != 0:
            msg = friendly_push_error(out)
            say(msg)
            return {"ok": False, "message": msg, "pulled": pulled}
    parts = [x for x in (("%d change%s from GitHub" % (pulled, "" if pulled == 1 else "s")) if pulled else "",
                         ("%d sent" % pushed) if pushed else "") if x]
    msg = ("Synced with GitHub: " + ", ".join(parts) if parts else "Up to date with GitHub") + "." + note
    say(msg)
    return {"ok": True, "pulled": pulled, "pushed": pushed, "message": msg, "changed": bool(pulled)}


def web_url(remote):
    m = re.match(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(\.git)?$", remote or "") or \
        re.match(r"^git@github\.com:([\w.-]+)/([\w.-]+?)(\.git)?$", remote or "")
    return "https://github.com/%s/%s" % (m.group(1), m.group(2)) if m else ""


def git_status(which):
    path = repo_path(which)
    out = {"repo": which, "path": str(path), "isRepo": (path / ".git").exists(), "gitAvailable": bool(find_git())}
    if not out["isRepo"]:
        return out
    rc, branch = git_in(path, "rev-parse", "--abbrev-ref", "HEAD")
    out["branch"] = branch if rc == 0 else ""
    rc, remote = git_in(path, "remote", "get-url", "origin")
    out["remote"] = remote if rc == 0 else ""
    out["web"] = web_url(out["remote"])
    rc, counts = git_in(path, "rev-list", "--left-right", "--count", "@{u}...HEAD")
    if rc == 0 and counts.split():
        behind, ahead = counts.split()[:2]
        out["behind"], out["ahead"] = int(behind), int(ahead)
    rc, st = git_in(path, "status", "--porcelain")
    out["dirty"] = len([l for l in st.splitlines() if l.strip()]) if rc == 0 else 0
    return out


def gh_info(check_login=True):
    exe = shutil.which("gh", path=env()["PATH"])
    info = {"installed": bool(exe), "authed": False, "user": ""}
    if exe and check_login:
        try:
            p = subprocess.run([exe, "auth", "status"], env=env(), capture_output=True, text=True, timeout=20)
            info["authed"] = p.returncode == 0
            m = re.search(r"account (\S+)", p.stdout + p.stderr)
            info["user"] = m.group(1) if m else ""
        except (subprocess.TimeoutExpired, OSError):
            pass
    return info


AUTH_HINTS = ("Authentication failed", "could not read Username", "Permission denied", "terminal prompts disabled",
              "Invalid username or token", "Repository not found", "403", "401")


def friendly_push_error(out):
    if any(h in out for h in AUTH_HINTS):
        return ("GitHub didn't accept the sign-in. Open Terminal and run:  gh auth login   (choose GitHub.com and HTTPS), "
                "then try again.\n\n" + out)
    if "non-fast-forward" in out or "fetch first" in out or "rejected" in out:
        return ("GitHub has changes this computer doesn't. Pull them first (git pull --rebase in the folder), then push again.\n\n" + out)
    return out


def commit_repo(path, message):
    """Stage everything and commit if there is anything new. Returns True if a commit was made."""
    if not find_git() or not (Path(path) / ".git").exists():
        return False
    git_in(path, "add", "-A")
    if git_in(path, "diff", "--cached", "--quiet")[0] == 0:
        return False
    rc, out = git_in(path, "commit", "-q", "-m", message)
    if rc != 0:
        raise RuntimeError("git commit failed: " + out)
    return True


def push_repo(which, log=None):
    """Commit pending work and push to origin. Raises with a plain-language message on failure."""
    need_git()
    path = repo_path(which)
    if which == "outputs":
        ensure_output_repo()
        commit_repo(path, "Publish " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    else:
        commit_all("push")
    st = git_status(which)
    if not st.get("remote"):
        raise store.StoreError("No GitHub repository is connected to this folder yet. Use Connect first.")
    if not st.get("branch") or st["branch"] == "HEAD":
        raise store.StoreError("This folder has no commits to push yet.")
    rc, out = git_in(path, "push", "-u", "origin", "HEAD", noninteractive=True)
    if rc != 0:
        raise store.StoreError(friendly_push_error(out), 502)
    return out


def outputs_folder(slug):
    """<output folder>/<project>/<document>, or <output folder>/<document> without a project. If the
    document moved between projects, its existing folder moves with it."""
    d = ensure_output_repo()
    info = store.read_doc_info(store.doc_path(slug))
    pid = info.get("project") or ""
    dest = (d / pid / slug) if pid else (d / slug)
    if not dest.exists():
        project_ids = [x["id"] for x in store.projects_list()]
        olds = [d / slug] + [d / x / slug for x in project_ids if x != pid]
        for old in olds:
            if old.is_dir() and old != dest and old.name == slug and old.resolve() != (d / pid).resolve():
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.rename(old, dest)
                break
    return d, dest


def copy_outputs(slug, tid, tag):
    """Copy a document's finished files into <output folder>/[<project>/]<document>/ (redlines in redlines/)."""
    d, dest = outputs_folder(slug)
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for o in list_outputs(slug, tid, tag):
        src = root() / "build" / o["name"]
        target_dir = dest / "redlines" if o["label"].startswith("Redline") else dest
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target_dir / src.name)       # contents only: no macOS metadata files on USB drives
        copied.append(str((target_dir / src.name).relative_to(d)))
    return copied


def publish_document(slug, push=False):
    """Copy the document's latest build to the output folder, commit it, optionally push."""
    info = store.read_doc_info(store.doc_path(slug))
    tag = last_tag(slug)
    copied = copy_outputs(slug, info["template"], tag)
    if not copied:
        raise store.StoreError("There's nothing built for this document yet. Press Run first.")
    tname = store.template(info["template"])["name"]
    made = commit_repo(output_dir(), "%s (%s): %s" % (slug, tname, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    return copied, made


# ---------------------------------------------------------------- PDF helper (web snapshots, annotated copies)

def pdf_tools():
    """rwpdf (app/mac/rwpdf.swift) lives in the app's runtime/bin; make_app.py also leaves a copy in its build cache."""
    t = builder.tool("rwpdf")
    if not t:
        c = Path.home() / "Library" / "Caches" / "ReWord Build" / "runtime" / "bin" / "rwpdf"
        t = str(c) if c.exists() else None
    return {"rwpdf": t} if t else {}


def text_snapshot(url, target):
    """Fallback snapshot: the page's text as a PDF (no images), via Pandoc and the TeX engine."""
    import lookup
    pandoc, tectonic = builder.tool("pandoc"), builder.tool("tectonic")
    if not (pandoc and tectonic):
        raise store.StoreError("Snapshots need ReWord's PDF helper or its PDF engine; neither is available here.", 501)
    try:
        data, ctype, final = lookup.fetch(url, "text/html")
    except lookup.LookupError as e:
        raise store.StoreError(str(e), 502)
    tmp = Path(target).with_suffix(".tmp")
    tmp.mkdir(exist_ok=True)
    try:
        html_path = tmp / "page.html"
        html_path.write_bytes(data)
        lua = tmp / "noimg.lua"
        lua.write_text("function Image(i) return {} end\nfunction RawBlock(r) return {} end\nfunction RawInline(r) return {} end\n")
        tex = tmp / "page.tex"
        p = subprocess.run([pandoc, "-f", "html", str(html_path), "--lua-filter", str(lua), "-s", "--template",
                            str(store.CODE / "templates" / "_note" / "note.latex"), "-M", "title=" + final, "-M", "source=Snapshot of " + final,
                            "-o", str(tex)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise store.StoreError("Couldn't convert the page.", 502)
        builder.compile_tex(tex, tmp, builder.tool_env(root()), lambda line: None)
        os.replace(tmp / "page.pdf", target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- pipeline job

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()
        self.running = False

    def reset(self):
        self.id = int(time.time() * 1000)
        self.doc = ""
        self.lines = []
        self.step = ""
        self.done = False
        self.ok = None
        self.outputs = []
        self.words = ""
        self.message = ""

    def log(self, line):
        with self.lock:
            self.lines.append(line.rstrip("\n"))

    def snapshot(self, since):
        with self.lock:
            return {"id": self.id, "doc": self.doc, "lines": self.lines[since:], "next": len(self.lines),
                    "step": self.step, "done": self.done, "ok": self.ok, "outputs": self.outputs,
                    "words": self.words, "message": self.message, "running": self.running}


JOB = Job()


def stream(cmd):
    """Run a command, stream its output into the job log, return the exit code."""
    JOB.log("$ " + " ".join(cmd))
    try:
        p = subprocess.Popen(cmd, cwd=root(), env=env(), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError:
        JOB.log("command not found: " + cmd[0])
        return 127
    for line in p.stdout:
        JOB.log(line)
        m = re.match(r"^Words:.*", line.strip())
        if m:
            JOB.words = m.group(0)
    return p.wait()


def docker_ready():
    return run_quiet(["docker", "info"], timeout=30)[0] == 0


def ensure_docker():
    """Return 'docker' or 'local', or raise with a plain-language reason."""
    have_docker = shutil.which("docker", path=env()["PATH"]) is not None
    have_pandoc = shutil.which("pandoc", path=env()["PATH"]) is not None
    if have_docker:
        if not docker_ready():
            JOB.step = "Starting Docker Desktop"
            JOB.log("Docker isn't running. Starting Docker Desktop (this can take a minute)...")
            run_quiet(["open", "-a", "Docker"])
            deadline = time.time() + 150
            while time.time() < deadline and not docker_ready():
                time.sleep(3)
        if docker_ready():
            if run_quiet(["docker", "image", "inspect", IMAGE])[0] != 0:
                JOB.step = "Building the build image (first time only, several minutes)"
                if stream(["make", "image"]) != 0:
                    raise RuntimeError("Couldn't build the Docker image. See the log above.")
            return "docker"
    if have_pandoc:
        JOB.log("Docker isn't available; using the Pandoc installed on this Mac instead.")
        return "local"
    raise RuntimeError("Docker isn't running and no local Pandoc was found. "
                       "Open Docker Desktop, wait for it to say it's running, and press Run again.")


def pipeline(slug):
    try:
        info = store.read_doc_info(store.doc_path(slug))
        tmpl = store.template(info["template"])
        doc = "documents/" + slug
        JOB.step = "Saving a snapshot"
        JOB.log("== Versioning ==")
        try:
            JOB.log(commit_all(slug))
        except RuntimeError as e:         # the build matters more than a git commit
            JOB.log("(Skipped the git commit: %s)" % e)

        JOB.log("== Build (%s) ==" % tmpl["name"])
        if builder.native_ready():
            # the portable route: Pandoc and Tectonic run directly, nothing else needed
            JOB.step = "Building " + " and ".join(o.upper() for o in tmpl["outputs"])
            try:
                JOB.words = builder.build(store.CODE, store.ROOT, slug, JOB.log) or ""
            except builder.BuildError as e:
                raise RuntimeError(str(e))
            base = redline_base(slug)
            tag = base[2] if base else None
            if tmpl.get("redline") and base:
                JOB.step = "Making the redline against " + base[2]
                JOB.log("== Redline against %s ==" % base[2])
                if not builder.redline(store.CODE, store.ROOT, slug, base, JOB.log):
                    JOB.log("(The redline failed, but the document itself built fine.)")
            elif tmpl.get("redline"):
                JOB.log("No saved version yet, so no redline. Use \"Tag version\" to set a baseline.")
        else:
            # working in the project folder: Docker (or a local Pandoc) through make
            mode = ensure_docker()
            make = ["make"] + (["USE_DOCKER=0"] if mode == "local" else []) + ["DOC=" + doc]
            JOB.step = "Building " + " and ".join(o.upper() for o in tmpl["outputs"])
            if stream(make + ["all"]) != 0:
                raise RuntimeError("The build failed. The last lines of the log above say why.")
            base = redline_base(slug)
            tag = base[2] if base else None
            if tmpl.get("redline") and base:
                JOB.step = "Making the redline against " + base[2]
                JOB.log("== Redline against %s ==" % base[2])
                if base[0] == "dir":
                    extra = ["BASE=" + base[2], "BASE_DIR=documents/%s/.versions/%s" % (slug, base[2])]
                else:
                    extra = ["BASE=" + base[1]]
                if stream(make + ["redline"] + extra) != 0:
                    JOB.log("(The redline failed, but the document itself built fine.)")
            elif tmpl.get("redline"):
                JOB.log("No saved version yet, so no redline. Use \"Tag version\" to set a baseline.")

        JOB.outputs = list_outputs(slug, info["template"], tag)

        JOB.step = "Copying to the output folder"
        JOB.log("== Output folder ==")
        try:
            copied, made = publish_document(slug)
            JOB.log("%d file%s copied to %s/%s/%s" % (len(copied), "" if len(copied) == 1 else "s", output_dir(), slug,
                                                    " (committed)" if made else ""))
            if (root() / ".git").exists() and find_git() and git_status("project").get("remote"):
                JOB.step = "Syncing your work with GitHub"
                JOB.log("== Sync ==")
                sync_work("run", JOB.log)
            if get_settings().get("autoPush") and git_status("outputs").get("remote"):
                JOB.step = "Pushing to GitHub"
                push_repo("outputs")
                JOB.log("Pushed the output folder to GitHub.")
        except Exception as e:  # noqa: BLE001 - the build itself succeeded
            JOB.log("(Couldn't finish the output-folder step: %s)" % e)

        JOB.ok = True
        JOB.message = "Done"
    except Exception as e:  # noqa: BLE001 - report anything to the user
        JOB.ok = False
        JOB.message = str(e)
        JOB.log("ERROR: " + str(e))
    finally:
        JOB.step = ""
        JOB.done = True
        JOB.running = False


def start_job(slug):
    with JOB.lock:
        if JOB.running:
            return False
        JOB.reset()
        JOB.doc = slug
        JOB.running = True
    threading.Thread(target=pipeline, args=(slug,), daemon=True).start()
    return True


# ---------------------------------------------------------------- app lifecycle
# When launched as an app (no Terminal), the server quits by itself once the window is gone.
# The page pings every few seconds and says goodbye as it closes. A reload says goodbye and
# pings again within a second or two, so only a real close lets the grace period run out.

class Lifecycle:
    def __init__(self):
        self.enabled = False
        self.started = time.time()
        self.last_ping = None       # time of the most recent ping
        self.bye_at = None          # time of the most recent goodbye
        self.grace = 8              # seconds after goodbye with no new ping
        self.idle = 180             # seconds with no ping at all (covers a hidden or sleeping window)
        self.first = 120            # seconds to wait for the very first ping

    def ping(self):
        """Record a ping; return how many seconds ago the previous one was (None if first)."""
        now = time.time()
        prev = None if self.last_ping is None else round(now - self.last_ping, 1)
        self.last_ping = now
        return prev

    def bye(self):
        self.bye_at = time.time()

    def should_quit(self, now):
        if not self.enabled or JOB.running:
            return False
        if self.last_ping is None:
            return now - self.started > self.first
        if self.bye_at and self.bye_at >= self.last_ping:
            return now - self.bye_at > self.grace
        return now - self.last_ping > self.idle


LIFE = Lifecycle()


# ---------------------------------------------------------------- HTTP

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "LawReviewApp"

    def log_message(self, fmt, *args):  # quiet
        pass

    # --- plumbing
    def send_json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def fail(self, msg, code=400, **extra):
        self.send_json(dict(error=msg, **extra), code)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20_000_000:
            raise ValueError("body too large")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode() or "{}")

    def local_only(self):
        """Block other websites from talking to this server (CSRF / DNS rebinding)."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self.fail("bad host", 403)
            return False
        origin = self.headers.get("Origin")
        if origin:
            o = urllib.parse.urlparse(origin)
            if o.hostname not in ("127.0.0.1", "localhost"):
                self.fail("bad origin", 403)
                return False
        if self.command == "POST" and self.path.startswith("/api/attach?"):
            if self.headers.get("X-ReWord") != "1":
                self.fail("missing header", 403)
                return False
        elif self.command in ("POST", "PUT"):
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                self.fail("json only", 415)
                return False
        return True

    def serve_file(self, path, download=False):
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % path.name)
        self.end_headers()
        self.wfile.write(data)

    def guarded(self, fn):
        try:
            fn()
        except store.StoreError as e:
            self.fail(str(e), e.code, **e.extra)
        except Exception as e:  # noqa: BLE001
            self.fail(str(e), 500)

    # --- routing
    def do_GET(self):
        if not self.local_only():
            return
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        p = u.path
        if p in ("/", "/index.html"):
            return self.serve_file(STATIC / "index.html")
        if p.startswith("/static/"):
            f = (STATIC / p[len("/static/"):]).resolve()
            if STATIC.resolve() not in f.parents:
                return self.send_error(404)
            return self.serve_file(f)
        if p.startswith("/files/"):          # attachments: /files/<tag>/<name>
            parts = [urllib.parse.unquote(x) for x in p[len("/files/"):].split("/")]
            if len(parts) != 2:
                return self.send_error(404)
            try:
                f = store.attachment_path(parts[0], parts[1])
            except store.StoreError:
                return self.send_error(404)
            return self.serve_file(f, download="download" in q)
        if p.startswith("/build/"):
            b = (root() / "build").resolve()
            f = (b / urllib.parse.unquote(p[len("/build/"):])).resolve()
            if b not in f.parents:
                return self.send_error(404)
            return self.serve_file(f, download="download" in q)
        routes = {
            "/api/state": lambda: self.send_json({"templates": store.templates(), "documents": store.documents(),
                                                  "projects": store.projects_list(), "status": status()}),
            "/api/projects": lambda: self.send_json({"projects": store.projects_list(), "colors": store.PROJECT_COLORS}),
            "/api/doc": lambda: self.api_doc(q.get("slug")),
            "/api/status": lambda: self.send_json(status(q.get("doc"))),
            "/api/job": lambda: self.send_json(JOB.snapshot(int(q.get("since") or 0))),
            "/api/notes": lambda: self.send_json({"notes": store.notes()}),
            "/api/note": lambda: self.send_json(store.read_note(store.note_path(q.get("id")))),
            "/api/citations": lambda: self.send_json({"citations": store.citations(), "types": store.CITE_TYPES, "schema": citeformat.schema()}),
            "/api/settings": lambda: self.send_json(self.settings_out()),
            "/api/git": lambda: self.send_json(git_status(q.get("repo"))),
            "/api/gh": lambda: self.send_json(gh_info()),
            "/api/ping": lambda: self.send_json({"ok": True, "since": LIFE.ping()}),
            "/api/files": lambda: self.send_json({"files": store.list_attachments(q.get("tag")), "tools": pdf_tools()}),
            "/api/annotations": lambda: self.send_json(store.read_annotations(q.get("tag"), q.get("name"))),
        }
        fn = routes.get(p)
        if not fn:
            return self.send_error(404)
        self.guarded(fn)

    def do_PUT(self):
        if not self.local_only():
            return
        routes = {"/api/file": self.api_save, "/api/note": self.api_save_note, "/api/citation": self.api_save_citation,
                  "/api/project": lambda b: self.send_json(store.update_project(b.get("id"), b)),
                  "/api/annotations": lambda b: self.send_json(store.write_annotations(b.get("tag"), b.get("name"), b.get("annotations"),
                                                                                       b.get("mtime"), b.get("force"))),
                  "/api/settings": self.api_save_settings}
        fn = routes.get(self.path)
        if not fn:
            return self.send_error(404)
        self.guarded(lambda: fn(self.body()))

    def do_POST(self):
        if not self.local_only():
            return
        if self.path.startswith("/api/attach?"):
            return self.guarded(self.api_attach)
        routes = {
            "/api/doc/new": self.api_doc_new, "/api/doc/rename": self.api_doc_rename, "/api/doc/option": self.api_doc_option,
            "/api/doc/delete": self.api_doc_delete, "/api/doc/template": self.api_doc_template,
            "/api/section/new": self.api_section_new, "/api/section/move": self.api_section_move,
            "/api/section/delete": self.api_section_delete,
            "/api/run": self.api_run, "/api/tag": self.api_tag,
            "/api/note/new": self.api_note_new, "/api/note/delete": self.api_note_delete,
            "/api/citation/new": self.api_citation_new, "/api/citation/delete": self.api_citation_delete,
            "/api/citation/preview": self.api_citation_preview, "/api/lookup": self.api_lookup,
            "/api/cite/render": self.api_cite_render,
            "/api/project/new": lambda b: self.send_json(store.create_project(b)),
            "/api/project/delete": lambda b: (store.delete_project(b.get("id")), self.send_json({"ok": True}))[1],
            "/api/note/project": lambda b: self.send_json(store.assign_note(b.get("id"), b.get("project") or "")),
            "/api/citation/projects": self.api_citation_projects, "/api/file/delete": self.api_file_delete,
            "/api/snapshot": self.api_snapshot, "/api/annotations/export": self.api_annotations_export, "/api/render": self.api_render, "/api/note/export": self.api_note_export,
            "/api/git/connect": self.api_git_connect, "/api/git/create": self.api_git_create,
            "/api/git/push": self.api_git_push, "/api/sync": lambda b: self.send_json(sync_work(b.get("reason") or "sync")), "/api/publish": self.api_publish, "/api/open": self.api_open,
            "/api/bye": lambda b: (LIFE.bye(), self.send_json({"ok": True}))[1],
        }
        fn = routes.get(self.path)
        if not fn:
            return self.send_error(404)
        self.guarded(lambda: fn(self.body()))

    # --- documents
    def api_doc(self, slug):
        info = store.read_doc_info(store.doc_path(slug))
        tag = last_tag(slug)
        self.send_json({"doc": info, "template": store.template(info["template"]), "files": store.doc_files(slug),
                        "status": status(slug), "outputs": list_outputs(slug, info["template"], tag)})

    def api_save(self, b):
        path = store.resolve_doc_file(b.get("doc"), b.get("file"))
        mt = store.save_file(path, b.get("content"), b.get("mtime"), b.get("force"))
        info = store.read_doc_info(store.doc_path(b.get("doc")))
        added = store.assign_citations(store.cited_tags(b.get("content")), info["project"]) if info.get("project") else []
        self.send_json({"mtime": mt, "status": status(b.get("doc")), "assigned": added})

    def api_doc_new(self, b):
        slug = store.create_document(b.get("template"), b.get("title"), b.get("project") or "")
        self.send_json({"slug": slug})

    def api_doc_rename(self, b):
        self.send_json({"title": store.rename_document(b.get("slug"), b.get("title"))})

    def api_doc_option(self, b):
        info = store.set_doc_option(b.get("slug"), b.get("key"), b.get("value"))
        self.send_json({"ok": True, "info": info})

    def api_doc_template(self, b):
        """Switch a document to another template, converting its citations and details (store.change_template)."""
        self.send_json(store.change_template(b.get("slug"), b.get("template")))

    def api_doc_delete(self, b):
        store.delete_document(b.get("slug"))
        self.send_json({"ok": True})

    def api_section_new(self, b):
        info = store.read_doc_info(store.doc_path(b.get("doc")))
        t = store.template(info["template"])
        if not t.get("multi_section", True) and store.section_paths(b.get("doc")):
            raise store.StoreError("This kind of document has a single section.")
        self.send_json({"file": store.new_section(b.get("doc"), b.get("title"), t.get("new_section_heading", "#"))})

    def api_section_move(self, b):
        self.send_json({"file": store.move_section(b.get("doc"), b.get("file"), b.get("dir"))})

    def api_section_delete(self, b):
        store.delete_section(b.get("doc"), b.get("file"))
        self.send_json({"ok": True})

    def api_run(self, b):
        store.doc_path(b.get("doc"))
        if not start_job(b.get("doc")):
            return self.fail("A run is already in progress.", 409)
        self.send_json({"id": JOB.id})

    def api_tag(self, b):
        slug = b.get("doc")
        store.doc_path(slug)
        suffix = (b.get("name") or "").strip()
        if not TAG_SUFFIX_RE.match(suffix):
            raise store.StoreError("Version names can use letters, numbers, dots, dashes (for example v0.2).")
        store.create_version(slug, suffix)         # the saved snapshot redlines compare against
        msg = ""
        if is_repo():                              # git is a bonus, never a requirement
            name = "%s/%s" % (slug, suffix)
            try:
                msg = commit_all(slug)
                if run_quiet(["git", "rev-parse", "-q", "--verify", "refs/tags/" + name])[0] != 0:
                    run_quiet(["git", "tag", name])
            except RuntimeError as e:
                msg = "(git commit skipped: %s)" % e
        self.send_json({"tag": suffix, "commit": msg, "status": status(slug)})

    # --- notes
    def api_note_new(self, b):
        self.send_json(store.create_note(b.get("title"), b.get("topic", ""), b.get("citation", ""), b.get("body", ""), b.get("project") or ""))

    def api_save_note(self, b):
        self.send_json(store.write_note(b.get("id"), b, b.get("mtime"), b.get("force")))

    def api_note_delete(self, b):
        store.delete_note(b.get("id"))
        self.send_json({"ok": True})

    # --- settings, output folder, GitHub
    def settings_out(self):
        s = get_settings()
        return {"outputDir": str(output_dir()), "outputDirIsDefault": not s["outputDir"], "autoPush": bool(s["autoPush"])}

    def api_save_settings(self, b):
        s = get_settings()
        if "outputDir" in b:
            text = (b.get("outputDir") or "").strip()
            if text:
                check_output_dir(text)
            s["outputDir"] = text
        if "autoPush" in b:
            s["autoPush"] = bool(b["autoPush"])
        save_settings(s)
        self.send_json(self.settings_out())

    def api_git_connect(self, b):
        need_git()
        which, url = b.get("repo"), (b.get("url") or "").strip()
        if not GITHUB_URL_RE.match(url):
            raise store.StoreError("Paste a GitHub repository address, like https://github.com/you/your-repo")
        path = ensure_output_repo() if which == "outputs" else ensure_work_repo()
        if not (path / ".git").exists():
            raise store.StoreError("That folder isn't a git repository.")
        has = git_in(path, "remote", "get-url", "origin")[0] == 0
        rc, out = git_in(path, "remote", "set-url" if has else "add", "origin", url)
        if rc != 0:
            raise store.StoreError("git couldn't save the address: " + out)
        self.send_json(git_status(which))

    def api_git_create(self, b):
        need_git()
        which, name = b.get("repo"), (b.get("name") or "").strip()
        if not REPO_NAME_RE.match(name):
            raise store.StoreError("Repository names can use letters, numbers, dots, dashes and underscores.")
        info = gh_info()
        if not info["installed"]:
            raise store.StoreError("The GitHub CLI isn't installed. In Terminal: brew install gh")
        if not info["authed"]:
            raise store.StoreError("Sign in to GitHub first. In Terminal: gh auth login")
        path = ensure_output_repo() if which == "outputs" else ensure_work_repo()
        commit_repo(path, "Initial commit" if which == "outputs" else "ReWord work (first sync)")
        exe = shutil.which("gh", path=env()["PATH"])
        vis = "--private" if b.get("private", True) else "--public"
        try:
            p = subprocess.run([exe, "repo", "create", name, vis, "--source", str(path), "--remote", "origin"],
                               env=env(), capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            raise store.StoreError("GitHub didn't answer in time. Try again.", 504)
        if p.returncode != 0:
            raise store.StoreError((p.stdout + p.stderr).strip() or "gh couldn't create the repository.", 502)
        self.send_json(git_status(which))

    def api_git_push(self, b):
        which = b.get("repo")
        out = push_repo(which)
        self.send_json({"status": git_status(which), "message": out})

    def api_publish(self, b):
        slug = b.get("doc")
        store.doc_path(slug)
        copied, made = publish_document(slug)
        pushed = ""
        if b.get("push"):
            push_repo("outputs")
            pushed = "pushed"
        self.send_json({"copied": copied, "committed": made, "pushed": pushed, "status": git_status("outputs")})

    def api_open(self, b):
        which, what = b.get("repo"), b.get("what")
        if what == "github":
            url = git_status(which).get("web")
            if not url:
                raise store.StoreError("No GitHub repository is connected yet.")
            run_quiet(["open", url])
        else:
            path = ensure_output_repo() if which == "outputs" else repo_path(which)
            run_quiet(["open", str(path)])
        self.send_json({"ok": True})

    # --- citations
    def api_citation_new(self, b):
        self.send_json(store.write_citation(b.get("tag"), b, create=True))

    def api_save_citation(self, b):
        self.send_json(store.write_citation(b.get("tag"), b, b.get("mtime"), b.get("force")))

    def api_citation_projects(self, b):
        """Add a citation to a project, or (from the citation form) set its projects by hand."""
        tag = b.get("tag")
        p = store.cite_path(tag)
        if not p.exists():
            raise store.StoreError("no such citation", 404)
        if b.get("add"):
            if not store.project_exists(b["add"]):
                raise store.StoreError("no such project", 404)
            store._edit_citation_projects(p, lambda pr, au: (pr, au) if b["add"] in pr else (pr + [b["add"]], au))
        else:
            want = [x for x in dict.fromkeys(b.get("projects") or []) if store.project_exists(x)]
            store._edit_citation_projects(p, lambda pr, au: (want, [x for x in au if x in want]))
        self.send_json(store.read_citation(p))

    def api_citation_preview(self, b):
        self.send_json(store.preview_citation(b))

    # --- attachments, web snapshots, annotated copies
    def api_attach(self):
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
        n = int(self.headers.get("Content-Length") or 0)
        if n > store.MAX_ATTACH:
            raise store.StoreError("That file is larger than 200 MB, too big to keep in a GitHub repository.", 413)
        data = self.rfile.read(n) if n else b""
        if not data:
            raise store.StoreError("The file is empty.")
        name = store.save_attachment(q.get("tag"), q.get("name"), data)
        self.send_json({"name": name, "files": store.list_attachments(q.get("tag"))})

    def api_file_delete(self, b):
        store.delete_attachment(b.get("tag"), b.get("name"))
        self.send_json({"files": store.list_attachments(b.get("tag"))})

    def api_snapshot(self, b):
        """Save a web page as a PDF beside the citation: with the Mac's WebKit (rwpdf) when available,
        otherwise a text-only copy made with Pandoc."""
        tag, url = b.get("tag"), (b.get("url") or "").strip()
        if not re.match(r"https?://", url, re.I):
            raise store.StoreError("Give the citation a web address (http:// or https://) first.")
        d = store.files_dir(tag)
        d.mkdir(parents=True, exist_ok=True)
        name = "snapshot %s.pdf" % datetime.date.today().isoformat()
        target = store.attachment_path(tag, name)
        tool = pdf_tools().get("rwpdf")
        if tool:
            p = subprocess.run([tool, "snapshot", url, str(target)], capture_output=True, text=True, timeout=90)
            if p.returncode != 0:
                raise store.StoreError((p.stderr.strip() or "The snapshot failed.")[:300], 502)
            how = "webkit"
        else:
            text_snapshot(url, target)
            how = "text"
        self.send_json({"name": target.name, "how": how, "files": store.list_attachments(tag)})

    def api_annotations_export(self, b):
        tool = pdf_tools().get("rwpdf")
        if not tool:
            raise store.StoreError("Exporting an annotated PDF needs ReWord's PDF helper, which is part of the Mac app.", 501)
        tag, name = b.get("tag"), b.get("name")
        src = store.attachment_path(tag, name)
        ann = src.with_name(src.name + ".annotations.json")
        if not ann.exists():
            raise store.StoreError("This file has no highlights or comments yet.")
        out = src.with_name(src.stem + "-annotated.pdf")
        p = subprocess.run([tool, "annotate", str(src), str(ann), str(out)], capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise store.StoreError((p.stderr.strip() or "The export failed.")[:300], 500)
        self.send_json({"name": out.name, "files": store.list_attachments(tag)})

    def _library(self):
        return {c["tag"]: {"type": c["type"], "fields": c["fields"], "tag": c["tag"]} for c in store.citations()}

    def _note_ast(self, md, meta=None, fmt="practitioner"):
        """Markdown -> Pandoc JSON with live citations resolved (draft, brief/memo type)."""
        pandoc = builder.tool("pandoc")
        if not pandoc:
            raise store.StoreError("The page view needs Pandoc, which isn't available here.", 501)
        p = subprocess.run([pandoc, "-f", "markdown+smart", "-t", "json"], input=md, capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            raise store.StoreError("Couldn't read this note: " + p.stderr.strip()[:300], 422)
        doc = json.loads(p.stdout)
        for k, v in (meta or {}).items():
            if v:
                doc.setdefault("meta", {})[k] = {"t": "MetaInlines", "c": citeformat.to_pandoc(citeformat.md_runs(v))}
        if fmt in ("apa", "chicago", "chicago-ad"):
            style, typeface = fmt, "practitioner"
        else:
            style, typeface = "bluebook", fmt if fmt in ("lawreview", "practitioner") else "practitioner"
        doc, _ = cites.resolve(doc, self._library(), mode="draft", typeface=typeface, style=style, references=False)
        return pandoc, json.dumps(doc)

    def api_render(self, b):
        """Instant page view of a research note: Markdown -> HTML (with footnotes and live citations)."""
        pandoc, ast = self._note_ast(b.get("md") or "", fmt=b.get("format") or "practitioner")
        p = subprocess.run([pandoc, "-f", "json", "-t", "html5", "--wrap=none"], input=ast, capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            raise store.StoreError("Couldn't render this note.", 422)
        self.send_json({"html": p.stdout})

    def api_note_export(self, b):
        """Export a note to Word or PDF into build/_notes/; returns its /build/ path."""
        n = store.read_note(store.note_path(b.get("id")))
        fmt = b.get("format")
        if fmt not in ("docx", "pdf"):
            raise store.StoreError("Choose Word or PDF.")
        src = ""
        if n.get("citation"):
            c = next((x for x in store.citations() if x["tag"] == n["citation"]), None)
            if c:
                src = c["forms"]["bluebook_practitioner"]["md"]
        pandoc, ast = self._note_ast(n.get("body") or "", {"title": n["title"], "topic": n.get("topic", ""), "source": src})
        out = root() / "build" / "_notes"
        out.mkdir(parents=True, exist_ok=True)
        stem = out / n["id"]
        env = builder.tool_env(root())
        code = store.CODE
        if fmt == "docx":
            p = subprocess.run([pandoc, "-f", "json", "-s", "--reference-doc", str(code / "templates" / "memo" / "reference.docx"),
                                "-o", str(stem) + ".docx"], input=ast, capture_output=True, text=True, cwd=str(code), env=env, timeout=60)
            if p.returncode != 0:
                raise store.StoreError("Word export failed: " + p.stderr.strip()[:300], 500)
        else:
            if not builder.tool("tectonic"):
                raise store.StoreError("PDF export needs the app's PDF engine (or use Word).", 501)
            tex = str(stem) + ".tex"
            p = subprocess.run([pandoc, "-f", "json", "-s", "--template", str(code / "templates" / "_note" / "note.latex"), "-o", tex],
                               input=ast, capture_output=True, text=True, cwd=str(code), env=env, timeout=60)
            if p.returncode != 0:
                raise store.StoreError("PDF export failed: " + p.stderr.strip()[:300], 500)
            try:
                builder.compile_tex(tex, out, env, lambda line: None)
            except builder.BuildError as e:
                raise store.StoreError(str(e), 500)
        self.send_json({"path": "_notes/%s.%s" % (n["id"], fmt)})

    def api_cite_render(self, b):
        """Chip text for live citations: {format: lawreview|practitioner|apa|chicago|chicago-ad, items: [{tag, pin, signal, paren, narrative, note}]}."""
        fmt = b.get("format") or "practitioner"
        style, typeface = (fmt, "practitioner") if fmt in ("apa", "chicago", "chicago-ad") else ("bluebook", fmt)
        lib = {}
        for c in store.citations():
            lib[c["tag"]] = {"type": c["type"], "fields": c["fields"], "tag": c["tag"]}
        out = []
        for it in (b.get("items") or [])[:2000]:
            runs = cites.chip_text(lib.get(it.get("tag", "")), it, typeface, style, bool(it.get("note", True)))
            out.append({"html": citeformat.to_html(runs), "md": citeformat.to_md(runs), "missing": it.get("tag", "") not in lib})
        self.send_json({"items": out})

    def api_lookup(self, b):
        try:
            self.send_json(lookup.lookup(b.get("query", "")))
        except lookup.LookupError as e:
            raise store.StoreError(str(e), 422)

    def api_citation_delete(self, b):
        store.delete_citation(b.get("tag"))
        self.send_json({"ok": True})


# ---------------------------------------------------------------- main

def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--root", help="data folder: documents, research, library, outputs (default: the project folder)")
    ap.add_argument("--code", help="folder holding the program's templates, filters and scripts (default: the project folder)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--app-mode", action="store_true",
                    help="quit automatically when the app window closes (used by ReWord.app)")
    ap.add_argument("--url-file", help="write the server's address to this file once it is listening")
    ap.add_argument("--idle-timeout", type=int, help="seconds without a ping before quitting (app mode)")
    a = ap.parse_args()
    if a.root:
        store.set_root(a.root)
    if a.code:
        store.set_code(a.code)
    server = None
    for port in range(a.port, a.port + 10):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
            PORT = port
            break
        except OSError:
            continue
    if not server:
        raise SystemExit("Couldn't find a free port near %d." % a.port)
    url = "http://127.0.0.1:%d/" % PORT
    print("ReWord is running at " + url)
    print("Data folder: %s" % root())
    print("Leave this window open while you write. Press Ctrl-C (or close it) to stop.")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    url_file = Path(a.url_file) if a.url_file else None
    if url_file:
        url_file.parent.mkdir(parents=True, exist_ok=True)
        url_file.write_text(url, encoding="utf-8")
    if a.app_mode:
        LIFE.enabled = True
        if a.idle_timeout:
            LIFE.idle = a.idle_timeout

        def watch():
            while True:
                time.sleep(2)
                if LIFE.should_quit(time.time()):
                    print("The window is closed; shutting down.")
                    server.shutdown()
                    return
        threading.Thread(target=watch, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if url_file and url_file.exists():
            try:
                url_file.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
