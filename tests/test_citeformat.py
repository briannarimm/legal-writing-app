"""Checks app/citeformat.py against examples from The Indigo Book 2.0 (2023 rev.) and APA 7th edition.

Run:  python3 tests/test_citeformat.py
Expected strings use ReWord's Markdown: *italic*, [x]{.smallcaps}.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import citeformat as cf  # noqa: E402

P = lambda given, family, **kw: dict(given=given, family=family, **kw)      # noqa: E731
ORG = lambda name: dict(literal=name)                                        # noqa: E731

CASES = []


def check(label, got_runs, want):
    got = cf.to_md(got_runs)
    CASES.append((label, got == want, got, want))


def C(t, **fields):
    return {'type': t, 'fields': fields}


# ---------------- cases (Indigo R11-R15, T19)
leonard = C('case', name='Leonard v. Pepsico, Inc.', volume='88', reporter='F. Supp. 2d', first_page='116',
            court='S.D.N.Y.', date='1999', history="aff'd, 210 F.3d 88 (2d Cir. 2000) (per curiam)")
check('case practitioner + history', cf.bluebook(leonard, 'practitioner', '127'),
      "*Leonard v. Pepsico, Inc.*, 88 F. Supp. 2d 116, 127 (S.D.N.Y. 1999), *aff'd*, 210 F.3d 88 (2d Cir. 2000) (per curiam)")
wayfair = C('case', name='South Dakota v. Wayfair, Inc.', volume='138', reporter='S. Ct.', first_page='2080', date='2018')
check('case scotus practitioner', cf.bluebook(wayfair, 'practitioner'), '*South Dakota v. Wayfair, Inc.*, 138 S. Ct. 2080 (2018)')
check('case law review footnote (roman)', cf.bluebook(wayfair, 'lawreview'), 'South Dakota v. Wayfair, Inc., 138 S. Ct. 2080 (2018)')
check('case law review in text (italic)', cf.bluebook(wayfair, 'lawreview', in_text=True), '*South Dakota v. Wayfair, Inc.*, 138 S. Ct. 2080 (2018)')
check('case short: government first party -> second party', cf.bluebook_short(
    C('case', name='United States v. Carmel', volume='548', reporter='F.3d', first_page='571', court='7th Cir.', date='2008'),
    'practitioner', '573'), '*Carmel*, 548 F.3d at 573')
check('case short: first party', cf.bluebook_short(
    C('case', name='Home Depot USA, Inc. v. Jackson', short_name='Home Depot', volume='139', reporter='S. Ct.', first_page='1743', date='2019'),
    'lawreview', '1744'), '*Home Depot*, 139 S. Ct. at 1744')
green = C('case', name='State v. Green', docket='No. 2012AP1475–CR', database='2013 WL 5811261', court='Wis. Ct. App.', date='2013-10-30')
check('unreported (Westlaw)', cf.bluebook(green, 'practitioner', '7'),
      '*State v. Green*, No. 2012AP1475–CR, 2013 WL 5811261, at \\*7 (Wis. Ct. App. Oct. 30, 2013)')
check('weight of authority', cf.bluebook(C('case', name='Ward v. Rock Against Racism', volume='491', reporter='U.S.', first_page='781',
      date='1989', weight='Marshall, J., dissenting'), 'practitioner'), '*Ward v. Rock Against Racism*, 491 U.S. 781 (1989) (Marshall, J., dissenting)')
check('Id. at page', cf.bluebook_id(wayfair, '2081'), '*Id.* at 2081')
check('id. lowercase', cf.bluebook_id(wayfair, '', cap=False), '*id.*')

# ---------------- statutes, regulations, constitutions, rules (R16-R23, T19)
check('U.S.C. no year', cf.bluebook(C('statute', title_no='42', code='U.S.C.', section='1983'), 'lawreview'), '42 U.S.C. § 1983')
check('named act, span', cf.bluebook(C('statute', name='Federal Food, Drug, and Cosmetic Act', title_no='21', code='U.S.C.', section='301–399i'), 'practitioner'),
      'Federal Food, Drug, and Cosmetic Act, 21 U.S.C. §§ 301–399i')
colo = C('statute', code='Colo. Rev. Stat.', section='13-90-107', date='2021')
check('state statute practitioner', cf.bluebook(colo, 'practitioner'), 'Colo. Rev. Stat. § 13-90-107 (2021)')
check('state statute law review (small caps)', cf.bluebook(colo, 'lawreview'), '[Colo. Rev. Stat.]{.smallcaps} § 13-90-107 (2021)')
check('unofficial code with publisher', cf.bluebook(C('statute', code='Tex. Est. Code Ann.', section='251.107', publisher='West', date='2019'), 'practitioner'),
      'Tex. Est. Code Ann. § 251.107 (West 2019)')
check('session law', cf.bluebook(C('statute', name='Patient Protection and Affordable Care Act', pub_law='111-148', stat='124 Stat. 119', date='2010'), 'practitioner', '§ 1101'),
      'Patient Protection and Affordable Care Act, Pub. L. No. 111-148, § 1101, 124 Stat. 119 (2010)')
check('statute Id. subsection', cf.bluebook_id(C('statute', title_no='7', code='U.S.C.', section='7101'), '(26)'), '*Id.* § 7101(26)')
check('statute short', cf.bluebook_short(C('statute', title_no='17', code='U.S.C.', section='107'), 'practitioner'), '17 U.S.C. § 107')
check('C.F.R.', cf.bluebook(C('regulation', title_no='36', code='C.F.R.', section='272.1', date='2020'), 'practitioner'), '36 C.F.R. § 272.1 (2020)')
check('constitution practitioner', cf.bluebook(C('constitution', jurisdiction='U.S.', provision='art. I, § 8, cl. 8'), 'practitioner'), 'U.S. Const. art. I, § 8, cl. 8')
check('constitution law review', cf.bluebook(C('constitution', jurisdiction='U.S.', provision='art. I, § 8, cl. 8'), 'lawreview'), '[U.S. Const.]{.smallcaps} art. I, § 8, cl. 8')
check('repealed amendment', cf.bluebook(C('constitution', jurisdiction='U.S.', provision='amend. XVIII', status='repealed 1933'), 'practitioner'), 'U.S. Const. amend. XVIII (repealed 1933)')
check('rule practitioner', cf.bluebook(C('rule', source='Fed. R. Civ. P.', number='12'), 'practitioner', '(b)(1)'), 'Fed. R. Civ. P. 12(b)(1)')
check('rule law review', cf.bluebook(C('rule', source='Fed. R. App. P.', number='32(a)'), 'lawreview'), '[Fed. R. App. P.]{.smallcaps} 32(a)')
rst = C('restatement', title='Restatement (Third) of Agency', section='2.01', publisher='Am. L. Inst.', date='2006')
check('restatement practitioner', cf.bluebook(rst, 'practitioner'), 'Restatement (Third) of Agency § 2.01 (Am. L. Inst. 2006)')
check('restatement law review', cf.bluebook(rst, 'lawreview'), '[Restatement (Third) of Agency]{.smallcaps} § 2.01 ([Am. L. Inst.]{.smallcaps} 2006)')

# ---------------- books, chapters, articles (R28-R31, T19)
vats = C('book', authors=[P('Anjali', 'Vats')], title='The Color of Creatorship: Intellectual Property, Race, and the Making of Americans', date='2020')
check('book practitioner', cf.bluebook(vats, 'practitioner'), 'Anjali Vats, *The Color of Creatorship: Intellectual Property, Race, and the Making of Americans* (2020)')
check('book law review', cf.bluebook(vats, 'lawreview'), '[Anjali Vats, The Color of Creatorship: Intellectual Property, Race, and the Making of Americans]{.smallcaps} (2020)')
check('book supra practitioner', cf.bluebook_short(vats, 'practitioner', '100'), 'Vats, *supra*, at 100')
check('book supra law review', cf.bluebook_short(vats, 'lawreview', '100', note=5), '[Vats]{.smallcaps}, *supra* note 5, at 100')
style = C('book', authors=[P('Joseph', 'Williams'), P('Joseph', 'Bizup')], title='Style: Ten Lessons in Clarity and Grace', edition='12', date='2016')
check('book two authors, edition', cf.bluebook(style, 'practitioner'), 'Joseph Williams & Joseph Bizup, *Style: Ten Lessons in Clarity and Grace* (12th ed. 2016)')
lilly = C('book', authors=[P('Graham C.', 'Lilly'), P('Daniel J.', 'Capra'), P('Stephen A.', 'Saltzburg')], title='Principles of Evidence', edition='6', date='2012')
check('book et al., pin', cf.bluebook(lilly, 'practitioner', '122'), 'Graham C. Lilly et al., *Principles of Evidence* 122 (6th ed. 2012)')
check('book et al. supra', cf.bluebook_short(lilly, 'practitioner', '90'), 'Lilly et al., *supra*, at 90')
check('book 2d edition ordinal', cf.bluebook(C('book', authors=[P('A', 'B')], title='T', edition='2', date='2001'), 'practitioner'), 'A B, *T* (2d ed. 2001)')
kim = C('chapter', authors=[P('Sung Hui', 'Kim')], title='The Ethics of In-House Practice', book_title='Lawyers in Practice: Ethical Decision Making in Context',
        editors=[P('Leslie C.', 'Levin'), P('Lynn', 'Mather')], date='2012', publisher='University of Chicago Press', first_page='197', last_page='220')
check('chapter practitioner', cf.bluebook(kim, 'practitioner'),
      'Sung Hui Kim, *The Ethics of In-House Practice*, in *Lawyers in Practice: Ethical Decision Making in Context* 197 (Leslie C. Levin & Lynn Mather eds., 2012)')
porter = C('journal', authors=[P('Elizabeth G.', 'Porter'), P('Kathryn A.', 'Watts')], title='Visual Rulemaking',
           journal='New York University Law Review', journal_abbrev='N.Y.U. L. Rev.', volume='91', issue='5', first_page='1183', last_page='1260', date='2016')
check('article practitioner', cf.bluebook(porter, 'practitioner'), 'Elizabeth G. Porter & Kathryn A. Watts, *Visual Rulemaking*, 91 N.Y.U. L. Rev. 1183 (2016)')
check('article law review', cf.bluebook(porter, 'lawreview', '1190'), 'Elizabeth G. Porter & Kathryn A. Watts, *Visual Rulemaking*, 91 [N.Y.U. L. Rev.]{.smallcaps} 1183, 1190 (2016)')
check('article supra law review', cf.bluebook_short(porter, 'lawreview', '1200', note=12), 'Porter & Watts, *supra* note 12, at 1200')
check('student note', cf.bluebook(C('journal', authors=[P('Amanda', 'Levendowski')], designation='Note', title='Using Copyright to Combat Revenge Porn',
      journal_abbrev='N.Y.U. J. Intell. Prop. & Ent. L.', volume='3', first_page='422', date='2014'), 'practitioner'),
      'Amanda Levendowski, Note, *Using Copyright to Combat Revenge Porn*, 3 N.Y.U. J. Intell. Prop. & Ent. L. 422 (2014)')
check('abbreviate Harvard Law Review', cf.Runs().r(cf.abbreviate_periodical('Harvard Law Review')), 'Harv. L. Rev.')
check('abbreviate Journal of Legal Studies', cf.Runs().r(cf.abbreviate_periodical('Journal of Legal Studies')), 'J. Legal Stud.')
check('abbreviate Law and Contemporary Problems', cf.Runs().r(cf.abbreviate_periodical('Law and Contemporary Problems')), 'Law & Contemp. Probs.')

# ---------------- news, web, reports (R30.4, R33, T19)
liptak = C('news', authors=[P('Adam', 'Liptak')], title='Supreme Court Rules for Cheerleader Punished for Vulgar Snapchat Message',
           publication='New York Times', publication_abbrev='N.Y. Times', date='2021-06-23', page='A1')
check('newspaper print practitioner', cf.bluebook(liptak, 'practitioner'),
      'Adam Liptak, *Supreme Court Rules for Cheerleader Punished for Vulgar Snapchat Message*, N.Y. Times, June 23, 2021, at A1')
check('newspaper print law review', cf.bluebook(liptak, 'lawreview'),
      'Adam Liptak, *Supreme Court Rules for Cheerleader Punished for Vulgar Snapchat Message*, [N.Y. Times]{.smallcaps}, June 23, 2021, at A1')
savage = C('news', authors=[P('Charlie', 'Savage')], title='U.N. Commission Presses U.S. on Torture', publication_abbrev='N.Y. Times',
           publication='The New York Times', date='2014-11-14', url='https://www.nytimes.com/2014/11/14/world/europe/un-commission-presses-us-on-torture.html')
check('newspaper online', cf.bluebook(savage, 'practitioner'),
      '*Charlie Savage*, *U.N. Commission Presses U.S. on Torture*, N.Y. Times (Nov. 14, 2014), https://www.nytimes.com/2014/11/14/world/europe/un-commission-presses-us-on-torture.html'.replace('*Charlie Savage*', 'Charlie Savage'))
manjoo = C('webpage', authors=[P('Farhad', 'Manjoo')], title='Why You Should Never, Ever Use Two Spaces After a Period', site='Slate',
           date='2011-01-11', time='6:00 AM', url='https://slate.com/technology/2011/01/two-spaces.html')
check('web practitioner', cf.bluebook(manjoo, 'practitioner'),
      'Farhad Manjoo, *Why You Should Never, Ever Use Two Spaces After a Period*, Slate (Jan. 11, 2011, 6:00 AM), https://slate.com/technology/2011/01/two-spaces.html')
check('web law review', cf.bluebook(manjoo, 'lawreview'),
      'Farhad Manjoo, *Why You Should Never, Ever Use Two Spaces After a Period*, [Slate]{.smallcaps} (Jan. 11, 2011, 6:00 AM), https://slate.com/technology/2011/01/two-spaces.html')
check('web no date: last visited', cf.bluebook(C('webpage', title='Economic Liberty', site_abbrev='Inst. for Just.', url='https://ij.org/issues/economic-liberty/',
      last_visited='2021-07-06'), 'practitioner'), '*Economic Liberty*, Inst. for Just., https://ij.org/issues/economic-liberty/ (last visited July 6, 2021)')
check('web supra', cf.bluebook_short(manjoo, 'practitioner'), 'Manjoo, *supra*')

# ---------------- legislative and litigation (R21, R24-R26)
check('bill', cf.bluebook(C('bill', number='S. 812', session='108th Cong.', date='2003'), 'practitioner'), 'S. 812, 108th Cong. (2003)')
check('bill with section', cf.bluebook(C('bill', title='Clinical Social Work Medicare Equality Act of 2001', number='S. 1083', session='107th Cong.', date='2001'), 'practitioner', '§ 2(b)'),
      'Clinical Social Work Medicare Equality Act of 2001, S. 1083, 107th Cong. § 2(b) (2001)')
check('state bill', cf.bluebook(C('bill', number='L.D. 3', session='127th Leg., Reg. Sess.', state='Me.', date='2015'), 'practitioner'), 'L.D. 3, 127th Leg., Reg. Sess. (Me. 2015)')
check('enacted bill', cf.bluebook(C('bill', number='S. 2318', session='112th Cong.', date='2013', status='enacted'), 'practitioner'), 'S. 2318, 112th Cong. (2013) (enacted)')
check('committee report', cf.bluebook(C('committee_report', chamber='S.', number='106-261', date='2000'), 'practitioner', '441'), 'S. Rep. No. 106-261, at 441 (2000)')
check('committee report law review', cf.bluebook(C('committee_report', chamber='H.R.', number='117-27', date='2021'), 'lawreview', '5'), '[H.R. Rep. No.]{.smallcaps} 117-27, at 5 (2021)')
check('conference report', cf.bluebook(C('committee_report', chamber='H.R.', number='110-803', date='2008', conference=True), 'practitioner', '105'),
      'H.R. Rep. No. 110-803, at 105 (2008) (Conf. Rep.)')
check('hearing', cf.bluebook(C('hearing', title='Welfare and Poverty in America: Hearing Before the S. Comm. on Fin.', session='114th Cong.', date='2015'), 'practitioner'),
      '*Welfare and Poverty in America: Hearing Before the S. Comm. on Fin.*, 114th Cong. (2015)')
check('own-case filing with ECF', cf.bluebook(C('filing', title="Pl.'s Compl.", ecf='147'), 'practitioner', '¶ 12'), "Pl.'s Compl. ¶ 12, ECF No. 147")
check('record cite', cf.bluebook(C('record', abbrev='R.', use_at=True), 'practitioner', '22'), 'R. at 22')
check('other-case filing', cf.bluebook(C('filing', title='Compl.', case_name='Parsell v. Shell Oil Co.', case_cite='421 F. Supp. 1275 (D. Conn. 1976)', docket='Civ. No. B-700'), 'practitioner', '5'),
      'Compl. at 5, *Parsell v. Shell Oil Co.*, 421 F. Supp. 1275 (D. Conn. 1976) (Civ. No. B-700)')

# ---------------- APA 7
walker = C('book', authors=[P('Matthew', 'Walker')], title='Why We Sleep: Unlocking the Power of Sleep and Dreams', publisher='Scribner', date='2017')
check('APA book', cf.apa_reference(walker), 'Walker, M. (2017). *Why we sleep: Unlocking the power of sleep and dreams*. Scribner.')
check('APA in-text', cf.apa_intext(walker), '(Walker, 2017)')
check('APA in-text page', cf.apa_intext(walker, '12'), '(Walker, 2017, p. 12)')
check('APA narrative', cf.apa_intext(walker, narrative=True), 'Walker (2017)')
check('APA article', cf.apa_reference(porter),
      'Porter, E. G., & Watts, K. A. (2016). Visual rulemaking. *New York University Law Review*, *91*(5), 1183–1260.')
check('APA in-text two authors', cf.apa_intext(porter), '(Porter & Watts, 2016)')
check('APA narrative two authors', cf.apa_intext(porter, narrative=True), 'Porter and Watts (2016)')
check('APA three authors et al.', cf.apa_intext(lilly, '88-103'), '(Lilly et al., 2012, pp. 88–103)')
check('APA article with DOI', cf.apa_reference(C('journal', authors=[P('Jane', 'Doe')], title='A Study of DNA in Courts', journal='Journal of Forensic Law',
      volume='12', issue='3', first_page='45', last_page='67', date='2020', doi='10.1000/xyz123')),
      'Doe, J. (2020). A study of DNA in courts. *Journal of Forensic Law*, *12*(3), 45–67. https://doi.org/10.1000/xyz123')
check('APA chapter', cf.apa_reference(kim),
      'Kim, S. H. (2012). The ethics of in-house practice. In L. C. Levin & L. Mather (Eds.), *Lawyers in practice: Ethical decision making in context* (pp. 197–220). University of Chicago Press.')
check('APA webpage', cf.apa_reference(manjoo),
      'Manjoo, F. (2011, January 11). *Why you should never, ever use two spaces after a period*. Slate. https://slate.com/technology/2011/01/two-spaces.html')
check('APA news online', cf.apa_reference(savage),
      'Savage, C. (2014, November 14). U.N. commission presses U.S. on torture. *The New York Times*. https://www.nytimes.com/2014/11/14/world/europe/un-commission-presses-us-on-torture.html')
check('APA report, org author = publisher', cf.apa_reference(C('report', authors=[ORG('Pew Research Center')], title='The State of American Jobs',
      publisher='Pew Research Center', date='2016', url='https://www.pewresearch.org/jobs')),
      'Pew Research Center. (2016). *The state of American jobs*. https://www.pewresearch.org/jobs')
check('APA report sentence case keeps acronym-ish words', cf.apa_reference(C('report', authors=[ORG('National Institute of Mental Health')],
      title='Anxiety Disorders', title_apa='Anxiety disorders', number='NIH Publication No. 09-3879', date='2009')),
      'National Institute of Mental Health. (2009). *Anxiety disorders* (NIH Publication No. 09-3879).')
check('APA no date', cf.apa_intext(C('webpage', authors=[ORG('American Bar Association')], title='About Us', site='ABA')), '(American Bar Association, n.d.)')
check('APA case reference', cf.apa_reference(wayfair), '*South Dakota v. Wayfair, Inc.*, 138 S. Ct. 2080 (2018).')
check('APA case in-text', cf.apa_intext(wayfair), '(*South Dakota v. Wayfair, Inc.*, 2018)')
check('APA statute in-text', cf.apa_intext(C('statute', name='Americans with Disabilities Act of 1990', title_no='42', code='U.S.C.', section='12101', date='1990')),
      '(Americans with Disabilities Act of 1990, 1990)')
check('APA 21+ authors', cf.Runs().r(cf.apa_names([P('A', 'N%d' % k) for k in range(1, 23)])),
      ', '.join('N%d, A.' % k for k in range(1, 20)) + ', . . . N22, A.')
check('APA initials hyphenated', cf.Runs().r(cf.apa_name(P('Jean-Paul', 'Sartre'))), 'Sartre, J.-P.')

ok = sum(1 for _, good, _, _ in CASES if good)
for label, good, got, want in CASES:
    if not good:
        print('FAIL', label)
        print('   got: ', got)
        print('   want:', want)
print('%d/%d passed' % (ok, len(CASES)))
sys.exit(0 if ok == len(CASES) else 1)
