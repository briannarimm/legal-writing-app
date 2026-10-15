"""Moving a document's text from one template's citation system to another's. Standard library only.

Citations themselves never need rewriting: a live citation ([…]{.cite tag="…"}) is formatted from the
library at build time in whatever style the template uses. What changes between templates is *where*
citations sit:

    notes        law review article, Chicago notes and bibliography   the citation is a footnote
    paren        APA, Chicago author-date                            "… matters (Walker, 2017)."
    sentence     memos, briefs, email (Bluebook in the text)         "… matters. Walker, Why We Sleep 45."

convert_sections() moves citations between those places. Footnotes holding only citations become text
citations and back; footnotes that also say something else stay footnotes (their citations are restyled
when the document is built). Narrative citations ("Walker (2017) found …") keep the author's name in
the sentence when they move into a note.
"""
import re

CHIP_ATTR_RE = re.compile(r'\{\.cite((?:\s+[a-z]+="(?:\\.|[^"\\])*")*)\s*\}')
ATTR_RE = re.compile(r'([a-z]+)="((?:\\.|[^"\\])*)"')
DEF_RE = re.compile(r'^\[\^([^\]\s]+)\]:[ \t]?(.*)$')
REF_RE = re.compile(r'\[\^([^\]\s]+)\](?!:)')
GAP = ' \t\u200b'              # what may sit between the citations of a string cite (with one ";")
CLOSERS = '"\'”’)*_'            # closing quotes, parentheses and emphasis that follow punctuation
PUNCT = '.,;:?!'


def placement(tmpl, style):
    """Where a template puts its citations: notes · paren · sentence."""
    if tmpl.get('cite_mode') == 'footnote':
        return 'notes'
    return 'paren' if style in ('apa', 'chicago-ad') else 'sentence'


# ------------------------------------------------------------------ finding citations

def find_chips(text):
    """[(start, end, attrs)] for every live citation in a piece of Markdown (brackets may nest)."""
    out = []
    i = 0
    while True:
        i = text.find('[', i)
        if i < 0:
            return out
        depth, k = 0, i
        while k < len(text):
            ch = text[k]
            if ch == '\\':
                k += 2
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if k >= len(text):
            return out
        m = CHIP_ATTR_RE.match(text, k + 1)
        if m:
            attrs = {a: re.sub(r'\\(.)', r'\1', v) for a, v in ATTR_RE.findall(m.group(1))}
            out.append((i, m.end(), attrs))
            i = m.end()
        else:
            i += 1


def groups(text):
    """Citations side by side (a string cite: separated only by ';' and spaces) as [(start, end, [chips])]."""
    chips = find_chips(text)
    out = []
    for c in chips:
        if out:
            between = text[out[-1][1]:c[0]]
            if between.strip(GAP) == ';':
                out[-1] = (out[-1][0], c[1], out[-1][2] + [c])
                continue
        out.append((c[0], c[1], [c]))
    return out


def set_attr(chip_md, key, value):
    """The same citation with one attribute changed (value '' removes it)."""
    m = CHIP_ATTR_RE.search(chip_md, chip_md.rfind('{.cite'))
    attrs = [(a, v) for a, v in ATTR_RE.findall(m.group(1)) if a != key]
    if value:
        attrs.append((key, value.replace('\\', '\\\\').replace('"', '\\"')))
    return chip_md[:m.start()] + '{.cite' + ''.join(' %s="%s"' % kv for kv in attrs) + '}'


def cites_only(text):
    """True when a note holds nothing but citations (and the punctuation between and after them)."""
    if not find_chips(text):
        return False
    rest = text
    for s, e, _ in reversed(find_chips(text)):
        rest = rest[:s] + rest[e:]
    return rest.strip(GAP + '\n;.,') == ''


# ------------------------------------------------------------------ a section's footnotes

def split_notes(md):
    """(body lines, {label: note text}, [labels in order]) as the editor reads them (md.js parse)."""
    lines = md.replace('\r\n', '\n').split('\n')
    body, defs, order = [], {}, []
    i = 0
    while i < len(lines):
        m = DEF_RE.match(lines[i])
        if not m:
            body.append(lines[i])
            i += 1
            continue
        paras = [[m.group(2)]]
        j = i + 1
        while j < len(lines):
            if re.match(r'^( {4}|\t)\S', lines[j]):
                paras[-1].append(lines[j].strip())
                j += 1
                continue
            if lines[j].strip() == '':
                k = j
                while k < len(lines) and lines[k].strip() == '':
                    k += 1
                if k < len(lines) and re.match(r'^( {4}|\t)\S', lines[k]):
                    paras.append([])
                    j = k
                    continue
            break
        defs[m.group(1)] = '\n\n    '.join(' '.join(p) for p in paras)
        order.append(m.group(1))
        i = j
    while body and body[-1].strip() == '':
        body.pop()
    return body, defs, order


