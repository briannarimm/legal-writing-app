"""Live citations: turn the citation marks in a document into formatted text. Standard library only.

In the Markdown a citation is a span that points at the library:

    [Smith v. Jones, 123 F.3d 456 (8th Cir. 1999)]{.cite tag="smith-v-jones" pin="460" signal="See" paren="holding that …"}

The text inside the brackets is only what the editor last showed; the build always reformats from the
library entry, so fixing a citation in the library fixes it everywhere.  Attributes:

    tag        the library entry (required)
    pin        pincite: 460 · 460–61 · § 2(b) · ¶ 12
    signal     See, See also, Cf., But see, E.g., … (italicized, capitalized to fit the sentence)
    paren      explanatory parenthetical, without the parentheses
    narrative  APA only: "Walker (2017)" instead of "(Walker, 2017)"
    form       force "full" (repeat the full citation) for this one occurrence

resolve(doc, …) walks the Pandoc AST in reading order (footnotes in place) and replaces every mark:

  draft   every citation in full (signal, pin, parenthetical)
  final   Bluebook short forms worked out:
            Id. when the immediately preceding citation was this source alone (not after a string cite,
                never for record cites; it may lead a string cite; in law review footnotes not when the
                preceding footnote cited more than one authority);
            the short form once a full citation has been given (in law review footnotes, cases and other
                primary authorities return to the full form if not cited in the previous five footnotes);
            supra (with "note N" in law review footnotes) for secondary sources; hereinafter only in the
                first full citation.
  APA     always "(Author, Year)" / "Author (Year)", parenthetical cites side by side are combined
          ("(Ray, 2004; Walker, 2017)"), same-author-same-year sources get 2017a/2017b, and the
          References list is built from what was cited.
  Chicago notes and bibliography (style "chicago"): full notes in the draft; in the final draft a shortened
          note once the full note has been given (Chicago 18 prefers shortened notes to ibid.). The
          Bibliography is built from what was cited (legal materials stay in the notes).
  Chicago author-date (style "chicago-ad"): like APA, "(Walker 2017, 45)" / "Walker (2017, 45)", combined
          and suffixed the same way, with a References list in Chicago form.

For brief templates every authority is also wrapped in an .auth span so the table of authorities
lists it (filters/toa.lua and scripts/make_toa.py do the rest).
"""
import json
import re
from pathlib import Path

import citeformat as cf

SIGNALS = ['see generally', 'see also', 'see, e.g.,', 'see', 'cf.', 'but see', 'but cf.', 'contra', 'accord', 'e.g.,',
           'compare', 'with', 'and', 'but see, e.g.,', 'see also, e.g.,']


# ------------------------------------------------------------------ the library

def key_of(attrs):
    """Which library entry a citation mark points at: its tag, or tag#chapter for a chapter of an edited book."""
    tag = (attrs or {}).get('tag', '')
    ch = ((attrs or {}).get('chapter') or '').strip()
    return tag + '#' + ch if ch else tag


def library_entries(c):
    """The library entries one citation gives: (key, entry). An edited book gives the whole book under its tag,
    each chapter under tag#chapter, and each chapter again under the tag it had as a citation of its own
    before it was gathered into the book ("former_tag"), so marks written then still resolve."""
    base = {'type': c['type'], 'fields': c['fields'], 'tag': c['tag']}
    yield c['tag'], base
    for ch in cf.chapters(base):
        e = cf.edited_chapter(base, ch['id'])
        yield c['tag'] + '#' + ch['id'], e
        if ch.get('former_tag'):
            yield ch['former_tag'], e


def library_from(citations):
    lib = {}
    for c in citations:
        for k, e in library_entries(c):
            if k not in lib or k == c['tag']:
                lib[k] = e
    return lib


