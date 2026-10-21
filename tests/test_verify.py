"""Checks verification (the Verify tab, store.verification): every citation in a project's documents in reading order,
with what it supports, its pinpoint, and results that persist per project; an approval stops counting when the citation
or the words before it change, while a citation sent back stays sent back (marked as edited since).

Run:  python3 tests/test_verify.py
"""
import json
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
    case = {'type': 'case', 'fields': {'name': 'Smith v. Jones', 'volume': '1', 'reporter': 'F.3d', 'first_page': '2', 'date': '2000', 'court': '8th Cir.'}}
    store.write_citation('smith', case, create=True)
    p = store.create_project({'name': 'Article'})['id']
    other = store.create_project({'name': 'Other'})['id']

    art = store.create_document('article', 'Verify Article', p)
    d = store.doc_path(art)
    for f in store.section_paths(art):
        f.unlink()
    (d / '01-intro.md').write_text('# Introduction\n\nCourts protect privacy.[^a] They say so often.\n\n'
                                   '[^a]: *See* [Smith]{.cite tag="smith" pin="4"}; [Gone]{.cite tag="gone"}.\n', encoding='utf-8')
    (d / '02-argument.md').write_text('# Argument\n\nThe court in [*Smith*]{.cite tag="smith"} held so.[^b]\n\n'
                                      '[^b]: [Smith]{.cite tag="smith" pin="4" paren="holding *so*"}.\n', encoding='utf-8')
    elsewhere = store.create_document('article', 'Other Article', other)
    (store.doc_path(elsewhere) / '01-x.md').write_text('# X\n\n[Smith]{.cite tag="smith"}\n', encoding='utf-8')

    r = store.verification(p)
    items = r['items']
    check('only the project\'s documents', [x['slug'] for x in r['documents']] == [art], str(r['documents']))
    check('every citation, in reading order', [(x['file'], x['tag']) for x in items] ==
          [('01-intro.md', 'smith'), ('01-intro.md', 'gone'), ('02-argument.md', 'smith'), ('02-argument.md', 'smith')], str([(x['file'], x['tag']) for x in items]))
    a, gone, txt, b = items
    check('footnote numbers', a['number'] == 1 and b['number'] == 2 and txt['where'] == 'text', str((a.get('number'), b.get('number'))))
    check('what a footnote supports', a['supports'][0] == 'Courts protect privacy.' and a['supports'][1].startswith('They say'), str(a.get('supports')))
    check('pinpoint and parenthetical', a['pin'] == '4' and b['paren'] == 'holding so', str((a['pin'], b['paren'])))
    check('whole footnote around the cite', a['before'] == 'See' and a['after'].startswith('; Gone'), str((a['before'], a['after'])))
    check('missing source flagged', gone['missing'] and not a['missing'])
    check('keys count repeats of the same pinpoint', a['key'] == art + ':smith:4:0' and b['key'] == art + ':smith:4:1' and txt['key'] == art + ':smith::0',
          str([x['key'] for x in items]))
    check('k per footnote for going there', a['k'] == 0 and txt['k'] == 0 and b['k'] == 0)
    check('nothing checked yet', not any(x.get('status') for x in items))

    store.set_verification(p, a['key'], 'approved', sig=a['sig'], tag='smith', doc=art)
    store.set_verification(p, txt['key'], 'failed', 'Pin cite is to the dissent', sig=txt['sig'], tag='smith', doc=art)
    saved = json.loads(store.verification_path(p).read_text(encoding='utf-8'))
    check('saved per project', set(saved['results']) == {a['key'], txt['key']} and not store.verification_path(other).exists())
    items = store.verification(p)['items']
    check('results come back', items[0]['status'] == 'approved' and items[2]['status'] == 'failed' and items[2]['reason'] == 'Pin cite is to the dissent')
    check('not edited yet', items[0]['edited'] is False and items[2]['edited'] is False)

    # edit both: the approval no longer counts; the sent-back one stays sent back, marked edited
    (d / '01-intro.md').write_text('# Introduction\n\nCourts protect privacy.[^a] They say so often.\n\n'
                                   '[^a]: *But see* [Smith]{.cite tag="smith" pin="4"}; [Gone]{.cite tag="gone"}.\n', encoding='utf-8')
    (d / '02-argument.md').write_text('# Argument\n\nThe majority in [*Smith*]{.cite tag="smith"} held so.[^b]\n\n'
                                      '[^b]: [Smith]{.cite tag="smith" pin="4" paren="holding *so*"}.\n', encoding='utf-8')
    items = store.verification(p)['items']
    check('approval reset after an edit', not items[0].get('status') and items[0].get('was') == 'approved', str(items[0]))
    check('sent back stays, marked edited', items[2]['status'] == 'failed' and items[2]['edited'] is True, str(items[2]))

    store.set_verification(p, items[2]['key'], '')
    check('clearing a result', not store.verification(p)['items'][2].get('status'))
    try:
        store.set_verification(p, a['key'], 'maybe')
        check('rejects an unknown result', False)
    except store.StoreError:
        check('rejects an unknown result', True)
    try:
        store.verification('../x')
        check('rejects a bad project', False)
    except store.StoreError:
        check('rejects a bad project', True)

    store.set_verification(p, a['key'], 'approved', sig='x')
    store.reset_verification(p)
    check('start over', store.verification_path(p).exists() and json.loads(store.verification_path(p).read_text())['results'] == {})
    check('projects list ignores the verification folder', sorted(x['id'] for x in store.projects_list()) == sorted([p, other]))
    store.delete_project(p)
    check('deleting the project trashes its results', not (tmp / 'projects' / 'verification' / (p + '.json')).exists())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok = sum(1 for _, g, _ in CASES if g)
for label, good, detail in CASES:
    if not good:
        print('FAIL', label, detail)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