def join_notes(body, defs, order):
    text = '\n'.join(body).rstrip('\n')
    notes = ['[^%s]: %s' % (lb, defs[lb]) for lb in order if lb in defs]
    return (text + ('\n\n' + '\n\n'.join(notes) if notes else '')).strip('\n') + '\n'


def paragraphs(body):
    """Split body lines into blocks; yields (kind, lines) with kind 'text' for prose paragraphs."""
    out, cur, fence = [], [], False
    for ln in body:
        if re.match(r'^(```|~~~)', ln):
            fence = not fence
        if not fence and ln.strip() == '':
            if cur:
                out.append(cur)
            out.append(None)
            cur = []
        else:
            cur.append(ln)
    if cur:
        out.append(cur)
    blocks = []
    for b in out:
        if b is None:
            blocks.append(('blank', ['']))
            continue
        first = b[0]
        prose = not (re.match(r'^(#{1,6}\s|\||:::|```|~~~|\\begin|<|\s{4}|\t|-{3,}\s*$|\*{3,}\s*$|Table:)', first))
        blocks.append(('text' if prose else 'raw', b))
    return blocks


# ------------------------------------------------------------------ text citations -> notes

def _attach_after_punct(text, at):
    """Where a note marker goes: after the punctuation (and closing quotes) that follows `at`, if any."""
    k = at
    if k < len(text) and text[k] in PUNCT:
        k += 1
        while k < len(text) and text[k] in CLOSERS:
            k += 1
        return k
    return None


def to_notes(text, new_label, names_for):
    """Move every text citation in one paragraph into a new footnote. Returns (text, [(label, note)])."""
    notes = []
    found = groups(text)
    labels = [new_label() for _ in found]           # numbered in reading order
    for (s, e, chips), label in reversed(list(zip(found, labels))):
        narrative = [c for c in chips if c[2].get('narrative')]
        moved = []
        for c in chips:
            md = text[c[0]:c[1]]
            moved.append(md)                 # a narrative mark keeps narrative="1" so it can come back
        notes.append((label, '; '.join(moved) + '.'))
        marker = '[^%s]' % label
        if narrative and len(chips) == 1:
            # "Walker (2017) found …" -> "Walker[^n] found …"
            names = names_for(chips[0][2].get('tag', ''))
            pre, post = text[:s].rstrip(GAP), text[e:]
            if names and pre.endswith(names + ',') and post[:1] == ',':
                text = pre[:-1] + marker + post[1:]          # back from Bluebook: "Walker, [cite], found"
            else:
                text = text[:s] + names + marker + text[e:]
            continue
        pre, post = text[:s].rstrip(GAP + '\n'), text[e:]
        lead = text[len(pre):s]
        if post[:1] == '.' and re.search(r'[.?!][%s]*$' % re.escape(CLOSERS), pre):
            # a citation sentence after the sentence it supports
            text = pre + marker + post[1:]
        elif pre.endswith(',') and post[:1] == ',':
            # a citation clause set off by commas
            text = pre + marker + post[1:]
        elif pre == '' and post.strip(GAP + '.') == '':
            text = marker                    # a paragraph that is only a citation (rejoined below)
        else:
            k = _attach_after_punct(post, 0)
            if k is not None:
                text = pre + post[:k] + marker + post[k:]
            else:
                text = pre + marker + (post if post[:1] in GAP + '\n' or not post else (lead[:1] or ' ') + post)
    notes.reverse()
    return text, notes


# ------------------------------------------------------------------ notes -> text citations

