"""Checks edited books ("Chapter(s) in edited book"): one citation holding many chapters, each cited as
tag + chapter; formatting of a chapter and of the whole book; Id. and short forms per chapter; Cited in and
Verify keys per chapter; a source's files with labels and chapters; and the consolidation script that gathers
single-chapter citations into their books.

Run:  python3 tests/test_edited_book.py      (the build checks need pandoc on the PATH)
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'scripts'))
import citeformat as cf  # noqa: E402
import cites  # noqa: E402
import store  # noqa: E402

CASES = []


def check(label, ok, detail=''):
    CASES.append((label, bool(ok), detail))


P = lambda given, family: {'given': given, 'family': family}      # noqa: E731
BOOK = {'type': 'edited_book', 'fields': {
    'editors': [P('Michael', 'Banton')], 'title': 'Anthropological Approaches to the Study of Religion',
    'title_apa': 'Anthropological approaches to the study of religion', 'publisher': 'Tavistock', 'date': '1966',
    'chapters': [
        {'id': 'spiro', 'authors': [P('Melford E.', 'Spiro')], 'title': 'Religion: Problems of Definition and Explanation',
         'title_apa': 'Religion: Problems of definition and explanation', 'first_page': '85', 'last_page': '126'},
        {'id': 'geertz', 'authors': [P('Clifford', 'Geertz')], 'title': 'Religion as a Cultural System',
         'title_apa': 'Religion as a cultural system', 'first_page': '1', 'last_page': '46'}]}}
OLD_SPIRO = {'type': 'chapter', 'fields': {
    'authors': [P('Melford E.', 'Spiro')], 'title': 'Religion: Problems of Definition and Explanation',
    'title_apa': 'Religion: Problems of definition and explanation', 'editors': [P('Michael', 'Banton')],
    'book_title': 'Anthropological Approaches to the Study of Religion', 'book_title_apa': 'Anthropological approaches to the study of religion',
    'publisher': 'Tavistock', 'date': '1966', 'first_page': '85', 'last_page': '126'}}

# ---------------- formatting
b = dict(BOOK, tag='banton')
spiro = cf.edited_chapter(b, 'spiro')
for k in ('bluebook_lawreview', 'bluebook_practitioner', 'short_lawreview', 'apa_reference', 'apa_intext', 'chicago_note', 'chicago_bib',
          'chicago_ad_reference'):
    a, o = cf.describe(spiro)[k]['text'], cf.describe(OLD_SPIRO)[k]['text']
    check('a chapter formats like a single chapter citation: ' + k, a == o, '%r vs %r' % (a, o))
check('the whole book is a book with its editor', cf.bluebook(b, 'practitioner').plain() ==
      'Anthropological Approaches to the Study of Religion (Michael Banton ed., 1966)', cf.bluebook(b, 'practitioner').plain())
check('an unknown chapter is None', cf.edited_chapter(b, 'nope') is None)
check('chapter label', cf.chapter_label(BOOK['fields']['chapters'][0]) == 'Spiro, Religion: Problems of Definition and Explanation (pp. 85–126)',
      cf.chapter_label(BOOK['fields']['chapters'][0]))
check('chapter label with its chosen number', cf.chapter_label(dict(BOOK['fields']['chapters'][0], number='7')).startswith('Chapter 7: Spiro, Religion'),
      cf.chapter_label(dict(BOOK['fields']['chapters'][0], number='7')))
check('the number is not a field of the chapter citation',
      'number' not in cf.edited_chapter({'type': 'edited_book', 'fields': dict(BOOK['fields'], chapters=[dict(BOOK['fields']['chapters'][0], number='7')])},
                                        BOOK['fields']['chapters'][0]['id'])['fields'])
check('warnings name the chapter', cf.warnings({'type': 'edited_book', 'fields': dict(BOOK['fields'], chapters=[{'id': 'x', 'first_page': '3'}])})
      == ['chapter 1: chapter title'], str(cf.warnings({'type': 'edited_book', 'fields': dict(BOOK['fields'], chapters=[{'id': 'x', 'first_page': '3'}])})))

# ---------------- the library and the build
lib = cites.library_from([dict(BOOK, tag='banton')])
check('library keys', sorted(lib) == ['banton', 'banton#geertz', 'banton#spiro'], str(sorted(lib)))
check('key_of', cites.key_of({'tag': 'banton', 'chapter': 'spiro'}) == 'banton#spiro' and cites.key_of({'tag': 'x'}) == 'x')
withold = dict(BOOK, tag='banton', fields=dict(BOOK['fields'], chapters=[dict(BOOK['fields']['chapters'][0], former_tag='spiro-1966')]))
check('a gathered chapter still answers to its old tag', cites.library_from([withold]).get('spiro-1966', {}).get('type') == 'chapter')

PANDOC = shutil.which('pandoc')
if PANDOC:
    def run(md, mode='final'):
        j = subprocess.run([PANDOC, '-f', 'markdown+smart', '-t', 'json'], input=md, capture_output=True, text=True, check=True).stdout
        doc, report = cites.resolve(json.loads(j), lib, mode=mode, typeface='lawreview', style='bluebook')
        return subprocess.run([PANDOC, '-f', 'json', '-t', 'plain', '--wrap=none'], input=json.dumps(doc), capture_output=True, text=True,
                              check=True).stdout, report
    out, rep = run('A.[^1] B.[^2] C.[^3]\n\n[^1]: [x]{.cite tag="banton" chapter="spiro" pin="90"}.\n\n'
                   '[^2]: [x]{.cite tag="banton" chapter="geertz" pin="5"}.\n\n[^3]: [x]{.cite tag="banton" chapter="geertz" pin="6"}.\n')
    check('full chapter citation in the build', 'Spiro, Religion: Problems of Definition and Explanation, in ANTHROPOLOGICAL'.upper() in out.upper() and '85, 90' in out, out)
    check('another chapter of the same book is not Id.', 'Geertz, Religion' in out.split('\n[2]')[1].split('\n[3]')[0], out)
    check('the same chapter again is Id.', 'Id. at 6' in out.split('\n[3]')[1], out)
    check('nothing missing', not rep.get('missing'), str(rep))
    out, rep = run('A.[^1]\n\n[^1]: [x]{.cite tag="banton" chapter="gone"}.\n')
    check('a chapter that is not in the book is reported missing', 'missing citation' in out, out)
else:
    print('(pandoc not found: build checks skipped)')

# ---------------- the store: saving, Cited in, Verify, files
tmp = Path(tempfile.mkdtemp())
try:
    store.set_root(tmp)
    store.set_code(ROOT)
    c = store.write_citation('banton', {'type': 'edited_book', 'fields': dict(BOOK['fields'], chapters=BOOK['fields']['chapters'] + [{'title': ''}]
                                                                             + [{'authors': [P('A', 'Wallace')], 'title': 'Rituals', 'series': 'kept'}])},
                             create=True)
    chs = c['fields']['chapters']
    check('empty chapter rows are dropped, ids kept and made', [x['id'] for x in chs] == ['spiro', 'geertz', 'wallace-rituals'], str(chs))
    check('keys the form does not show are kept', chs[2].get('series') == 'kept')
    check('chapter forms for the menus', [x['id'] for x in c['chapters']] == ['spiro', 'geertz', 'wallace-rituals'] and
          c['chapters'][0]['forms']['bluebook_practitioner']['text'].startswith('Melford E. Spiro'), str(c['chapters'][0]))
    check('preview has chapters', len(store.preview_citation({'type': 'edited_book', 'fields': BOOK['fields']})['chapters']) == 2)

    p = store.create_project({'name': 'Religion'})['id']
    art = store.create_document('article', 'Religion Article', p)
    d = store.doc_path(art)
    for f in store.section_paths(art):
        f.unlink()
    (d / '01-intro.md').write_text('# Intro\n\nReligion is hard.[^a] Very.[^b]\n\n'
                                   '[^a]: [Spiro]{.cite tag="banton" chapter="spiro" pin="90"}.\n\n'
                                   '[^b]: [Geertz]{.cite tag="banton" chapter="geertz" pin="90"}; [Gone]{.cite tag="banton" chapter="nope"}.\n',
                                   encoding='utf-8')
    v = store.verification(p)['items']
    check('verify keys name the chapter', [x['key'] for x in v] == [art + ':banton#spiro:90:0', art + ':banton#geertz:90:0', art + ':banton#nope::0'],
          str([x['key'] for x in v]))
    check('verify items carry tag and chapter', v[0]['tag'] == 'banton' and v[0]['chapter'] == 'spiro')
    check('verify text is the chapter', 'Spiro' in v[0]['text'] and 'Geertz' in v[1]['text'], str([x['text'] for x in v]))
    check('a missing chapter is missing', v[2]['missing'] and not v[0]['missing'])
    u = store.citation_uses('banton')
    check('Cited in lists every chapter', u['total'] == 3 and 'Spiro' in u['documents'][0]['uses'][0]['text'], str(u['total']))
    check('counts go to the book', store.citation_uses()['counts'].get('banton') == 3)

    store.save_attachment('banton', 'book.pdf', b'%PDF-1.4 book')
    store.save_attachment('banton', 'spiro.pdf', b'%PDF-1.4 spiro', chapter='spiro')
    store.save_attachment('banton', 'spiro-de.pdf', b'%PDF-1.4 spiro', chapter='spiro', label='German translation')
    files = {f['name']: f for f in store.list_attachments('banton')}
    check('files carry their chapter and label', files['spiro.pdf']['chapter'] == 'spiro' and files['spiro-de.pdf']['label'] == 'German translation'
          and files['book.pdf']['chapter'] == '', str(files))
    check('the meta file is not a file of the source', '_files.json' not in files)
    store.set_file_meta('banton', 'book.pdf', label='Whole book scan')
    check('label set', {f['name']: f for f in store.list_attachments('banton')}['book.pdf']['label'] == 'Whole book scan')
    store.delete_attachment('banton', 'spiro-de.pdf')
    meta = json.loads((store.files_dir('banton') / '_files.json').read_text())
    check('deleting a file forgets its label', 'spiro-de.pdf' not in meta['files'] and 'spiro.pdf' in meta['files'], str(meta))
    bib = store.bibliography('')[1]
    check('bibliography export lists chapters', '**Chapter** `spiro`: Melford E. Spiro' in bib, bib[-800:])

    # ---------------- consolidating single-chapter citations into edited books
    import consolidate_chapters as cc
    data = tmp / 'data'
    (data / 'library' / 'citations').mkdir(parents=True)
    store.set_root(data)
    store.write_citation('banton-1966', {'type': 'book', 'fields': {'title': 'Anthropological Approaches to the Study of Religion',
                                                                     'title_apa': 'Anthropological approaches to the study of religion',
                                                                     'publisher': 'Tavistock', 'date': '1966', 'editors': [P('Michael', 'Banton')]}},
                         create=True)
    store.write_citation('spiro-1966', OLD_SPIRO, create=True)
    store.write_citation('geertz-1966', {'type': 'chapter', 'fields': dict(OLD_SPIRO['fields'], authors=[P('Clifford', 'Geertz')],
                                                                         title='Religion as a Cultural System', first_page='1', last_page='46')}, create=True)
    store.write_citation('kahan-1999', {'type': 'chapter', 'fields': {'authors': [P('Dan M.', 'Kahan')], 'title': 'The Progressive Appropriation of Disgust',
                                                                     'editors': [P('Susan A.', 'Bandes')], 'book_title': 'The Passions of Law',
                                                                     'publisher': 'New York University Press', 'date': '1999', 'first_page': '63'}},
                         create=True)
    store.save_attachment('spiro-1966', 'spiro.pdf', b'%PDF-1.4 s')
    store.save_attachment('banton-1966', 'whole.pdf', b'%PDF-1.4 w')
    store.write_annotations('spiro-1966', 'spiro.pdf', [{'id': 'a1', 'page': 1, 'rects': [[0, 0, 1, 1]], 'text': 'x'}])
    pr = store.create_project({'name': 'Religion'})['id']
    doc = store.create_document('article', 'Religion Article', pr)
    dd = store.doc_path(doc)
    for f in store.section_paths(doc):
        f.unlink()
    (dd / '01-a.md').write_text('# A\n\nText.[^a]\n\n[^a]: [Spiro]{.cite tag="spiro-1966" pin="90"}; [K]{.cite tag="kahan-1999"}; '
                                '[G]{.cite tag="geertz-1966" pin="2"}.\n', encoding='utf-8')
    before = store.verification(pr)['items']
    for it in before:
        store.set_verification(pr, it['key'], 'approved', sig=it['sig'], tag=it['tag'], doc=doc)
    notes = store.create_note('About Spiro', citation='spiro-1966', body='See [S]{.cite tag="spiro-1966"}.', project=pr)
    plan = cc.plan(data)
    check('plan gathers chapters of one book into the existing edited book', any(g['book_tag'] == 'banton-1966' and
          sorted(x['tag'] for x in g['chapters']) == ['geertz-1966', 'spiro-1966'] for g in plan['books']), json.dumps(plan['books'], indent=1)[:1500])
    report = cc.apply(data, plan)
    after = store.verification(pr)['items']
    check('every citation keeps its text', [x['text'] for x in after] == [x['text'] for x in before],
          '\n'.join('%s | %s' % (a['text'], b['text']) for a, b in zip(before, after)))
    check('every approval still counts', all(x.get('status') == 'approved' for x in after), str([(x['key'], x.get('status'), x.get('was')) for x in after]))
    check('old chapter citations are gone', not store.cite_path('spiro-1966').exists() and not store.cite_path('kahan-1999').exists())
    bk = store.read_citation(store.cite_path('banton-1966'))
    check('the book is an edited book with both chapters', bk['type'] == 'edited_book' and [x['id'] for x in bk['fields']['chapters']] ==
          ['geertz-1966', 'spiro-1966'], str(bk['fields']))
    fl = {f['name']: f for f in store.list_attachments('banton-1966')}
    check('chapter PDFs move to the book, marked with their chapter', fl.get('spiro.pdf', {}).get('chapter') == 'spiro-1966' and
          fl['spiro.pdf']['annotations'] == 1 and fl['whole.pdf']['chapter'] == '', str(fl))
    n = store.read_note(store.note_path(notes['id']))
    check('notes link the book, and their citations name the chapter', n['citations'] == ['banton-1966'] and
          'tag="banton-1966" chapter="spiro-1966"' in n['body'], str((n['citations'], n['body'])))
    check('a single chapter becomes an edited book of its own', any(x['type'] == 'edited_book' and [ch['id'] for ch in x['fields']['chapters']] == ['kahan-1999']
                                                                   for x in store.citations()))
    check('projects carried to the book', pr in bk['projects'], str(bk['projects']))
    check('report counts', report['rewritten'] == 4 and report['verify_keys'] == 3, str(report))
    check('running it again changes nothing', not cc.plan(data)['books'])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

bad = [c for c in CASES if not c[1]]
for label, ok, detail in CASES:
    if not ok:
        print('FAIL', label, '\n   ', detail)
print('%d/%d passed' % (len(CASES) - len(bad), len(CASES)))
sys.exit(1 if bad else 0)
