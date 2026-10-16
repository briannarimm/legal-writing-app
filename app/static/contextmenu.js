/* The right-click menu. It replaces the browser's own menu everywhere in the app, and what it offers
 * depends on what you right-click:
 *
 *   text you're writing      spelling suggestions, Cut / Copy / Paste, italic / bold / small caps,
 *                            paragraph styles, Insert citation or footnote, Look Up, search
 *   a live citation          edit it, open it in Citations, copy it, remove it
 *   a footnote mark or note  go to the other end, delete the footnote
 *   documents and sections   open, rename, move to a project, move up or down, delete
 *   notes and sources        open, copy the citation in any style, start a note, delete
 *   a PDF in the reader      highlight the selection in a color, comment, copy as a quote
 *   the preview, the log     zoom, open in a tab, copy
 *   anywhere else            new document / note / citation, the command palette, theme
 *
 * Hold ⌥ Option while you right-click to get the system menu instead.
 *
 * In the Mac app, Cut, Copy, Paste and spelling go through the native shell (app/mac/main.swift,
 * the "reword" message handler), so Paste works exactly like ⌘V. In a browser the menu falls back
 * to the clipboard API.
 *
 *   App.menu.open(x, y, items)    show a menu; items are
 *       { label, run, icon, kbd, disabled, danger, checked, swatch, items: [submenu] } · '-' · { header }
 *   App.menu.close()
 */