def from_note(text, at, end, note, kind, names_for=None):
    """Replace the marker text[at:end] with the note's citations, placed for `kind` (paren or sentence)."""
    found = find_chips(note)
    chips = [note[s:e] for s, e, _ in found]
    cites = '; '.join(chips)
    pre, post = text[:at], text[end:]
    if kind == 'paren' and len(found) == 1 and found[0][2].get('narrative') and names_for:
        # "Walker[^n] found …" -> "Walker (2017) found …" (the narrative citation names the author itself)
        names = names_for(found[0][2].get('tag', ''))
        if names and pre.endswith(names):
            return pre[:-len(names)] + cites + post
    # the punctuation (and closing quotes) just before the marker
    m = re.search(r'([%s])([%s]*)$' % (re.escape(PUNCT), re.escape(CLOSERS)), pre)
    if kind == 'paren':
        if m and m.group(1) not in '?!':
            # "matters.[^1]" -> "matters (Walker, 2017)."  /  "said “x.”[^1]" -> "said “x” (Walker, 2017)."
            head = pre[:m.start()]
            return head + m.group(2) + ' ' + cites + m.group(1) + post
        return pre + ' ' + cites + post
    # Bluebook in the text: a citation sentence after a sentence, a clause after a comma or a word
    if m and m.group(1) in '.?!':
        return pre + ' ' + cites + '.' + post
    if m and m.group(1) == ',':
        return pre + ' ' + cites + ',' + post
    if re.match(r'^\s*[%s]' % re.escape(PUNCT), post):
        return pre + ', ' + cites + post
    return pre + ', ' + cites + ',' + post


# ------------------------------------------------------------------ the whole document

def convert_sections(sections, src, dst, names_for):
    """sections: [(name, markdown)]; src/dst: placement() of the old and new template.
    Returns ([(name, markdown)], report) where report counts what moved."""
    report = {'to_notes': 0, 'to_text': 0, 'notes_kept': 0}
    if src == dst:
        return sections, report
    taken = set()
    for _, md in sections:
        taken |= set(REF_RE.findall(md)) | set(m.group(1) for m in re.finditer(r'(?m)^\[\^([^\]\s]+)\]:', md))
    counter = [0]

    def new_label():
        while True:
            counter[0] += 1
            lb = 'cite-%d' % counter[0]
            if lb not in taken:
                taken.add(lb)
                return lb

    out = []
    for name, md in sections:
        body, defs, order = split_notes(md)
        created = set()
        # 1. text citations become notes (from APA, Chicago author-date, or Bluebook-in-the-text)
        if src != 'notes':
            blocks = paragraphs(body)
            new_body = []
            for kind, lines in blocks:
                if kind != 'text':
                    new_body.extend(lines)
                    continue
                text, notes = to_notes('\n'.join(lines), new_label, names_for)
                if notes:
                    report['to_notes'] += len(notes)
                    for lb, note in notes:
                        defs[lb] = note
                        order.append(lb)
                        created.add(lb)
                    # a paragraph that was only a citation: its note goes on the paragraph before
                    if REF_RE.fullmatch(text.strip()) and new_body:
                        k = len(new_body) - 1
                        while k >= 0 and new_body[k].strip() == '':
                            k -= 1
                        if k >= 0 and not new_body[k].startswith(('#', '[^')):
                            new_body[k] = new_body[k] + text.strip()
                            while new_body and new_body[-1].strip() == '':
                                new_body.pop()
                            continue
                new_body.extend(text.split('\n'))
            body = new_body
        # 2. notes that are only citations become text citations (to APA, author-date or Bluebook-in-the-text)
        if dst != 'notes':
            text = '\n'.join(body)
            for m in reversed(list(REF_RE.finditer(text))):
                lb = m.group(1)
                note = defs.get(lb)
                if note is None or not cites_only(note):
                    continue
                text = from_note(text, m.start(), m.end(), note, dst, names_for)
                defs.pop(lb)
                if lb not in created:
                    report['to_text'] += 1
                else:
                    report['to_notes'] -= 1        # it moved twice (APA <-> Bluebook): count it once
                    report['to_text'] += 1
            body = text.split('\n')
        report['notes_kept'] += sum(1 for lb in defs if lb not in created and find_chips(defs[lb]))
        out.append((name, join_notes(body, defs, order)))
    return out, report


# ------------------------------------------------------------------ document details (metadata.yaml)

def _scalar(meta, key):
    m = re.search(r'(?m)^%s:[ \t]*(.+?)[ \t]*$' % re.escape(key), meta)
    if not m:
        return ''
    v = m.group(1).strip()
    if v in ('|', '>', '|-', '>-'):
        return ''
    return _unquote(v)


def _unquote(v):
    v = re.sub(r'\s+#.*$', '', v.strip()) if not v.strip().startswith(('"', "'")) else v.strip()
    if len(v) > 1 and v.startswith('"') and v.endswith('"'):
        return re.sub(r'\\(.)', r'\1', v[1:-1])
    if len(v) > 1 and v.startswith("'") and v.endswith("'"):
        return v[1:-1].replace("''", "'")
    return v


def _block(meta, key):
    """A `key: |` block's text, without its indentation."""
    m = re.search(r'(?m)^%s:[ \t]*[|>]-?[ \t]*\n((?:[ \t]+.*\n?|[ \t]*\n)+)' % re.escape(key), meta)
    if not m:
        return ''
    lines = m.group(1).rstrip().split('\n')
    return '\n'.join(ln.strip() for ln in lines).strip()