def load_library(data_dir):
    """All citations under <data>/library/citations, by key (read with the same parser the app uses)."""
    import store       # noqa: E402  (store sets its roots; reading needs only the file parser)
    out = []
    d = Path(data_dir) / 'library' / 'citations'
    if d.exists():
        for p in sorted(d.glob('*.md')):
            try:
                out.append(store.read_citation(p))
            except (OSError, ValueError):
                continue
    return library_from(out)


# ------------------------------------------------------------------ AST helpers

def attrs_of(span):
    ident, classes, kv = span['c'][0]
    return classes, dict(kv)


def is_cite(x):
    return isinstance(x, dict) and x.get('t') == 'Span' and 'cite' in x['c'][0][1]


def stringify(inlines):
    out = []
    for x in inlines or []:
        t = x.get('t')
        if t == 'Str': out.append(x['c'])
        elif t in ('Space', 'SoftBreak', 'LineBreak'): out.append(' ')
        elif t in ('Emph', 'Strong', 'SmallCaps', 'Strikeout', 'Underline', 'Superscript', 'Subscript'):
            out.append(stringify(x['c']))
        elif t in ('Span', 'Link', 'Quoted'):
            out.append(stringify(x['c'][-1] if t != 'Quoted' else x['c'][1]))
        elif t == 'Code': out.append(x['c'][1])
    return ''.join(out)


def md_inlines(md):
    """Small rich text (parenthetical) -> Pandoc inlines via the formatter's run parser."""
    return cf.to_pandoc(cf.md_runs(md))


# ------------------------------------------------------------------ the resolver

PAREN_STYLES = {'apa': (cf.apa_intext, cf.apa_sort_key, cf.apa_author_year),
                'chicago-ad': (cf.chicago_ad_intext, cf.chicago_sort_key, cf.chicago_ad_author_year)}
REF_HEADING = {'apa': 'References', 'chicago-ad': 'References', 'chicago': 'Bibliography'}


def reference_entry(c, style, year_suffix=''):
    """A reference-list or bibliography entry in the document's style (None: not listed)."""
    if style == 'chicago':
        return cf.chicago_bib(c)
    if style == 'chicago-ad':
        return cf.chicago_ad_reference(c, year_suffix)
    if c['type'] == 'constitution':
        return None
    return cf.apa_reference(c, year_suffix=year_suffix)


def sort_key(c, style):
    return cf.chicago_sort_key(c) if style.startswith('chicago') else cf.apa_sort_key(c)


