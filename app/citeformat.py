"""Citation formatting for ReWord: Bluebook-style legal citation and APA 7th edition. Standard library only.

A citation is a source type plus a dict of fields (see TYPES). This module turns it into formatted text:

    bluebook(c, typeface, pin)          full citation (no final period; the caller adds signals, parentheticals, period)
    bluebook_short(c, typeface, pin, note)   short form (supra note N where the rules allow supra)
    bluebook_id(c, pin, cap)            Id. / id. with the right pincite form
    apa_reference(c)                    APA 7 reference-list entry (with its final period)
    apa_intext(c, pin, narrative)       APA 7 in-text citation, e.g. (Walker, 2017, p. 12) or Walker (2017)

typeface is "lawreview" (academic legal documents, citations in footnotes: large and small caps for books,
periodical titles, constitutions, rules...) or "practitioner" (briefs, memos: italics only). The rules follow
The Indigo Book 2.0 (2023 revision; CC0), especially T19 for the law review typeface. See
docs/citation-rules.md for what is covered.

Formatted text is a list of runs: (text, fmt) with fmt '' (roman), 'i' (italic) or 'sc' (large and small caps).
to_md() writes ReWord's Markdown (*italic*, [x]{.smallcaps}); to_html() is for previews; to_pandoc() builds
Pandoc AST inlines for the build.
"""
import json
import re
from pathlib import Path

# ------------------------------------------------------------------ runs

class Runs(list):
    def add(self, text, fmt=''):
        if text:
            if self and self[-1][1] == fmt:
                self[-1] = (self[-1][0] + text, fmt)
            else:
                self.append((text, fmt))
        return self

    def r(self, text): return self.add(text, '')
    def i(self, text): return self.add(text, 'i')
    def sc(self, text): return self.add(text, 'sc')

    def extend_runs(self, other):
        for t, f in other:
            self.add(t, f)
        return self

    def plain(self):
        return ''.join(t for t, _ in self)


def md_runs(md):
    """Parse ReWord's inline Markdown subset (used in rich fields such as case history) into runs."""
    out = Runs()
    md = md or ''
    pos = 0
    pat = re.compile(r'\[((?:\\.|[^\]\\])*)\]\{\.smallcaps\}|\*((?:\\.|[^*\\])+)\*|_((?:\\.|[^_\\])+)_')
    unesc = lambda s: re.sub(r'\\(.)', r'\1', s)      # noqa: E731
    for m in pat.finditer(md):
        out.r(unesc(md[pos:m.start()]))
        if m.group(1) is not None:
            out.sc(unesc(m.group(1)))
        else:
            out.i(unesc(m.group(2) or m.group(3)))
        pos = m.end()
    out.r(unesc(md[pos:]))
    return out


_MD_SPECIAL = re.compile(r'([\\*_\[\]`<>@$^~|#])')


def to_md(runs):
    out = []
    for text, fmt in runs:
        e = _MD_SPECIAL.sub(r'\\\1', text)
        if fmt == 'i':
            lead = len(e) - len(e.lstrip()); trail = len(e) - len(e.rstrip())
            core = e.strip()
            out.append(e[:lead] + ('*' + core + '*' if core else '') + (e[len(e) - trail:] if trail else ''))
        elif fmt == 'sc':
            out.append('[' + e + ']{.smallcaps}')
        else:
            out.append(e)
    return ''.join(out)


def to_html(runs):
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')      # noqa: E731
    out = []
    for text, fmt in runs:
        if fmt == 'i': out.append('<i>' + esc(text) + '</i>')
        elif fmt == 'sc': out.append('<span class="sc">' + esc(text) + '</span>')
        else: out.append(esc(text))
    return ''.join(out)


def to_pandoc(runs):
    """Pandoc JSON inlines (Str/Space, wrapped in Emph or SmallCaps)."""
    def words(text):
        out = []
        for k, part in enumerate(re.split(r'( +)', text)):
            if not part:
                continue
            out.append({'t': 'Space'} if part.startswith(' ') else {'t': 'Str', 'c': part})
        return out
    out = []
    for text, fmt in runs:
        w = words(text)
        if not w:
            continue
        if fmt == 'i': out.append({'t': 'Emph', 'c': w})
        elif fmt == 'sc': out.append({'t': 'SmallCaps', 'c': w})
        else: out.extend(w)
    return out


# ------------------------------------------------------------------ source types and their fields
# kind: text | rich (italics/small caps allowed) | authors | date | select | bool
# Each field: (key, label, kind, hint).  "*" in a label marks what the formatter needs at minimum.

F = lambda key, label, kind='text', hint='', **kw: dict(key=key, label=label, kind=kind, hint=hint, **kw)   # noqa: E731

AUTHORS = F('authors', 'Authors', 'authors', 'Add each author. For an organization as author, use the organization line.')
URL = F('url', 'Link (URL)', 'text', 'Optional for printed sources; needed for web sources.')
HEREINAFTER = F('hereinafter', 'Short title (hereinafter)', 'text',
                'Optional. Used in short forms instead of the author, e.g. when you cite two works by one author.')
TITLE_APA = F('title_apa', 'Title in sentence case (APA)', 'text',
              'APA capitalizes only the first word, the first word after a colon, and proper nouns. Leave blank to use an automatic version (check it).')