def authors_of(meta):
    """Author names in a document's details, whatever shape the template used."""
    names = []
    m = re.search(r'(?m)^author:[ \t]*\n((?:[ \t]+.*\n?)+)', meta)
    if m:
        for ln in m.group(1).split('\n'):
            x = re.match(r'^\s*-\s*(.+?)\s*$', ln)
            if not x:
                continue
            v = x.group(1)
            if v.startswith('name:'):
                v = v[5:].strip()
            elif re.match(r'^[\w-]+:(\s|$)', v):          # another key of a list item ({affiliation: …})
                continue
            names.append(_unquote(v))
    else:
        v = _scalar(meta, 'author')
        if v:
            names = [v]
    if not names:
        for key in ('from', 'signature'):
            v = _scalar(meta, key)
            if v:
                names = [v]
                break
    return [n for n in names if n and n != 'Your Name']


KEPT_MARK = '# Details from the'


def _q(v):
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'


def convert_metadata(old, seed, title, old_name):
    """The new template's details (from its starter file), with the title, authors, abstract and keywords
    carried over, and the old details kept below as comments so nothing is lost."""
    new = seed.replace('{{title}}', title.replace('\\', '\\\\').replace('"', '\\"'))
    names = authors_of(old)
    if names:
        if re.search(r'(?m)^author:[ \t]*\n', new):
            # a list of authors; keep the first entry's shape (with or without name:)
            m = re.search(r'(?m)^author:[ \t]*\n((?:[ \t]+.*\n?)+)', new)
            first = re.match(r'^(\s*)-\s*(name:\s*)?', m.group(1))
            indent, has_name = first.group(1), bool(first.group(2))
            items = ''.join('%s- %s%s\n' % (indent, 'name: ' if has_name else '', _q(n)) for n in names)
            new = new[:m.start(1)] + items + new[m.end(1):]
        elif re.search(r'(?m)^author:', new):
            new = re.sub(r'(?m)^author:.*$', lambda _: 'author: ' + _q(', '.join(names)), new, 1)
        elif re.search(r'(?m)^from:', new):
            new = re.sub(r'(?m)^from:.*$', lambda _: 'from: ' + _q(names[0]), new, 1)
        elif re.search(r'(?m)^signature:', new):
            new = re.sub(r'(?m)^signature:.*$', lambda _: 'signature: ' + _q(names[0]), new, 1)
    abstract = _block(old, 'abstract') or _scalar(old, 'abstract')
    if abstract and re.search(r'(?m)^#?\s*abstract:', new):
        block = 'abstract: |\n' + ''.join('  ' + ln + '\n' for ln in abstract.split('\n'))
        m = re.search(r'(?m)^#?\s*abstract:[ \t]*(?:[|>]-?[ \t]*\n(?:[ \t]+.*\n?|[ \t]*\n(?=[ \t]))*|.*\n?)', new)
        new = new[:m.start()] + block + new[m.end():]
    # other one-line details both templates have (affiliation, date, running head …)
    for m in list(re.finditer(r'(?m)^(#\s*)?([a-z][\w-]*):[ \t]*(\S.*)?$', new)):
        key = m.group(2)
        if key in ('title', 'author', 'abstract', 'keywords', 'lang') or (m.group(3) or '').strip() in ('|', '>'):
            continue
        v = _scalar(old, key)
        if v and v not in ('Your Name',):
            new = re.sub(r'(?m)^#?\s*%s:.*$' % re.escape(key), lambda _: '%s: %s' % (key, _q(v)), new, 1)
    kw = re.search(r'(?m)^keywords:.*(?:\n[ \t]+-.*)*', old)
    if kw and re.search(r'(?m)^#?\s*keywords:', new):
        m = re.search(r'(?m)^#?\s*keywords:.*(?:\n[ \t]+-.*)*', new)
        new = new[:m.start()] + kw.group(0) + new[m.end():]
    live = old.split(KEPT_MARK)[0]                  # earlier switches' kept details are in _trash, not repeated here
    kept = [ln for ln in live.rstrip('\n').split('\n') if ln.strip()]
    if kept:
        new = new.rstrip('\n') + '\n\n' + KEPT_MARK + ' %s template, kept for reference (copy anything you need above):\n' % old_name
        new += ''.join('# ' + ln.lstrip('# ') + '\n' if ln.lstrip().startswith('#') else '# ' + ln + '\n' for ln in kept)
    return new