class Resolver:
    def __init__(self, library, mode='draft', typeface='practitioner', style='bluebook', toa=False, note_offset=0):
        self.lib = library
        self.mode = mode
        self.typeface = typeface
        self.style = style
        self.toa = toa
        self.note_no = note_offset          # footnotes before the first one in the body (e.g. Word author note)
        self.in_note = None
        self.first_note = {}                # tag -> footnote number of the first full citation
        self.last_note = {}                 # tag -> last footnote that cited it
        self.full_given = set()
        self.prev_group = None              # tags of the previous citation sentence/clause
        self.note_tags = {}                 # footnote number -> tags it cites (law review Id. rule)
        self.last_cited_note = None         # the last footnote that cited anything
        self.cited = []                     # tags in first-cited order
        self.missing = []
        self.suffix = {}                    # APA year suffixes: tag -> 'a' / 'b'

    # ---- APA year suffixes (2017a, 2017b) need the whole document first
    def prescan(self, blocks):
        tags = []

        def walk(x):
            if isinstance(x, dict):
                if is_cite(x):
                    tags.append(key_of(attrs_of(x)[1]))
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(blocks)
        seen = []
        for t in tags:
            if t in self.lib and t not in seen:
                seen.append(t)
        groups = {}
        for t in seen:
            c = self.lib[t]
            if c['type'] in cf.LEGAL_TYPES:
                continue
            who, year = PAREN_STYLES.get(self.style, PAREN_STYLES['apa'])[2](c)
            groups.setdefault((who.plain().lower(), year), []).append(t)
        for key, ts in groups.items():
            if len(ts) > 1 and key[1] not in ('', 'n.d.'):
                title = cf.ch_title if self.style.startswith('chicago') else cf.apa_title
                ts.sort(key=lambda t: title(self.lib[t]).plain().lower())
                for k, t in enumerate(ts):
                    self.suffix[t] = chr(ord('a') + k)

    # ---- one citation
    def id_allowed(self, tag):
        """Law review footnotes (Bluebook R4.1): id. may point into the preceding footnote only when that
        footnote cites a single authority."""
        if self.typeface != 'lawreview' or self.in_note is None or self.note_tags.get(self.in_note):
            return True
        prev = self.note_tags.get(self.last_cited_note, set())
        return len(prev) <= 1

    def bluebook_one(self, c, a, cap, in_text, first):
        tag, pin = c['tag'], a.get('pin', '').strip()
        typeface = 'practitioner' if (self.typeface == 'lawreview' and in_text) else self.typeface
        t = c['type']
        out = cf.Runs()
        signal = a.get('signal', '').strip()
        if signal:
            s = signal[0].upper() + signal[1:] if cap else signal[0].lower() + signal[1:]
            out.i(s + ' ')          # the space stays italic so "See id." is one italic run
            cap = False
        form = 'full'
        if self.mode == 'final' and a.get('form') != 'full':
            if self.prev_group == [tag] and first and t != 'record' and self.id_allowed(tag):
                form = 'id'
            elif tag in self.full_given:
                form = 'short'
                if self.typeface == 'lawreview' and self.in_note is not None and t in cf.NO_SUPRA:
                    last = self.last_note.get(tag)
                    if last is None or self.in_note - last > 5:
                        form = 'full'          # the "preceding five footnotes" rule for short forms
        if form == 'id':
            out.extend_runs(cf.bluebook_id(c, pin, cap))
        elif form == 'short':
            out.extend_runs(cf.bluebook_short(c, typeface, pin, note=self.first_note.get(tag), in_text=in_text))
        else:
            cc = c
            if tag in self.full_given and cf.g(c, 'hereinafter'):
                cc = {'type': c['type'], 'fields': dict(c['fields'], hereinafter='')}
            out.extend_runs(cf.bluebook(cc, typeface, pin, in_text=in_text and self.typeface == 'lawreview'))
            if tag not in self.full_given:
                self.full_given.add(tag)
                if self.in_note is not None:
                    self.first_note[tag] = self.in_note
        if a.get('paren', '').strip():
            out.r(' (').extend_runs(cf.md_runs(a['paren'].strip())).r(')')
        if self.in_note is not None:
            self.last_note[tag] = self.in_note
        return out

    def chicago_one(self, c, a, cap):
        """One Chicago note citation: full the first time (and always in the draft), shortened after that."""
        tag, pin = c['tag'], a.get('pin', '').strip()
        out = cf.Runs()
        signal = a.get('signal', '').strip()
        if signal:
            out.r((signal[0].upper() if cap else signal[0].lower()) + signal[1:] + ' ')     # roman in Chicago
        if self.mode == 'final' and a.get('form') != 'full' and tag in self.full_given:
            out.extend_runs(cf.chicago_short(c, pin))
        else:
            out.extend_runs(cf.chicago_note(c, pin))
            self.full_given.add(tag)
        if a.get('paren', '').strip():
            out.r(' (').extend_runs(cf.md_runs(a['paren'].strip())).r(')')
        return out

    def render_group(self, spans, cap, in_text):
        """A run of adjacent citation marks (a string citation) -> inlines."""
        items = []
        for sp in spans:
            _, a = attrs_of(sp)
            tag = key_of(a)
            c = self.lib.get(tag)
            if c is None:
                self.missing.append(tag)
                items.append((tag, None, a))
                continue
            c = dict(c, tag=tag)
            if tag not in self.cited:
                self.cited.append(tag)
            items.append((tag, c, a))
        out = []
        if self.style in PAREN_STYLES:
            out = self.apa_group(items)
        else:
            for k, (tag, c, a) in enumerate(items):
                if k:
                    out.extend([{'t': 'Str', 'c': ';'}, {'t': 'Space'}])
                if c is None:
                    out.append({'t': 'Str', 'c': '[missing citation: %s]' % tag})
                    continue
                if self.style == 'chicago':
                    runs = self.chicago_one(c, a, cap and k == 0)
                else:
                    runs = self.bluebook_one(c, a, cap and k == 0, in_text, k == 0)
                inl = cf.to_pandoc(runs)
                if self.toa and c['type'] in cf.TOA_GROUP:
                    inl = [{'t': 'Span', 'c': [['', ['auth'], [['tag', tag]]], inl]}]
                out.extend(inl)
        self.prev_group = [t for t, _, _ in items]
        if self.in_note is not None and not in_text:
            self.note_tags.setdefault(self.in_note, set()).update(t for t, _, _ in items)
            self.last_cited_note = self.in_note
        return out

    def apa_group(self, items):
        """Parenthetical text citations (APA or Chicago author-date), side-by-side ones in one pair."""
        intext, key = PAREN_STYLES[self.style][:2]
        out = cf.Runs()
        paren = [(t, c, a) for t, c, a in items if c is not None and not a.get('narrative')]
        narr = [(t, c, a) for t, c, a in items if c is not None and a.get('narrative')]
        for t, c, a in narr:
            if out:
                out.r('; ')
            out.extend_runs(intext(c, a.get('pin', '').strip(), narrative=True, year_suffix=self.suffix.get(t, '')))
        if paren:
            if out:
                out.r(' ')
            parts = []
            for t, c, a in sorted(paren, key=lambda x: key(x[1])):
                one = intext(c, a.get('pin', '').strip(), year_suffix=self.suffix.get(t, ''))
                inner = cf.Runs(one[:])
                # strip the outer parentheses of each so they can share one pair
                if inner and inner[0][0].startswith('('):
                    inner[0] = (inner[0][0][1:], inner[0][1])
                if inner and inner[-1][0].endswith(')'):
                    inner[-1] = (inner[-1][0][:-1], inner[-1][1])
                sig = a.get('signal', '').strip()
                if sig:
                    inner = cf.Runs().r(sig[0].lower() + sig[1:] + ' ').extend_runs(inner) if parts else cf.Runs().r(sig + ' ').extend_runs(inner)
                parts.append(inner)
            out.r('(')
            for k, p in enumerate(parts):
                if k:
                    out.r('; ')
                out.extend_runs(p)
            out.r(')')
        for t, c, a in items:
            if c is None:
                out.r('[missing citation: %s]' % t)
        return cf.to_pandoc(out)

    # ---- walking the document
    def inlines(self, xs, in_header=False, start_cap=True):
        out = []
        i = 0
        while i < len(xs):
            x = xs[i]
            if is_cite(x):
                # gather a string citation: marks separated only by ';' and spaces
                group = [x]
                j = i + 1
                while True:
                    k, semicolon = j, False
                    while k < len(xs) and (xs[k].get('t') in ('Space', 'SoftBreak') or
                                           (xs[k].get('t') == 'Str' and xs[k]['c'].strip(';\u200b') == '')):
                        semicolon = semicolon or (xs[k].get('t') == 'Str' and ';' in xs[k]['c'])
                        k += 1
                    if semicolon and k < len(xs) and is_cite(xs[k]):
                        group.append(xs[k]); j = k + 1
                    else:
                        break
                prev_text = stringify(out).rstrip()
                cap = (not prev_text and start_cap) or bool(re.search(r'[.?!]["”’)]*$', prev_text))
                if in_header:
                    saved = (self.mode, self.prev_group)
                    self.mode = 'draft'
                    rendered = self.render_group(group, cap, True)
                    self.mode, self.prev_group = saved
                else:
                    rendered = self.render_group(group, cap, self.in_note is None)
                # "Id." + the period typed after the mark: one period, not "Id.."
                nxt = xs[j] if j < len(xs) else None
                if (nxt and nxt.get('t') == 'Str' and nxt['c'].startswith('.') and
                        stringify(rendered).rstrip().endswith('.')):
                    xs = xs[:j] + ([{'t': 'Str', 'c': nxt['c'][1:]}] if nxt['c'][1:] else []) + xs[j + 1:]
                out.extend(rendered)
                i = j
                continue
            t = x.get('t')
            if t == 'Note':
                self.note_no += 1
                outer = self.in_note
                self.in_note = self.note_no
                x = {'t': 'Note', 'c': self.blocks(x['c'])}
                self.in_note = outer
            elif t in ('Emph', 'Strong', 'SmallCaps', 'Strikeout', 'Underline', 'Superscript', 'Subscript'):
                x = {'t': t, 'c': self.inlines(x['c'], in_header, False)}
            elif t == 'Span':
                x = {'t': 'Span', 'c': [x['c'][0], self.inlines(x['c'][1], in_header, False)]}
            elif t == 'Link':
                x = {'t': 'Link', 'c': [x['c'][0], self.inlines(x['c'][1], in_header, False), x['c'][2]]}
            elif t == 'Quoted':
                x = {'t': 'Quoted', 'c': [x['c'][0], self.inlines(x['c'][1], in_header, False)]}
            out.append(x)
            i += 1
        return out

    def blocks(self, bs):
        out = []
        for b in bs:
            t = b.get('t')
            if t in ('Para', 'Plain'):
                b = {'t': t, 'c': self.inlines(b['c'])}
            elif t == 'Header':
                b = {'t': 'Header', 'c': [b['c'][0], b['c'][1], self.inlines(b['c'][2], in_header=True)]}
            elif t == 'BlockQuote':
                b = {'t': t, 'c': self.blocks(b['c'])}
            elif t in ('BulletList',):
                b = {'t': t, 'c': [self.blocks(item) for item in b['c']]}
            elif t == 'OrderedList':
                b = {'t': t, 'c': [b['c'][0], [self.blocks(item) for item in b['c'][1]]]}
            elif t == 'Div':
                b = {'t': 'Div', 'c': [b['c'][0], self.blocks(b['c'][1])]}
            elif t == 'LineBlock':
                b = {'t': t, 'c': [self.inlines(line) for line in b['c']]}
            out.append(b)
        return out

    # ---- APA References (or any reference list) built from what was cited
    def reference_blocks(self):
        tags = [t for t in self.cited if t in self.lib]
        tags.sort(key=lambda t: sort_key(self.lib[t], self.style))
        out = []
        for t in tags:
            runs = reference_entry(self.lib[t], self.style, self.suffix.get(t, ''))
            if runs:
                out.append({'t': 'Para', 'c': cf.to_pandoc(runs)})
        return out


