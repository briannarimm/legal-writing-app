"""Checks that saving never quietly loses work (app/store.py): fields a citation's form doesn't show survive a save,
things thrown away in the same second are all kept in _trash, and Verify results written at the same time all land.

Run:  python3 tests/test_library.py
"""
import json
import shutil
import sys
import tempfile
import threading
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

    # a source written by another tool, with fields the book form has no box for
    p = store.cite_path('durkheim-1915')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(store.dump_front({'type': 'book', 'fields': {
        'authors': [{'given': 'Émile', 'family': 'Durkheim'}], 'title': 'The Elementary Forms of the Religious Life',
        'translators': [{'given': 'Joseph Ward', 'family': 'Swain'}], 'original_date': '1912', 'date': '1915',
        '_override_short': 'Durkheim, *Elementary Forms*'}}, 'x'), encoding='utf-8')
    before = store.read_citation(p)
    check('the translator from a list of people shows in the citation', 'Swain trans.' in before['forms']['bluebook_practitioner']['text'],
          before['forms']['bluebook_practitioner']['text'])
    # the form sends back only the fields it shows (and no override: the box was emptied)
    store.write_citation('durkheim-1915', {'type': 'book', 'fields': {
        'authors': [{'given': 'Émile', 'family': 'Durkheim'}], 'title': 'The Elementary Forms of the Religious Life', 'date': '1915',
        'publisher': 'George Allen & Unwin'}}, force=True)
    meta, _ = store.parse_front(p.read_text(encoding='utf-8'))
    f = meta['fields']
    check('a save keeps fields the form doesn’t show', f.get('translators') and f.get('original_date') == '1912', json.dumps(f))
    check('a save keeps what the form changed', f.get('publisher') == 'George Allen & Unwin', json.dumps(f))
    check('an override emptied in the form stays empty', '_override_short' not in f, json.dumps(f))

    # throwing away two things with the same name in the same second
    d = tmp / 'research'
    d.mkdir(parents=True, exist_ok=True)
    for text in ('first', 'second'):
        (d / 'same.md').write_text(text, encoding='utf-8')
        store.trash(d / 'same.md', d)
    kept = sorted(x.read_text(encoding='utf-8') for x in (d / '_trash').iterdir())
    check('both copies are in _trash', kept == ['first', 'second'], str(kept))

    # Verify: results recorded at the same moment (one card after another, fast) all land
    store.create_project({'name': 'Race'})
    pid = store.projects_list()[0]['id']
    keys = ['doc:tag-%d::0' % k for k in range(40)]
    threads = [threading.Thread(target=store.set_verification, args=(pid, k, 'approved', '', 's', 't', 'doc')) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    got = store._read_verification(pid)['results']
    check('no result is lost when several are saved at once', all(k in got for k in keys), '%d of %d' % (sum(k in got for k in keys), len(keys)))

    # a footnote with two citations whose saved text is only their tag (another tool wrote them): around one card,
    # the other reads as a citation, not as "doe-2020"
    store.write_citation('smith', {'type': 'case', 'fields': {'name': 'Smith v. Jones', 'volume': '1', 'reporter': 'F.3d',
                                                               'first_page': '2', 'date': '2000'}}, create=True)
    store.write_citation('doe-2020', {'type': 'journal', 'fields': {'authors': [{'given': 'Jane', 'family': 'Doe'}], 'title': 'Privacy',
                                                                   'journal': 'Yale Law Journal', 'volume': '9', 'first_page': '1', 'date': '2020'}},
                         create=True)
    slug = store.create_document('article', 'Two Cites', pid)
    (store.doc_path(slug) / '01-intro.md').write_text(
        '# Intro\n\nCourts agree.[^a]\n\n[^a]: [smith]{.cite tag="smith"}; [doe-2020]{.cite tag="doe-2020" signal="see"}.\n', encoding='utf-8')
    items = [x for x in store.verification(pid)['items'] if x['slug'] == slug]
    check('a neighbouring citation reads as a citation in Verify', items and 'Smith v. Jones' in items[1]['before'] and 'smith' not in items[1]['before'],
          str([x['before'] for x in items]))
    uses = store.citation_uses('doe-2020')['documents'][0]['uses'][0]
    check('… and in Cited in', 'Smith v. Jones' in uses['before'], uses['before'])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok = sum(1 for _, good, _ in CASES if good)
for label, good, detail in CASES:
    print(('ok   ' if good else 'FAIL ') + label + ('' if good else '\n     ' + detail))
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
