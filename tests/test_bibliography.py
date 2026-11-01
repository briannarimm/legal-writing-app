"""Checks the annotated bibliography layout (templates/bibliography, filters/bibliography.lua): a note before the
first entry is kept first and prints flush left (no first-line indent) in the PDF and in Word, while the entries
keep their hanging indent and the annotations their indent.

Run:  python3 tests/test_bibliography.py      (needs pandoc on the PATH)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import cites  # noqa: E402
import store  # noqa: E402

CASES = []


def check(label, ok, detail=''):
    CASES.append((label, bool(ok), detail))


MD = '''This bibliography gathers sources on learning machines.

[Doe]{.cite tag="doe-2020" form="entry"}

Doe argues things about learning machines.

[Ray]{.cite tag="ray-2004" form="entry"}

Ray studies something else.
'''

tmp = Path(tempfile.mkdtemp())
try:
    store.set_root(tmp)
    store.set_code(ROOT)
    store.write_citation('doe-2020', {'type': 'book', 'fields': {'authors': [{'given': 'Jane', 'family': 'Doe'}], 'title': 'Learning machines',
                                                                'publisher': 'Penguin', 'date': '2020'}}, create=True)
    store.write_citation('ray-2004', {'type': 'book', 'fields': {'authors': [{'given': 'Ann', 'family': 'Ray'}], 'title': 'Other things',
                                                                'publisher': 'Penguin', 'date': '2004'}}, create=True)
    src = tmp / 'entries.md'
    src.write_text(MD, encoding='utf-8')
    meta = tmp / 'metadata.yaml'
    meta.write_text('title: "Bib"\ncitation-style: apa\n', encoding='utf-8')
    ast = subprocess.run(['pandoc', '-d', 'defaults/common.yaml', '--metadata-file', str(meta), str(src), '-t', 'json'],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    tmpl = json.loads((ROOT / 'templates' / 'bibliography' / 'template.json').read_text(encoding='utf-8'))
    library = cites.load_library(tmp)

    latex_json, _ = cites.resolve_json_text(ast, library, tmpl, 'draft', 'latex')
    blocks = json.loads(latex_json)['blocks']
    check('the note comes first, in a bib-intro', blocks[0]['t'] == 'Div' and 'bib-intro' in blocks[0]['c'][0][1], str(blocks[0])[:200])
    check('entries follow, sorted', [b['c'][0][1] for b in blocks[1:]] == [['bib-entry'], ['bib-entry']])
    tex = subprocess.run(['pandoc', '-f', 'json', '-d', 'templates/bibliography/pdf.yaml', '-s', '-t', 'latex'], input=latex_json,
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    check('PDF: the note is not indented', '\\noindent This bibliography gathers' in tex, tex[tex.find('\\begin{document}'):][:400])
    check('PDF: the entries keep their environment', tex.count('\\begin{bibentry}') == 2 and tex.count('\\begin{bibannotation}') == 2)

    docx_json, _ = cites.resolve_json_text(ast, library, tmpl, 'draft', 'docx')
    out = tmp / 'bib.docx'
    subprocess.run(['pandoc', '-f', 'json', '-d', 'templates/bibliography/docx.yaml', '-o', str(out)], input=docx_json,
                   cwd=ROOT, capture_output=True, text=True, check=True)
    xml = zipfile.ZipFile(out).read('word/document.xml').decode('utf-8')
    paras = [(re.findall(r'w:pStyle w:val="(\w+)"', p), ''.join(re.findall(r'<w:t[^>]*>([^<]*)', p)))
             for p in re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)]
    note = [st for st, text in paras if text.startswith('This bibliography gathers')]
    check('Word: the note uses Normal (no first-line indent)', note == [['Normal']], str(paras))
    check('Word: entries and annotations keep their styles',
          [st for st, _ in paras].count(['Bibliography']) == 2 and [st for st, _ in paras].count(['Annotation']) == 2, str(paras))
    src.write_text(MD.split('\n\n', 1)[1], encoding='utf-8')
    ast2 = subprocess.run(['pandoc', '-d', 'defaults/common.yaml', '--metadata-file', str(meta), str(src), '-t', 'json'],
                          cwd=ROOT, capture_output=True, text=True, check=True).stdout
    no_intro, _ = cites.resolve_json_text(ast2, library, tmpl, 'draft', 'latex')
    check('no note: no bib-intro', 'bib-intro' not in no_intro)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

bad = [c for c in CASES if not c[1]]
for label, ok, detail in CASES:
    if not ok:
        print('FAIL', label, '\n   ', detail)
print('%d/%d passed' % (len(CASES) - len(bad), len(CASES)))
sys.exit(1 if bad else 0)