def entry_tag(b):
    """The tag if this block is a bibliography entry: a paragraph holding just one {.cite form="entry"} mark."""
    if b.get('t') not in ('Para', 'Plain'):
        return None
    items = [x for x in b['c'] if not (x.get('t') in ('Space', 'SoftBreak') or (x.get('t') == 'Str' and x['c'].strip('\u200b.') == ''))]
    if len(items) == 1 and is_cite(items[0]):
        _, a = attrs_of(items[0])
        if a.get('form') == 'entry':
            return key_of(a)
    return None


def annotated_bibliography(blocks, library, style, typeface, resolver):
    """Entries (an entry mark plus the paragraphs after it, its annotation) sorted and formatted:
    Div.bib-entry [Para entry, Div.bib-annotation [...]]. Blocks before the first entry stay first."""
    intro, entries, cur = [], [], None
    for b in blocks:
        t = entry_tag(b)
        if t is not None:
            cur = {'tag': t, 'notes': []}
            entries.append(cur)
        elif cur is None:
            intro.append(b)
        else:
            cur['notes'].append(b)
    missing, cited = [], []

    def key(e):
        c = library.get(e['tag'])
        if not c:
            return ('~', e['tag'])
        return sort_key(c, style)          # by author surname (or title), then year, in every style
    out = list(intro)
    for e in sorted(entries, key=key):
        c = library.get(e['tag'])
        if c is None:
            missing.append(e['tag'])
            runs = cf.Runs().r('[missing citation: %s]' % e['tag'])
        else:
            cited.append(e['tag'])
            if style in ('apa', 'chicago', 'chicago-ad'):
                runs = reference_entry(c, style, resolver.suffix.get(e['tag'], ''))
                if runs is None:                    # legal materials: their citation, as a bibliography entry
                    runs = cf.bluebook(c, 'practitioner')
                    if not runs.plain().rstrip().endswith('.'):
                        runs.r('.')
            else:
                runs = cf.bluebook(c, typeface)
                if not runs.plain().rstrip().endswith('.'):
                    runs.r('.')
        entry = {'t': 'Para', 'c': cf.to_pandoc(runs)}
        ann = {'t': 'Div', 'c': [['', ['bib-annotation'], []], e['notes']]} if e['notes'] else None
        out.append({'t': 'Div', 'c': [['', ['bib-entry'], []], [entry] + ([ann] if ann else [])]})
    return out, cited, missing