TYPES = {
    # ---------------- core legal
    'case': dict(label='Case', group='Legal', fields=[
        F('name', 'Case name*', 'rich', 'As cited, with Bluebook abbreviations: Leonard v. Pepsico, Inc.'),
        F('short_name', 'Short name', 'text', 'For short forms: usually the first party (not a government). Default: first party.'),
        F('volume', 'Volume'), F('reporter', 'Reporter', hint='F.3d, S. Ct., U.S., F. Supp. 2d, S.W.3d …'),
        F('first_page', 'First page'),
        F('database', 'Database cite (unreported)', hint='e.g. 2013 WL 5811261 (instead of volume/reporter/page)'),
        F('docket', 'Docket number', hint='For unreported or pending cases: No. 13-7451'),
        F('court', 'Court', hint='8th Cir., S.D.N.Y., Mo. Ct. App. Leave blank when the reporter shows the court (U.S., S. Ct.).'),
        F('date', 'Year or full date*', 'date', 'Year for reported cases; full date for unreported ones.'),
        F('parallel', 'Parallel citation', hint='Optional, e.g. 830 S.E.2d 169'),
        F('weight', 'Weight of authority', hint='Optional: en banc, per curiam, Marshall, J., dissenting'),
        F('history', 'Subsequent history', 'rich', "Optional: aff'd, 210 F.3d 88 (2d Cir. 2000)"),
        URL]),
    'statute': dict(label='Statute', group='Legal', fields=[
        F('name', 'Name of the act', hint='Optional: Civil Rights Act of 1964'),
        F('title_no', 'Title number', hint='42 for 42 U.S.C.; blank for codes without titles'),
        F('code', 'Code*', hint='U.S.C., Mo. Rev. Stat., Fla. Stat., N.Y. Gen. Bus. Law'),
        F('section', 'Section*', hint='1983 · for several sections use an en dash: 2000e–2000e-17'),
        F('publisher', 'Publisher', hint='Only for unofficial codes: West, LexisNexis, McKinney'),
        F('date', 'Year', 'date', 'Optional for the current U.S. Code; required for state codes.'),
        F('pub_law', 'Public Law number', hint='For session laws: 111-148'),
        F('stat', 'Statutes at Large', hint='For session laws: 124 Stat. 119'),
        F('status', 'Status', hint='Optional: repealed 2015'),
        URL]),
    'regulation': dict(label='Regulation', group='Legal', fields=[
        F('name', 'Name', hint='Optional: the regulation’s or agency’s name'),
        F('title_no', 'Title number', hint='40 for 40 C.F.R.'),
        F('code', 'Code', hint='C.F.R. (default), Mo. Code Regs. Ann. tit. 15'),
        F('section', 'Section or part', hint='52.21, or pt. 130'),
        F('fed_reg', 'Federal Register cite', hint='For rules not yet codified or proposed: 88 Fed. Reg. 1234'),
        F('codified_at', 'To be codified at', hint='Proposed rules: 40 C.F.R. pt. 63'),
        F('date', 'Year or date*', 'date', 'Year of the C.F.R. edition, or the Federal Register date'),
        URL]),
    'constitution': dict(label='Constitution', group='Legal', fields=[
        F('jurisdiction', 'Jurisdiction*', hint='U.S., Mo., Ga. (state abbreviation)'),
        F('provision', 'Provision*', hint='art. I, § 8, cl. 3   or   amend. XIV, § 1'),
        F('status', 'Status', hint='Optional: repealed 1933')]),
    'rule': dict(label='Court rule', group='Legal', fields=[
        F('source', 'Rules*', hint='Fed. R. Civ. P., Fed. R. Evid., Mo. Sup. Ct. R.'),
        F('number', 'Rule number*', hint='12(b)(6)'), URL]),
    'restatement': dict(label='Restatement, model code, uniform act', group='Legal', fields=[
        F('title', 'Title*', hint='Restatement (Second) of Torts · U.C.C. · Model Penal Code · Unif. Trade Secrets Act'),
        F('section', 'Section*', hint='402A, or 2-207'),
        F('publisher', 'Publisher', hint='Am. L. Inst. · Unif. L. Comm’n'),
        F('date', 'Year', 'date'), URL]),
    # ---------------- academic
    'journal': dict(label='Journal or law review article', group='Academic', fields=[
        AUTHORS,
        F('designation', 'Student piece', hint='Optional: Note, Comment'),
        F('title', 'Article title*', 'rich'), TITLE_APA,
        F('journal', 'Journal name*', hint='Full name: Harvard Law Review'),
        F('journal_abbrev', 'Journal abbreviation (Bluebook)', hint='Harv. L. Rev. Leave blank to use an automatic abbreviation.'),
        F('volume', 'Volume'), F('issue', 'Issue'),
        F('first_page', 'First page'), F('last_page', 'Last page'),
        F('article_number', 'Article number', hint='For journals that number articles instead of pages: e2422779122'),
        F('date', 'Year*', 'date'), F('doi', 'DOI', hint='10.1000/xyz123'), URL, HEREINAFTER]),
    'book': dict(label='Book', group='Academic', fields=[
        AUTHORS,
        F('editors', 'Editors', 'authors', 'For an edited book with no single author.'),
        F('translator', 'Translator'),
        F('title', 'Title*', 'rich'), TITLE_APA,
        F('edition', 'Edition', hint='2, 3, rev.'), F('volume', 'Volume (multi-volume works)'),
        F('publisher', 'Publisher'), F('date', 'Year*', 'date'),
        F('doi', 'DOI'), URL, HEREINAFTER]),
    # One edited book holding any number of its chapters. Each chapter is cited as tag + chapter
    # ({.cite tag="book" chapter="ch-id"}) and formats as a chapter in that book (see edited_chapter);
    # citing the book with no chapter gives the whole book. Every field of the book is shared by its chapters.
    'edited_book': dict(label='Chapter(s) in edited book', group='Academic', fields=[
        F('editors', 'Editors*', 'authors', 'The book’s editors.'),
        F('title', 'Book title*', 'rich'),
        F('title_apa', 'Book title in sentence case (APA)', 'text', TITLE_APA['hint']),
        F('edition', 'Edition'), F('volume', 'Volume (multi-volume works)'),
        F('publisher', 'Publisher'), F('date', 'Year*', 'date'),
        F('doi', 'DOI (the book)', hint='A chapter’s own DOI goes with the chapter.'), URL,
        F('hereinafter', 'Short title for the whole book (hereinafter)', 'text', HEREINAFTER['hint']),
        F('chapters', 'Chapters', 'chapters', 'Each chapter you cite. When you cite this book, you pick the chapter.', fields=[
            AUTHORS,
            F('title', 'Chapter title*', 'rich'), TITLE_APA,
            F('first_page', 'First page'), F('last_page', 'Last page'),
            F('doi', 'Chapter DOI'), F('url', 'Chapter link (URL)', hint='Blank = the book’s link.'), HEREINAFTER])]),
    # A single chapter. Kept so older libraries and lookups still format; new chapters go in an edited book.
    'chapter': dict(label='Chapter in an edited book (single)', group='Academic', hidden=True, fields=[
        AUTHORS,
        F('title', 'Chapter title*', 'rich'), TITLE_APA,
        F('editors', 'Editors*', 'authors'),
        F('book_title', 'Book title*', 'rich'),
        F('book_title_apa', 'Book title in sentence case (APA)'),
        F('edition', 'Edition'),
        F('first_page', 'First page'), F('last_page', 'Last page'),
        F('publisher', 'Publisher'), F('date', 'Year*', 'date'),
        F('doi', 'DOI'), URL, HEREINAFTER]),
    # ---------------- web, news, reports
    'news': dict(label='Newspaper or magazine article', group='Web & news', fields=[
        AUTHORS,
        F('designation', 'Designation', hint='Optional: Editorial, Op-Ed, Letter to the Editor'),
        F('title', 'Title*', 'rich'), TITLE_APA,
        F('publication', 'Publication*', hint='New York Times, The New Yorker'),
        F('publication_abbrev', 'Publication abbreviation (Bluebook)', hint='N.Y. Times. Blank = automatic.'),
        F('date', 'Date*', 'date'),
        F('page', 'Page (print)', hint='A1, or 40 for a magazine'),
        F('volume', 'Volume (APA, magazines)'), F('issue', 'Issue (APA, magazines)'),
        URL, HEREINAFTER]),
    'webpage': dict(label='Web page or blog post', group='Web & news', fields=[
        AUTHORS,
        F('title', 'Page title*', 'rich'), TITLE_APA,
        F('site', 'Website name*', hint='Slate, Knight First Amendment Institute'),
        F('site_abbrev', 'Website abbreviation (Bluebook)', hint='Knight First Amend. Inst. Blank = automatic.'),
        F('date', 'Date posted', 'date', 'As shown on the page. Leave blank if there is none.'),
        F('time', 'Time posted', hint='Optional: 6:00 AM'),
        F('last_visited', 'Last visited', 'date', 'Used when the page has no date.'),
        URL, HEREINAFTER]),
    'report': dict(label='Report or white paper', group='Web & news', fields=[
        AUTHORS,
        F('title', 'Title*', 'rich'), TITLE_APA,
        F('number', 'Report number', hint='Optional: Report No. 23-1'),
        F('publisher', 'Publisher', hint='Leave blank when the author published it'),
        F('date', 'Year or date*', 'date'), F('doi', 'DOI'), URL, HEREINAFTER]),
    # ---------------- legislative and litigation
    'bill': dict(label='Bill or resolution', group='Legislative & litigation', fields=[
        F('title', 'Name of the bill', hint='Optional: Paycheck Fairness Act'),
        F('number', 'Bill number*', hint='H.R. 3054 · S. 812 · H.R. Res. 431 · L.D. 3'),
        F('session', 'Congress or session*', hint='117th Cong. · 127th Leg., Reg. Sess.'),
        F('state', 'State (state bills)', hint='Me., Mo.'),
        F('date', 'Year*', 'date'),
        F('status', 'Status', hint='Optional: enacted · as passed by House, Dec. 3, 2014'), URL]),
    'hearing': dict(label='Committee hearing', group='Legislative & litigation', fields=[
        F('title', 'Hearing title*', 'rich', 'Cell Tax Fairness Act of 2008: Hearing on H.R. 5793 Before the Subcomm. on … of the H. Comm. on the Judiciary'),
        F('session', 'Congress or session*', hint='110th Cong.'), F('state', 'State (state hearings)'),
        F('date', 'Year*', 'date'), URL, HEREINAFTER]),
    'committee_report': dict(label='Committee report', group='Legislative & litigation', fields=[
        F('chamber', 'Chamber*', 'select', options=['H.R.', 'S.']),
        F('number', 'Report number*', hint='117-27'),
        F('date', 'Year*', 'date'),
        F('conference', 'Conference report', 'bool'),
        F('reprinted', 'Reprinted in', hint='Optional: 1986 U.S.C.C.A.N. 42, 412'), URL]),
    'filing': dict(label='Court filing (brief, motion, transcript…)', group='Legislative & litigation', fields=[
        F('title', 'Document (abbreviated)*', hint="Pl.'s Mot. Summ. J. · Def.'s Br. · Smith Dep. · Compl."),
        F('ecf', 'ECF number', hint='Optional: 147'),
        F('date', 'Date of the document', 'date', 'Optional; include when it matters.'),
        F('case_name', 'Case (if filed in another case)', 'rich', 'Leave blank for documents in your own case.'),
        F('case_cite', 'That case’s citation or court and date', hint='421 F. Supp. 1275 (D. Conn. 1976)  or  (9th Cir. Apr. 17, 2015)'),
        F('docket', 'That case’s docket number', hint='No. 06-19139'), URL]),
    'record': dict(label='Record citation', group='Legislative & litigation', fields=[
        F('abbrev', 'Record abbreviation*', hint='R. · J.A. · App. · Tr.'),
        F('use_at', 'Write “at” before the page', 'bool', 'R. at 22 (on) or R. 22 (off)', default=True)]),
    # ---------------- anything else
    'other': dict(label='Other (type it yourself)', group='Other', fields=[
        F('text', 'Bluebook citation*', 'rich', 'Typed exactly as it should appear.'),
        F('text_apa', 'APA reference entry', 'rich'),
        F('text_chicago', 'Chicago note', 'rich', 'Optional. Used in Chicago documents; the Bluebook citation is used when blank.'),
        F('intext_apa', 'APA in-text form', hint='Author, Year (without parentheses)'),
        F('short', 'Short form', 'rich'), URL]),
}

GROUPS = ['Legal', 'Academic', 'Web & news', 'Legislative & litigation', 'Other']

# Bluebook does not allow supra for these (Indigo R6.2.3): primary sources, restatements, regulations.
NO_SUPRA = {'case', 'statute', 'regulation', 'constitution', 'rule', 'restatement', 'bill', 'committee_report', 'filing', 'record'}
# The table-of-authorities group each type lands in (briefs).
TOA_GROUP = {'case': 'case', 'statute': 'statute', 'constitution': 'constitution', 'rule': 'rule',
             'restatement': 'other', 'regulation': 'regulation'}
LEGAL_TYPES = {'case', 'statute', 'regulation', 'constitution', 'rule', 'restatement', 'bill', 'hearing',
               'committee_report', 'filing', 'record'}


def schema():
    return {'types': TYPES, 'groups': GROUPS}


# ------------------------------------------------------------------ small helpers

# Fields saved under another type's name (a source typed in by hand or by another tool, or one whose type was
# changed): read them where this type expects them, so the citation still formats in full.
ALIASES = {('news', 'publication'): 'site', ('news', 'publication_abbrev'): 'site_abbrev', ('news', 'page'): 'first_page',
           ('webpage', 'site'): 'publication', ('webpage', 'site_abbrev'): 'publication_abbrev'}


def g(c, key):
    f = c.get('fields') or {}
    v = f.get(key, '')
    if not v and (c.get('type'), key) in ALIASES:
        v = f.get(ALIASES[(c.get('type'), key)], '')
    if not v and key == 'translator' and isinstance(f.get('translators'), list):
        v = ' & '.join(bb_name(p) for p in f['translators'] if isinstance(p, dict) and (p.get('family') or p.get('literal')))
    if isinstance(v, str):
        return v.strip()
    return v


def _close(text):
    """A sentence of a reference entry: the text with a period, unless it already ends with one (Inc., n.d.)."""
    t = (text or '').rstrip()
    return t if not t or t[-1] in '.?!' else t + '.'


MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']
BB_MONTHS = ['Jan.', 'Feb.', 'Mar.', 'Apr.', 'May', 'June', 'July', 'Aug.', 'Sept.', 'Oct.', 'Nov.', 'Dec.']


def parse_date(s):
    """'2021', '2021-08', '2021-08-19' -> (y, m, d) with None for missing parts; anything else -> None."""
    m = re.fullmatch(r'\s*(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?\s*', s or '')
    if not m:
        return None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None), (int(m.group(3)) if m.group(3) else None)


def normalize_date(s):
    """'June 23, 2021', 'Jun. 2021', '23 June 2021', '2021-6-3' -> '2021-06-23' / '2021-06' / '2021-06-03'.
    Anything else is kept as typed (for example 'n.d.' or 'current through July 22, 2021')."""
    s = (s or '').strip()
    d = parse_date(s)
    if d:
        y, mo, da = d
        return '%04d' % y + ('-%02d' % mo if mo else '') + ('-%02d' % da if da else '')
    names = [m[:3].lower() for m in MONTHS]
    m = re.fullmatch(r'([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})', s) or None
    if m and m.group(1)[:3].lower() in names:
        return '%s-%02d-%02d' % (m.group(3), names.index(m.group(1)[:3].lower()) + 1, int(m.group(2)))
    m = re.fullmatch(r'(\d{1,2})\s+([A-Za-z]{3,})\.?,?\s+(\d{4})', s)
    if m and m.group(2)[:3].lower() in names:
        return '%s-%02d-%02d' % (m.group(3), names.index(m.group(2)[:3].lower()) + 1, int(m.group(1)))
    m = re.fullmatch(r'([A-Za-z]{3,})\.?,?\s+(\d{4})', s)
    if m and m.group(1)[:3].lower() in names:
        return '%s-%02d' % (m.group(2), names.index(m.group(1)[:3].lower()) + 1)
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)            # US style 6/23/2021
    if m:
        return '%s-%02d-%02d' % (m.group(3), int(m.group(1)), int(m.group(2)))
    return s


