"""Checks "Cited in" (store.citation_uses): every place a document's sections and research notes cite a source, in
reading order, with the section, the footnote number across sections, which match it is (so the editor can find the
chip again), where it sits in the file (for the Markdown editor), the words around it, and the counts per source.

Run:  python3 tests/test_uses.py
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
    case = {'type': 'case', 'fields': {'name': 'Smith v. Jones', 'volume': '1', 'reporter': 'F.3d', 'first_page': '2', 'date': '2000', 'court': '8th Cir.'}}
    book = {'type': 'book', 'fields': {'authors': [{'given': 'Valerie', 'family': 'Curtis'}], 'title': "Don't Look, Don't Touch",
                                        'publisher': 'Univ. of Chicago Press', 'date': '2013'}}
    store.write_citation('smith', case, create=True)
    store.write_citation('curtis-2013', book, create=True)

    # a law review article: citations in footnotes, numbered across sections
    art = store.create_document('article', 'Uses Article')
    d = store.doc_path(art)
    for f in store.section_paths(art):
        f.unlink()
    (d / '01-intro.md').write_text('# Introduction\n\nFirst point.[^a] Second point.[^b]\n\n'
                                   '[^a]: *See* [Smith v. Jones, 1 F.3d 2]{.cite tag="smith" pin="4"}.\n\n'
                                   '[^b]: Plain note.\n', encoding='utf-8')
    (d / '02-argument.md').write_text('# Argument\n\nThe court in [*Smith*]{.cite tag="smith"} held, as **plainly** stated, '
                                      'that disgust matters.[^c]\n\n'
                                      '[^c]: [Smith]{.cite tag="smith" pin="7" signal="See also"}; '
                                      '[[Curtis]{.smallcaps}, Don\'t Look]{.cite tag="curtis-2013"}.\n', encoding='utf-8')
    # an APA paper citing the book in the text, twice, plus an old table-of-authorities mark
    apa = store.create_document('journal-apa', 'Uses APA')
    a = store.doc_path(apa)
    for f in store.section_paths(apa):
        f.unlink()
    (a / '01-intro.md').write_text('# Introduction\n\nDisgust protects us [(Curtis, 2013)]{.cite tag="curtis-2013"}.\n'
                                   'It also misleads us [curtis-2013]{.cite tag="curtis-2013" pin="p. 12"}.\n\n'
                                   'A brief cited [Smith v. Jones]{.auth tag="smith"} once.\n', encoding='utf-8')
    # a research note
    store.create_note('Disgust notes', body='Curtis argues [(Curtis, 2013)]{.cite tag="curtis-2013"} that it evolved.\n')

    r = store.citation_uses('smith')
    docs = {x['slug']: x for x in r['documents']}
    check('finds both documents', set(docs) == {art, apa}, str(list(docs)))
    check('total counts every place', r['total'] == 4, str(r['total']))
    u = docs[art]['uses']
    check('reading order', [x['file'] for x in u] == ['01-intro.md', '02-argument.md', '02-argument.md'], str([x['file'] for x in u]))
    check('footnote 1', u[0]['where'] == 'footnote' and u[0]['label'] == 'a' and u[0]['number'] == 1, str(u[0]))
    check('text citation', u[1]['where'] == 'text' and u[1]['k'] == 0 and 'number' not in u[1], str(u[1]))
    check('footnotes number across sections', u[2]['number'] == 3 and u[2]['label'] == 'c', str(u[2]))
    check('section titles', u[0]['section'] == 'Introduction' and u[1]['section'] == 'Argument')
    check('words before', u[1]['before'].endswith('The court in'), u[1]['before'])
    check('words after, as plain text', u[1]['after'].startswith('held, as plainly stated'), u[1]['after'])
    check('chip text from the library', 'Smith v. Jones' in u[1]['text'], u[1]['text'])
    check('pin and signal in the chip text', 'See also' in u[2]['text'] and '7' in u[2]['text'], u[2]['text'])
    md = (d / '02-argument.md').read_text(encoding='utf-8')
    check('start and end mark the span', md[u[1]['start']:u[1]['end']] == '[*Smith*]{.cite tag="smith"}', md[u[1]['start']:u[1]['end']])
    au = docs[apa]['uses']
    check('table-of-authorities marks count', len(au) == 1 and au[0]['kind'] == 'auth', str(au))

    r = store.citation_uses('curtis-2013')
    docs = {x['slug']: x for x in r['documents']}
    cu = docs[apa]['uses']
    check('k counts matches in the same text', [x['k'] for x in cu] == [0, 1], str([x['k'] for x in cu]))
    check('APA chip text', cu[1]['text'].startswith('(Curtis, 2013'), cu[1]['text'])
    check('nested brackets in a footnote', docs[art]['uses'][0]['where'] == 'footnote' and docs[art]['uses'][0]['k'] == 0, str(docs[art]['uses']))
    check('k is per footnote', docs[art]['uses'][0]['label'] == 'c')
    check('research notes', len(r['notes']) == 1 and r['notes'][0]['title'] == 'Disgust notes' and r['notes'][0]['uses'][0]['where'] == 'text')
    check('total with notes', r['total'] == 4, str(r['total']))

    counts = store.citation_uses()['counts']
    check('counts per source', counts == {'smith': 4, 'curtis-2013': 4}, str(counts))
    check('nothing for an uncited source', store.citation_uses('nobody')['total'] == 0)
    try:
        store.citation_uses('../etc')
        check('rejects a bad tag', False)
    except store.StoreError:
        check('rejects a bad tag', True)

    # trashed documents don't count
    store.delete_document(apa)
    check('trash is left out', store.citation_uses()['counts'].get('smith') == 3, str(store.citation_uses()['counts']))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok = sum(1 for _, g, _ in CASES if g)
for label, good, detail in CASES:
    if not good:
        print('FAIL', label, detail)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
