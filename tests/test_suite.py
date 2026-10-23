"""Checks ReSuite hand-offs (app/suite.py): a document read as an outline for RePublish, hand-offs only
read from the suite's Handoffs folder, RePDF's highlights made into one research note, and the links
that open the other apps (or their download pages when they aren't installed).

Run:  python3 tests/test_suite.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import store  # noqa: E402
import suite  # noqa: E402

CASES = []


def check(label, ok, detail=''):
    CASES.append((label, bool(ok), detail))


tmp = Path(tempfile.mkdtemp())
support = tmp / 'ReSuite'
os.environ['RESUITE_SUPPORT_DIR'] = str(support)
ran = []
suite.RUN = lambda cmd: (ran.append(cmd), 1 if 'missing' in ' '.join(cmd) else 0)[1]
try:
    store.set_root(tmp / 'data')
    store.set_code(Path(__file__).resolve().parent.parent)

    # metadata.yaml: the few keys an outline needs
    m = suite.read_meta('# comment\ntitle: "Courts \\"Online\\""\nsubtitle: Three pilots  # note\nauthor:\n'
                        '  - name: Brianna Imm\n    note: "J.D."\n  - name: "Jane Doe"\nabstract: |\n  One line\n  and two.\n\n  New para.\n'
                        '# date: "never"\nlang: en-US\n')
    check('quoted title', m.get('title') == 'Courts "Online"', m.get('title'))
    check('comment after a value', m.get('subtitle') == 'Three pilots', m.get('subtitle'))
    check('author names', m.get('author') == ['Brianna Imm', 'Jane Doe'], m.get('author'))
    check('abstract folded', m.get('abstract') == 'One line and two.\n\nNew para.', repr(m.get('abstract')))
    check('commented keys skipped', 'date' not in m)
    check('memo sender', suite.read_meta('to: "A"\nfrom: "Brianna Imm"\n').get('from') == 'Brianna Imm')

    # a document as an outline
    store.write_citation('doe', {'type': 'case', 'fields': {'name': 'Doe v. Roe', 'volume': '1', 'reporter': 'F.4th', 'first_page': '2', 'date': '2024'}}, create=True)
    slug = store.create_document('article', 'Online Dispute Resolution')
    d = store.doc_path(slug)
    (d / 'metadata.yaml').write_text('title: "Online Dispute Resolution"\nauthor:\n  - name: Brianna Imm\nabstract: |\n'
                                     '  Rural litigants travel farther.\n', encoding='utf-8')
    (d / '01-introduction.md').write_text(
        '# Introduction {.unnumbered}\n\nThe average rural litigant drives seventy miles.[^a] See [Doe v. Roe]{.cite tag="doe"}.\n\n'
        '[^a]: A footnote that should not appear.\n    More of it.\n\nMissed hearings lead to *default* judgments.\n\n'
        'A third paragraph that is left out.\n', encoding='utf-8')
    (d / '02-background.md').write_text(
        '# Three pilots\n\n- Utah small claims\n- Michigan MI-Resolve\n\n## What worked\n\n<!-- a comment -->\n'
        '| a | b |\n|---|---|\n\n```\ncode\n```\n', encoding='utf-8')
    (d / '03-notes.md').write_text('Text before any heading.\n', encoding='utf-8')
    o = suite.outline(slug)
    check('kind and sender', o['kind'] == 'outline' and o['from'] == 'reword' and o['version'] == 1)
    check('title', o['title'] == 'Online Dispute Resolution')
    check('presenter from authors', o['details'].get('presenter') == 'Brianna Imm', o['details'])
    check('abstract', o['abstract'] == 'Rural litigants travel farther.', o['abstract'])
    heads = [s['heading'] for s in o['sections']]
    check('sections by heading', heads == ['Introduction', 'Three pilots', 'Notes'], heads)
    intro = o['sections'][0]
    check('first two paragraphs, plain', intro['text'] == 'The average rural litigant drives seventy miles. See Doe v. Roe. '
          'Missed hearings lead to default judgments.', intro['text'])
    check('footnotes left out', 'footnote' not in json.dumps(o))
    check('lists and subheadings become bullets', o['sections'][1]['bullets'] == ['Utah small claims', 'Michigan MI-Resolve', 'What worked'],
          o['sections'][1]['bullets'])
    check('tables, code and comments left out', 'code' not in json.dumps(o['sections']) and 'comment' not in json.dumps(o['sections']))
    check('references from citations', len(o['references']) == 1 and 'Doe v. Roe' in o['references'][0], o['references'])
    check('no suite project', 'suiteProject' not in o)

    # a references section wins over the cited sources
    (d / '04-references.md').write_text('# References\n\n- Jane Doe, Courts Online (2025).\n', encoding='utf-8')
    o = suite.outline(slug)
    check('references section', o['references'] == ['Jane Doe, Courts Online (2025).'] and 'References' not in [s['heading'] for s in o['sections']],
          o['references'])

    # a suite project that holds the document (or its ReWord project) goes with the outline
    (support / 'Projects').mkdir(parents=True)
    sid = '8E0D4C1A-0000-4000-8000-000000000001'
    (support / 'Projects' / (sid + '.json')).write_text(json.dumps({
        'formatVersion': 1, 'id': sid, 'name': 'ODR Talk', 'color': '#1F8FA6',
        'items': [{'id': 'x', 'kind': 'rewordDocument', 'app': 'reword', 'path': slug, 'title': 'ODR'}]}), encoding='utf-8')
    (support / 'Projects' / 'broken.json').write_text('{not json', encoding='utf-8')
    o = suite.outline(slug)
    check('suite project found', o.get('suiteProject') == sid)
    check('suite project summary', suite.suite_project_summary(suite.suite_project_for(slug)) == {'id': sid, 'name': 'ODR Talk', 'color': '#1F8FA6'})

    # sending it to RePublish: a hand-off file and a link
    ran.clear()
    r = suite.send_outline(slug, 'slides')
    files = list((support / 'Handoffs').glob('*.json'))
    check('hand-off written', len(files) == 1 and json.loads(files[0].read_text())['title'] == 'Online Dispute Resolution')
    check('link opened', ran and ran[-1][0] == 'open' and ran[-1][1].startswith('republish://handoff?file=') and 'make=slides' in ran[-1][1], ran)
    check('reported installed', r.get('installed') is True and r.get('sections') == 3, r)
    try:
        suite.send_outline(slug, 'novel')
        check('unknown make refused', False)
    except store.StoreError:
        check('unknown make refused', True)

    # not installed: the download page opens instead
    ran.clear()
    suite.APPS['republish']['scheme'] = 'missing'
    r = suite.open_link('republish', 'new')
    suite.APPS['republish']['scheme'] = 'republish'
    check('download page when missing', r['installed'] is False and ran[-1] == ['open', suite.APPS['republish']['get']], ran)
    ran.clear()
    suite.launch('hub')
    check('launch by bundle id', ran == [['open', '-b', 'com.briannarimm.ReSuite']], ran)
    check('link encoding', suite.link('republish', 'handoff', {'file': '/a b/c&d.json', 'make': 'poster'}) ==
          'republish://handoff?file=%2Fa%20b%2Fc%26d.json&make=poster')

    # hand-offs are read only from the Handoffs folder
    outside = tmp / 'evil.json'
    outside.write_text(json.dumps({'kind': 'highlights', 'highlights': [{'page': 1, 'text': 'x'}]}), encoding='utf-8')
    for label, path in (('outside the folder', str(outside)), ('dot-dot path', str(support / 'Handoffs' / '..' / '..' / 'evil.json')),
                        ('not json', str(support / 'Handoffs' / 'x.txt')), ('nothing', '')):
        try:
            suite.receive(path)
            check('refused: ' + label, False)
        except store.StoreError:
            check('refused: ' + label, True)
    link = support / 'Handoffs' / 'link.json'
    os.symlink(outside, link)
    try:
        suite.receive(str(link))
        check('refused: a link out of the folder', False)
    except store.StoreError:
        check('refused: a link out of the folder', True)
    link.unlink()

    # RePDF's highlights become one research note, quoted in page order, linked to the library's source
    store.write_citation('smith', {'type': 'case', 'fields': {'name': 'Smith v. Jones', 'volume': '1', 'reporter': 'F.3d', 'first_page': '2', 'date': '2000'}}, create=True)
    pdf = store.files_dir('smith') / 'Smith.pdf'
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b'%PDF-1.4\n')
    p = store.create_project({'name': 'ODR'})
    items = [{'id': 'y', 'kind': 'rewordProject', 'app': 'reword', 'path': p['id'], 'title': 'ODR'}]
    proj = json.loads((support / 'Projects' / (sid + '.json')).read_text())
    proj['items'] += items
    (support / 'Projects' / (sid + '.json')).write_text(json.dumps(proj), encoding='utf-8')
    h = {'version': 1, 'kind': 'highlights', 'from': 'repdf', 'title': 'Smith v. Jones', 'source': str(pdf), 'suiteProject': sid.lower(),
         'highlights': [{'page': 7, 'text': 'Second *passage*', 'note': 'Why it matters.'}, {'page': 2, 'text': 'First passage'},
                        {'page': 3, 'text': '', 'note': ''}, 'junk']}
    hf = suite.write_handoff(h)
    note = suite.receive_highlights(str(hf))
    check('note titled', note['title'] == 'Highlights: Smith v. Jones', note['title'])
    body = note['body']
    check('page order with pages', body.index('First passage (p. 2)') < body.index('(p. 7)'), body)
    check('markdown in quotes escaped', 'Second \\*passage\\*' in body, body)
    check('comments kept', 'Why it matters.' in body)
    check('empty highlights skipped', body.count('> ') == 2, body)
    check('linked to the source', note['citations'] == ['smith'], note['citations'])
    check('in the suite project\'s ReWord project', note['project'] == p['id'], note['project'])
    again = suite.receive_highlights(str(hf))
    check('opened twice, one note', again['id'] == note['id'] and len(store.notes()) == 1)
    try:
        suite.receive_highlights(str(suite.write_handoff({'kind': 'outline', 'title': 'x'})))
        check('outline refused by ReWord', False)
    except store.StoreError:
        check('outline refused by ReWord', True)
    try:
        suite.receive_highlights(str(suite.write_handoff({'kind': 'highlights', 'highlights': []})))
        check('no highlights refused', False)
    except store.StoreError:
        check('no highlights refused', True)
    other = suite.note_from_highlights({'kind': 'highlights', 'source': str(tmp / 'Elsewhere.pdf'), 'highlights': [{'page': 1, 'text': 'x'}]})
    check('a PDF outside the library: no source, named by its file', other['citations'] == [] and other['title'] == 'Highlights: Elsewhere')

    # old hand-offs are cleared away by the next sender
    old = support / 'Handoffs' / 'old.json'
    old.write_text('{}', encoding='utf-8')
    os.utime(old, (0, 0))
    suite.write_handoff({'kind': 'details'})
    check('old hand-offs pruned', not old.exists())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok = sum(1 for _, g, _ in CASES if g)
for label, good, detail in CASES:
    if not good:
        print('FAIL', label, detail)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