def bb_date(s, full=True):
    """Bluebook date: Aug. 19, 2021 / Aug. 2021 / 2021.  full=False gives the year only."""
    d = parse_date(s)
    if not d:
        return s or ''
    y, mo, da = d
    if not full or not mo:
        return str(y)
    return BB_MONTHS[mo - 1] + (' %d,' % da if da else '') + ' %d' % y


def year_of(s):
    d = parse_date(s)
    if d:
        return str(d[0])
    m = re.search(r'\b(1[5-9]\d\d|20\d\d)\b', s or '')
    return m.group(1) if m else ''


def apa_date(s, full=False):
    d = parse_date(s)
    if not d:
        return s or 'n.d.'
    y, mo, da = d
    if full and mo:
        return '%d, %s' % (y, MONTHS[mo - 1]) + (' %d' % da if da else '')
    return str(y)


def ordinal_bb(ed):
    """Bluebook edition ordinals: 2d, 3d, 4th … (rev. stays as typed)."""
    if not re.fullmatch(r'\d+', ed or ''):
        return ed
    n = int(ed)
    if 10 <= n % 100 <= 20: suf = 'th'
    else: suf = {1: 'st', 2: 'd', 3: 'd'}.get(n % 10, 'th')
    return '%d%s' % (n, suf)


def ordinal_apa(ed):
    if not re.fullmatch(r'\d+', ed or ''):
        return ed
    n = int(ed)
    if 10 <= n % 100 <= 20: suf = 'th'
    else: suf = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return '%d%s' % (n, suf)


def people(c, key='authors'):
    v = (c.get('fields') or {}).get(key) or []
    return [p for p in v if isinstance(p, dict) and (p.get('family') or p.get('literal') or p.get('given'))]


def bb_name(p):
    if p.get('literal'):
        return p['literal'].strip()
    n = ' '.join(x for x in (p.get('given', '').strip(), p.get('family', '').strip()) if x)
    return n + (', ' + p['suffix'].strip() if p.get('suffix') else '')


def bb_names(ps):
    """Bluebook author list: A; A & B; three or more: A et al. (Indigo R28.2.2, R30.2.3)."""
    names = [bb_name(p) for p in ps]
    if len(names) <= 2:
        return ' & '.join(names)
    return names[0] + ' et al.'


def family(p):
    return (p.get('literal') or p.get('family') or p.get('given') or '').strip()


def short_names(ps):
    """Surnames for short forms: Skinner; Nimmer & Nimmer; Lilly et al."""
    f = [family(p) for p in ps]
    if len(f) <= 2:
        return ' & '.join(f)
    return f[0] + ' et al.'


def initials(given):
    """'Jane Ann' -> 'J. A.'; 'Jean-Paul' -> 'J.-P.'; 'J.R.R.' -> 'J. R. R.'"""
    out = []
    for part in re.split(r'\s+', (given or '').strip()):
        if not part:
            continue
        hy = [h for h in part.split('-') if h]
        bits = []
        for h in hy:
            letters = re.findall(r'[A-Za-zÀ-ÿ]', h)
            if re.fullmatch(r'([A-Za-z]\.)+', h):        # already initials
                bits.append(' '.join(x + '.' for x in letters))
            elif letters:
                bits.append(letters[0].upper() + '.')
        out.append('-'.join(bits))
    return ' '.join(out)


def apa_name(p):
    if p.get('literal'):
        return p['literal'].strip()
    s = family(p)
    ini = initials(p.get('given', ''))
    if ini:
        s += ', ' + ini
    if p.get('suffix'):
        s += ', ' + p['suffix'].strip()
    return s


def apa_names(ps):
    """APA 7 reference list: up to 20 authors, '&' before the last; 21+ = first 19, …, last."""
    n = [apa_name(p) for p in ps]
    if not n:
        return ''
    if len(n) == 1:
        return n[0]
    if len(n) <= 20:
        return ', '.join(n[:-1]) + ', & ' + n[-1]
    return ', '.join(n[:19]) + ', . . . ' + n[-1]


def apa_editor_names(ps):
    """In chapter entries editors are written 'L. C. Levin & L. Mather'."""
    def one(p):
        if p.get('literal'):
            return p['literal'].strip()
        return ' '.join(x for x in (initials(p.get('given', '')), family(p)) if x)
    n = [one(p) for p in ps]
    if len(n) <= 2:
        return ' & '.join(n)
    return ', '.join(n[:-1]) + ', & ' + n[-1]


def intext_names(ps, narrative=False):
    """APA in-text: Walker; Smith & Jones (narrative: Smith and Jones); three or more: Smith et al."""
    f = [family(p) for p in ps]
    if not f:
        return ''
    if len(f) == 1:
        return f[0]
    if len(f) == 2:
        return f[0] + (' and ' if narrative else ' & ') + f[1]
    return f[0] + ' et al.'


SMALL = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so', 'yet', 'as', 'at', 'by', 'in', 'of', 'off', 'on',
         'per', 'to', 'up', 'via', 'v.', 'vs.', 'with', 'from', 'into', 'over'}


# Words APA keeps capitalized that a machine can recognize; other proper nouns need the APA title field.
PROPER = set('''American Americans English British European African Asian Canadian Mexican Chinese Japanese Indian
Native Black Latino Latina Latinx Hispanic Christian Jewish Muslim Catholic Protestant Congress Constitution
January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday I'''.split())
VERB_MONTHS = {'May', 'March'}


def sentence_case(title, start=True):
    """A best guess at APA sentence case. Keeps words with capitals after the first letter (DNA, McDonald),
    capitalizes the first word and the first word after a colon. Proper nouns can't be detected: check it.
    start=False continues a title that began in an earlier run (no capital for its first word)."""
    words = re.split(r'(\s+)', title or '')
    out, cap_next = [], start
    for k, w in enumerate(words):
        if not w or w.isspace():
            out.append(w); continue
        core = re.sub(r'^[^\w]+|[^\w]+$', '', w)
        parts = [x for x in re.split(r'[-–/]', core) if x]
        proper = core.rstrip('.').title() in PROPER
        if proper and core in VERB_MONTHS:          # "May be next", "March on": a month only beside a number (May 2021)
            near = [x for x in (words[k - 2] if k > 1 else '', words[k + 2] if k + 2 < len(words) else '')]
            proper = any(re.match(r'\d', x) for x in near)
        keep = any(len(x) > 1 and x[1:] != x[1:].lower() for x in parts) or proper
        if keep:
            nw = w
        elif cap_next:
            nw = w[:1].upper() + w[1:].lower() if core else w
        else:
            nw = w.lower()
        out.append(nw)
        cap_next = bool(re.search(r'[:?!—]$', w))
    return ''.join(out)


# ------------------------------------------------------------------ abbreviations (Indigo Book tables)

_ABBR = None


