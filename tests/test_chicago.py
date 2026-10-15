"""Checks Chicago style (18th ed.) in app/citeformat.py and app/cites.py: full and shortened notes, the
bibliography, author-date text citations and reference list, and what chicago_gaps() reports.

Run:  python3 tests/test_chicago.py      (needs pandoc on the PATH, or LT_RUNTIME pointing at ReWord's runtime)
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import cites  # noqa: E402
import citeformat as cf  # noqa: E402

rt = os.environ.get('LT_RUNTIME') or str(Path.home() / 'Library/Caches/ReWord Build/runtime')
PANDOC = str(Path(rt) / 'bin' / 'pandoc') if (Path(rt) / 'bin' / 'pandoc').exists() else shutil.which('pandoc')
if not PANDOC:
    sys.exit('pandoc not found')

P = lambda given, family: {'given': given, 'family': family}      # noqa: E731
LIB = {
    'walker': {'type': 'book', 'fields': {'authors': [P('Matthew', 'Walker')], 'title': 'Why We Sleep: Unlocking the Power of Sleep and Dreams',
                                          'publisher': 'Scribner', 'date': '2017'}},
    'ray': {'type': 'journal', 'fields': {'authors': [P('Oakley', 'Ray')], 'title': 'How the Mind Hurts and Heals the Body',
                                          'journal': 'American Psychologist', 'volume': '59', 'issue': '1', 'first_page': '29',
                                          'last_page': '40', 'date': '2004', 'doi': '10.1037/0003-066X.59.1.29'}},
    'lee': {'type': 'chapter', 'fields': {'authors': [P('Ann', 'Lee')], 'title': 'Courts and Change', 'editors': [P('Lynn', 'Mather'), P('Leslie', 'Levin')],
                                          'book_title': 'Lawyers in Practice', 'first_page': '45', 'last_page': '67',
                                          'publisher': 'University of Chicago Press', 'date': '2012'}},
    'many': {'type': 'journal', 'fields': {'authors': [P('A', 'One'), P('B', 'Two'), P('C', 'Three'), P('D', 'Four')], 'title': 'Teams',
                                           'journal': 'Science', 'volume': '1', 'first_page': '1', 'last_page': '2', 'date': '2020'}},
    'page': {'type': 'webpage', 'fields': {'title': 'Why Sleep Matters', 'site': 'Sleep Foundation', 'last_visited': '2024-03-02',
                                           'url': 'https://example.org/sleep'}},
    'nopub': {'type': 'book', 'fields': {'authors': [P('Jane', 'Doe')], 'title': 'Old Book', 'date': '1999'}},
    'wayfair': {'type': 'case', 'fields': {'name': 'South Dakota v. Wayfair, Inc.', 'volume': '138', 'reporter': 'S. Ct.', 'first_page': '2080', 'date': '2018'}},
}
CASES = []


def check(label, got, want):
    CASES.append((label, want in got, got, want))


def plain(runs):
    return runs.plain() if runs is not None else 'None'


def cite(tag, **a):
    attrs = ' '.join('%s="%s"' % (k, v) for k, v in a.items())
    return '[x]{.cite tag="%s"%s}' % (tag, (' ' + attrs) if attrs else '')


def run(md, mode, style):
    j = subprocess.run([PANDOC, '-f', 'markdown+smart', '-t', 'json'], input=md, capture_output=True, text=True, check=True).stdout
    doc, report = cites.resolve(json.loads(j), LIB, mode=mode, style=style)
    return subprocess.run([PANDOC, '-f', 'json', '-t', 'plain', '--wrap=none'], input=json.dumps(doc), capture_output=True, text=True, check=True).stdout


# ---------------- formatter
check('book note', plain(cf.chicago_note(LIB['walker'], '45')), 'Matthew Walker, Why We Sleep: Unlocking the Power of Sleep and Dreams (Scribner, 2017), 45')
check('book short note: four words, no subtitle', plain(cf.chicago_short(LIB['walker'], '45')), 'Walker, Why We Sleep, 45')
check('book bibliography', plain(cf.chicago_bib(LIB['walker'])), 'Walker, Matthew. Why We Sleep: Unlocking the Power of Sleep and Dreams. Scribner, 2017.')
check('journal note', plain(cf.chicago_note(LIB['ray'], '31')), 'Oakley Ray, “How the Mind Hurts and Heals the Body,” American Psychologist 59, no. 1 (2004): 31, https://doi.org/10.1037/0003-066X.59.1.29')
check('journal short note: comma inside the quotes', plain(cf.chicago_short(LIB['ray'], '31')), 'Ray, “How the Mind Hurts,” 31')
check('journal bibliography', plain(cf.chicago_bib(LIB['ray'])), 'Ray, Oakley. “How the Mind Hurts and Heals the Body.” American Psychologist 59, no. 1 (2004): 29–40.')
check('chapter note', plain(cf.chicago_note(LIB['lee'], '50')), 'Ann Lee, “Courts and Change,” in Lawyers in Practice, ed. Lynn Mather and Leslie Levin (University of Chicago Press, 2012), 50')
check('chapter bibliography', plain(cf.chicago_bib(LIB['lee'])), 'Lee, Ann. “Courts and Change.” In Lawyers in Practice, edited by Lynn Mather and Leslie Levin, 45–67. University of Chicago Press, 2012.')
check('four authors: et al. in notes', plain(cf.chicago_note(LIB['many'])), 'A One et al., “Teams,”')
check('four authors: all in the bibliography', plain(cf.chicago_bib(LIB['many'])), 'One, A, B Two, C Three, and D Four.')
check('undated web page: accessed', plain(cf.chicago_note(LIB['page'])), '“Why Sleep Matters,” Sleep Foundation, accessed March 2, 2024, https://example.org/sleep')
check('case keeps legal form', plain(cf.chicago_note(LIB['wayfair'], '2081')), 'South Dakota v. Wayfair, Inc., 138 S. Ct. 2080, 2081 (2018)')
check('case not in the bibliography', plain(cf.chicago_bib(LIB['wayfair'])), 'None')
check('author-date reference', plain(cf.chicago_ad_reference(LIB['ray'])), 'Ray, Oakley. 2004. “How the Mind Hurts and Heals the Body.” American Psychologist 59, no. 1: 29–40.')
check('author-date in-text', plain(cf.chicago_ad_intext(LIB['walker'], '45')), '(Walker 2017, 45)')
check('author-date narrative', plain(cf.chicago_ad_intext(LIB['walker'], '45', narrative=True)), 'Walker (2017, 45)')
check('author-date: three or more authors', plain(cf.chicago_ad_intext(LIB['many'])), '(One et al. 2020)')
check('author-date, no author: title and n.d.', plain(cf.chicago_ad_reference(LIB['page'])), '“Why Sleep Matters.” n.d. Sleep Foundation.')
check('gaps: book without a publisher', ', '.join(cf.chicago_gaps(LIB['nopub'])), 'publisher')
check('gaps: complete journal has none', ', '.join(cf.chicago_gaps(LIB['ray'])) or 'none', 'none')
check('gaps: other type has no Chicago form', ', '.join(cf.chicago_gaps({'type': 'other', 'fields': {'text': 'X'}})), 'Chicago form')

# ---------------- notes and bibliography in a document
doc = ('A.[^1] B.[^2] C.[^3]\n\n'
       '[^1]: ' + cite('walker', pin='12', signal='See') + '.\n\n'
       '[^2]: ' + cite('ray', pin='31') + '; ' + cite('wayfair', pin='2081') + '.\n\n'
       '[^3]: ' + cite('walker', pin='40') + '.\n')
final = run(doc, 'final', 'chicago')
check('signal roman, full first note', final, '[1] See Matthew Walker, Why We Sleep: Unlocking the Power of Sleep and Dreams (Scribner, 2017), 12.')
check('shortened note after the full one', final, '[3] Walker, Why We Sleep, 40.')
check('Bibliography heading and entries, no case', final, 'Bibliography\n\nRay, Oakley.')
check('case left out of the bibliography', 'Wayfair' not in final.split('Bibliography')[1].split('[1]')[0] and 'ok' or 'listed', 'ok')
draft = run(doc, 'draft', 'chicago')
check('draft: every note in full', draft, '[3] Matthew Walker, Why We Sleep: Unlocking the Power of Sleep and Dreams (Scribner, 2017), 40.')

# ---------------- author-date in a document
ad = run('Sleep matters ' + cite('walker', pin='12') + '. ' + cite('ray', narrative='1') + ' agreed. Both ' + cite('walker') + '; ' + cite('ray') + '.\n', 'draft', 'chicago-ad')
check('author-date parenthetical', ad, 'Sleep matters (Walker 2017, 12).')
check('author-date narrative in a document', ad, 'Ray (2004) agreed.')
check('author-date combined, alphabetical', ad, '(Ray 2004; Walker 2017)')
check('author-date References list', ad, 'References\n\nRay, Oakley. 2004.')

ok = sum(1 for _, good, _, _ in CASES if good)
for label, good, got, want in CASES:
    if not good:
        print('FAIL', label, '\n   want:', want, '\n   got:', got)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