def is_refs_header(b):
    return b.get('t') == 'Header' and b['c'][0] == 1 and re.fullmatch(r'\s*(references?|bibliography|works cited)\s*', stringify(b['c'][2]).lower() or '') is not None


def add_references(blocks, refs, heading='References'):
    """Put the generated entries under the "References" heading (merged with anything typed there, in
    alphabetical order); add the heading at the end if the document has none."""
    if not refs:
        return blocks
    for k, b in enumerate(blocks):
        if is_refs_header(b):
            end = next((m for m in range(k + 1, len(blocks)) if blocks[m].get('t') == 'Header' and blocks[m]['c'][0] == 1), len(blocks))
            typed = [x for x in blocks[k + 1:end] if x.get('t') in ('Para', 'Plain')]
            others = [x for x in blocks[k + 1:end] if x.get('t') not in ('Para', 'Plain')]
            have = {stringify(x['c']).strip().lower() for x in typed}
            merged = typed + [r for r in refs if stringify(r['c']).strip().lower() not in have]
            merged.sort(key=lambda x: re.sub(r'^[“"‘\'*_]+', '', stringify(x['c']).lower()))
            return blocks[:k + 1] + others + merged + blocks[end:]
    head = {'t': 'Header', 'c': [1, [heading.lower(), [], []], [{'t': 'Str', 'c': heading}]]}
    return blocks + [head] + refs