def abbreviations():
    global _ABBR
    if _ABBR is None:
        try:
            _ABBR = json.loads((Path(__file__).parent / 'data' / 'abbreviations.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _ABBR = {'t11': [], 't12': [], 't15': [], 't18': []}
    return _ABBR


def _word_table(periodical=True):
    table = {}
    for words, ab in abbreviations().get('t11', []):
        for w in [x.strip() for x in words.split(',')]:
            if not w:
                continue
            key = w.lower()
            # T11 lists University twice (Univ. and U.); periodical titles use U.
            if key in table and not (periodical and len(ab) < len(table[key])):
                continue
            table[key] = ab
    for words, ab in abbreviations().get('t12', []):
        table[words.lower()] = ab
    for words, ab in abbreviations().get('t15', []):
        for w in [x.strip() for x in words.split(',')]:
            table[w.lower()] = ab
    return table


def abbreviate_periodical(name):
    """Harvard Law Review -> Harv. L. Rev. (Indigo R30.3: T15 institutions, then T11/T12 words; drop a, at, in, of, the)."""
    if not name:
        return ''
    table = _word_table(True)
    toks = re.findall(r"[\w’'&.-]+|[,:;]", name)
    out = []
    i = 0
    lower = [t.lower() for t in toks]
    while i < len(toks):
        hit = None
        for n in (4, 3, 2):            # multi-word institution names first (William & Mary, New York)
            if i + n <= len(toks):
                phrase = ' '.join(lower[i:i + n])
                if phrase in table:
                    hit = (table[phrase], n); break
        if hit:
            out.append(hit[0]); i += hit[1]; continue
        t, lt = toks[i], lower[i]
        if lt in ('a', 'at', 'in', 'of', 'the') and out:
            i += 1; continue
        if lt in (',', ':', ';'):
            i += 1; continue
        if lt == 'and':
            out.append('&'); i += 1; continue
        if lt == 'law' and not out:     # Law is not abbreviated when it is the first word
            out.append(t); i += 1; continue
        ab = table.get(lt)
        if ab is None and lt.endswith('s') and lt[:-1] in table:
            ab = table[lt[:-1]]                # plurals: Departments -> Dep'ts, but Sciences -> Sci. (T11 note)
            ab = ab if ab.endswith('.') else ab + 's'
        out.append(ab or t)
        i += 1
    # Close up adjacent single capitals: "L. J." -> "L.J." (Indigo R7 spacing)
    s = ' '.join(out)
    s = re.sub(r'\b([A-Z])\. (?=[A-Z]\.(?:\s|$))', r'\1.', s)
    return s


# ------------------------------------------------------------------ Bluebook

SCOTUS_REPORTERS = {'U.S.', 'S. Ct.', 'S.Ct.', 'L. Ed.', 'L. Ed. 2d', 'U.S.L.W.'}
HISTORY_PHRASES = [
    "rev'd on other grounds", "rev’d on other grounds", "rev'd sub nom.", "rev’d sub nom.", "aff'd sub nom.", "aff’d sub nom.",
    "aff'd", "aff’d", "rev'd", "rev’d", "aff'g", "aff’g", "rev'g", "rev’g", 'cert. denied', 'cert. granted',
    'petition for cert. filed', 'vacated as moot', 'vacated', 'overruled by', 'abrogated by', 'superseded by statute',
    'as recognized in', 'modified', 'sub nom.', 'reh’g denied', "reh'g denied", 'appeal dismissed']


def history_runs(md):
    if re.search(r'[*_]|\{\.smallcaps\}', md or ''):
        return md_runs(md)                # she formatted it herself
    out = Runs()
    text = md or ''
    pat = re.compile('|'.join(re.escape(p) for p in sorted(HISTORY_PHRASES, key=len, reverse=True)))
    pos = 0
    for m in pat.finditer(text):
        out.r(text[pos:m.start()]); out.i(m.group(0)); pos = m.end()
    out.r(text[pos:])
    return out


def pin_after(pin, sep=', '):
    return (sep + pin) if pin else ''


def is_span(sec):
    """Several sections (§§): an en dash span, a list, 'to', or et seq. A hyphen alone is part of a section
    number in most codes (13-90-107, 2000e-2), so spans are written with an en dash: 301–399i."""
    return bool(re.search(r'–|,|\bto\b|et seq', sec or ''))


def is_lr(typeface):
    return typeface == 'lawreview'


def bluebook(c, typeface='practitioner', pin='', in_text=False):
    """Full citation. in_text: the citation sits in a textual sentence of a law review (case names italic there)."""
    if g(c, '_override_bluebook'):
        return md_runs(g(c, '_override_bluebook'))
    t = c.get('type', 'other')
    fn = _BB.get(t, _bb_other)
    lr = is_lr(typeface) and not in_text
    return fn(c, lr, pin)


def _sc_or(lr, out, text, otherwise=''):
    """Small caps in law review style, else the given practitioner format ('' roman, 'i' italic)."""
    if lr: out.sc(text)
    else: out.add(text, otherwise)


# A Westlaw or Lexis cite typed at the end of the docket number: No. 25-CR-239, 2025 WL 2427700
EMBEDDED_DB = re.compile(r'\b(\d{4}\s+(?:WL|(?:U\.S\.\s*(?:Dist\.|App\.)\s*|[A-Z][\w.]*\s+)?LEXIS)\s+\d+)\s*$')


def _database_of(c):
    """The case's database cite (2013 WL 5811261): its own field, or the end of its docket number."""
    if g(c, 'database'):
        return g(c, 'database')
    m = EMBEDDED_DB.search(g(c, 'docket')) if not g(c, 'volume') else None
    return m.group(1) if m else ''


def _star_pin(pin):
    """Pincites in a database cite are star pages: at *7 (a page range too: at *7–8)."""
    return ', at *' + pin.lstrip('*') if re.fullmatch(r'\*?\d+(?:[-–]\*?\d+)?', pin) else ', ' + pin


def _bb_case(c, lr, pin):
    out = Runs()
    name = md_runs(g(c, 'name'))
    for text, fmt in name:
        out.add(text, '' if lr else 'i')
    out.r(', ')
    rep = g(c, 'reporter')
    if g(c, 'database'):
        if g(c, 'docket'):
            out.r(g(c, 'docket') + ', ')
        out.r(g(c, 'database'))
        if pin:
            out.r(_star_pin(pin))
    else:
        cite = ' '.join(x for x in (g(c, 'volume'), rep, g(c, 'first_page')) if x)
        if g(c, 'docket') and not g(c, 'volume'):
            out.r(g(c, 'docket') + (' ' if cite else ''))
        out.r(cite)
        if pin:
            out.r(_star_pin(pin) if _database_of(c) else ', ' + pin)
        if g(c, 'parallel'):
            out.r(', ' + g(c, 'parallel'))
    court = g(c, 'court')
    if rep in SCOTUS_REPORTERS and court in ('', 'U.S.', 'U.S. Sup. Ct.', 'S. Ct.'):
        court = ''
    unreported = bool(g(c, 'database') or (g(c, 'docket') and not g(c, 'volume')))
    date = bb_date(g(c, 'date'), full=unreported)
    paren = ' '.join(x for x in (court, date) if x)
    if paren:
        out.r(' (' + paren + ')')
    if g(c, 'weight'):
        out.r(' (' + g(c, 'weight') + ')')
    if g(c, 'history'):
        out.r(', ').extend_runs(history_runs(g(c, 'history')))
    return out


US_CODES = {'U.S.C.', 'U.S.C.A.', 'U.S.C.S.', 'I.R.C.'}


def _bb_statute(c, lr, pin):
    out = Runs()
    if g(c, 'name'):
        out.r(g(c, 'name') + ', ')
    code, sec = g(c, 'code'), g(c, 'section')
    if code and sec:
        if g(c, 'title_no'):
            out.r(g(c, 'title_no') + ' ')
        if lr and code not in US_CODES:
            out.sc(code)
        else:
            out.r(code)
        sym = '§§' if is_span(sec) else '§'
        out.r(' ' + sym + ' ' + sec + (pin if pin.startswith('(') else pin_after(pin)))
        paren = ' '.join(x for x in (g(c, 'publisher'), bb_date(g(c, 'date'), full=False)) if x)
        if paren:
            out.r(' (' + paren + ')')
        if g(c, 'pub_law') and g(c, 'stat'):
            out.r(', Pub. L. No. ' + g(c, 'pub_law') + ', ' + g(c, 'stat'))
    elif g(c, 'pub_law'):
        out.r('Pub. L. No. ' + g(c, 'pub_law') + pin_after(pin) + (', ' + g(c, 'stat') if g(c, 'stat') else ''))
        y = bb_date(g(c, 'date'), full=False)
        if y and not re.search(r'\b' + y + r'\b', g(c, 'name')):
            out.r(' (' + y + ')')
    if g(c, 'status'):
        out.r(' (' + g(c, 'status') + ')')
    return out


def _bb_regulation(c, lr, pin):
    out = Runs()
    if g(c, 'name'):
        out.r(g(c, 'name') + ', ')
    if g(c, 'fed_reg') and not g(c, 'section'):
        out.r(g(c, 'fed_reg') + pin_after(pin))
        when = bb_date(g(c, 'date'))
        extra = ' (proposed %s)' % when if g(c, 'codified_at') else (' (%s)' % when if when else '')
        out.r(extra)
        if g(c, 'codified_at'):
            out.r(' (to be codified at ' + g(c, 'codified_at') + ')')
        return out
    code = g(c, 'code') or 'C.F.R.'
    sec = g(c, 'section')
    if g(c, 'title_no'):
        out.r(g(c, 'title_no') + ' ')
    out.r(code + ' ')
    out.r(sec if sec.startswith('pt.') else '§ ' + sec)
    out.r(pin if pin.startswith('(') else pin_after(pin))
    y = bb_date(g(c, 'date'), full=False)
    if y:
        out.r(' (' + y + ')')
    return out


def _bb_constitution(c, lr, pin):
    out = Runs()
    _sc_or(lr, out, (g(c, 'jurisdiction') or 'U.S.') + ' Const.')
    prov = g(c, 'provision')
    if prov:
        out.r(' ' + prov)
    if pin:
        out.r((', ' if prov else ' ') + pin)
    if g(c, 'status'):
        out.r(' (' + g(c, 'status') + ')')
    return out


def _bb_rule(c, lr, pin):
    out = Runs()
    _sc_or(lr, out, g(c, 'source'))
    out.r(' ' + g(c, 'number') + (pin if pin.startswith('(') else pin_after(pin)))
    return out


def _bb_restatement(c, lr, pin):
    out = Runs()
    _sc_or(lr, out, g(c, 'title'))
    sec = g(c, 'section')
    out.r(' § ' + sec + (pin if pin.startswith('(') or not pin else ' ' + pin if pin.startswith('cmt') else pin_after(pin)))
    pub, y = g(c, 'publisher'), bb_date(g(c, 'date'), full=False)
    if pub or y:
        out.r(' (')
        if pub:
            _sc_or(lr, out, pub)
            if y: out.r(' ')
        out.r(y + ')')
    return out


def _authors(c, out, lr_sc=False):
    names = bb_names(people(c))
    if names:
        if lr_sc: out.sc(names + ', ')
        else: out.r(names + ', ')
    return bool(names)


def _hereinafter(c, out, fmt):
    h = g(c, 'hereinafter')
    if h:
        out.r(' [hereinafter ').add(h, fmt).r(']')


def _bb_journal(c, lr, pin):
    out = Runs()
    _authors(c, out)
    if g(c, 'designation'):
        out.r(g(c, 'designation') + ', ')
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'i')
    out.r(', ')
    if g(c, 'volume'):
        out.r(g(c, 'volume') + ' ')
    journal = g(c, 'journal_abbrev') or abbreviate_periodical(g(c, 'journal'))
    _sc_or(lr, out, journal)
    page = g(c, 'first_page') or g(c, 'article_number')
    if page:
        out.r(' ' + page + pin_after(pin))
    elif pin:                                    # published online without pages yet
        out.r(', at ' + pin)
    y = bb_date(g(c, 'date'), full=False)
    if y:
        out.r(' (' + y + ')')
    if g(c, 'url') and not g(c, 'doi'):
        out.r(', ' + g(c, 'url'))
    _hereinafter(c, out, 'i')
    return out


def _bb_book(c, lr, pin):
    out = Runs()
    if g(c, 'volume'):
        out.r(g(c, 'volume') + ' ')
    names = bb_names(people(c))
    title_fmt = 'sc' if lr else 'i'
    if names:
        out.add(names + ', ', 'sc' if lr else '')
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, title_fmt if fmt != 'sc' or not lr else 'sc')
    if pin:
        out.r(' ' + pin)
    bits = []
    eds = people(c, 'editors')
    if eds:
        bits.append(bb_names(eds) + (' eds.' if len(eds) > 1 else ' ed.'))
    if g(c, 'translator'):
        bits.append(g(c, 'translator') + ' trans.')
    ed = g(c, 'edition')
    y = bb_date(g(c, 'date'), full=False)
    tail = ' '.join(x for x in ((ordinal_bb(ed) + ' ed.') if ed and ed != 'rev.' else ('rev. ed.' if ed == 'rev.' else ''), y) if x)
    if tail:
        bits.append(tail)
    if bits:
        out.r(' (' + ', '.join(bits) + ')')
    _hereinafter(c, out, title_fmt)
    return out


def _bb_chapter(c, lr, pin):
    out = Runs()
    _authors(c, out)
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'i')
    out.r(', in ')
    for text, fmt in md_runs(g(c, 'book_title')):
        out.add(text, 'sc' if lr else 'i')
    if g(c, 'first_page'):
        out.r(' ' + g(c, 'first_page'))
    if pin:
        out.r(', ' + pin)
    bits = []
    eds = people(c, 'editors')
    if eds:
        bits.append(bb_names(eds) + (' eds.' if len(eds) > 1 else ' ed.'))
    ed = g(c, 'edition')
    y = bb_date(g(c, 'date'), full=False)
    tail = ' '.join(x for x in ((ordinal_bb(ed) + ' ed.') if ed else '', y) if x)
    if tail:
        bits.append(tail)
    if bits:
        out.r(' (' + ', '.join(bits) + ')')
    _hereinafter(c, out, 'i')
    return out


def _bb_news(c, lr, pin):
    out = Runs()
    _authors(c, out)
    if g(c, 'designation'):
        out.r(g(c, 'designation') + ', ')
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'i')
    pub = g(c, 'publication_abbrev') or abbreviate_periodical(g(c, 'publication'))
    if pub:
        out.r(', ')
        _sc_or(lr, out, pub)
    date = bb_date(g(c, 'date'))
    if g(c, 'page') and not g(c, 'url'):
        out.r(', ' + date + ', at ' + g(c, 'page') + pin_after(pin))
    else:
        out.r(' (' + date + ')' if date else '')
        if pin:
            out.r(', at ' + pin)
        if g(c, 'url'):
            out.r(', ' + g(c, 'url'))
    _hereinafter(c, out, 'i')
    return out


