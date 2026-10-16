"""Checks the 1.1.2 data repository (app/server.py): an old data folder's separate outputs/ repository
is folded into the work repository with both histories kept, a folder whose history doesn't share a
start with GitHub's still syncs without losing either side, and an interrupted rebase is undone
without losing edits. Uses local bare repositories as "GitHub"; nothing touches the network.

Run:  python3 tests/test_data_repo.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import server  # noqa: E402
import store  # noqa: E402

CASES = []


def check(label, ok, detail=''):
    CASES.append((label, bool(ok), detail))


def git(d, *a):
    return subprocess.run(['git', '-C', str(d)] + list(a), capture_output=True, text=True).stdout.strip()


def make_repo(d, files, msg):
    d.mkdir(parents=True, exist_ok=True)
    git(d, 'init', '-q', '-b', 'main')
    git(d, 'config', 'user.name', 'T'); git(d, 'config', 'user.email', 't@t')
    for name, text in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)
    git(d, 'add', '-A'); git(d, 'commit', '-q', '-m', msg)


tmp = Path(tempfile.mkdtemp())
store.set_code(Path(__file__).resolve().parent.parent)

# 1) an old data folder: work repo ignoring outputs/, outputs/ its own repo with two commits
data = tmp / 'data'
make_repo(data, {'.gitignore': server.WORK_GITIGNORE + 'outputs/\n', 'research/a.md': 'note\n'}, 'work 1')
make_repo(data / 'outputs', {'memo/memo.pdf': 'pdf1'}, 'out 1')
(data / 'outputs' / 'memo' / 'memo.pdf').write_text('pdf2')
git(data / 'outputs', 'commit', '-qam', 'out 2')
store.set_root(data)
check('old layout: outputs separate', not server.outputs_in_work())
check('combined', server.combine_outputs_repo(log=lambda *_: None))
check('outputs now in work', server.outputs_in_work() and Path(server.repo_path('outputs')).resolve() == data.resolve())
check('outputs files tracked', 'outputs/memo/memo.pdf' in git(data, 'ls-files'))
log = git(data, 'log', '--format=%s', '--all')
check('both histories kept', all(m in log for m in ('work 1', 'out 1', 'out 2')), log)
check('old repo kept', (data / '.git' / 'reword-outputs-repo' / 'HEAD').exists())
check('gitignore no longer ignores outputs', 'outputs/' not in (data / '.gitignore').read_text().splitlines())
check('clean after combining', git(data, 'status', '--porcelain') == '', git(data, 'status', '--porcelain'))
check('second run is a no-op', not server.combine_outputs_repo(log=lambda *_: None))

# 2) GitHub already has history; this folder was set up again from scratch with the same files plus one new
remote = tmp / 'remote.git'
subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(remote)])
git(data, 'remote', 'add', 'origin', str(remote))
git(data, 'push', '-q', '-u', 'origin', 'main')
fresh = tmp / 'fresh'
make_repo(fresh, {'research/a.md': 'note\n', 'research/new.md': 'only here\n'}, 'fresh start')
git(fresh, 'remote', 'add', 'origin', str(remote))
store.set_root(fresh)
r = server.sync_work('test')
check('unrelated histories sync', r.get('ok'), r.get('message'))
remote_log = git(remote, 'log', '--format=%s', 'main')
check('GitHub keeps its history', 'out 2' in remote_log and 'fresh start' in remote_log, remote_log)
files = git(remote, 'ls-tree', '-r', '--name-only', 'main')
check('nothing dropped', 'research/new.md' in files and 'outputs/memo/memo.pdf' in files, files)

# 3) an interrupted rebase with an edit typed afterwards
store.set_root(data)
git(data, 'pull', '-q', '--no-rebase', 'origin', 'main')
(data / 'research' / 'a.md').write_text('local change\n'); git(data, 'commit', '-qam', 'local')
git(data, 'checkout', '-q', '-b', 'other', 'HEAD~1')
(data / 'research' / 'b.md').write_text('b\n'); git(data, 'add', '-A'); git(data, 'commit', '-qm', 'other')
git(data, 'checkout', '-q', 'main')
(data / '.git' / 'rebase-merge').mkdir()   # simulate: a rebase that never finished
(data / '.git' / 'rebase-merge' / 'head-name').write_text('refs/heads/main\n')
(data / '.git' / 'rebase-merge' / 'orig-head').write_text(git(data, 'rev-parse', 'HEAD') + '\n')
(data / '.git' / 'rebase-merge' / 'onto').write_text(git(data, 'rev-parse', 'HEAD') + '\n')
(data / '.git' / 'rebase-merge' / 'interactive').write_text('')
(data / '.git' / 'rebase-merge' / 'git-rebase-todo').write_text('')
(data / '.git' / 'rebase-merge' / 'done').write_text('')
(data / 'research' / 'typed.md').write_text('typed after the crash\n')
msg = server.finish_interrupted_git(data)
check('interrupted rebase cleared', msg is None and not (data / '.git' / 'rebase-merge').exists(), msg)
check('edit kept', (data / 'research' / 'typed.md').exists())
r = server.sync_work('test')
check('sync works afterwards', r.get('ok'), r.get('message'))

for label, ok, detail in CASES:
    print(('ok   ' if ok else 'FAIL ') + label + ('' if ok else '  ' + str(detail)))
print('%d/%d passed' % (sum(ok for _, ok, _ in CASES), len(CASES)))
sys.exit(0 if all(ok for _, ok, _ in CASES) else 1)
