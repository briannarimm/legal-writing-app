"""Checks projects (app/store.py): membership, add-only automatic assignment of cited sources, moving,
notes, deleting a project, and that automatic assignment keeps a citation's timestamp.

Run:  python3 tests/test_projects.py
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
    case = {'type': 'case', 'fields': {'name': 'Smith v. Jones', 'volume': '1', 'reporter': 'F.3d', 'first_page': '2', 'date': '2000'}}
    for t in ('smith', 'doe', 'roe', 'linked'):
        store.write_citation(t, case, create=True)

    a = store.create_project({'name': 'Law Review Article', 'citation_style': 'bluebook-lawreview', 'default_template': 'article'})
    b = store.create_project({'name': 'Sleep Paper', 'citation_style': 'apa'})
    check('project ids from names', a['id'] == 'law-review-article' and b['id'] == 'sleep-paper', a['id'] + ' ' + b['id'])
    check('color assigned', a['color'].startswith('#') and len(a['color']) == 7)
    check('listed', [p['id'] for p in store.projects_list()] == ['law-review-article', 'sleep-paper'])

    # a document in a project: saving text that cites a source adds the source to the project
    slug = store.create_document('memo', 'Memo A', a['id'])
    check('document records its project', store.read_doc_info(store.doc_path(slug)).get('project') == a['id'])
    before = store.read_citation(store.cite_path('smith'))['mtime']
    added = store.assign_citations(store.cited_tags('See [x]{.cite tag="smith" pin="3"}.'), a['id'])
    after = store.read_citation(store.cite_path('smith'))
    check('cited source joins the project', after['projects'] == [a['id']] and after['projects_auto'] == [a['id']], str(after['projects']))
    check('assignment keeps the timestamp', after['mtime'] == before)
    check('assign returns what changed', added == ['smith'])
    check('assigning again is a no-op', store.assign_citations({'smith'}, a['id']) == [])

    # old table-of-authorities marks count too
    check('cited_tags finds .auth and .cite', store.cited_tags('[A]{.auth tag="doe"} and [B]{.cite tag="roe" form="entry"}') == {'doe', 'roe'})

    # moving the document to another project brings its sources (and keeps the old project: add-only)
    sec = sorted(store.section_paths(slug))[0]
    sec.write_text(sec.read_text() + '\nSee [x]{.cite tag="smith"} and [y]{.cite tag="doe"}.\n')
    store.set_doc_option(slug, 'project', b['id'])
    s2 = store.read_citation(store.cite_path('smith'))
    d2 = store.read_citation(store.cite_path('doe'))
    check('moved doc: sources join the new project', b['id'] in s2['projects'] and b['id'] in d2['projects'])
    check('moved doc: old project kept (add-only)', a['id'] in s2['projects'])
    check('moving to no project', store.set_doc_option(slug, 'project', '').get('project') is None)

    # notes: body cites and the linked source join the note's project
    n = store.create_note('A note', citation='linked', body='Per [x]{.cite tag="roe"}.', project=b['id'])
    check('note records its project', n['project'] == b['id'])
    check('note: cited source joins', b['id'] in store.read_citation(store.cite_path('roe'))['projects'])
    check('note: linked source joins', b['id'] in store.read_citation(store.cite_path('linked'))['projects'])
    m = store.assign_note(n['id'], a['id'])
    check('note moved', m['project'] == a['id'] and a['id'] in store.read_citation(store.cite_path('roe'))['projects'])
    w = store.write_note(n['id'], {'title': 'A note', 'body': 'Nothing cited now.'})
    check('note save keeps its project', w['project'] == a['id'])
    check('add-only: uncited source keeps the project', a['id'] in store.read_citation(store.cite_path('roe'))['projects'])

    # the citation form can set projects by hand (and saving the form without them keeps them)
    c = store.write_citation('roe', dict(case, projects=[b['id']]))
    check('set by hand', c['projects'] == [b['id']])
    c = store.write_citation('roe', case)
    check('form save without projects keeps them', c['projects'] == [b['id']])

    # bibliography in a project gets its citation style
    bib = store.create_document('bibliography', 'Bib', b['id'])
    meta = (store.doc_path(bib) / 'metadata.yaml').read_text()
    check('bibliography takes the project citation style', 'citation-style: apa' in meta)
    bib2 = store.create_document('bibliography', 'Bib2', a['id'])
    check('law review style', 'citation-style: bluebook-lawreview' in (store.doc_path(bib2) / 'metadata.yaml').read_text())

    # deleting a project: items stay, without it
    store.delete_project(b['id'])
    check('project gone', [p['id'] for p in store.projects_list()] == ['law-review-article'])
    check('trashed, not deleted', any((tmp / 'projects' / '_trash').iterdir()))
    check('documents lose it', store.read_doc_info(store.doc_path(bib)).get('project') is None)
    check('citations lose it', b['id'] not in store.read_citation(store.cite_path('smith'))['projects'])
    check('citation keeps other projects', a['id'] in store.read_citation(store.cite_path('smith'))['projects'])
    check('documents still there', (store.doc_path(bib) / 'document.json').exists())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok = sum(1 for _, g, _ in CASES if g)
for label, good, detail in CASES:
    if not good:
        print('FAIL', label, detail)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
