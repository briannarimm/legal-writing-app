"""Checks research notes linked to several sources (1.3.2): older single-source notes read as a list of one
and keep their source when saved, links are many-to-many, and the project bibliography export.

Run:  python3 tests/test_note_links.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import store  # noqa: E402

CASES = []


def check(label, ok, detail=''):
    CASES.append((label, bool(ok), detail))


tmp = Path(tempfile.mkdtemp())
try:
    store.set_root(tmp)
    store.set_code(Path(__file__).resolve().parent.parent)
    store.write_citation('smith', {'type': 'case', 'fields': {'name': 'Smith v. Jones', 'volume': '1', 'reporter': 'F.3d', 'first_page': '2',
                                                              'court': '9th Cir.', 'date': '2000', 'url': 'https://example.org/smith'}}, create=True)
    store.write_citation('walker', {'type': 'journal', 'fields': {'authors': [{'given': 'Matthew', 'family': 'Walker'}], 'title': 'Why We Sleep',
                                                                 'journal': 'Sleep J.', 'volume': '4', 'first_page': '10', 'date': '2017',
                                                                 'doi': 'https://doi.org/10.1000/xyz'}}, create=True)
    store.write_citation('roe', {'type': 'case', 'fields': {'name': 'Roe v. Doe', 'volume': '3', 'reporter': 'U.S.', 'first_page': '4', 'date': '1990'}}, create=True)
    proj = store.create_project({'name': 'Sleep Paper', 'citation_style': 'apa'})

    # a note from before 1.3.2: one source under "citation"
    store.notes_dir().mkdir(parents=True, exist_ok=True)
    old = store.notes_dir() / 'old-note.md'
    old.write_text('---\ntitle: "Old note"\ntopic: "Standing"\ncitation: "smith"\ncreated: "2026-01-01"\nupdated: "2026-01-01"\n---\nBody text.\n')
    n = store.read_note(old)
    check('old note reads as a list of one', n['citations'] == ['smith'] and n['citation'] == 'smith', str(n['citations']))
    check('list entry has the links too', next(x for x in store.notes() if x['id'] == 'old-note')['citations'] == ['smith'])

    # saving it from an older page (no "citations") keeps its source; saving the title alone keeps it too
    store.write_note('old-note', {'title': 'Old note', 'body': 'Body text.'})
    check('save without links keeps the source', store.read_note(old)['citations'] == ['smith'])
    store.write_note('old-note', {'citation': 'roe'})
    check('older page changing its one source', store.read_note(old)['citations'] == ['roe'])
    store.write_note('old-note', {'citations': ['smith', 'walker', 'smith', '']})
    r = store.read_note(old)
    check('several sources, no duplicates or blanks', r['citations'] == ['smith', 'walker'], str(r['citations']))
    meta, _ = store.parse_front(old.read_text())
    check('file keeps the first under the old key', meta.get('citation') == 'smith' and meta.get('citations') == ['smith', 'walker'], str(meta))
    check('body and topic untouched', r['body'] == 'Body text.\n' and r['topic'] == 'Standing')

    # many-to-many: another note links walker too; both list it
    m = store.create_note('Sleep note', citations=['walker', 'roe'], project=proj['id'])
    check('new note with several sources', m['citations'] == ['walker', 'roe'])
    check('a source in two notes', sorted(x['id'] for x in store.notes() if 'walker' in x['citations']) == ['old-note', 'sleep-note'])
    check('linked sources join the note project', all(proj['id'] in store.read_citation(store.cite_path(t))['projects'] for t in ('walker', 'roe')))
    check('older create (one tag) still works', store.create_note('One', citation='smith')['citations'] == ['smith'])
    store.write_note('sleep-note', {'citations': []})
    check('unlink all', store.read_note(store.note_path('sleep-note'))['citations'] == [] and store.read_note(store.note_path('sleep-note'))['citation'] == '')
    store.assign_note('old-note', proj['id'])
    check('moving a note brings all its sources', proj['id'] in store.read_citation(store.cite_path('smith'))['projects'])

    # a deleted source stays linked (shown as missing), nothing is lost
    store.delete_citation('roe')
    store.write_note('old-note', {'citations': ['smith', 'roe']})
    check('missing source kept', store.read_note(old)['citations'] == ['smith', 'roe'])

    # bibliography export
    name, text, count = store.bibliography(proj['id'])
    check('bibliography file name', name == 'sleep-paper-bibliography.md', name)
    check('bibliography counts the project sources', count == 2, str(count))
    check('bibliography has the tags', '`walker`' in text and '`smith`' in text)
    check('bibliography DOI cleaned and linked', 'https://doi.org/10.1000/xyz' in text and '(https://doi.org/https' not in text, text)
    check('bibliography has links and where to look', '<https://example.org/smith>' in text and 'Where to look:' in text)
    check('bibliography says when no copy is on file', 'Copy on file:** no' in text)
    check('bibliography in the project style (APA)', 'Walker, M. (2017)' in text, text)
    check('grouped by type', text.index('## Case') < text.index('## Journal'))
    store.save_attachment('smith', 'smith.pdf', b'%PDF-1.4\n')
    name, text, count = store.bibliography('')
    check('library export', name == 'reword-library-bibliography.md' and count == 2 and 'Copy on file:** yes (smith.pdf)' in text, text)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

bad = [c for c in CASES if not c[1]]
for label, ok, detail in CASES:
    print(('ok   ' if ok else 'FAIL ') + label + ('' if ok else '  ' + detail[:600]))
print('%d/%d passed' % (len(CASES) - len(bad), len(CASES)))
sys.exit(1 if bad else 0)