def _bb_webpage(c, lr, pin):
    out = Runs()
    _authors(c, out)
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'i')
    site = g(c, 'site_abbrev') or abbreviate_periodical(g(c, 'site'))
    if site:
        out.r(', ')
        _sc_or(lr, out, site)
    if pin:
        out.r(' ' + pin)
    date = bb_date(g(c, 'date'))
    if date:
        out.r(' (' + date + (', ' + g(c, 'time') if g(c, 'time') else '') + ')')
    if g(c, 'url'):
        out.r(', ' + g(c, 'url'))
    if not date and g(c, 'last_visited'):
        out.r(' (last visited ' + bb_date(g(c, 'last_visited')) + ')')
    _hereinafter(c, out, 'i')
    return out


def _bb_report(c, lr, pin):
    out = Runs()
    names = bb_names(people(c))
    if names:
        out.add(names + ', ', 'sc' if lr else '')
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'sc' if lr else 'i')
    if g(c, 'number'):
        out.r(', ' + g(c, 'number'))
    if pin:
        out.r(' ' + pin)
    when = bb_date(g(c, 'date'))
    if when:
        out.r(' (' + ((g(c, 'publisher') + ' ') if g(c, 'publisher') else '') + when + ')')
    if g(c, 'url'):
        out.r(', ' + g(c, 'url'))
    _hereinafter(c, out, 'sc' if lr else 'i')
    return out


def _bb_bill(c, lr, pin):
    out = Runs()
    if g(c, 'title'):
        out.r(g(c, 'title') + ', ')
    out.r(g(c, 'number') + ', ' + g(c, 'session'))
    if pin:
        out.r(' ' + pin)
    y = bb_date(g(c, 'date'), full=False)
    state = g(c, 'state')
    status = g(c, 'status')
    if status and status != 'enacted' and not state:
        out.r(' (' + status + ')')
    else:
        out.r(' (' + ' '.join(x for x in (state, y) if x) + ')')
        if status == 'enacted':
            out.r(' (enacted)')
    return out


def _bb_hearing(c, lr, pin):
    out = Runs()
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'i')
    out.r(', ' + g(c, 'session'))
    if pin:
        out.r(' ' + pin)
    out.r(' (' + ' '.join(x for x in (g(c, 'state'), bb_date(g(c, 'date'), full=False)) if x) + ')')
    if g(c, 'url'):
        out.r(', ' + g(c, 'url'))
    _hereinafter(c, out, 'i')
    return out


def _bb_committee_report(c, lr, pin):
    out = Runs()
    _sc_or(lr, out, (g(c, 'chamber') or 'H.R.') + ' Rep. No.')
    out.r(' ' + g(c, 'number'))
    if pin:
        out.r(', at ' + pin)
    out.r(' (' + bb_date(g(c, 'date'), full=False) + ')')
    if g(c, 'conference'):
        out.r(' (Conf. Rep.)')
    if g(c, 'reprinted'):
        out.r(', ').i('as reprinted in').r(' ' + g(c, 'reprinted'))
    return out


def _bb_filing(c, lr, pin):
    out = Runs()
    title = g(c, 'title')
    if g(c, 'case_name'):
        out.r(title + (' at ' + pin if pin else '') + ', ')
        out.extend_runs(Runs((t, 'i') for t, _ in md_runs(g(c, 'case_name'))))
        if g(c, 'docket') and g(c, 'case_cite', ).startswith('('):
            out.r(', ' + g(c, 'docket') + ' ' + g(c, 'case_cite'))
        else:
            if g(c, 'case_cite'):
                out.r(', ' + g(c, 'case_cite'))
            if g(c, 'docket'):
                out.r(' (' + g(c, 'docket') + ')')
        if g(c, 'ecf'):
            out.r(', ECF No. ' + g(c, 'ecf'))
        if g(c, 'url'):
            out.r(', ' + g(c, 'url'))
        return out
    out.r(title + (' ' + pin if pin else ''))
    if g(c, 'date'):
        out.r(', ' + bb_date(g(c, 'date')))
    if g(c, 'ecf'):
        out.r(', ECF No. ' + g(c, 'ecf'))
    return out


def _bb_record(c, lr, pin):
    use_at = (c.get('fields') or {}).get('use_at', True)
    return Runs().r(g(c, 'abbrev') + ((' at ' if use_at else ' ') + pin if pin else ''))


def _bb_other(c, lr, pin):
    out = md_runs(g(c, 'text'))
    if pin:
        out.r(', ' + pin)
    return out


_BB = {'case': _bb_case, 'statute': _bb_statute, 'regulation': _bb_regulation, 'constitution': _bb_constitution,
       'rule': _bb_rule, 'restatement': _bb_restatement, 'journal': _bb_journal, 'book': _bb_book,
       'chapter': _bb_chapter, 'news': _bb_news, 'webpage': _bb_webpage, 'report': _bb_report, 'bill': _bb_bill,
       'hearing': _bb_hearing, 'committee_report': _bb_committee_report, 'filing': _bb_filing,
       'record': _bb_record, 'other': _bb_other}


# ---------------- Bluebook short forms

def default_short_name(name_md):
    """First party, unless it is a government (Indigo R15.2.3): United States v. Carmel -> Carmel."""
    name = md_runs(name_md).plain()
    name = re.sub(r'^(In re|Ex parte)\s+', '', name)
    parts = re.split(r'\s+v\.\s+', name, 1)
    first = parts[0]
    gov = re.fullmatch(r'(United States|U\.S\.|State|People|Commonwealth|City of .+|County of .+|[A-Z][a-z]+ County|'
                       r'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|'
                       r'Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|'
                       r'Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|'
                       r'New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|'
                       r'Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|'
                       r'West Virginia|Wisconsin|Wyoming)', first.strip())
    pick = parts[1] if gov and len(parts) > 1 else first
    pick = re.split(r',\s*(Inc\.|LLC|Co\.|Corp\.|Ltd\.)', pick)[0]
    return pick.strip()


def short_author_runs(c, lr):
    """The author part of a supra short form; falls back to the hereinafter title or the title."""
    out = Runs()
    t = c.get('type')
    if g(c, 'hereinafter'):
        fmt = 'sc' if (lr and t in ('book', 'report')) else 'i'
        out.add(g(c, 'hereinafter'), fmt)
        return out
    ps = people(c) or people(c, 'editors')
    if ps:
        out.add(short_names(ps), 'sc' if (lr and t in ('book', 'report')) else '')
        return out
    for text, fmt in md_runs(g(c, 'title')):
        out.add(text, 'sc' if (lr and t in ('book', 'report')) else 'i')
    return out


def bluebook_short(c, typeface='practitioner', pin='', note=None, in_text=False):
    """Short form after a full citation (not Id.). note = footnote number of the full citation, for supra."""
    if g(c, '_override_short'):
        return md_runs(g(c, '_override_short'))
    t = c.get('type', 'other')
    lr = is_lr(typeface) and not in_text
    out = Runs()
    if t == 'case':
        short = g(c, 'short_name') or default_short_name(g(c, 'name'))
        out.i(short)
        db = _database_of(c)
        if db:                                   # Green, 2013 WL 5811261, at *7
            out.r(', ' + db + (_star_pin(pin) if pin else ''))
        elif g(c, 'volume') or g(c, 'reporter'):  # Carmel, 548 F.3d at 573
            out.r(', ' + ' '.join(x for x in (g(c, 'volume'), g(c, 'reporter')) if x) +
                  (' at ' + pin if pin else (' ' + g(c, 'first_page') if g(c, 'first_page') else '')))
        elif g(c, 'docket'):                     # Albrecht, No. 01-CV-0039, slip op. at 3
            out.r(', ' + g(c, 'docket') + (', slip op. at ' + pin if pin else ''))
        elif pin:
            out.r(', at ' + pin)
        return out
    if t == 'regulation' and g(c, 'fed_reg') and not g(c, 'section'):
        # a rule cited to the Federal Register: 85 Fed. Reg. at 15,640 (Indigo R14.4)
        m = re.fullmatch(r'(.*?)\s+(\S+)', g(c, 'fed_reg'))
        if m and pin:
            return out.r(m.group(1) + ' at ' + pin)
        return out.r(g(c, 'fed_reg'))
    if t in ('statute', 'regulation'):
        if t == 'statute' and not g(c, 'section'):
            return bluebook(c, typeface, pin, in_text)
        if g(c, 'title_no'):
            out.r(g(c, 'title_no') + ' ')
        code = g(c, 'code') or ('C.F.R.' if t == 'regulation' else '')
        if lr and t == 'statute' and code not in US_CODES:
            out.sc(code)
        else:
            out.r(code)
        sec = g(c, 'section')
        out.r(' ' + (sec if sec.startswith('pt.') else ('§§ ' if is_span(sec) and t == 'statute' else '§ ') + sec))
        out.r(pin if pin.startswith('(') else pin_after(pin))
        return out
    if t == 'committee_report':
        _sc_or(lr, out, (g(c, 'chamber') or 'H.R.') + ' Rep. No.')
        return out.r(' ' + g(c, 'number') + (', at ' + pin if pin else ''))
    if t == 'filing':
        return Runs().r(g(c, 'title') + (' ' + pin if pin else ''))
    if t in NO_SUPRA or t == 'other':
        if t == 'other' and g(c, 'short'):
            r = md_runs(g(c, 'short'))
            return r.r(', ' + pin) if pin else r
        return bluebook(c, typeface, pin, in_text)
    # secondary sources: Author, supra note N, at pin
    out.extend_runs(short_author_runs(c, lr))
    out.r(', ').i('supra')
    if note and is_lr(typeface):
        out.r(' note %s' % note)
    if pin:
        out.r(', ' + ('' if re.match(r'[§¶]', pin) else 'at ') + pin)
    return out


def bluebook_id(c, pin='', cap=True):
    """Id. (cap) / id., with "at" for page pincites but not for §, ¶ (Indigo R6.2.2)."""
    out = Runs().i('Id.' if cap else 'id.')
    if not pin:
        return out
    t = c.get('type')
    if t in ('statute', 'regulation') and pin.startswith('('):
        sec = g(c, 'section')
        return out.r(' § ' + sec + pin)
    if re.match(r'[§¶]|art\.|amend\.|cl\.|cmt\.', pin) or (t in ('constitution',) and pin):
        return out.r(' ' + pin)
    if t == 'case' and _database_of(c) and re.fullmatch(r'\*?\d+(?:[-–]\*?\d+)?', pin):
        return out.r(' at *' + pin.lstrip('*'))
    if t == 'record':
        return out.r(' at ' + pin)
    return out.r(' at ' + pin)