def resolve(doc, library, mode='draft', typeface='practitioner', style='bluebook', toa=False, note_offset=0, references=None,
            bibliography=False):
    """doc: Pandoc JSON (dict). Returns (doc, report). references: None = automatic (APA style only).
    bibliography: the document is an annotated bibliography (entries become sorted reference entries)."""
    r = Resolver(library, mode, typeface, style, toa, note_offset)
    if style in PAREN_STYLES:
        r.prescan(doc['blocks'])
    if bibliography:
        blocks, cited, missing = annotated_bibliography(doc['blocks'], library, style, typeface, r)
        doc = dict(doc, blocks=r.blocks(blocks))
        return doc, {'cited': cited, 'missing': sorted(set(missing + r.missing))}
    doc = dict(doc, blocks=r.blocks(doc['blocks']))
    want_refs = (style in REF_HEADING) if references is None else references
    if want_refs:
        doc['blocks'] = add_references(doc['blocks'], r.reference_blocks(), REF_HEADING.get(style, 'References'))
    report = {'cited': r.cited, 'missing': sorted(set(r.missing))}
    return doc, report


def meta_text(meta, key):
    v = (meta or {}).get(key)
    if not v:
        return ''
    if v.get('t') == 'MetaString':
        return v['c']
    if v.get('t') in ('MetaInlines', 'MetaBlocks'):
        return stringify(v['c'] if v['t'] == 'MetaInlines' else [i for b in v['c'] for i in b.get('c', []) if isinstance(i, dict)])
    return ''


