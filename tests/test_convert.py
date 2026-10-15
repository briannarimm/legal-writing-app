"""Checks switching a document's template (app/convert.py, store.change_template): citations move between
footnotes and the text, narrative citations survive a round trip, notes with commentary stay notes, the
reference list follows the template, the details carry over, and a copy of the old files is kept.

Run:  python3 tests/test_convert.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import convert  # noqa: E402
import store  # noqa: E402

CASES = []


def check(label, got, want):
    CASES.append((label, want in got, got, want))


def names(tag):
    return {'walker': 'Walker'}.get(tag, tag)


W = '[Walker]{.cite tag="walker" pin="12"}'
N = '[Walker (2017)]{.cite tag="walker" narrative="1"}'
R = '[Ray]{.cite tag="ray"}'

# ---------------- the pieces
check('chips with nested brackets', str(len(convert.find_chips('[[A]{.smallcaps} b]{.cite tag="a"} and [c]{.cite tag="c" pin="2"}'))), '2')
check('string cite is one group', str(len(convert.groups(W + '; ' + R))), '1')
check('cites-only note', str(convert.cites_only(W + '; ' + R + '.')), 'True')
check('note with commentary', str(convert.cites_only('This is commentary, see ' + R + '.')), 'False')

# APA -> notes
secs, rep = convert.convert_sections([('01-a.md', 'Sleep matters ' + W + '.\n' + N + ' found it.\nStress hurts ' + R + '; ' + W + ', and it is bad.\n')],
                                     'paren', 'notes', names)
md = secs[0][1]
check('APA cite -> note after the period', md, 'Sleep matters.[^cite-1]')
check('narrative -> name in the text, note after it', md, 'Walker[^cite-2] found it.')
check('string cite mid-sentence -> one note after the comma', md, 'Stress hurts,[^cite-3] and it is bad.')
check('note text', md, '[^cite-1]: ' + W + '.')
check('report counts', str(rep['to_notes']), '3')

# notes -> APA, back again
back, rep2 = convert.convert_sections(secs, 'notes', 'paren', names)
check('round trip APA -> notes -> APA', back[0][1], 'Sleep matters ' + W + '.\n' + N + ' found it.\nStress hurts ' + R + '; ' + W + ', and it is bad.\n')

# notes -> Bluebook in the text (memo)
memo, _ = convert.convert_sections([('01-a.md', 'The rule is clear.[^1] It applies,[^2] usually.\n\nA point.[^3]\n\n[^1]: ' + W + '.\n\n[^2]: '
                                     + R + '.\n\n[^3]: This is commentary, see ' + R + '.\n')], 'notes', 'sentence', names)
check('citation sentence after the sentence', memo[0][1], 'The rule is clear. ' + W + '. It applies, ' + R + ', usually.')
check('commentary note stays a note', memo[0][1], '[^3]: This is commentary, see ' + R + '.')

# Bluebook in the text -> notes
lr, _ = convert.convert_sections(memo, 'sentence', 'notes', names)
check('memo -> article: citation sentence becomes a note', lr[0][1], 'The rule is clear.[^cite-1] It applies,[^cite-2] usually.')

# details
meta = convert.convert_metadata('title: "X"\nauthor:\n  - name: Ann Lee\n    note: "J.D."\nabstract: |\n  Old abstract.\n',
                                'title: "{{title}}"\nauthor: "Your Name"\naffiliation: "U"\n', 'X', 'Law review article')
check('authors carried over', meta, 'author: "Ann Lee"')
check('old details kept as comments', meta, '# Details from the Law review article template')
check('old note kept', meta, '#     note: "J.D."')

# ---------------- a whole document in a data folder
tmp = Path(tempfile.mkdtemp())
try:
    store.set_root(tmp)
    store.set_code(Path(__file__).resolve().parent.parent)
    P = lambda g, f: {'given': g, 'family': f}      # noqa: E731
    store.write_citation('walker', {'type': 'book', 'fields': {'authors': [P('Matthew', 'Walker')], 'title': 'Why We Sleep', 'date': '2017'}}, create=True)
    store.write_citation('ray', {'type': 'journal', 'fields': {'authors': [P('Oakley', 'Ray')], 'title': 'How the Mind Hurts', 'journal': 'Am. Psych.',
                                                               'volume': '59', 'first_page': '29', 'last_page': '40', 'date': '2004'}}, create=True)
    slug = store.create_document('assignment', 'Sleep Paper')
    p = store.doc_path(slug)
    (p / '01-paper.md').write_text('Sleep matters ' + W + '.\n' + N + ' found it.\n')
    original = (p / '01-paper.md').read_text()
    r = store.change_template(slug, 'journal-chicago')
    check('template recorded', store.read_doc_info(p)['template'], 'journal-chicago')
    check('cites moved into notes', (p / '01-paper.md').read_text(), 'Sleep matters.[^cite-1]')
    check('References renamed to Bibliography', (p / '02-references.md').read_text(), '# Bibliography')
    check('gap reported: book without a publisher', str(r['gaps']), "'tag': 'walker', 'missing': ['publisher']")
    check('backup kept', (tmp / r['backup'] / '01-paper.md').read_text(), original)
    store.change_template(slug, 'article')
    check('empty reference list removed for the article', ' '.join(f.name for f in store.section_paths(slug)), '01-paper.md')
    store.change_template(slug, 'journal-apa')
    check('back to APA: text restored', (p / '01-paper.md').read_text(), original)
    check('reference list added back', ' '.join(f.name for f in store.section_paths(slug)), '02-references.md')
    try:
        store.change_template(slug, 'bibliography')
        check('bibliography refused', 'allowed', 'refused')
    except store.StoreError:
        check('bibliography refused', 'refused', 'refused')
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ok = sum(1 for _, good, _, _ in CASES if good)
for label, good, got, want in CASES:
    if not good:
        print('FAIL', label, '\n   want:', want, '\n   got:\n' + got)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