# ------------------------------------------------------------------ APA 7

def apa_title(c, key='title', apa_key='title_apa'):
    """Sentence-case title runs (APA). Uses the APA field if given, else an automatic sentence case."""
    if g(c, apa_key):
        return md_runs(g(c, apa_key))
    res = Runs()
    for k, (text, fmt) in enumerate(md_runs(g(c, key))):
        prev = res.plain().rstrip()
        res.add(sentence_case(text, start=(k == 0 or prev.endswith(':'))), fmt)
    return res


def _end(out):
    """Make sure an element ends with a period (but not after a ? or !)."""
    s = out.plain().rstrip()
    if s and s[-1] not in '.?!':
        out.r('.')
    return out


def _doi_or_url(c):
    doi = g(c, 'doi')
    if doi:
        return doi if doi.startswith('http') else 'https://doi.org/' + re.sub(r'^doi:\s*', '', doi, flags=re.I)
    return g(c, 'url')


def apa_reference(c, year_suffix=''):
    if g(c, '_override_apa'):
        return md_runs(g(c, '_override_apa'))
    t = c.get('type', 'other')
    if t == 'other':
        return md_runs(g(c, 'text_apa') or g(c, 'text'))
    if t in LEGAL_TYPES:
        # APA 7 (ch. 11) uses legal citation form for legal materials, with case names in italics.
        out = bluebook(c, 'practitioner')
        _end(out)
        if g(c, 'url'):
            out.r(' ' + g(c, 'url'))
        return out
    out = Runs()
    ps = people(c)
    eds = people(c, 'editors') if t == 'book' else []
    title_runs = apa_title(c)
    full_date = t in ('news', 'webpage')
    d = apa_date(g(c, 'date'), full=full_date)
    if year_suffix and re.match(r'\d{4}', d):
        d = d[:4] + year_suffix + d[4:]
    date = '(' + d + ').'
    italic_title = t in ('book', 'webpage', 'report')

    def put_title():
        for text, fmt in title_runs:
            out.add(text, 'i' if italic_title else fmt)

    if ps:
        out.r(apa_names(ps))
        _end(out); out.r(' ' + date + ' ')
        put_title()
    elif eds:
        out.r(apa_names(eds) + (' (Eds.).' if len(eds) > 1 else ' (Ed.).') + ' ' + date + ' ')
        put_title()
    else:                                   # no author: the title moves to the author position
        put_title()
        if t == 'book':
            _book_parens(c, out)
        _end(out); out.r(' ' + date)
        title_runs = Runs()

    if t == 'journal':
        _end(out); out.r(' ')
        out.i(g(c, 'journal'))
        if g(c, 'volume'):
            out.r(', ').i(g(c, 'volume'))
            if g(c, 'issue'):
                out.r('(' + g(c, 'issue') + ')')
        pages = '–'.join(x for x in (g(c, 'first_page'), g(c, 'last_page')) if x)
        if pages:
            out.r(', ' + pages)
        elif g(c, 'article_number'):
            out.r(', Article ' + g(c, 'article_number'))
        out.r('.')
    elif t == 'book':
        if ps or eds:
            _book_parens(c, out)
            _end(out)
        if g(c, 'publisher'):
            out.r(' ' + _close(g(c, 'publisher')))
    elif t == 'chapter':
        _end(out)
        out.r(' In ')
        e = people(c, 'editors')
        if e:
            out.r(apa_editor_names(e) + (' (Eds.), ' if len(e) > 1 else ' (Ed.), '))
        out.extend_runs(Runs((x, 'i') for x, _ in apa_title(c, 'book_title', 'book_title_apa')))
        bits = []
        if g(c, 'edition'):
            bits.append(ordinal_apa(g(c, 'edition')) + ' ed.')
        pages = '–'.join(x for x in (g(c, 'first_page'), g(c, 'last_page')) if x)
        if pages:
            bits.append(('pp. ' if '–' in pages else 'p. ') + pages)
        if bits:
            out.r(' (' + ', '.join(bits) + ')')
        out.r('.')
        if g(c, 'publisher'):
            out.r(' ' + _close(g(c, 'publisher')))
    elif t == 'news':
        _end(out)
        if g(c, 'publication'):
            out.r(' ').i(g(c, 'publication'))
            if g(c, 'volume'):
                out.r(', ').i(g(c, 'volume'))
                if g(c, 'issue'):
                    out.r('(' + g(c, 'issue') + ')')
                if g(c, 'page'):
                    out.r(', ' + g(c, 'page'))
            out.r('.')
    elif t == 'webpage':
        _end(out)
        site = g(c, 'site')
        if site and not (len(ps) == 1 and ps[0].get('literal', '').strip() == site):
            out.r(' ' + _close(site))
    elif t == 'report':
        if g(c, 'number'):
            out.r(' (' + g(c, 'number') + ')')
        _end(out)
        pub = g(c, 'publisher')
        if pub and not (len(ps) == 1 and ps[0].get('literal', '').strip() == pub):
            out.r(' ' + _close(pub))
    link = _doi_or_url(c)
    if link:
        out.r(' ' + link)
    if t == 'webpage' and not parse_date(g(c, 'date')) and g(c, 'last_visited'):
        # APA: retrieval date only for pages that change over time; ReWord adds it when the page has no date
        pass
    return out


def _book_parens(c, out):
    bits = []
    if g(c, 'edition'):
        bits.append((ordinal_apa(g(c, 'edition')) + ' ed.') if g(c, 'edition') != 'rev.' else 'Rev. ed.')
    if g(c, 'volume'):
        bits.append('Vol. ' + g(c, 'volume'))
    if g(c, 'translator'):
        bits.append(g(c, 'translator') + ', Trans.')
    if bits:
        out.r(' (' + '; '.join(bits) + ')')


def apa_author_year(c, narrative=False):
    """(author runs, year) for in-text citations."""
    t = c.get('type', 'other')
    if t == 'other':
        txt = g(c, 'intext_apa')
        if txt:
            m = re.match(r'(.*?),\s*(\S+)\s*$', txt)
            if m:
                return Runs().r(m.group(1)), m.group(2)
            return Runs().r(txt), ''
        return md_runs(g(c, 'text')), ''
    if t == 'case':
        return Runs().extend_runs(Runs((x, 'i') for x, _ in md_runs(g(c, 'name')))), year_of(g(c, 'date'))
    if t in LEGAL_TYPES:
        if t == 'statute' and g(c, 'name'):
            return Runs().r(g(c, 'name')), year_of(g(c, 'date'))
        r = bluebook(c, 'practitioner')
        return r, ''
    ps = people(c) or people(c, 'editors')
    if ps:
        return Runs().r(intext_names(ps, narrative)), apa_date(g(c, 'date'))
    # no author: the title (italic for books, reports and web pages; in quotation marks otherwise)
    title = apa_title(c)
    if t in ('book', 'webpage', 'report'):
        return Runs((x, 'i') for x, _ in title), apa_date(g(c, 'date'))
    return Runs().r('“').extend_runs(title).r('”'), apa_date(g(c, 'date'))


def apa_pin(pin):
    """'12' -> 'p. 12', '12-14' -> 'pp. 12–14'; anything else (para. 3, Chapter 2) is kept."""
    if not pin:
        return ''
    if re.fullmatch(r'\d+', pin):
        return 'p. ' + pin
    if re.fullmatch(r'\d+\s*[-–]\s*\d+', pin):
        return 'pp. ' + re.sub(r'\s*[-–]\s*', '–', pin)
    return pin


def apa_intext(c, pin='', narrative=False, year_suffix=''):
    who, year = apa_author_year(c, narrative)
    year = (year + year_suffix) if year else ''
    p = apa_pin(pin)
    out = Runs()
    if narrative:
        out.extend_runs(who)
        inner = ', '.join(x for x in (year, p) if x)
        if inner:
            out.r(' (' + inner + ')')
        return out
    out.r('(').extend_runs(who)
    for x in (year, p):
        if x:
            out.r(', ' + x)
    out.r(')')
    return out


def apa_sort_key(c):
    who, year = apa_author_year(c)
    return (re.sub(r'^(the|a|an)\s+', '', who.plain().lower().strip('“”')), year)


# ------------------------------------------------------------------ Chicago (18th edition)
# Two systems from the same fields:
#   notes and bibliography   chicago_note (full note), chicago_short (shortened note), chicago_bib (bibliography entry)
#   author-date              chicago_ad_reference (reference list), chicago_ad_intext: (Walker 2017, 45) / Walker (2017, 45)
# Legal materials follow legal citation form in Chicago (CMOS 14.269 ff.), so cases, statutes and the
# rest use the practitioner Bluebook form, and they are left out of the bibliography and reference list.
# Chicago 18 dropped the place of publication, so no new fields are needed: chicago_gaps() lists the
# optional fields Chicago would use that a citation is missing (a book's publisher, a journal's pages…).

def ch_date(s):
    """Chicago date: August 19, 2021 / August 2021 / 2021 (anything else as typed)."""
    d = parse_date(s)
    if not d:
        return s or ''
    y, mo, da = d
    if not mo:
        return str(y)
    return MONTHS[mo - 1] + (' %d,' % da if da else '') + ' %d' % y


def ch_name(p, inverted=False):
    if p.get('literal'):
        return p['literal'].strip()
    given, fam, suf = p.get('given', '').strip(), p.get('family', '').strip(), p.get('suffix', '').strip()
    if inverted and fam:
        return fam + (', ' + given if given else '') + (', ' + suf if suf else '')
    return ' '.join(x for x in (given, fam, suf) if x)


def _series(names, et_al_after=None, keep=None):
    if not names:
        return ''
    if et_al_after and len(names) > et_al_after:
        return ', '.join(names[:keep]) + (',' if keep > 1 else '') + ' et al.'
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return names[0] + ' and ' + names[1]
    return ', '.join(names[:-1]) + ', and ' + names[-1]


def ch_note_names(ps):
    """Notes: A; A and B; A, B, and C; four or more: A et al. (CMOS 14.76)."""
    return _series([ch_name(p) for p in ps], 3, 1)


def ch_bib_names(ps):
    """Bibliography and reference list: first name inverted; more than six: the first three, et al."""
    n = [ch_name(p, k == 0) for k, p in enumerate(ps)]
    if len(n) == 2:
        return n[0] + ', and ' + n[1]
    return _series(n, 6, 3)


def ch_short_names(ps):
    return _series([family(p) for p in ps], 3, 1)


def ch_ad_names(ps):
    """Author-date text citations: A; A and B; three or more: A et al. (CMOS 18, 13.111)."""
    return _series([family(p) for p in ps], 2, 1)