def style_of(template, meta=None):
    """(style, typeface) for a template: style is bluebook · apa · chicago (notes and bibliography) ·
    chicago-ad (author-date). Templates with "cite_style": "document" (the annotated bibliography) take it
    from the document's `citation-style:` (apa · bluebook · bluebook-lawreview · chicago · chicago-author-date)."""
    cs = template.get('cite_style')
    if cs == 'document':
        v = meta_text(meta, 'citation-style').strip().lower()
        if v.startswith('bluebook'):
            return 'bluebook', 'lawreview' if 'law' in v else 'practitioner'
        if v.startswith('chicago'):
            return ('chicago-ad' if 'date' in v or v.endswith('-ad') else 'chicago'), 'practitioner'
        return 'apa', 'practitioner'
    if cs in ('apa', 'chicago', 'chicago-ad'):
        return cs, 'practitioner'
    return 'bluebook', (template.get('cite_typeface') or 'practitioner')


def options_for(template, mode='draft', meta=None):
    """resolve() keyword arguments for a template (template.json) and the document's metadata."""
    style, typeface = style_of(template, meta)
    return {'mode': mode, 'style': style, 'typeface': typeface, 'toa': bool(template.get('toa')),
            'bibliography': bool(template.get('bibliography'))}


def front_notes(meta):
    """Word builds turn the author and title notes into the first footnotes (filters/docx.lua)."""
    n = 0
    authors = meta.get('author')
    if authors:
        items = authors['c'] if authors.get('t') == 'MetaList' else [authors]
        for a in items:
            if a.get('t') == 'MetaMap' and 'note' in a['c']:
                n += 1
    if 'title-note' in meta:
        n += 1
    return n


def chip_text(c, attrs, typeface='practitioner', style='bluebook', in_note=True):
    """What a citation chip shows in the editor: the draft (full) form with its signal, pin and
    parenthetical; APA in-text form for APA templates. Returns runs."""
    if c is None:
        return cf.Runs().r('[missing citation: %s]' % key_of(attrs))
    pin = (attrs.get('pin') or '').strip()
    if attrs.get('form') == 'entry':
        if style in ('apa', 'chicago', 'chicago-ad'):
            return reference_entry(c, style) or cf.bluebook(c, 'practitioner')
        return cf.bluebook(c, typeface)
    if style in PAREN_STYLES:
        return PAREN_STYLES[style][0](c, pin, narrative=bool(attrs.get('narrative')))
    out = cf.Runs()
    sig = (attrs.get('signal') or '').strip()
    if style == 'chicago':
        if sig:
            out.r(sig + ' ')
        out.extend_runs(cf.chicago_note(c, pin))
        if (attrs.get('paren') or '').strip():
            out.r(' (').extend_runs(cf.md_runs(attrs['paren'].strip())).r(')')
        return out
    if sig:
        out.i(sig + ' ')
    tf = 'practitioner' if (typeface == 'lawreview' and not in_note) else typeface
    out.extend_runs(cf.bluebook(c, tf, pin))
    if (attrs.get('paren') or '').strip():
        out.r(' (').extend_runs(cf.md_runs(attrs['paren'].strip())).r(')')
    return out


def resolve_json_text(text, library, template, mode='draft', fmt='latex'):
    doc = json.loads(text)
    offset = front_notes(doc.get('meta', {})) if fmt == 'docx' else 0
    doc, report = resolve(doc, library, note_offset=offset, **options_for(template, mode, doc.get('meta', {})))
    return json.dumps(doc), report
