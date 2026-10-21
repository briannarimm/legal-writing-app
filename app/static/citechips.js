/* Live citation chips. A chip is <span class="cite" data-tag data-pin data-signal data-paren data-narrative
 * data-form contenteditable="false">full citation</span>; md.js reads and writes them as
 * [text]{.cite tag="…" …}. The text is refreshed from the library (the server formats it), and the
 * build re-formats every chip, adding short forms, Id. and supra in the final draft (app/cites.py).
 *
 *   App.chips.refresh(roots, format)        re-render chip text in these elements
 *   App.chips.html(c, attrs)                a new chip's HTML (with the library's current full form)
 *   App.chips.edit(chip, {format, changed}) the little editor that opens when you click a chip
 */
(function () {
  'use strict';
  const { el, post, toast } = App;

  const SIGNALS = ['', 'See', 'See also', 'Cf.', 'Compare', 'But see', 'But cf.', 'See generally', 'E.g.,', 'See, e.g.,', 'Accord', 'Contra'];

  async function refresh(roots, format) {
    const chips = [];
    roots.forEach(r => r && r.querySelectorAll('span.cite').forEach(c => chips.push(c)));
    if (!chips.length) return;
    const items = chips.map(ch => ({ tag: ch.dataset.tag, pin: ch.dataset.pin || '', signal: ch.dataset.signal || '',
      paren: ch.dataset.paren || '', narrative: ch.dataset.narrative || '', form: ch.dataset.form || '', note: format !== 'lawreview' || !!ch.closest('.note-body') }));
    let r;
    try { r = await post('/api/cite/render', { format, items }); } catch (e) { return; }
    r.items.forEach((it, k) => {
      const ch = chips[k];
      if (!ch.isConnected) return;
      ch.innerHTML = it.html;
      ch.classList.toggle('missing', !!it.missing);
      ch.title = it.missing ? 'This citation is no longer in the library (' + ch.dataset.tag + ')' : 'Live citation: click to edit the pin cite, signal or parenthetical';
    });
  }

  function chipHtml(c, attrs, format) {
    const a = Object.assign({ tag: c.tag }, attrs || {});
    const text = App.citeMarkdown(c, App.isParenFormat(format) ? (a.narrative ? 'narrative' : 'intext') : 'full', format);
    return MD.citeChip(a, MD.inlineHtml(text));
  }

  /* ------------------------------------------------------------ the chip editor */
  let pop = null, popChip = null;
  function closePop() {
    if (pop) { pop.remove(); pop = null; }
    if (popChip) popChip.classList.remove('editing');
    popChip = null;
  }
  document.addEventListener('mousedown', e => { if (pop && !pop.contains(e.target) && e.target !== popChip && !popChip.contains(e.target)) closePop(); });
  document.addEventListener('keydown', e => { if (pop && e.key === 'Escape') { e.preventDefault(); const ch = popChip; closePop(); placeCaretAfter(ch); } });
  window.addEventListener('resize', closePop);

  function placeCaretAfter(ch) {
    if (!ch || !ch.isConnected) return;
    const ed = ch.closest('[contenteditable="true"]');
    if (ed) ed.focus();
    let z = ch.nextSibling;
    if (!(z && z.nodeType === 3)) { z = document.createTextNode('​'); ch.after(z); }
    const r = document.createRange(); r.setStart(z, z.nodeValue.startsWith('​') ? 1 : 0); r.collapse(true);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  }

  function edit(chip, opts) {
    closePop();
    const format = opts.format || 'practitioner';
    const apa = App.isParenFormat(format);          // APA or Chicago author-date: (Author, Year) in the text
    popChip = chip; chip.classList.add('editing');
    pop = el('div', 'chip-pop');
    const c = App.citation(chip.dataset.tag);
    const head = el('div', 'chip-head');
    head.append(el('code', '', chip.dataset.tag), el('span', 'muted small', c ? App.typeLabel(c.type) : 'not in the library'));
    pop.appendChild(head);
    let timer;
    const changed = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => { await refresh([chip.parentElement], format); if (opts.changed) opts.changed(chip); }, 150);
    };
    const set = (k, v) => { if (v) chip.dataset[k] = v; else delete chip.dataset[k]; changed(); };
    const row = (label, input) => { const r = el('label', 'chip-row'); r.append(el('span', '', label), input); pop.appendChild(r); return input; };

    const sig = el('select');
    SIGNALS.forEach(s => { const o = el('option', '', s || '(no signal)'); o.value = s; sig.appendChild(o); });
    const cur = chip.dataset.signal || '';
    if (cur && !SIGNALS.includes(cur)) { const o = el('option', '', cur); o.value = cur; sig.appendChild(o); }
    sig.value = cur;
    row('Signal', sig).addEventListener('change', () => set('signal', sig.value));
    const pin = el('input'); pin.value = chip.dataset.pin || ''; pin.placeholder = apa ? '12 · 12-14 · para. 3' : '460 · 460–61 · § 2(b) · ¶ 12';
    row(apa ? 'Page' : 'Pin cite', pin).addEventListener('input', () => set('pin', pin.value.trim()));
    if (!apa) {
      const par = el('input'); par.value = chip.dataset.paren || ''; par.placeholder = 'holding that …  (no parentheses)';
      row('Parenthetical', par).addEventListener('input', () => set('paren', par.value.trim()));
      const full = el('input'); full.type = 'checkbox'; full.checked = chip.dataset.form === 'full';
      const fl = el('label', 'chip-check'); fl.append(full, ' Always the full citation here (no short form or Id.)');
      full.addEventListener('change', () => set('form', full.checked ? 'full' : ''));
      pop.appendChild(fl);
    } else {
      const nar = el('input'); nar.type = 'checkbox'; nar.checked = !!chip.dataset.narrative;
      const nl = el('label', 'chip-check'); nl.append(nar, format === 'apa' ? ' Narrative: Walker (2017) instead of (Walker, 2017)' : ' Narrative: Walker (2017) instead of (Walker 2017)');
      nar.addEventListener('change', () => set('narrative', nar.checked ? '1' : ''));
      pop.appendChild(nl);
    }
    pop.appendChild(el('div', 'hint', apa ? 'In-text citations are the same every time; the References list is built from them.'
      : format === 'chicago' ? 'Drafts show every note in full. With Final draft on, Save also builds a copy with shortened notes after the first full one.'
      : 'Drafts show every citation in full. With Final draft on, Save also builds a copy with Id., short forms and supra.'));
    const acts = el('div', 'row');
    const swap = el('button', 'btn small', 'Change source…'); swap.type = 'button';
    swap.onclick = () => {
      const keep = chip; closePop();
      App.pickCitation({ title: 'Change the source', format, live: true, onPick: (nc, which) => {
        keep.dataset.tag = nc.tag;
        if (App.isParenFormat(format)) { if (which === 'narrative') keep.dataset.narrative = '1'; else delete keep.dataset.narrative; }
        refresh([keep.parentElement], format).then(() => opts.changed && opts.changed(keep));
      } });
    };
    const open = el('button', 'btn small', 'Open in Citations'); open.type = 'button'; open.disabled = !c;
    open.onclick = () => { closePop(); App.showView('citations').then(() => App.views.citations.open(chip.dataset.tag)); };
    const rm = el('button', 'btn small danger', 'Remove'); rm.type = 'button';
    rm.onclick = () => { const p = chip.parentElement; chip.remove(); closePop(); if (opts.changed) opts.changed(null, p); };
    const done = el('button', 'btn small primary', 'Done'); done.type = 'button';
    done.onclick = () => { const ch = chip; closePop(); placeCaretAfter(ch); };
    acts.append(swap, open, rm, done);
    pop.appendChild(acts);
    document.body.appendChild(pop);
    const r = chip.getBoundingClientRect();
    const w = Math.min(420, window.innerWidth - 24);
    pop.style.width = w + 'px';
    pop.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left)) + 'px';
    const below = r.bottom + 8, h = pop.offsetHeight;
    pop.style.top = (below + h < window.innerHeight - 8 ? below : Math.max(8, r.top - h - 8)) + 'px';
    pin.focus();
  }

  /* ------------------------------------------------------------ going to a citation ("Cited in") */
  // u = one place from /api/citation/uses: {tag, k (which match in its text or footnote), start, end (in the file)}.
  // In the rich editor: scroll the chip into the middle, flash it, and put the caret after it.
  function reveal(root, u) {
    const sel = 'span.cite[data-tag="' + CSS.escape(u.tag) + '"], span.auth[data-tag="' + CSS.escape(u.tag) + '"]';
    const list = root ? Array.from(root.querySelectorAll(sel)) : [];
    const chip = list[u.k];
    if (!chip) return revealRaw(root, u, u.k - list.length) || (list.length ? reveal(root, Object.assign({}, u, { k: list.length - 1 })) : false);
    placeCaretAfter(chip);
    chip.scrollIntoView({ block: 'center', behavior: 'smooth' });
    chip.classList.remove('flash'); void chip.offsetWidth; chip.classList.add('flash');
    setTimeout(() => chip.classList.remove('flash'), 2400);
    return true;
  }
  // A paragraph the editor can't show as formatted text (a table, raw LaTeX…) stays plain Markdown, so its
  // citations aren't chips: select the n-th one's Markdown there instead.
  function revealRaw(root, u, n) {
    if (!root || n < 0) return false;
    const key = 'tag="' + u.tag + '"';
    for (const raw of root.querySelectorAll('.raw')) {
      const t = raw.firstChild && raw.firstChild.nodeType === 3 ? raw.firstChild : null;
      if (!t) continue;
      let i = -1;
      while ((i = t.nodeValue.indexOf(key, i + 1)) >= 0) {
        if (n-- > 0) continue;
        const a = Math.max(0, t.nodeValue.lastIndexOf('[', i)), b = t.nodeValue.indexOf('}', i) + 1 || i + key.length;
        const r = document.createRange(); r.setStart(t, a); r.setEnd(t, b);
        raw.focus();
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
        const box = r.getBoundingClientRect(), sc = raw.closest('.scroller');
        if (sc) sc.scrollTop += box.top - sc.getBoundingClientRect().top - sc.clientHeight / 2;
        return true;
      }
    }
    return false;
  }
  // In a Markdown text box: select the citation's source text and scroll it into the middle.
  function revealText(ta, u) {
    const v = ta.value, key = 'tag="' + u.tag + '"';
    let a = u.start, b = u.end;
    if (!(a >= 0 && b <= v.length && v.slice(a, b).includes(key))) {          // typed since it was saved: find it again
      let i = -1;
      for (let n = 0; n <= (u.k || 0); n++) { const j = v.indexOf(key, i + 1); if (j < 0) break; i = j; }
      if (i < 0) return false;
      a = v.lastIndexOf('[', i); b = v.indexOf('}', i) + 1;
    }
    ta.focus();
    ta.setSelectionRange(a, b);
    // how far down the selection is: lay the text before it out in an invisible copy of the box
    const cs = getComputedStyle(ta), m = document.createElement('div');
    ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing', 'paddingTop', 'paddingLeft', 'paddingRight', 'tabSize']
      .forEach(k => { m.style[k] = cs[k]; });
    Object.assign(m.style, { position: 'absolute', visibility: 'hidden', left: '-9999px', top: '0', boxSizing: 'border-box',
      width: ta.clientWidth + 'px', whiteSpace: 'pre-wrap', overflowWrap: 'break-word', border: '0' });
    m.textContent = v.slice(0, a) + '​';
    document.body.appendChild(m);
    const y = m.scrollHeight;
    m.remove();
    ta.scrollTop = Math.max(0, y - ta.clientHeight / 2);
    return true;
  }

  App.chips = { refresh, html: chipHtml, edit, close: closePop, reveal, revealText };
})();