def ch_title(c, key='title'):
    """Title runs in headline style as typed (small caps from the law review form become roman)."""
    return Runs((t, '' if f == 'sc' else f) for t, f in md_runs(g(c, key)))


def ch_italic(runs):
    """An italic title: words already in italics inside it (a case name, a ship) turn roman."""
    return Runs((t, '' if f == 'i' else 'i') for t, f in runs)


def _quoted(out, runs, punct=''):
    """“Title,” with the comma or period inside the quotation marks (not after ? or !). Quotation marks inside
    the title become single ones: “‘They Had Access’: Why …” (CMOS 6.11)."""
    runs = Runs((t.replace('“', '‘').replace('”', '’'), f) for t, f in runs)
    out.r('“').extend_runs(runs)
    if punct and not runs.plain().rstrip().endswith(('?', '!')):
        out.r(punct)
    return out.r('”')


ITALIC_TITLE = {'book', 'report'}
QUOTED_TITLE = {'journal', 'chapter', 'news', 'webpage'}


def ch_pin(pin):
    return re.sub(r'(?<=\d)\s*-\s*(?=\d)', '–', pin or '')


def ch_edition(c):
    ed = g(c, 'edition')
    if not ed:
        return ''
    return 'rev. ed.' if ed == 'rev.' else (ordinal_apa(ed) + ' ed.' if re.fullmatch(r'\d+', ed) else ed + ' ed.')


def ch_link(c):
    return _doi_or_url(c)


def ch_who(c, note=True):
    """(names, is_editor_list) for the author position."""
    ps = people(c)
    if ps:
        return (ch_note_names(ps) if note else ch_bib_names(ps)), False
    eds = people(c, 'editors') if c.get('type') == 'book' else []
    if eds:
        return (ch_note_names(eds) if note else ch_bib_names(eds)) + (', eds.' if len(eds) > 1 else ', ed.'), True
    return '', False


def chicago_note(c, pin=''):
    """Full note (no final period)."""
    t = c.get('type', 'other')
    if t == 'other':
        return md_runs(g(c, 'text_chicago') or g(c, 'text'))
    if t in LEGAL_TYPES:
        return bluebook(c, 'practitioner', pin)
    pin = ch_pin(pin)
    out = Runs()
    who, _ = ch_who(c)
    if who:
        out.r(who + ', ')
    title = ch_title(c)
    year = year_of(g(c, 'date')) or g(c, 'date') or 'n.d.'
    if t in ('book', 'report'):
        out.extend_runs(ch_italic(title))
        extra = []
        eds = people(c, 'editors') if t == 'book' and people(c) else []
        if eds:
            extra.append('ed. ' + ch_note_names(eds))
        if g(c, 'translator'):
            extra.append('trans. ' + g(c, 'translator'))
        if ch_edition(c):
            extra.append(ch_edition(c))
        if t == 'book' and g(c, 'volume'):
            extra.append('vol. ' + g(c, 'volume'))
        if t == 'report' and g(c, 'number'):
            extra.append(g(c, 'number'))
        for x in extra:
            out.r(', ' + x)
        pub = g(c, 'publisher')
        if t == 'report' and pub and len(people(c)) == 1 and people(c)[0].get('literal', '').strip() == pub:
            pub = ''
        date = ch_date(g(c, 'date')) if t == 'report' else year
        out.r(' (' + ', '.join(x for x in (pub, date) if x) + ')')
        if pin:
            out.r(', ' + pin)
    elif t == 'chapter':
        _quoted(out, title, ',').r(' in ')
        out.extend_runs(ch_italic(ch_title(c, 'book_title')))
        eds = people(c, 'editors')
        if eds:
            out.r(', ed. ' + ch_note_names(eds))
        if ch_edition(c):
            out.r(', ' + ch_edition(c))
        out.r(' (' + ', '.join(x for x in (g(c, 'publisher'), year) if x) + ')')
        if pin:
            out.r(', ' + pin)
    elif t == 'journal':
        _quoted(out, title, ',').r(' ').i(g(c, 'journal'))
        if g(c, 'volume'):
            out.r(' ' + g(c, 'volume'))
        if g(c, 'issue'):
            out.r(', no. ' + g(c, 'issue'))
        out.r(' (' + ch_date(g(c, 'date')) + ')' if g(c, 'date') else '')
        if pin:
            out.r(': ' + pin)
    elif t == 'news':
        _quoted(out, title, ',')
        if g(c, 'publication'):
            out.r(' ').i(g(c, 'publication'))
        if g(c, 'date'):
            out.r((', ' if g(c, 'publication') else ' ') + ch_date(g(c, 'date')))
    elif t == 'webpage':
        _quoted(out, title, ',')
        if g(c, 'site'):
            out.r(' ' + g(c, 'site'))
        if parse_date(g(c, 'date')):
            out.r(', ' + ch_date(g(c, 'date')))
        elif g(c, 'last_visited'):
            out.r(', accessed ' + ch_date(g(c, 'last_visited')))
    else:
        out.extend_runs(title)
    link = ch_link(c)
    if link:
        out.r(', ' + link)
    return out


def _short_title(c):
    """Up to four key words of the main title (no subtitle, no leading article), or the hereinafter title."""
    if g(c, 'hereinafter'):
        return Runs().r(g(c, 'hereinafter'))
    runs = ch_title(c)
    text = runs.plain()
    main = re.split(r'[:?!]\s', text, 1)[0].strip()
    main = re.split(r'\s+[(\[—]', main, 1)[0]                # not into a parenthetical: Behavioral Immune System (and …
    main = re.sub(r'^[“"‘]+|[”"’]+$', '', main).strip()      # a title that opens with a quotation
    main = re.sub(r'^(The|A|An)\s+', '', main)
    words = main.split()
    if len(words) > 4:
        words = words[:4]
        while len(words) > 1 and re.sub(r'\W', '', words[-1]).lower() in SMALL:    # never end on "and", "of", "but"
            words.pop()
        main = ' '.join(words).rstrip(',;')
    # keep the italics of the original words where they survive
    out, pos = Runs(), text.find(main)
    if pos < 0:
        return Runs().r(main)
    k = 0
    for t, f in runs:
        a, b = max(k, pos), min(k + len(t), pos + len(main))
        if a < b:
            out.add(t[a - k:b - k], f)
        k += len(t)
    return out


def chicago_short(c, pin=''):
    """Shortened note: Walker, *Why We Sleep*, 45 / Ray, “How the Mind Hurts,” 31."""
    t = c.get('type', 'other')
    if t == 'other':
        r = md_runs(g(c, 'short') or g(c, 'text_chicago') or g(c, 'text'))
        return r.r(', ' + pin) if pin and g(c, 'short') else r
    if t in LEGAL_TYPES:
        return bluebook_short(c, 'practitioner', pin)
    pin = ch_pin(pin)
    out = Runs()
    ps = people(c) or (people(c, 'editors') if t == 'book' else [])
    if ps:
        out.r(ch_short_names(ps) + ', ')
    st = _short_title(c)
    if t in QUOTED_TITLE:
        _quoted(out, st, ',' if pin else '')
        if pin:
            out.r(' ' + pin)
        return out
    out.extend_runs(ch_italic(st))
    if pin:
        out.r(', ' + pin)
    return out


def _bib_body(c, out, year_first=False, title_done=False):
    """Everything after the author (and, author-date, the year) in a bibliography or reference-list entry."""
    t = c.get('type', 'other')
    title = ch_title(c)
    date_full = ch_date(g(c, 'date'))
    year = year_of(g(c, 'date')) or g(c, 'date') or 'n.d.'
    if t in ('book', 'report'):
        if not title_done:
            out.extend_runs(ch_italic(title)); _end(out)
        eds = people(c, 'editors') if t == 'book' and people(c) else []
        if eds:
            out.r(' Edited by ' + _series([ch_name(p) for p in eds]) + '.')
        if g(c, 'translator'):
            out.r(' Translated by ' + g(c, 'translator') + '.')
        if ch_edition(c):
            e = ch_edition(c)
            out.r(' ' + e[0].upper() + e[1:])
        if t == 'book' and g(c, 'volume'):
            out.r(' Vol. ' + g(c, 'volume') + '.')
        if t == 'report' and g(c, 'number'):
            out.r(' ' + g(c, 'number') + '.')
        pub = g(c, 'publisher')
        if t == 'report' and pub and len(people(c)) == 1 and people(c)[0].get('literal', '').strip() == pub:
            pub = ''
        facts = [pub] + ([] if year_first else [date_full if t == 'report' else year])
        facts = [x for x in facts if x]
        if facts:
            out.r(' ' + _close(', '.join(facts)))
    elif t == 'chapter':
        (out if title_done else _quoted(out, title, '.')).r(' In ')
        out.extend_runs(ch_italic(ch_title(c, 'book_title')))
        eds = people(c, 'editors')
        if eds:
            out.r(', edited by ' + _series([ch_name(p) for p in eds]))
        pages = '–'.join(x for x in (g(c, 'first_page'), g(c, 'last_page')) if x)
        if pages:
            out.r(', ' + pages)
        out.r('.')
        if ch_edition(c):
            e = ch_edition(c)
            out.r(' ' + e[0].upper() + e[1:])
        facts = [x for x in [g(c, 'publisher')] + ([] if year_first else [year]) if x]
        if facts:
            out.r(' ' + _close(', '.join(facts)))
    elif t == 'journal':
        (out if title_done else _quoted(out, title, '.')).r(' ').i(g(c, 'journal'))
        if g(c, 'volume'):
            out.r(' ' + g(c, 'volume'))
        if g(c, 'issue'):
            out.r(', no. ' + g(c, 'issue'))
        d = parse_date(g(c, 'date'))
        if year_first:
            if d and d[1]:
                out.r(' (' + MONTHS[d[1] - 1] + ')')
        elif g(c, 'date'):
            out.r(' (' + date_full + ')')
        pages = '–'.join(x for x in (g(c, 'first_page'), g(c, 'last_page')) if x) or g(c, 'article_number')
        if pages:
            out.r(': ' + pages)
        out.r('.')
    elif t == 'news':
        if not title_done:
            _quoted(out, title, '.')
        if g(c, 'publication'):
            out.r(' ').i(g(c, 'publication'))
            if g(c, 'date'):
                out.r(', ' + date_full)
            out.r('.')
        elif g(c, 'date'):
            out.r(' ' + _close(date_full))
    elif t == 'webpage':
        if not title_done:
            _quoted(out, title, '.')
        if g(c, 'site'):
            out.r(' ' + g(c, 'site'))
            if parse_date(g(c, 'date')):
                out.r(', ' + date_full)
            _end(out)
        elif parse_date(g(c, 'date')):
            out.r(' ' + date_full + '.')
        if not parse_date(g(c, 'date')) and g(c, 'last_visited'):
            out.r(' Accessed ' + ch_date(g(c, 'last_visited')) + '.')
    link = ch_link(c)
    if link:
        out.r(' ' + link + ('' if link.endswith('.') else '.'))
    return out


