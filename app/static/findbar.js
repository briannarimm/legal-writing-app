/* Find and Replace (⌘F, ⇧⌘H) in the document or research note you're writing: the text, its footnotes, or
 * the Markdown when you edit as Markdown. ⌘G and ⇧⌘G (or Enter and ⇧Enter) step through the matches.
 * Citations are left alone: a live citation's text comes from the library, so it is neither searched nor replaced.
 * Matches are painted with the CSS Custom Highlight API; replacing goes through the editor's own typing, so ⌘Z
 * undoes it.
 *
 *   App.find.open(replace?)   App.find.next(±1)   App.find.close()
 */
(function () {
  'use strict';
  const { $, el, toast } = App;

  const bar = el('div', 'find-bar glass'); bar.hidden = true;
  bar.setAttribute('role', 'search');
  const q = el('input'); q.type = 'search'; q.placeholder = 'Find'; q.spellcheck = false; q.setAttribute('aria-label', 'Find');
  const count = el('span', 'find-count muted small');
  const mk = (label, title, fn) => { const b = el('button', 'icon-btn', label); b.type = 'button'; b.title = title; b.onclick = fn; return b; };
  const prev = mk('‹', 'Previous match (⇧⌘G)', () => step(-1));
  const next = mk('›', 'Next match (⌘G)', () => step(1));
  const caseBtn = mk('Aa', 'Match upper and lower case', () => { caseBtn.classList.toggle('active'); search(); });
  const wordBtn = mk('“ ”', 'Whole words only', () => { wordBtn.classList.toggle('active'); search(); });
  const more = mk('⇄', 'Replace (⇧⌘H)', () => setReplace(!bar.classList.contains('replacing')));
  const close = mk('✕', 'Close (Esc)', () => hide());
  const r = el('input'); r.type = 'text'; r.placeholder = 'Replace with'; r.spellcheck = false; r.setAttribute('aria-label', 'Replace with');
  const one = el('button', 'btn small', 'Replace'); one.type = 'button'; one.onclick = () => replace(false);
  const all = el('button', 'btn small', 'All'); all.type = 'button'; all.title = 'Replace every match'; all.onclick = () => replace(true);
  const row1 = el('div', 'find-row'), row2 = el('div', 'find-row find-replace');
  row1.append(q, count, prev, next, caseBtn, wordBtn, more, close);
  row2.append(r, one, all);
  bar.append(row1, row2);
  document.body.appendChild(bar);
  bar.addEventListener('mousedown', e => { if (e.target === bar) e.preventDefault(); });

  const hl = (typeof Highlight === 'function' && window.CSS && CSS.highlights) ? CSS.highlights : null;
  let matches = [];        // rich: {range}; Markdown: {ta, a, b}
  let cur = -1;

  /* ------------------------------------------------------------ where to look */
  function target() {
    if (App.view === 'writing') {
      if (!App.views.writing.current()) return null;
      if (App.editMode === 'md' && !$('#doc-md').hidden) return { ta: $('#doc-md') };
      if ($('#page').hidden) return null;                                    // the Details box
      return { roots: [$('#doc'), ...document.querySelectorAll('#notes .note-body')] };
    }
    if (App.view === 'research') {
      if ($('#note-editor').hidden) return null;
      return App.editMode === 'md' ? { ta: $('#note-md') } : { roots: [$('#note-body')] };
    }
    return null;
  }

  function pattern() {
    const text = q.value;
    if (!text) return null;
    let src = text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/["“”]/g, '["“”]').replace(/['‘’]/g, "['‘’]");
    if (wordBtn.classList.contains('active')) src = '(?<![\\p{L}\\p{N}])' + src + '(?![\\p{L}\\p{N}])';
    return new RegExp(src, 'gu' + (caseBtn.classList.contains('active') ? '' : 'i'));
  }

  // The text of an editor as one string, block by block, with a map back to its text nodes. Citations and footnote
  // marks are skipped; a match never runs from one paragraph into the next.
  function textOf(root) {
    const parts = [];
    let s = '';
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: n => n.parentElement.closest('span.cite, .fnref, .note-label') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    let lastBlock = null, n;
    while ((n = walk.nextNode())) {
      const block = n.parentElement.closest('p, li, h1, h2, h3, h4, h5, h6, blockquote, .raw, .note-body > div, div');
      if (lastBlock && block !== lastBlock) s += '\n';
      lastBlock = block;
      parts.push({ node: n, at: s.length });
      s += n.nodeValue;
    }
    return { s, parts };
  }
  function pointAt(map, i, end) {
    let k = 0;
    while (k + 1 < map.parts.length && (end ? map.parts[k + 1].at < i : map.parts[k + 1].at <= i)) k++;
    const p = map.parts[k];
    return [p.node, Math.min(Math.max(0, i - p.at), p.node.nodeValue.length)];
  }

  function search(keep) {
    const t = target(), re = pattern();
    matches = [];
    if (t && re) {
      if (t.ta) {
        let m;
        while ((m = re.exec(t.ta.value))) { if (!m[0]) { re.lastIndex++; continue; } matches.push({ ta: t.ta, a: m.index, b: m.index + m[0].length }); }
      } else {
        t.roots.forEach(root => {
          if (!root) return;
          const map = textOf(root);
          let m;
          while ((m = re.exec(map.s))) {
            if (!m[0]) { re.lastIndex++; continue; }
            if (m[0].includes('\n')) continue;
            const range = document.createRange();
            range.setStart(...pointAt(map, m.index, false));
            range.setEnd(...pointAt(map, m.index + m[0].length, true));
            matches.push({ range, root });
          }
        });
      }
    }
    if (!keep || cur >= matches.length) cur = matches.length ? 0 : -1;
    paint();
    if (cur >= 0 && !keep) show(matches[cur]);
  }

  function paint() {
    count.textContent = !q.value ? '' : matches.length ? (cur + 1) + ' of ' + matches.length : 'Not found';
    count.classList.toggle('none', !!q.value && !matches.length);
    if (!hl) return;
    hl.delete('rw-find'); hl.delete('rw-find-cur');
    const ranges = matches.filter(m => m.range).map(m => m.range);
    if (ranges.length) hl.set('rw-find', new Highlight(...ranges));
    if (cur >= 0 && matches[cur].range) hl.set('rw-find-cur', new Highlight(matches[cur].range));
  }

  function show(m) {
    if (!m) return;
    if (m.ta) {          // a text box: select it (seen when you close the bar or click in) and scroll to it
      App.chips.revealText(m.ta, { tag: '', start: m.a, end: m.b });
      q.focus();
      return;
    }
    const box = m.range.getBoundingClientRect(), sc = m.root.closest('.scroller');
    const top = sc && sc.getBoundingClientRect().top + bar.offsetHeight + 24;       // clear of the find bar
    if (sc && (box.top < top || box.bottom > sc.getBoundingClientRect().bottom - 40)) {
      sc.scrollTop += box.top - sc.getBoundingClientRect().top - sc.clientHeight / 3;
    }
    if (!hl) { const s = getSelection(); s.removeAllRanges(); s.addRange(m.range); }
  }

  function step(dir) {
    if (!matches.length) { search(); if (!matches.length) return; }
    cur = (cur + dir + matches.length) % matches.length;
    paint(); show(matches[cur]);
  }

  // Replace through the editor's own typing (insertText), so undo works and the document notices the change.
  function replaceAt(m, text) {
    if (m.ta) {
      m.ta.focus(); m.ta.setSelectionRange(m.a, m.b);
      if (!document.execCommand('insertText', false, text)) { m.ta.setRangeText(text, m.a, m.b, 'end'); m.ta.dispatchEvent(new Event('input', { bubbles: true })); }
      return;
    }
    const s = getSelection();
    s.removeAllRanges(); s.addRange(m.range);
    m.root.focus({ preventScroll: true });
    s.removeAllRanges(); s.addRange(m.range);
    if (text) document.execCommand('insertText', false, text); else document.execCommand('delete');
  }
  function replace(every) {
    if (!q.value) { q.focus(); return; }
    search(true);
    if (!matches.length) return;
    const text = r.value;
    if (every) {
      const n = matches.length;
      for (let i = matches.length - 1; i >= 0; i--) replaceAt(matches[i], text);
      search(); toast('Replaced ' + n + ' match' + (n === 1 ? '' : 'es') + '. ⌘Z undoes them one at a time.');
    } else {
      const m = matches[cur];
      replaceAt(m, text);
      // go on to the next match after the replaced text (the new text may itself match)
      const s = getSelection(), caret = m.ta ? m.ta.selectionEnd : (s.rangeCount ? s.getRangeAt(0) : null);
      search(true);
      const i = matches.findIndex(x => (x.ta ? x.a >= caret : caret && x.range.compareBoundaryPoints(Range.END_TO_START, caret) >= 0));
      cur = matches.length ? (i >= 0 ? i : 0) : -1;
      paint(); if (cur >= 0) show(matches[cur]);
    }
    r.focus();
  }

  function setReplace(on) { bar.classList.toggle('replacing', on); more.classList.toggle('active', on); if (on) r.focus(); }

  function open(withReplace) {
    const t = target();
    if (!t) {
      if (App.view === 'citations') { const s = $('#ct-search'); s.focus(); s.select(); return; }
      toast('Open a document or note to search it.', true); return;
    }
    // start from the selected words, as most Mac apps do
    const sel = t.ta ? t.ta.value.slice(t.ta.selectionStart, t.ta.selectionEnd) : String(getSelection());
    if (sel && !sel.includes('\n') && sel.length < 80) q.value = sel;
    bar.hidden = false;
    place();
    setReplace(!!withReplace || bar.classList.contains('replacing') && withReplace !== false);
    q.focus(); q.select();
    search();
  }
  function hide() {
    if (bar.hidden) return;
    bar.hidden = true;
    if (hl) { hl.delete('rw-find'); hl.delete('rw-find-cur'); }
    const m = matches[cur];
    if (m && m.ta) { m.ta.focus(); m.ta.setSelectionRange(m.a, m.b); }
    else if (m && m.range && m.range.startContainer.isConnected) {
      m.root.focus({ preventScroll: true });
      const s = getSelection(); s.removeAllRanges(); s.addRange(m.range);
    }
    matches = []; cur = -1;
  }
  function place() {
    const pane = App.view === 'research' ? $('#note-split .note-left') : $('#editor-pane');
    const b = pane && pane.getBoundingClientRect();
    if (!b || !b.width) return;
    const w = Math.min(440, b.width - 16);
    bar.style.width = w + 'px';
    bar.style.top = (b.top + 8) + 'px';
    bar.style.left = Math.max(b.left + 8, b.right - w - 16) + 'px';
  }
  window.addEventListener('resize', () => { if (!bar.hidden) place(); });

  let timer = null;
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => search(), 120); });
  q.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
    else if (e.key === 'Escape') { e.preventDefault(); hide(); }
  });
  r.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); replace(e.altKey); }
    else if (e.key === 'Escape') { e.preventDefault(); hide(); }
  });
  // keep the matches current while you type in the document (and close when you leave it)
  let typing = null;
  document.addEventListener('input', e => {
    if (bar.hidden || bar.contains(e.target)) return;
    clearTimeout(typing); typing = setTimeout(() => search(true), 250);
  });
  const nav = App.showView;
  App.showView = async function (name) { hide(); return nav.call(App, name); };

  document.addEventListener('keydown', e => {
    if (!e.metaKey || e.ctrlKey || e.altKey || document.querySelector('dialog[open]')) return;      // ⌃F stays "forward one letter"
    if (e.code === 'KeyF' && !e.shiftKey) { e.preventDefault(); open(); }
    else if (e.code === 'KeyH' && e.shiftKey) { e.preventDefault(); open(true); }
    else if (e.code === 'KeyG' && !bar.hidden) { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
    else if (e.code === 'KeyG') { e.preventDefault(); if (q.value) { open(); } }
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !bar.hidden && !bar.contains(e.target)) hide(); });

  App.find = { open, close: hide, next: step };
  App.cmd.global.find = () => open(false);
  App.cmd.global.replace = () => open(true);
  App.cmd.global.findNext = () => (bar.hidden ? open(false) : step(1));
  App.cmd.global.findPrevious = () => (bar.hidden ? open(false) : step(-1));
})();
