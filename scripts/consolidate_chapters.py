#!/usr/bin/env python3
"""Gather single-chapter citations ("Chapter in an edited book") into edited books ("Chapter(s) in edited book").

Chapters of the same book (same book title, editors and year) become chapters of one edited-book citation. A book
citation already in the library for that book (a Book with those editors, or an edited book) becomes that edited
book and keeps its tag; otherwise a new tag is made from the first editor and the year (bandes-1999), or the book's
title. Each chapter keeps its old tag as its chapter id, so nothing that pointed at it is lost:

  - live citations in documents and research notes:  {.cite tag="spiro-1966"}  ->  {.cite tag="banton-1966" chapter="spiro-1966"}
  - research notes' linked sources:                 spiro-1966  ->  banton-1966
  - Verify results:                                  doc:spiro-1966:90:0  ->  doc:banton-1966#spiro-1966:90:0
  - the chapter's files (and highlights):            library/files/spiro-1966/  ->  library/files/banton-1966/, marked as that chapter
  - the chapter's projects:                          added to the book's
  - older copies (document versions, other tools):   still resolve, through the chapter's "former_tag"

A chapter whose book details differ from the book's (another publisher, say) keeps its own value, so every
citation reads exactly as before; the report lists them, and anything else that changed.

Run it on a clone of the data repository, never on the live data folder:

    python3 scripts/consolidate_chapters.py <data folder>            # what it would do
    python3 scripts/consolidate_chapters.py <data folder> --apply    # do it (writes a report to stdout)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import citeformat as cf  # noqa: E402
import cites  # noqa: E402
import store  # noqa: E402

BOOK_KEYS = ('editors', 'edition', 'publisher', 'date', 'translator')   # from a chapter: the book's details
CHAPTER_KEYS = ('authors', 'title', 'title_apa', 'first_page', 'last_page', 'doi', 'url', 'hereinafter')


def _norm(md):
    s = re.sub(r'\\(.)', r'\1', re.sub(r'\]\{\.smallcaps\}|[*_\[\]]', '', md or ''))
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def _names(ps):
    return tuple(sorted(_norm(p.get('family') or p.get('literal') or '') for p in (ps or []) if isinstance(p, dict)))


def _book_key(title, editors, date):
    return (_norm(title), _names(editors), cf.year_of(date or '') or '')


FORMS = ('bluebook_lawreview', 'bluebook_practitioner', 'short_lawreview', 'short_practitioner', 'apa_reference', 'apa_intext',
         'chicago_note', 'chicago_short', 'chicago_bib', 'chicago_ad_reference', 'chicago_ad_intext')


def _forms(c):
    d = cf.describe(c)
    return {k: d[k]['text'] for k in FORMS}


def plan(data):
    """What would change: {"books": [{book_tag, existing, chapters: [{tag, ...}]}]}."""
    store.set_root(Path(data))
    lib = store.citations()
    tags = {c['tag'] for c in lib}
    chapters = [c for c in lib if c['type'] == 'chapter']
    if not chapters:
        return {'books': []}
    books = {}
    for c in lib:                                           # books this library already has, by their details
        f = c['fields']
        if c['type'] == 'edited_book' or (c['type'] == 'book' and f.get('editors') and not f.get('authors')):
            books.setdefault(_book_key(f.get('title'), f.get('editors'), f.get('date')), c)
    groups = {}
    for c in chapters:
        f = c['fields']
        groups.setdefault(_book_key(f.get('book_title'), f.get('editors'), f.get('date')), []).append(c)
    out, taken = [], set(tags)
    for key, chs in sorted(groups.items(), key=lambda kv: min(c['tag'] for c in kv[1])):
        chs.sort(key=lambda c: c['tag'])
        existing = books.get(key)
        if existing:
            book_tag = existing['tag']
        else:
            f = chs[0]['fields']
            eds = f.get('editors') or []
            who = (eds[0].get('family') or eds[0].get('literal') or '') if eds else ''
            year = cf.year_of(f.get('date') or '') or ''
            words = re.sub(r'^(the|a|an) ', '', _norm(re.split(r'[:—]', f.get('book_title') or '')[0])).split()[:3]
            base = store.slugify((who + ' ' + year) if who else ' '.join(words) + (' ' + year if year else ''), 'edited-book', 48)
            book_tag = store.unique(base, lambda t: t in taken)
            taken.add(book_tag)
        out.append({'book_tag': book_tag, 'existing': existing['type'] if existing else None, 'title': chs[0]['fields'].get('book_title', ''),
                    'chapters': [{'tag': c['tag'], 'title': c['fields'].get('title', '')} for c in chs]})
    return {'books': out}


def _move_files(src_tag, dst_tag, chapter, report):
    src, dst = store.files_dir(src_tag), store.files_dir(dst_tag)
    if not src.exists():
        return
    meta_src, meta_dst = store.read_files_meta(src_tag), store.read_files_meta(dst_tag)
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.iterdir()):
        if not p.is_file() or p.name.endswith('.annotations.json') or p.name == store.FILES_META or p.name.startswith('.'):
            continue
        name = p.name
        if (dst / name).exists():
            stem, ext = p.stem, p.suffix
            name = store.unique(stem, lambda s: (dst / (s + ext)).exists()) + ext
        p.rename(dst / name)
        ann = src / (p.name + '.annotations.json')
        if ann.exists():
            a = json.loads(ann.read_text(encoding='utf-8'))
            a['file'] = name
            store.write_atomic(dst / (name + '.annotations.json'), json.dumps(a, indent=1, ensure_ascii=False) + '\n')
            ann.unlink()
        m = dict(meta_src.get(p.name) or {})
        m['chapter'] = chapter
        meta_dst[name] = m
        report['files'].append('%s/%s -> %s/%s (chapter %s)' % (src_tag, p.name, dst_tag, name, chapter))
    store.write_files_meta(dst_tag, meta_dst)
    rest = [x for x in src.rglob('*') if x.is_file() and x.name != store.FILES_META]
    if rest:                                                # a _trash folder and the like: move it beside the book's
        for x in rest:
            to = dst / ('_trash' if '_trash' in x.parts else '_moved') / src_tag / x.relative_to(src)
            to.parent.mkdir(parents=True, exist_ok=True)
            x.rename(to)
    for x in sorted(src.rglob('*'), reverse=True):
        if x.is_file():
            x.unlink()
        else:
            x.rmdir()
    src.rmdir()


CITE_TAG_RE = re.compile(r'(\{\.(?:cite|auth)\b[^}]*?\btag=")([a-z0-9][a-z0-9-]*)(")')


def _rewrite_marks(md, moved):
    """{.cite tag="old" …} -> {.cite tag="book" chapter="old" …}. A mark that already names a chapter is left alone."""
    n = 0

    def sub(m):
        nonlocal n
        tag = m.group(2)
        if tag not in moved:
            return m.group(0)
        whole = md[m.start():md.find('}', m.end()) + 1]
        if re.search(r'\bchapter="', whole):
            return m.group(0)
        n += 1
        extra = '" chapter="' + tag if m.group(1).startswith('{.cite') else ''
        return m.group(1) + moved[tag] + extra + m.group(3)
    return CITE_TAG_RE.sub(sub, md), n


def apply(data, the_plan=None):
    data = Path(data)
    store.set_root(data)
    the_plan = the_plan or plan(data)
    report = {'books': [], 'differences': [], 'files': [], 'rewritten': 0, 'notes': 0, 'verify_keys': 0, 'leftovers': []}
    if not the_plan['books']:
        return report
    by_tag = {c['tag']: c for c in store.citations()}
    moved = {}                                              # old chapter tag -> book tag
    for g in the_plan['books']:
        chs = [by_tag[x['tag']] for x in g['chapters']]
        first = chs[0]['fields']
        book = by_tag.get(g['book_tag'])
        if book:
            fields = dict(book['fields'])
            if book['type'] == 'book':
                fields.pop('authors', None)
            old_chapters = list(fields.get('chapters') or [])
            projects, auto = list(book.get('projects') or []), list(book.get('projects_auto') or [])
        else:
            fields = {k: first[k] for k in BOOK_KEYS if first.get(k)}
            if first.get('book_title'):
                fields['title'] = first['book_title']
            if first.get('book_title_apa'):
                fields['title_apa'] = first['book_title_apa']
            old_chapters, projects, auto = [], [], []
        if not fields.get('title_apa') and first.get('book_title_apa'):
            fields['title_apa'] = first['book_title_apa']
        new_chapters = []
        for c in chs:
            f = c['fields']
            ch = {'id': c['tag'], 'former_tag': c['tag']}
            for k, v in f.items():
                if k in CHAPTER_KEYS or k.startswith('_override'):
                    ch[k] = v
            # a book detail this chapter has differently: the chapter keeps its own, so it reads as before
            for k in BOOK_KEYS:
                if f.get(k) and f.get(k) != fields.get(k):
                    if not fields.get(k):
                        fields[k] = f[k]
                    else:
                        ch[k] = f[k]
            for k, v in f.items():                         # other keys (a series…): the book's if it has none, else the chapter's
                if k not in CHAPTER_KEYS and k not in BOOK_KEYS and k not in ('book_title', 'book_title_apa') and not k.startswith('_override'):
                    if k not in fields:
                        fields[k] = v
                    elif fields[k] != v:
                        ch[k] = v
            new_chapters.append(ch)
            for p in c.get('projects') or []:
                if p not in projects:
                    projects.append(p)
                    if p in (c.get('projects_auto') or []):
                        auto.append(p)
            moved[c['tag']] = g['book_tag']
        fields['chapters'] = old_chapters + [x for x in new_chapters if x['id'] not in {o.get('id') for o in old_chapters}]
        # write the book (keeping its creation date), then check every chapter reads as it did
        p = store.cite_path(g['book_tag'])
        created = book.get('created') if book else min((c.get('created') or '') for c in chs) or store.now()
        store.write_citation(g['book_tag'], {'type': 'edited_book', 'fields': fields}, force=True, create=not book)
        meta, body = store.parse_front(p.read_text(encoding='utf-8'))
        meta['created'] = created
        meta.pop('projects', None); meta.pop('projects_auto', None)
        if projects:
            meta['projects'] = projects
            if auto:
                meta['projects_auto'] = auto
        store.write_atomic(p, store.dump_front(meta, body))
        newbook = store.read_citation(p)
        ids = [x['id'] for x in newbook['fields'].get('chapters', [])]
        for c in chs:
            if c['tag'] not in ids:
                raise SystemExit('chapter %s did not keep its id in %s' % (c['tag'], g['book_tag']))
            before = _forms(c)
            after = _forms(cf.edited_chapter(newbook, c['tag']))
            for k in FORMS:
                if before[k] != after[k]:
                    report['differences'].append({'chapter': c['tag'], 'form': k, 'before': before[k], 'after': after[k]})
        report['books'].append({'tag': g['book_tag'], 'was': g['existing'] or 'new', 'title': newbook['fields'].get('title', ''),
                                'chapters': [c['tag'] for c in chs], 'warnings': newbook['missing']})
        for c in chs:
            _move_files(c['tag'], g['book_tag'], c['tag'], report)
            store.cite_path(c['tag']).unlink()

    # documents and research notes: the marks, and notes' linked sources
    for info in store.documents():
        for f in store.section_paths(info['slug']):
            md = f.read_text(encoding='utf-8')
            new, n = _rewrite_marks(md, moved)
            if n:
                store.write_atomic(f, new)
                report['rewritten'] += n
    if store.notes_dir().exists():
        for f in sorted(store.notes_dir().glob('*.md')):
            text = f.read_text(encoding='utf-8')
            meta, body = store.parse_front(text)
            body2, n = _rewrite_marks(body, moved)
            links = store.note_citations(meta)
            links2 = []
            for t in links:
                t = moved.get(t, t)
                if t not in links2:
                    links2.append(t)
            if n or links2 != links:
                if links2 != links:
                    meta.update(store._note_links(links2))
                store.write_atomic(f, store.dump_front(meta, body2))
                report['rewritten'] += n
                report['notes'] += 1

    # Verify results: doc:old:pin:n -> doc:book#old:pin:n
    vdir = store.projects_dir() / 'verification'
    if vdir.exists():
        for f in sorted(vdir.glob('*.json')):
            d = json.loads(f.read_text(encoding='utf-8'))
            res, changed = {}, False
            for k, v in (d.get('results') or {}).items():
                parts = k.split(':')
                if len(parts) >= 4 and parts[1] in moved:
                    parts[1] = moved[parts[1]] + '#' + parts[1]
                    k = ':'.join(parts)
                    if isinstance(v, dict) and v.get('tag') in moved:
                        v = dict(v, tag=moved[v['tag']])
                    changed = True
                    report['verify_keys'] += 1
                res[k] = v
            if changed:
                d['results'] = res
                store.write_atomic(f, json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True) + '\n')

    # anything that still names an old tag (outside built outputs and document versions, which still resolve)
    pat = re.compile(r'tag="(%s)"' % '|'.join(re.escape(t) for t in moved))
    for f in data.rglob('*'):
        if f.is_file() and f.suffix in ('.md', '.json', '.yaml') and not {'outputs', '.git', 'build', '_versions', 'versions', '.versions'} & set(f.relative_to(data).parts):
            if pat.search(f.read_text(encoding='utf-8', errors='ignore')):
                report['leftovers'].append(str(f.relative_to(data)))
    return report


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = Path(sys.argv[1]).expanduser().resolve()
    if 'Application Support' in str(data):
        sys.exit("That's ReWord's live data folder. Run this on a clone of the data repository instead.")
    p = plan(data)
    if '--apply' not in sys.argv:
        print(json.dumps(p, indent=1, ensure_ascii=False))
        return
    print(json.dumps(apply(data, p), indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