def chicago_bib(c):
    """Bibliography entry (with its final period), or None for legal materials (cited in notes only)."""
    t = c.get('type', 'other')
    if t == 'other':
        return _end(md_runs(g(c, 'text_chicago') or g(c, 'text')))
    if t in LEGAL_TYPES:
        return None
    out = Runs()
    who, _ = ch_who(c, note=False)
    if who:
        out.r(who); _end(out); out.r(' ')
    return _bib_body(c, out)


def chicago_ad_reference(c, year_suffix=''):
    """Author-date reference-list entry: Walker, Matthew. 2017. *Why We Sleep*. Scribner. None for legal materials."""
    t = c.get('type', 'other')
    if t == 'other':
        return _end(md_runs(g(c, 'text_chicago') or g(c, 'text')))
    if t in LEGAL_TYPES:
        return None
    year = (year_of(g(c, 'date')) or 'n.d.') + year_suffix
    out = Runs()
    who, _ = ch_who(c, note=False)
    if who:
        out.r(who); _end(out); out.r(' ' + _close(year) + ' ')
        return _bib_body(c, out, year_first=True)
    # no author: the title leads, then the year
    title = ch_title(c)
    if t in QUOTED_TITLE:
        _quoted(out, title, '.')
    else:
        out.extend_runs(ch_italic(title)); _end(out)
    out.r(' ' + year); _end(out)
    return _bib_body(c, out, year_first=True, title_done=True)


def chicago_ad_author_year(c, narrative=False):
    """(author runs, year) for author-date text citations."""
    t = c.get('type', 'other')
    if t == 'other':
        txt = g(c, 'intext_apa')
        if txt:
            m = re.match(r'(.*?),?\s+(\d{4}\w?|n\.d\.)\s*$', txt)
            if m:
                return Runs().r(m.group(1)), m.group(2)
            return Runs().r(txt), ''
        return md_runs(g(c, 'text_chicago') or g(c, 'text')), ''
    if t in LEGAL_TYPES:
        return bluebook(c, 'practitioner'), ''
    ps = people(c) or (people(c, 'editors') if t == 'book' else [])
    year = year_of(g(c, 'date')) or 'n.d.'
    if ps:
        return Runs().r(ch_ad_names(ps)), year
    st = _short_title(c)
    if t in QUOTED_TITLE:
        return Runs().r('“').extend_runs(st).r('”'), year
    return ch_italic(st), year


def chicago_ad_intext(c, pin='', narrative=False, year_suffix=''):
    """(Walker 2017, 45) or, narrative, Walker (2017, 45)."""
    if c.get('type') in LEGAL_TYPES:          # legal citation form, with the pincite in its place
        r = bluebook(c, 'practitioner', pin)
        return r if narrative else Runs().r('(').extend_runs(r).r(')')
    who, year = chicago_ad_author_year(c, narrative)
    year = (year + year_suffix) if year else ''
    pin = ch_pin(pin)
    tail = ', '.join(x for x in (year, pin) if x)
    out = Runs()
    if narrative:
        out.extend_runs(who)
        if tail:
            out.r(' (' + tail + ')')
        return out
    out.r('(').extend_runs(who)
    if year:
        out.r(' ' + year)
    if pin:
        out.r(', ' + pin)
    return out.r(')')


def chicago_sort_key(c):
    who, year = chicago_ad_author_year(c)
    ps = people(c) or (people(c, 'editors') if c.get('type') == 'book' else [])
    first = ch_name(ps[0], True) if ps else who.plain()
    return (re.sub(r'^(the|a|an)\s+', '', first.lower().strip('“”*')), year)


def chicago_gaps(c):
    """Optional fields Chicago uses that this citation leaves empty (labels). The citation still formats."""
    t = c.get('type', 'other')
    gaps = []
    if t == 'other':
        if not g(c, 'text_chicago'):
            gaps.append('Chicago form (the Bluebook text is used)')
        return gaps
    if t in LEGAL_TYPES:
        return gaps
    if not (people(c) or people(c, 'editors')) and t in ('book', 'journal', 'chapter'):
        gaps.append('authors')
    if t in ('book', 'chapter') and not g(c, 'publisher'):
        gaps.append('publisher')
    if t == 'journal':
        if not g(c, 'volume'):
            gaps.append('volume')
        if not g(c, 'first_page'):
            gaps.append('page range')
        elif not g(c, 'last_page'):
            gaps.append('last page')
    if t == 'chapter' and not (g(c, 'first_page') and g(c, 'last_page')):
        gaps.append('page range')
    if t == 'webpage' and not parse_date(g(c, 'date')) and not g(c, 'last_visited'):
        gaps.append('date posted or date last visited')
    if t == 'news' and not parse_date(g(c, 'date')):
        gaps.append('date')
    return gaps


# ------------------------------------------------------------------ everything for one citation (previews, library)

# ------------------------------------------------------------------ edited books and their chapters

EDITED_BOOK_KEYS = ('editors', 'title', 'title_apa', 'edition', 'volume', 'publisher', 'date', 'doi', 'url', 'hereinafter', 'translator')
CHAPTER_KEYS = ('authors', 'title', 'title_apa', 'first_page', 'last_page', 'doi', 'url', 'hereinafter')
OVERRIDES = ('_override_bluebook', '_override_short', '_override_apa')


def chapters(c):
    """An edited book's chapters (dicts with an "id"), in the order they were added."""
    if (c or {}).get('type') != 'edited_book':
        return []
    return [x for x in ((c.get('fields') or {}).get('chapters') or []) if isinstance(x, dict) and x.get('id')]


def find_chapter(c, chapter_id):
    return next((x for x in chapters(c) if x.get('id') == chapter_id), None)


def edited_book_whole(c):
    """An edited book cited as a whole: a book with editors."""
    f = c.get('fields') or {}
    out = {k: v for k, v in f.items() if k != 'chapters'}
    return dict(c, type='book', fields=out)


def edited_chapter(c, chapter_id):
    """One chapter of an edited book, as a "chapter" citation: the chapter's own fields plus the book's.
    None when the book has no such chapter."""
    ch = find_chapter(c, chapter_id)
    if ch is None:
        return None
    f = c.get('fields') or {}
    # the book's details; not what belongs to one chapter (left over, say, from a single chapter's citation)
    out = {k: v for k, v in f.items() if k not in ('chapters', 'title', 'title_apa', 'hereinafter', 'volume', 'authors', 'first_page',
                                                    'last_page', 'book_title', 'book_title_apa') and not k.startswith('_override')}
    if f.get('title'):
        out['book_title'] = f['title']
    if f.get('title_apa'):
        out['book_title_apa'] = f['title_apa']
    for k, v in ch.items():
        if k not in ('id', 'number') and v not in ('', None, []):
            out[k] = v
    return {'type': 'chapter', 'fields': out, 'tag': c.get('tag', ''), 'chapter': chapter_id}


def chapter_label(ch):
    """How a chapter is named in menus: Chapter 4: Author, Title (pp. 85–126). The number is the one chosen for it, if any."""
    who = ', '.join(p.get('family') or p.get('literal') or p.get('given', '') for p in (ch.get('authors') or [])[:2] if isinstance(p, dict))
    if len(ch.get('authors') or []) > 2:
        who += ' et al.'
    title = re.sub(r'\\(.)', r'\1', re.sub(r'\]\{\.smallcaps\}|[*_\[\]]', '', ch.get('title') or '')) or ch.get('id', '')
    pages = '–'.join(x for x in (ch.get('first_page', ''), ch.get('last_page', '')) if x)
    pages = ('pp. ' if '–' in pages else 'p. ') + pages if pages else ''
    num = str(ch.get('number') or '').strip()
    return ('Chapter %s: ' % num if num else '') + (who + ', ' if who else '') + title + (' (%s)' % pages if pages else '')


def _formattable(c):
    """Formatters take a book or a chapter: an edited book given to one is formatted as the whole book."""
    if isinstance(c, dict) and c.get('type') == 'edited_book':
        return edited_book_whole(c)
    return c


def describe(c, pin=''):
    """All the forms of one citation, as Markdown and HTML, for the library and the editor."""
    forms = {
        'bluebook_lawreview': bluebook(c, 'lawreview', pin),
        'bluebook_practitioner': bluebook(c, 'practitioner', pin),
        'short_lawreview': bluebook_short(c, 'lawreview', pin, note='N'),
        'short_practitioner': bluebook_short(c, 'practitioner', pin),
        'apa_reference': apa_reference(c),
        'apa_intext': apa_intext(c, pin),
        'apa_narrative': apa_intext(c, pin, narrative=True),
        'chicago_note': chicago_note(c, pin),
        'chicago_short': chicago_short(c, pin),
        'chicago_bib': chicago_bib(c) or Runs().r('(not listed: legal materials are cited in notes only)'),
        'chicago_ad_reference': chicago_ad_reference(c) or Runs().r('(not listed: legal materials are cited in the text only)'),
        'chicago_ad_intext': chicago_ad_intext(c, pin),
        'chicago_ad_narrative': chicago_ad_intext(c, pin, narrative=True),
    }
    return {k: {'md': to_md(v), 'html': to_html(v), 'text': v.plain()} for k, v in forms.items()}


def warnings(c):
    """Fields marked * that are empty, by label (for an edited book, its chapters' too)."""
    spec = TYPES.get(c.get('type', 'other'))
    if not spec:
        return []
    out = []
    for f in spec['fields']:
        if f['label'].endswith('*'):
            v = (c.get('fields') or {}).get(f['key'])
            if not v or (isinstance(v, str) and not v.strip()):
                out.append(f['label'].rstrip('*'))
        if f['kind'] == 'chapters':
            for k, ch in enumerate((c.get('fields') or {}).get(f['key']) or []):
                for sub in f['fields']:
                    v = ch.get(sub['key']) if isinstance(ch, dict) else None
                    if sub['label'].endswith('*') and (not v or (isinstance(v, str) and not v.strip())):
                        out.append('chapter %d: %s' % (k + 1, sub['label'].rstrip('*').lower()))
    return out


def _wrap_formatters():
    """Every formatter (a function whose first argument is the citation) accepts an edited book."""
    import functools
    import inspect
    skip = {'warnings', 'chapters', 'find_chapter', 'edited_book_whole', 'edited_chapter', 'chapter_label', '_formattable', 'g'}
    for name, fn in list(globals().items()):
        if not inspect.isfunction(fn) or fn.__module__ != __name__ or name in skip:
            continue
        params = list(inspect.signature(fn).parameters)
        if not params or params[0] != 'c':
            continue

        def wrapped(c, *a, _fn=fn, **kw):
            return _fn(_formattable(c), *a, **kw)
        globals()[name] = functools.wraps(fn)(wrapped)


_wrap_formatters()