(function () {
  'use strict';
  const { $, $$, el, toast } = App;

  /* ------------------------------------------------------------ icons (24×24, stroked like the ribbon's) */
  const T = (txt, size, fam, x, y) => '<text x="' + (x || 12) + '" y="' + (y || 18) + '" text-anchor="middle" font-size="' + (size || 17) +
    '" font-family="' + (fam || 'Georgia,serif') + '" stroke="none" fill="currentColor">' + txt + '</text>';
  const ICONS = {
    cut: '<circle cx="6" cy="7" r="2.6"/><circle cx="6" cy="17" r="2.6"/><path d="M8.3 8.4L20 18 M8.3 15.6L20 6"/>',
    copy: '<path d="M9 9h11v11H9z M5 15V4h11"/>',
    paste: '<path d="M9 3h6v3H9z M7 4.5H5V21h14V4.5h-2"/>',
    all: '<path d="M4 4h16v16H4z" stroke-dasharray="2.5 2.5"/>',
    italic: T('<tspan font-style="italic">I</tspan>', 18),
    bold: T('<tspan font-weight="700">B</tspan>', 17),
    smallcaps: T('S<tspan font-size="12">C</tspan>', 16),
    para: '<path d="M10 20V4h8 M14 4v16 M10 4a4 4 0 0 0 0 8"/>',
    cite: T('“”', 24, null, 12, 22),
    footnote: T('a', 16, null, 9, 18) + T('1', 10, 'sans-serif', 17, 11),
    open: '<path d="M14 4h6v6 M20 4l-9 9 M18 14v6H4V6h6"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16z M13 7l4 4"/>',
    trash: '<path d="M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13"/>',
    folder: '<path d="M3 7h6l2 2h10v10H3z"/>',
    plus: '<path d="M12 5v14 M5 12h14"/>',
    doc: '<path d="M6 3h9l4 4v14H6z M14 3v5h5"/>',
    note: '<path d="M5 4h14v16H5z M8 9h8 M8 13h8 M8 17h5"/>',
    book: '<path d="M4 5c3-1 6-1 8 1 2-2 5-2 8-1v14c-3-1-6-1-8 1-2-2-5-2-8-1z M12 6v14"/>',
    search: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    scale: '<path d="M12 4v16 M7 20h10 M5 7h14 M5 7l-3 6a3 3 0 0 0 6 0z M19 7l-3 6a3 3 0 0 0 6 0z"/>',
    up: '<path d="M12 19V5 M6 11l6-6 6 6"/>',
    down: '<path d="M12 5v14 M6 13l6 6 6-6"/>',
    zoomIn: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5 M8 10.5h5 M10.5 8v5"/>',
    zoomOut: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5 M8 10.5h5"/>',
    fit: '<path d="M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5"/>',
    run: '<path d="M7 5l12 7-12 7z"/>',
    link: '<path d="M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1 M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1"/>',
    marker: '<path d="M14 4l6 6-8 8H6v-6z M4 21h9"/>',
    comment: '<path d="M4 5h16v11H9l-5 4z"/>',
    quote: T('❝', 18, null, 12, 19),
    save: '<path d="M5 4h11l3 3v13H5z M8 4v5h7V4 M8 20v-6h8v6"/>',
    palette: '<path d="M4 6h16 M4 12h16 M4 18h10"/>',
    keys: '<path d="M3 7h18v11H3z M6 10h1 M9 10h1 M12 10h1 M15 10h1 M18 10h0 M7 14.5h10"/>',
    theme: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>',
    ribbon: '<path d="M3 5h18v5H3z M3 14h18 M3 18h12"/>',
    spell: T('abc', 11, 'sans-serif', 12, 12) + '<path d="M7 17l3 3 7-7"/>',
    tag: '<path d="M3 12V4h8l9 9-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    jump: '<path d="M5 12h12 M13 7l5 5-5 5"/>',
    markdown: '<path d="M3 6h18v12H3z M6 15V9l3 3 3-3v6 M15 9v6 M13 13l2 2 2-2"/>',
  };
  const svg = name => '<svg viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';

  /* ------------------------------------------------------------ the native shell (Mac app) */
  const bridge = () => (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.reword) || null;
  async function native(msg) {
    const b = bridge();
    if (!b) return null;
    try { return await b.postMessage(msg); } catch (e) { return null; }
  }

  /* ------------------------------------------------------------ drawing the menu */
  const open = [];       // the open menu levels: { box, items, rows, sel, anchor }
  let subTimer = null;
  let restoreFocus = null;

  function tidy(items) {
    const out = [];
    (items || []).forEach(it => {
      if (!it) return;
      if (it === '-') { if (out.length && out[out.length - 1] !== '-') out.push('-'); return; }
      if (it.items) { it = Object.assign({}, it, { items: tidy(it.items) }); if (!it.items.length) return; }
      out.push(it);
    });
    while (out.length && out[out.length - 1] === '-') out.pop();
    while (out.length && out[0] === '-') out.shift();
    return out;
  }

  const usable = it => it && it !== '-' && !it.header && !it.disabled;

  function host() {
    // a modal dialog sits in the top layer, above everything else: the menu has to live inside it
    const dlgs = $$('dialog[open]');
    return dlgs.length ? dlgs[dlgs.length - 1] : document.body;
  }

  function render(items, level) {
    const box = el('div', 'ctx-menu');
    box.setAttribute('role', 'menu');
    box.addEventListener('mousedown', e => e.preventDefault());       // keep focus and the text selection where they are
    box.addEventListener('contextmenu', e => { e.preventDefault(); e.stopPropagation(); });
    const rows = [];
    items.forEach((it, i) => {
      if (it === '-') { box.appendChild(el('div', 'ctx-sep')); rows.push(null); return; }
      if (it.header) { box.appendChild(el('div', 'ctx-head', it.header)); rows.push(null); return; }
      const row = el('div', 'ctx-item' + (it.danger ? ' danger' : '') + (it.disabled ? ' disabled' : ''));
      row.setAttribute('role', it.checked != null ? 'menuitemcheckbox' : 'menuitem');
      if (it.checked != null) row.setAttribute('aria-checked', it.checked ? 'true' : 'false');
      if (it.disabled) row.setAttribute('aria-disabled', 'true');
      if (it.items) row.setAttribute('aria-haspopup', 'menu');
      const ic = el('span', 'ctx-ic');
      if (it.swatch) ic.appendChild(el('span', 'ctx-swatch ' + it.swatch + (it.checked ? ' on' : '')));
      else if (it.checked) ic.innerHTML = svg('check');
      else if (it.icon) ic.innerHTML = svg(it.icon);
      const label = el('span', 'ctx-label', it.label);
      if (it.title) row.title = it.title;
      row.append(ic, label);
      if (it.items) row.appendChild(el('span', 'ctx-arrow', '›'));
      else if (it.kbd) row.appendChild(el('span', 'ctx-kbd', it.kbd));
      row.addEventListener('mouseenter', () => hover(level, i));
      row.addEventListener('click', e => { e.stopPropagation(); activate(level, i, true); });
      box.appendChild(row);
      rows.push(row);
    });
    return { box, items, rows, sel: -1 };
  }

  function place(m, x, y, anchor) {
    const pad = 6, W = window.innerWidth, H = window.innerHeight;
    const w = m.box.offsetWidth, h = m.box.offsetHeight;
    let left, top, origin = '';
    if (anchor) {                                    // a submenu: beside its row
      left = anchor.right - 3;
      if (left + w > W - pad) { left = anchor.left - w + 3; origin = 'right'; } else origin = 'left';
      top = anchor.top - 5;
      if (top + h > H - pad) top = H - pad - h;
      origin += ' top';
    } else {
      left = x; top = y;
      if (left + w > W - pad) { left = Math.max(pad, x - w); origin = 'right'; } else origin = 'left';
      if (top + h > H - pad) { top = y - h >= pad ? y - h : H - pad - h; origin += ' bottom'; } else origin += ' top';
    }
    m.box.style.left = Math.max(pad, left) + 'px';
    m.box.style.top = Math.max(pad, top) + 'px';
    m.box.style.maxHeight = (H - pad * 2) + 'px';
    m.box.style.transformOrigin = origin;
  }

  function show(items, x, y) {
    close();
    items = tidy(items);
    if (!items.length) return;
    restoreFocus = document.activeElement;
    const m = render(items, 0);
    host().appendChild(m.box);
    place(m, x, y);
    open.push(m);
    document.documentElement.classList.add('ctx-open');
  }

  function close() {
    clearTimeout(subTimer);
    while (open.length) open.pop().box.remove();
    document.documentElement.classList.remove('ctx-open');
  }
  function closeFrom(level) {
    clearTimeout(subTimer);
    while (open.length > level) open.pop().box.remove();
  }

  function select(level, i) {
    const m = open[level];
    if (!m) return;
    m.rows.forEach((r, k) => r && r.classList.toggle('sel', k === i));
    m.sel = i;
    const r = m.rows[i];
    if (r) r.scrollIntoView({ block: 'nearest' });
  }

  function openSub(level, i, focusFirst) {
    const m = open[level], it = m && m.items[i];
    if (!it || !it.items || it.disabled) return;
    if (open[level + 1] && open[level + 1].parentIndex === i) { if (focusFirst) select(level + 1, first(open[level + 1].items)); return; }
    closeFrom(level + 1);
    const sub = render(it.items, level + 1);
    sub.parentIndex = i;
    host().appendChild(sub.box);
    place(sub, 0, 0, m.rows[i].getBoundingClientRect());
    open.push(sub);
    if (focusFirst) select(level + 1, first(it.items));
  }

  // Submenus open and close after a short pause, so moving the pointer diagonally into one doesn't close it.
  function hover(level, i) {
    select(level, i);
    clearTimeout(subTimer);
    const it = open[level].items[i], sub = open[level + 1];
    if (sub && sub.parentIndex === i) { closeFrom(level + 2); return; }
    if (it.items && !it.disabled) subTimer = setTimeout(() => openSub(level, i, false), 140);
    else if (sub) subTimer = setTimeout(() => closeFrom(level + 1), 250);
  }

  function first(items) { return items.findIndex(usable); }
  function step(items, from, dir) {
    for (let k = 1; k <= items.length; k++) {
      const j = (from + dir * k + items.length * 2) % items.length;
      if (usable(items[j])) return j;
    }
    return from;
  }

  function activate(level, i, byMouse) {
    const m = open[level], it = m && m.items[i];
    if (!it || it.disabled || it.header || it === '-') return;
    if (it.items) { openSub(level, i, !byMouse); return; }
    close();
    // put focus back where it was (the menu never takes it, but a click inside a submenu can blur in some browsers)
    if (restoreFocus && restoreFocus !== document.activeElement && restoreFocus.isConnected && restoreFocus.focus) {
      try { restoreFocus.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    }
    try {
      const r = it.run && it.run();
      if (r && r.catch) r.catch(err => toast(err.message || String(err), true));
    } catch (err) { toast(err.message || String(err), true); }
  }

  // Keys while a menu is open: arrows, Enter, Escape, and a letter jumps to the item that starts with it.
  document.addEventListener('keydown', e => {
    if (!open.length) return;
    if (e.metaKey || e.ctrlKey) { close(); return; }                 // a shortcut: let it through
    const level = open.length - 1, m = open[level];
    const k = e.key;
    e.preventDefault(); e.stopPropagation();
    if (k === 'Escape' || k === 'Tab') close();
    else if (k === 'ArrowDown') select(level, step(m.items, m.sel < 0 ? -1 : m.sel, 1));
    else if (k === 'ArrowUp') select(level, step(m.items, m.sel < 0 ? m.items.length : m.sel, -1));
    else if (k === 'Home') select(level, first(m.items));
    else if (k === 'End') select(level, step(m.items, m.items.length, -1));
    else if (k === 'ArrowRight') { if (m.sel >= 0 && m.items[m.sel].items) openSub(level, m.sel, true); }
    else if (k === 'ArrowLeft') { if (level > 0) closeFrom(level); }
    else if (k === 'Enter' || k === ' ') { if (m.sel >= 0) activate(level, m.sel, false); }
    else if (k.length === 1 && /\S/.test(k)) {
      const ch = k.toLowerCase();
      const n = m.items.length;
      for (let d = 1; d <= n; d++) {
        const j = ((m.sel < 0 ? -1 : m.sel) + d) % n;
        const it = m.items[j];
        if (usable(it) && it.label.toLowerCase().replace(/^[“"(]/, '').startsWith(ch)) { select(level, j); break; }
      }
    }
  }, true);

  const inMenu = t => open.some(m => m.box.contains(t));
  document.addEventListener('mousedown', e => { if (open.length && !inMenu(e.target)) close(); }, true);
  document.addEventListener('wheel', e => { if (open.length && !inMenu(e.target)) close(); }, { capture: true, passive: true });
  document.addEventListener('scroll', e => { if (open.length && !inMenu(e.target)) close(); }, true);
  window.addEventListener('resize', close);
  window.addEventListener('blur', close);

  /* ------------------------------------------------------------ helpers the actions share */
  const isTextInput = t => t && ((t.tagName === 'INPUT' && /^(text|search|url|email|tel|password|number|)$/i.test(t.type)) || t.tagName === 'TEXTAREA');
  const editableOf = t => {
    if (!t || !t.closest) return null;
    if (isTextInput(t)) return t;
    const ce = t.closest('[contenteditable="true"], [contenteditable=""]');
    return ce && ce.isContentEditable ? ce : null;
  };
  const readOnly = t => !!(t && (t.readOnly || t.disabled));

  function selectionText(target) {
    if (isTextInput(target)) {
      try { return target.value.slice(target.selectionStart, target.selectionEnd); } catch (e) { return ''; }
    }
    const s = getSelection();
    return s && s.rangeCount ? s.toString() : '';
  }
  const short = (s, n) => { s = s.replace(/\s+/g, ' ').trim(); return s.length > (n || 28) ? s.slice(0, (n || 28) - 1).trim() + '…' : s; };

  async function copyText(text, html) {
    try {
      if (html && window.ClipboardItem) {
        await navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })]);
      } else await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // older engines: copy from a hidden box
      const box = document.createElement('textarea'); box.value = text;
      box.style.cssText = 'position:fixed;left:-9999px;top:0';
      document.body.appendChild(box); box.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { /* ignore */ }
      box.remove();
      if (!ok) toast('Couldn’t reach the clipboard.', true);
      return ok;
    }
  }

  // Cut, Copy, Paste, Select All. The Mac app does these natively, exactly as the Edit menu would.
  function edit(cmd, target) {
    if (target && target.focus && document.activeElement !== target && !(target.contains && target.contains(document.activeElement))) {
      try { target.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    }
    if (bridge()) {
      return native({ action: 'edit', command: cmd }).then(ok => { if (ok !== true) fallbackEdit(cmd, target); });
    }
    return fallbackEdit(cmd, target);
  }
  function fallbackEdit(cmd, target) {
    if (cmd === 'paste') return pasteFromClipboard(target);
    if (cmd === 'selectAll' && isTextInput(target)) { target.select(); return; }
    let ok = false;
    try { ok = document.execCommand(cmd); } catch (e) { /* ignore */ }
    if (!ok && (cmd === 'cut' || cmd === 'copy')) {
      const t = selectionText(target);
      if (t) copyText(t).then(() => { if (cmd === 'cut') document.execCommand('delete'); });
    }
  }
  async function pasteFromClipboard(target) {
    let html = '', text = '';
    try {
      if (navigator.clipboard.read) {
        for (const item of await navigator.clipboard.read()) {
          if (!html && item.types.includes('text/html')) html = await (await item.getType('text/html')).text();
          if (!text && item.types.includes('text/plain')) text = await (await item.getType('text/plain')).text();
        }
      } else text = await navigator.clipboard.readText();
    } catch (e) {
      try { text = await navigator.clipboard.readText(); }
      catch (e2) { toast('This browser doesn’t let menus read the clipboard. Press ⌘V to paste.', true); return; }
    }
    if (!html && !text) return;
    const into = editableOf(document.activeElement) || target;
    if (!into) return;
    // hand it to the app's own paste handling (rich.js cleans formatting); plain fields just take the text
    let handled = false;
    try {
      const dt = new DataTransfer();
      if (html) dt.setData('text/html', html);
      if (text) dt.setData('text/plain', text);
      handled = !into.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    } catch (e) { /* no synthetic clipboard events: insert the text below */ }
    if (!handled) document.execCommand('insertText', false, text || html.replace(/<[^>]+>/g, ''));
  }

  function editItems(target, opts) {
    opts = opts || {};
    const has = !!selectionText(target);
    const ro = opts.readOnly || readOnly(target);
    const editable = !!editableOf(target) && !ro;
    return [
      editable ? { label: 'Cut', icon: 'cut', kbd: '⌘X', disabled: !has, run: () => edit('cut', target) } : null,
      { label: 'Copy', icon: 'copy', kbd: '⌘C', disabled: !has, run: () => edit('copy', target) },
      editable ? { label: 'Paste', icon: 'paste', kbd: '⌘V', run: () => edit('paste', target) } : null,
      editable || opts.selectAll ? { label: 'Select All', icon: 'all', kbd: '⌘A', run: () => (opts.selectAll ? opts.selectAll() : edit('selectAll', target)) } : null,
    ];
  }

  // Look Up (macOS Dictionary) and web searches for the selected words.
  function lookItems(text) {
    const q = short(text, 200);
    if (!q || q.length < 2) return [];
    const w = short(text, 24);
    return [
      bridge() && q.split(' ').length <= 4 ? { label: 'Look Up “' + w + '”', icon: 'book', run: () => native({ action: 'lookUp', word: q }) } : null,
      { label: 'Search the Web for “' + w + '”', icon: 'search', run: () => window.open('https://www.google.com/search?q=' + encodeURIComponent(q), '_blank') },
      { label: 'Search Case Law for “' + w + '”', icon: 'scale', title: 'Google Scholar, case law',
        run: () => window.open('https://scholar.google.com/scholar?hl=en&as_sdt=2006&q=' + encodeURIComponent(q), '_blank') },
    ];
  }

  // A ribbon command, greyed out when its ribbon button is (wrong view, Details box open…).
  function cmd(label, name, opts) {
    opts = opts || {};
    const btns = $$('#ribbon [data-cmd="' + name + '"]');
    const off = btns.length && btns.every(b => b.disabled || b.hidden);
    return Object.assign({ label, disabled: !!off, run: () => App.ribbon.run(name) }, opts);
  }

  /* ------------------------------------------------------------ spelling (Mac app) */
  const WORD = /[\p{L}\p{M}'’]/u;
  function wordRange(node, offset) {
    if (!node || node.nodeType !== 3) return null;
    const s = node.nodeValue;
    let a = offset, b = offset;
    while (a > 0 && WORD.test(s[a - 1])) a--;
    while (b < s.length && WORD.test(s[b])) b++;
    while (a < b && /['’]/.test(s[a])) a++;
    while (b > a && /['’]/.test(s[b - 1])) b--;
    if (a === b) return null;
    const r = document.createRange(); r.setStart(node, a); r.setEnd(node, b);
    return r;
  }
  function wordAt(x, y) {
    const s = getSelection();
    if (s.rangeCount && !s.isCollapsed) {
      const t = s.toString().trim();
      if (!t || /\s/.test(t)) return null;                          // only a single word gets suggestions
      const r = s.getRangeAt(0);
      return wordRange(r.startContainer, r.startOffset);
    }
    const c = document.caretRangeFromPoint ? document.caretRangeFromPoint(x, y) : null;
    return c ? wordRange(c.startContainer, c.startOffset) : null;
  }
  async function spellingItems(root, x, y) {
    if (!bridge() || !root || root.spellcheck === false) return [];
    const range = wordAt(x, y);
    if (!range) return [];
    const word = range.toString();
    if (word.length < 2) return [];
    const r = await native({ action: 'spell', word });
    if (!r || !r.misspelled) return [];
    const replace = g => {
      root.focus();
      const s = getSelection(); s.removeAllRanges(); s.addRange(range);
      document.execCommand('insertText', false, g);
    };
    const guesses = (r.guesses || []).slice(0, 6);
    return [
      { header: guesses.length ? 'Spelling' : 'No spelling suggestions' },
      ...guesses.map(g => ({ label: g, run: () => replace(g) })),
      { label: 'Learn Spelling', icon: 'spell', run: () => native({ action: 'learn', word }) },
      '-',
    ];
  }

  /* ------------------------------------------------------------ the menus, by what was clicked */
  const isRichBlock = r => r && (r.id === 'doc' || r.id === 'note-body');

  function formatItems(root) {
    const sel = getSelection();
    const has = sel.rangeCount && !sel.isCollapsed;
    const items = [];
    if (has) {
      items.push({ label: 'Italic', icon: 'italic', kbd: '⌘I', run: () => App.ribbon.run('italic') },
        { label: 'Bold', icon: 'bold', kbd: '⌘B', run: () => App.ribbon.run('bold') },
        { label: 'Small Caps', icon: 'smallcaps', kbd: '⇧⌘K', run: () => App.ribbon.run('smallcaps') });
    }
    const blockSel = $('#tb-block');
    if (isRichBlock(root) && !blockSel.hidden && !blockSel.disabled) {
      const b = Rich.currentBlock(root);
      const cur = b ? b.tagName.toLowerCase() : 'p';
      const style = v => () => { blockSel.value = v; blockSel.dispatchEvent(new Event('change')); };
      const inList = b && b.tagName === 'LI' ? b.parentElement.tagName.toLowerCase() : '';
      const sub = [
        { label: 'Body Text', checked: cur === 'p', kbd: '⇧⌘N', run: style('p') },
        { label: 'Heading 1', checked: cur === 'h1', kbd: '⌥⌘1', run: style('h1') },
        { label: 'Heading 2', checked: cur === 'h2', kbd: '⌥⌘2', run: style('h2') },
        { label: 'Heading 3', checked: cur === 'h3', kbd: '⌥⌘3', run: style('h3') },
        { label: 'Heading 4', checked: cur === 'h4', kbd: '⌥⌘4', run: style('h4') },
        { label: 'Block Quote', checked: cur === 'blockquote', kbd: '⌥⌘Q', run: () => App.ribbon.run('quote') },
        '-',
        { label: 'Bulleted List', checked: inList === 'ul', kbd: '⇧⌘L', run: () => App.ribbon.run('ul') },
        { label: 'Numbered List', checked: inList === 'ol', kbd: '⇧⌘7', run: () => App.ribbon.run('ol') },
      ];
      if (root.id === 'doc' && App.views.writing.headingScheme() === 'article' && b && b.tagName === 'H1') {
        const on = (b.dataset.attrs || '').split(/\s+/).includes('.unnumbered');
        sub.push('-', { label: 'No Number on This Heading', checked: on, kbd: '⌥⌘U', run: () => App.ribbon.run('unnumbered') });
      }
      items.push({ label: 'Paragraph', icon: 'para', items: sub });
    } else if (isRichBlock(root)) {
      items.push({ label: 'Paragraph', icon: 'para', items: [
        { label: 'Bulleted List', kbd: '⇧⌘L', run: () => App.ribbon.run('ul') },
        { label: 'Numbered List', kbd: '⇧⌘7', run: () => App.ribbon.run('ol') },
        { label: 'Block Quote', kbd: '⌥⌘Q', run: () => App.ribbon.run('quote') },
      ] });
    }
    return items;
  }

  function insertItems(root) {
    const inDoc = root.id === 'doc', inNote = root.classList.contains('note-body') && root.closest('#notes');
    if (!(inDoc || inNote || root.id === 'note-body')) return [];
    const fnBtn = $('#tb-footnote');
    return [
      cmd('Insert Citation…', 'cite', { icon: 'cite', kbd: '⌃⌘C' }),
      inDoc && fnBtn && !fnBtn.hidden ? cmd('Insert Footnote', 'footnote', { icon: 'footnote', kbd: '⌥⌘F' }) : null,
    ];
  }

  // Remove a chip or footnote mark the way typing would, so ⌘Z brings it back.
  function deleteNode(node) {
    const root = node.closest('[contenteditable="true"]');
    if (!root) { node.remove(); return; }
    root.focus();
    const r = document.createRange(); r.selectNode(node);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    if (!document.execCommand('delete')) { node.remove(); root.dispatchEvent(new Event('input', { bubbles: true })); }
  }
  const clickEl = n => n && n.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

  function chipItems(chip) {
    const tag = chip.dataset.tag, c = App.citation(tag);
    const text = chip.textContent.replace(/​/g, '').trim();
    return [
      { header: c ? App.typeLabel(c.type) + ' · ' + tag : tag + ' (not in the library)' },
      { label: 'Edit Citation…', icon: 'edit', title: 'Pin cite, signal, parenthetical', run: () => clickEl(chip) },
      { label: 'Open in Citations', icon: 'open', disabled: !c, run: async () => { await App.showView('citations'); App.views.citations.open(tag); } },
      { label: 'Copy Citation', icon: 'copy', run: () => copyText(text, chip.innerHTML) },
      { label: 'Remove Citation', icon: 'trash', danger: true, run: () => deleteNode(chip) },
    ];
  }

  function footnoteMarkItems(ref) {
    return [
      { header: 'Footnote' },
      { label: 'Go to Footnote', icon: 'jump', run: () => clickEl(ref) },
      { label: 'Delete Footnote', icon: 'trash', danger: true, run: () => deleteNode(ref) },
    ];
  }
  function footnoteItems(note) {
    const ref = $('#doc .fnref[data-label="' + CSS.escape(note.dataset.label) + '"]');
    return [
      { label: 'Go to Footnote Mark', icon: 'jump', disabled: !ref, run: () => clickEl(note.querySelector('.note-num')) },
      ref ? { label: 'Delete Footnote', icon: 'trash', danger: true, run: () => deleteNode(ref) } : null,
    ];
  }

  function projectItems(current, move) {
    const list = App.projects.list || [];
    if (!list.length) return null;
    return { label: 'Move to Project', icon: 'folder', items: [
      { label: 'No Project', checked: !current, run: () => move('') },
      '-',
      ...list.map(p => ({ label: p.name, checked: current === p.id, run: () => move(p.id) })),
    ] };
  }

  function docItems(row) {
    const slug = row.dataset.slug, d = App.state.documents.find(x => x.slug === slug);
    if (!d) return [];
    const W = App.views.writing, isOpen = W.current() === slug;
    return [
      { header: d.title },
      { label: isOpen ? 'Open (already open)' : 'Open', icon: 'open', disabled: isOpen, run: () => W.open(slug) },
      { label: 'Rename…', icon: 'edit', run: () => W.rename(slug) },
      projectItems(d.project || '', pid => W.move(slug, pid)),
      isOpen ? cmd('Run (Build PDF and Word)', 'run', { icon: 'run', kbd: '⇧⌘R', run: () => $('#btn-run').click(), disabled: $('#btn-run').disabled }) : null,
      '-',
      { label: 'New Document…', icon: 'plus', kbd: '⌘N', run: () => App.cmd.global.newDoc() },
      '-',
      { label: 'Delete Document…', icon: 'trash', danger: true, run: () => W.remove(slug) },
    ];
  }

  function sectionItems(li) {
    const W = App.views.writing, file = li.dataset.file;
    const all = W.sections(), f = all.find(x => x.file === file);
    if (!f) return [];
    const secs = all.filter(x => x.kind === 'section'), i = secs.findIndex(x => x.file === file);
    const multi = W.multiSection() && f.kind === 'section';
    return [
      { header: f.title },
      { label: 'Open', icon: 'open', run: () => W.selectSection(file) },
      multi ? '-' : null,
      multi ? { label: 'Move Up', icon: 'up', disabled: i <= 0, run: () => W.moveSection(file, 'up') } : null,
      multi ? { label: 'Move Down', icon: 'down', disabled: i >= secs.length - 1, run: () => W.moveSection(file, 'down') } : null,
      W.multiSection() ? '-' : null,
      W.multiSection() ? { label: 'Add Section…', icon: 'plus', kbd: '⌃⌘S', run: () => W.addSection() } : null,
      multi ? '-' : null,
      multi ? { label: 'Remove Section…', icon: 'trash', danger: true, run: () => W.removeSection(file) } : null,
    ];
  }

  function noteRowItems(row) {
    const R = App.views.research, id = row.dataset.id, n = R.note(id);
    if (!n) return [];
    return [
      { header: n.title },
      { label: 'Open', icon: 'open', disabled: R.current() === id, run: () => R.open(id) },
      n.citation ? { label: 'Open Its Source', icon: 'cite', disabled: !App.citation(n.citation),
        run: async () => { await App.showView('citations'); App.views.citations.open(n.citation); } } : null,
      projectItems(n.project || '', pid => R.move(id, pid)),
      '-',
      { label: 'New Research Note…', icon: 'plus', kbd: '⌃⌘N', run: () => App.cmd.global.newNote() },
      '-',
      { label: 'Delete Note…', icon: 'trash', danger: true, run: () => R.remove(id) },
    ];
  }

  const FORMS = [
    ['bluebook_practitioner', 'Bluebook (Brief or Memo)'], ['bluebook_lawreview', 'Bluebook (Law Review)'],
    ['short_practitioner', 'Bluebook Short Form'], ['apa_reference', 'APA Reference'], ['apa_intext', 'APA In-Text'],
    ['chicago_note', 'Chicago Note'], ['chicago_bib', 'Chicago Bibliography'], ['chicago_ad_reference', 'Chicago Author-Date'],
  ];
  function citeCopyItems(c) {
    const f = c.forms || {};
    return [
      ...FORMS.filter(([k]) => f[k] && f[k].text).map(([k, label]) => ({ label, run: () => copyText(f[k].text, f[k].html) })),
      '-',
      { label: 'Tag (' + c.tag + ')', run: () => copyText(c.tag) },
    ];
  }
  function citeRowItems(row) {
    const tag = row.dataset.tag, c = App.citation(tag);
    if (!c) return [];
    return [
      { header: App.typeLabel(c.type) + ' · ' + tag },
      { label: 'Open', icon: 'open', run: () => App.views.citations.open(tag) },
      { label: 'Copy Citation', icon: 'copy', items: citeCopyItems(c) },
      { label: 'Start a Research Note', icon: 'note', run: () => App.views.citations.startNote(tag) },
      c.fields && c.fields.url ? { label: 'Open the Live Page', icon: 'link', run: () => window.open(c.fields.url, '_blank') } : null,
      '-',
      { label: 'New Citation…', icon: 'plus', kbd: '⌥⌘N', run: () => App.cmd.global.newCite() },
      '-',
      { label: 'Delete Citation…', icon: 'trash', danger: true, run: () => App.views.citations.remove(tag) },
    ];
  }

  function projectHeadItems(h) {
    const id = h.dataset.project || '';
    const folded = h.classList.contains('folded');
    return [
      { header: id ? App.projects.name(id) : 'No project' },
      { label: id ? 'Show Only This Project' : 'Show Only Items With No Project', icon: 'folder', run: () => App.projects.setScope(id || 'none') },
      { label: folded ? 'Expand' : 'Collapse', icon: folded ? 'down' : 'up', run: () => h.click() },
      '-',
      id ? { label: 'Edit Project…', icon: 'edit', run: () => App.projects.manage(id) } : null,
      { label: 'New Project…', icon: 'plus', kbd: '⌃⌥⌘J', run: () => App.projects.manage('+') },
    ];
  }

  /* the PDF reader in Citations */
  const COLORS = [['yellow', 'Yellow'], ['green', 'Green'], ['blue', 'Blue'], ['pink', 'Pink']];
  const colorItems = (r, a) => COLORS.map(([c, n]) => ({ label: n, swatch: c, checked: (a.color || 'yellow') === c, run: () => r.recolor(a, c) }));
  function readerItems(view, t) {
    const r = view.reader;
    const hl = t.closest('.hl');
    if (hl) {
      const a = r.annotation(hl.dataset.id);
      if (!a) return [];
      return [
        { header: 'Highlight · p. ' + a.page },
        { label: a.comment ? 'Edit Comment…' : 'Add a Comment…', icon: 'comment', run: () => clickEl(hl) },
        { label: 'Color', icon: 'marker', items: colorItems(r, a) },
        { label: 'Copy Quote', icon: 'quote', run: () => copyText('“' + a.text + '”') },
        '-',
        { label: 'Delete Highlight', icon: 'trash', danger: true, run: () => r.remove(a) },
      ];
    }
    const s = getSelection(), text = s.rangeCount && !s.isCollapsed && view.contains(s.anchorNode) ? s.toString() : '';
    if (r.bar) r.bar.hidden = true;
    if (text.trim()) {
      return [
        { header: 'Highlight' },
        ...COLORS.map(([c, n]) => ({ label: n, swatch: c, run: () => r.highlight(c) })),
        { label: 'Highlight and Comment…', icon: 'comment', run: () => { const a = r.highlight('yellow'); if (a) r.editAnn(a); } },
        '-',
        { label: 'Copy', icon: 'copy', kbd: '⌘C', run: () => copyText(text.replace(/\s+/g, ' ').trim()) },
        { label: 'Copy as Quote', icon: 'quote', run: () => copyText('“' + text.replace(/\s+/g, ' ').trim() + '”') },
        '-',
        ...lookItems(text),
      ];
    }
    return readerViewItems();
  }
  function readerViewItems() {
    return [
      cmd('Zoom In', 'readerIn', { icon: 'zoomIn', kbd: '⌥⌘+' }),
      cmd('Zoom Out', 'readerOut', { icon: 'zoomOut', kbd: '⌥⌘−' }),
      cmd('Fit Width', 'readerFit', { icon: 'fit' }),
      '-',
      cmd('Attach PDF…', 'attachFile', { icon: 'plus', kbd: '⌃⌘A' }),
      cmd('Snapshot the Web Page', 'snapshot', { icon: 'doc', kbd: '⌃⌘P' }),
      cmd('Export Annotated Copy…', 'exportAnnotated', { icon: 'save', kbd: '⌃⌘E', disabled: $('#src-export').disabled }),
    ];
  }
  function annItemItems(item) {
    const view = $('#src-view'), r = view && view.reader;
    const a = r && r.annotation(item.dataset.id);
    if (!a) return [];
    return [
      { header: 'Highlight · p. ' + a.page },
      { label: 'Show in the Document', icon: 'jump', run: () => r.reveal(a) },
      { label: a.comment ? 'Edit Comment…' : 'Add a Comment…', icon: 'comment', run: () => { r.reveal(a); setTimeout(() => r.editAnn(a), 80); } },
      { label: 'Color', icon: 'marker', items: colorItems(r, a) },
      { label: 'Copy Quote', icon: 'quote', run: () => copyText('“' + a.text + '”') },
      '-',
      { label: 'Delete Highlight', icon: 'trash', danger: true, run: () => r.remove(a) },
    ];
  }

  /* the Writing view's right pane */
  function selectAllIn(node) {
    const r = document.createRange(); r.selectNodeContents(node);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  }
  function previewItems() {
    return [
      { label: 'Zoom In', icon: 'zoomIn', kbd: '⌥⌘+', run: () => $('#pz-in').click() },
      { label: 'Zoom Out', icon: 'zoomOut', kbd: '⌥⌘−', run: () => $('#pz-out').click() },
      { label: 'Fit Width', icon: 'fit', run: () => $('#pz-val').click() },
      '-',
      { label: 'Open in Its Own Tab', icon: 'open', run: () => App.openPreviewInTab && App.openPreviewInTab() },
      { label: 'Run (Build Again)', icon: 'run', kbd: '⇧⌘R', disabled: $('#btn-run').disabled, run: () => $('#btn-run').click() },
    ];
  }

  function generalItems() {
    const theme = document.documentElement.dataset.theme;
    const collapsed = $('#ribbon').classList.contains('collapsed');
    const setTheme = id => () => { const b = $('[data-theme-btn="' + id + '"]'); if (b) b.click(); };
    return [
      { label: 'New Document…', icon: 'doc', kbd: '⌘N', run: () => App.cmd.global.newDoc() },
      { label: 'New Research Note…', icon: 'note', kbd: '⌃⌘N', run: () => App.cmd.global.newNote() },
      { label: 'New Citation…', icon: 'cite', kbd: '⌥⌘N', run: () => App.cmd.global.newCite() },
      '-',
      { label: 'Save Now', icon: 'save', kbd: '⌘S', run: () => App.saver.flush(true) },
      '-',
      { label: 'Command Palette…', icon: 'palette', kbd: '⌘K', run: () => App.togglePalette && App.togglePalette() },
      { label: 'Keyboard Shortcuts', icon: 'keys', kbd: '⌘/', run: () => App.toggleShortcuts && App.toggleShortcuts() },
      { label: 'Theme', icon: 'theme', items: [
        { label: 'Light', checked: theme === 'light', run: setTheme('light') },
        { label: 'Dark', checked: theme === 'dark', run: setTheme('dark') },
        { label: 'Dark, White Page', checked: theme === 'dark-paper', run: setTheme('dark-paper') },
      ] },
      { label: collapsed ? 'Show the Ribbon' : 'Hide the Ribbon', icon: 'ribbon', kbd: '⌥⌘R', run: () => $('#rb-collapse').click() },
    ];
  }

  // What to show for a right-click on `t` at (x, y).
  async function itemsFor(t, x, y) {
    // the PDF reader and its highlight list
    const view = t.closest('#src-view');
    if (view && view.reader) return readerItems(view, t);
    const ann = t.closest('#src-anns .ann-item');
    if (ann) return annItemItems(ann);
    if (t.closest('#cite-source') && !editableOf(t)) return readerViewItems();

    // live citations and footnote marks inside the text
    const root = editableOf(t);
    const chip = t.closest('span.cite');
    if (chip && root && root.dataset.rich) return [...chipItems(chip), '-', ...editItems(root)];
    const ref = t.closest('.fnref');
    if (ref && root && root.id === 'doc') return [...footnoteMarkItems(ref), '-', ...editItems(root)];

    // text you're editing
    if (root) {
      const sel = selectionText(root);
      if (root.dataset && root.dataset.rich) {                   // the rich editors: document, footnotes, notes, citation fields
        const note = root.closest('#notes .note');
        return [
          ...(await spellingItems(root, x, y)),
          ...editItems(root),
          '-',
          ...formatItems(root),
          '-',
          ...insertItems(root),
          ...(note ? ['-', ...footnoteItems(note)] : []),
          '-',
          ...(sel.trim() ? lookItems(sel) : []),
        ];
      }
      const md = root.id === 'doc-md' || root.id === 'note-md';
      return [
        ...editItems(root),
        md ? '-' : null,
        md ? { label: 'Edit as Rich Text', icon: 'markdown', kbd: '⌃⌘M', run: () => App.setEditMode('rich') } : null,
        root.type === 'search' && root.value ? '-' : null,
        root.type === 'search' && root.value ? { label: 'Clear Search', run: () => { root.value = ''; root.dispatchEvent(new Event('input', { bubbles: true })); } } : null,
        '-',
        ...(sel.trim() ? lookItems(sel) : []),
      ];
    }

    // lists in the side bars
    const docRow = t.closest('#tree .doc-row');
    if (docRow) return docItems(docRow);
    const sec = t.closest('#tree .sections li[data-file]');
    if (sec) return sectionItems(sec);
    if (t.closest('#tree .sections li.add')) return [{ label: 'Add Section…', icon: 'plus', kbd: '⌃⌘S', run: () => App.views.writing.addSection() }];
    const head = t.closest('.proj-head');
    if (head) return projectHeadItems(head);
    const noteRow = t.closest('#note-list .list-item[data-id]');
    if (noteRow) return noteRowItems(noteRow);
    const citeRow = t.closest('#cite-list .list-item[data-tag]');
    if (citeRow) return citeRowItems(citeRow);

    // links
    const a = t.closest('a[href]');
    if (a && !/^#|^javascript:/i.test(a.getAttribute('href') || '')) {
      return [
        { label: 'Open Link', icon: 'open', run: () => a.click() },
        { label: 'Copy Link Address', icon: 'link', run: () => copyText(a.href) },
      ];
    }

    // read-only text with a selection: copy it, look it up
    const sel = (getSelection().toString() || '');
    const selItems = sel.trim() ? [{ label: 'Copy', icon: 'copy', kbd: '⌘C', run: () => edit('copy') }, '-', ...lookItems(sel), '-'] : [];

    // the Writing view's right pane
    if (t.closest('#md-view')) {
      return [...selItems,
        { label: 'Copy All Markdown', icon: 'copy', run: () => copyText($('#md-view').innerText) },
        { label: 'Select All', icon: 'all', run: () => selectAllIn($('#md-view')) },
        { label: 'Edit as Markdown', icon: 'markdown', kbd: '⌃⌘M', run: () => App.setEditMode('md') }];
    }
    if (t.closest('#log-view')) {
      return [...selItems,
        { label: 'Copy the Whole Log', icon: 'copy', run: () => copyText($('#log-view').innerText) },
        { label: 'Run (Build Again)', icon: 'run', kbd: '⇧⌘R', disabled: $('#btn-run').disabled, run: () => $('#btn-run').click() }];
    }
    if (t.closest('#tab-pdf')) return [...selItems, ...previewItems()];

    return [...selItems, ...generalItems()];
  }

  document.addEventListener('contextmenu', e => {
    if (e.altKey) { close(); return; }                       // ⌥-right-click: the system menu
    const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
    if (!t || inMenu(t)) return;
    e.preventDefault();
    close();
    const x = e.clientX, y = e.clientY;
    Promise.resolve(itemsFor(t, x, y)).then(items => show(items, x, y)).catch(err => {
      console.error(err);
      show(generalItems(), x, y);
    });
  });

  App.menu = { open: show, close };
})();
