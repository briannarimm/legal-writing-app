"""Checks app/cites.py: draft and final citation forms, Id., supra note N, the five-footnote rule,
string citations, signals, APA grouping, year suffixes and the generated References list.

Run:  python3 tests/test_cites.py      (needs pandoc on the PATH, or LT_RUNTIME pointing at ReWord's runtime)
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import cites  # noqa: E402

rt = os.environ.get('LT_RUNTIME') or str(Path.home() / 'Library/Caches/ReWord Build/runtime')
PANDOC = str(Path(rt) / 'bin' / 'pandoc') if (Path(rt) / 'bin' / 'pandoc').exists() else shutil.which('pandoc')
if not PANDOC:
    sys.exit('pandoc not found')

P = lambda given, family: {'given': given, 'family': family}      # noqa: E731
LIB = {
    'porter': {'type': 'journal', 'fields': {'authors': [P('Elizabeth G.', 'Porter'), P('Kathryn A.', 'Watts')], 'title': 'Visual Rulemaking',
                                             'journal_abbrev': 'N.Y.U. L. Rev.', 'journal': 'New York University Law Review', 'volume': '91',
                                             'first_page': '1183', 'date': '2016'}},
    'wayfair': {'type': 'case', 'fields': {'name': 'South Dakota v. Wayfair, Inc.', 'volume': '138', 'reporter': 'S. Ct.', 'first_page': '2080', 'date': '2018'}},
    'usc1983': {'type': 'statute', 'fields': {'title_no': '42', 'code': 'U.S.C.', 'section': '1983'}},
    'record': {'type': 'record', 'fields': {'abbrev': 'R.', 'use_at': True}},
    'walker-a': {'type': 'book', 'fields': {'authors': [P('Matthew', 'Walker')], 'title': 'Why We Sleep', 'publisher': 'Scribner', 'date': '2017'}},
    'walker-b': {'type': 'journal', 'fields': {'authors': [P('Matthew', 'Walker')], 'title': 'A Sleep Study', 'journal': 'Sleep',
                                               'volume': '4', 'first_page': '1', 'last_page': '9', 'date': '2017'}},
    'ray': {'type': 'journal', 'fields': {'authors': [P('Oakley', 'Ray')], 'title': 'How the Mind Hurts and Heals the Body', 'journal': 'American Psychologist',
                                          'volume': '59', 'issue': '1', 'first_page': '29', 'last_page': '40', 'date': '2004'}},
}

CASES = []


def cite(tag, **a):
    attrs = ' '.join('%s="%s"' % (k, v) for k, v in a.items())
    return '[x]{.cite tag="%s"%s}' % (tag, (' ' + attrs) if attrs else '')


def run(md, mode, typeface='lawreview', style='bluebook', toa=False):
    j = subprocess.run([PANDOC, '-f', 'markdown+smart', '-t', 'json'], input=md, capture_output=True, text=True, check=True).stdout
    doc, report = cites.resolve(json.loads(j), LIB, mode=mode, typeface=typeface, style=style, toa=toa)
    out = subprocess.run([PANDOC, '-f', 'json', '-t', 'markdown', '--wrap=none'], input=json.dumps(doc), capture_output=True, text=True, check=True).stdout
    return out, report


def check(label, got, want):
    CASES.append((label, want in got, got, want))


# ---------------- law review footnotes, final mode
fill = ''.join('Filler %d.[^f%d]\n\n[^f%d]: Nothing here.\n\n' % (k, k, k) for k in range(6, 11))
article = ('A.[^1] B.[^2] C.[^3] D.[^4] E.[^5]\n\n' + fill + 'K.[^11] L.[^12]\n\n'
           '[^1]: ' + cite('porter', pin='1190') + '.\n\n'
           '[^2]: ' + cite('porter', pin='1200') + '.\n\n'
           '[^3]: ' + cite('wayfair', pin='2081', signal='See', paren='holding that states may tax remote sellers') + '.\n\n'
           '[^4]: ' + cite('wayfair', pin='2085') + '; ' + cite('porter', pin='1185') + '.\n\n'
           '[^5]: ' + cite('porter', pin='1190', signal='see also') + '.\n\n'
           '[^11]: ' + cite('wayfair', pin='2090') + '.\n\n'
           '[^12]: ' + cite('wayfair', pin='2090', signal='see') + '.\n')
final, _ = run(article, 'final')
check('fn1 full, law review type', final, 'Elizabeth G. Porter & Kathryn A. Watts, *Visual Rulemaking*, 91 [N.Y.U. L. Rev.]{.smallcaps} 1183, 1190 (2016).')
check('fn2 Id. at', final, '[^2]: *Id.* at 1200.')
check('fn3 signal + full case (roman in footnote) + parenthetical', final, '*See* South Dakota v. Wayfair, Inc., 138 S. Ct. 2080, 2081 (2018) (holding that states may tax remote sellers).')
check('fn4 string cite: short case; supra note 1', final, '*Wayfair*, 138 S. Ct. at 2085; Porter & Watts, *supra* note 1, at 1185.')
check('fn5 no Id. after a string cite; signal capitalized', final, '[^5]: *See also* Porter & Watts, *supra* note 1, at 1190.')
check('fn11 five-footnote rule: full again', final, '[^11]: South Dakota v. Wayfair, Inc., 138 S. Ct. 2080, 2090 (2018).')
check('fn12 See id.', final, '[^12]: *See id.* at 2090.')
draft, _ = run(article, 'draft')
check('draft: fn2 in full', draft, '[^2]: Elizabeth G. Porter & Kathryn A. Watts, *Visual Rulemaking*, 91 [N.Y.U. L. Rev.]{.smallcaps} 1183, 1200 (2016).')

# ---------------- practitioner text citations (briefs, memos)
brief = ('The statute creates a remedy. ' + cite('usc1983') + '. It applies to states. ' + cite('usc1983', pin='(a)') + '. '
         'The Court agreed. ' + cite('wayfair', pin='2081') + '. As the Court explained, ' + cite('wayfair', pin='2082') + ', the rule changed. '
         'The record shows it. ' + cite('record', pin='12') + '. Again. ' + cite('record', pin='14') + '.\n')
pf, report = run(brief, 'final', 'practitioner', toa=True)
check('practitioner full statute (TOA mark)', pf, '[42 U.S.C. § 1983]{.auth tag="usc1983"}.')
check('Id. § subsection', pf, '[*Id.* § 1983(a)]{.auth tag="usc1983"}.')
check('case full italic + toa mark', pf, '[*South Dakota v. Wayfair, Inc.*, 138 S. Ct. 2080, 2081 (2018)]{.auth tag="wayfair"}')
check('mid-sentence id. lowercase', pf, 'As the Court explained, [*id.* at 2082]{.auth tag="wayfair"}, the rule changed.')
check('record: no Id.', pf, 'Again. R. at 14.')
check('report lists cited', ' '.join(report['cited']), 'usc1983 wayfair record')

# ---------------- APA
apa = ('Sleep matters ' + cite('walker-a', pin='12') + '. ' + cite('walker-b', narrative='1') + ' agreed. '
       'Both say so ' + cite('walker-b') + '; ' + cite('ray') + '.\n\n# References\n')
a, _ = run(apa, 'final', style='apa')
check('APA year suffix (titles sort: A Sleep Study = a)', a, '(Walker, 2017b, p. 12)')
check('APA narrative', a, 'Walker (2017a) agreed.')
check('APA combined parenthetical, alphabetical', a, '(Ray, 2004; Walker, 2017a)')
check('APA references sorted with suffixes', a, 'Ray, O. (2004). How the mind hurts and heals the body. *American Psychologist*, *59*(1), 29--40.\n\nWalker, M. (2017a). A sleep study. *Sleep*, *4*, 1--9.\n\nWalker, M. (2017b). *Why we sleep*. Scribner.')
missing, rep = run('See ' + cite('nope') + '.\n', 'draft')
check('missing citation is visible', missing, '\\[missing citation: nope\\]')

ok = sum(1 for _, good, _, _ in CASES if good)
for label, good, got, want in CASES:
    if not good:
        print('FAIL', label, '\n   want:', want, '\n   got:\n' + got)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
