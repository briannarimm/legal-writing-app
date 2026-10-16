/* Keyboard shortcuts (Mac). One table drives three things: the key handler, the small key hint
 * printed on each ribbon button, and the ⌘/ cheat sheet. Add a row here and all three follow.
 *   mods:  m = ⌘ Command, s = ⇧ Shift, a = ⌥ Option, c = ⌃ Control
 *   code:  the physical key (KeyB, Digit7, Enter ...), so Option combos still match
 *   cmd:   a ribbon command (App.cmd...)   click: a button to press   fn: a function
 *   views: only active in these views (default: everywhere)
 *   on:    selector(s) of the buttons that get the hint
 * Where Word for Mac has a shortcut for the same thing, it is used here (⌘B, ⌘I, ⇧⌘K small caps,
 * ⇧⌘L bullets, ⌥⌘1–3 headings, ⇧⌘N Normal, ⌥⌘F footnote, ⇧⌘. ⇧⌘, text size, ⌘Y redo).
 * Save (⌘S) is handled in app.js; it is listed here for the hint and the sheet.
 */
(function () {
  'use strict';
  const { $, $$, el, toast } = App;

  const blockStyle = v => () => {
    const s = $('#tb-block');
    if (s.disabled) return;
    s.value = v; s.dispatchEvent(new Event('change'));
  };
  const goView = v => () => App.showView(v);

  const S = [
    // Document
    { g: 'Document', d: 'Save, build, publish and sync', mods: 'm', code: 'KeyS', key: 'S', on: '#btn-save', builtin: true },
    { g: 'Document', d: 'Final draft on or off', mods: 'am', code: 'KeyD', key: 'D', click: '#btn-final', on: '#btn-final', views: 'writing' },
    { g: 'Document', d: 'Tag version', mods: 'sm', code: 'KeyT', key: 'T', click: '#btn-tag', on: '#btn-tag', views: 'writing' },
    { g: 'Document', d: 'Manage projects', mods: 'cm', code: 'KeyJ', key: 'J', cmd: 'manageProjects', on: '[data-cmd="manageProjects"]' },
    { g: 'Document', d: 'New project', mods: 'acm', code: 'KeyJ', key: 'J', cmd: 'newProject', on: '[data-cmd="newProject"]' },
    { g: 'Document', d: 'Show data folder', mods: 'sm', code: 'KeyO', key: 'O', cmd: 'openData', on: '[data-cmd="openData"]' },
    // Text
    { g: 'Text', d: 'Italic', mods: 'm', code: 'KeyI', key: 'I', cmd: 'italic', on: '[data-cmd="italic"]' },
    { g: 'Text', d: 'Bold', mods: 'm', code: 'KeyB', key: 'B', cmd: 'bold', on: '[data-cmd="bold"]' },
    { g: 'Text', d: 'Small caps', mods: 'sm', code: 'KeyK', key: 'K', cmd: 'smallcaps', on: '[data-cmd="smallcaps"]' },
    { g: 'Text', d: 'Numbered list', mods: 'sm', code: 'Digit7', key: '7', cmd: 'ol', on: '[data-cmd="ol"]' },
    { g: 'Text', d: 'Bulleted list', mods: 'sm', code: 'KeyL', key: 'L', cmd: 'ul', on: '[data-cmd="ul"]' },
    { g: 'Text', d: 'Block quote', mods: 'am', code: 'KeyQ', key: 'Q', cmd: 'quote', on: '[data-cmd="quote"]' },
    { g: 'Text', d: 'Body text (Normal style)', mods: 'sm', code: 'KeyN', key: 'N', fn: blockStyle('p'), opt: 'p' },
    { g: 'Text', d: 'Heading 1', mods: 'am', code: 'Digit1', key: '1', fn: blockStyle('h1'), opt: 'h1' },
    { g: 'Text', d: 'Heading 2', mods: 'am', code: 'Digit2', key: '2', fn: blockStyle('h2'), opt: 'h2' },
    { g: 'Text', d: 'Heading 3', mods: 'am', code: 'Digit3', key: '3', fn: blockStyle('h3'), opt: 'h3' },
    { g: 'Text', d: 'Heading 4', mods: 'am', code: 'Digit4', key: '4', fn: blockStyle('h4'), opt: 'h4' },
    { g: 'Text', d: 'Larger editor text', mods: 'sm', code: 'Period', key: '.', click: '#size-up', on: '#size-up' },
    { g: 'Text', d: 'Smaller editor text', mods: 'sm', code: 'Comma', key: ',', click: '#size-down', on: '#size-down' },
    { g: 'Text', d: 'Redo', mods: 'm', code: 'KeyY', key: 'Y', fn: () => document.execCommand('redo') },
    { g: 'Text', d: 'Toggle “no number” on a heading', mods: 'am', code: 'KeyU', key: 'U', cmd: 'unnumbered', on: '[data-cmd="unnumbered"]', views: 'writing' },
    // Insert
    { g: 'Insert', d: 'Citation from your library', mods: 'cm', code: 'KeyC', key: 'C', cmd: 'cite', on: '[data-cmd="cite"]' },
    { g: 'Insert', d: 'Sources (annotated bibliography)', mods: 'am', code: 'KeyB', key: 'B', cmd: 'bibAdd', on: '[data-cmd="bibAdd"]', views: 'writing' },
    { g: 'Insert', d: 'Footnote', mods: 'am', code: 'KeyF', key: 'F', cmd: 'footnote', on: '[data-cmd="footnote"]', views: 'writing' },
    { g: 'Insert', d: 'New section', mods: 'cm', code: 'KeyS', key: 'S', cmd: 'addSection', on: '[data-cmd="addSection"]', views: 'writing' },
    { g: 'Insert', d: 'New document', mods: 'm', code: 'KeyN', key: 'N', cmd: 'newDoc', on: '[data-cmd="newDoc"]' },
    { g: 'Insert', d: 'New research note', mods: 'cm', code: 'KeyN', key: 'N', cmd: 'newNote', on: '[data-cmd="newNote"]' },
    { g: 'Insert', d: 'New citation', mods: 'am', code: 'KeyN', key: 'N', cmd: 'newCite', on: '[data-cmd="newCite"]' },
    { g: 'Insert', d: 'Copy email', mods: 'sm', code: 'KeyE', key: 'E', click: '#em-copy', on: '#em-copy', views: 'writing' },
    // Research and the citation library (their own ribbon tabs)
    { g: 'Research', d: 'Export the note as PDF', mods: 'cm', code: 'KeyE', key: 'E', cmd: 'exportPdf', on: '[data-cmd="exportPdf"]', views: 'research' },
    { g: 'Research', d: 'Export the note as Word', mods: 'cm', code: 'KeyW', key: 'W', cmd: 'exportDocx', on: '[data-cmd="exportDocx"]', views: 'research' },
    { g: 'Library', d: 'Look up a DOI, ISBN or web address', mods: 'cm', code: 'KeyU', key: 'U', cmd: 'lookup', on: '[data-cmd="lookup"]', views: 'citations' },
    { g: 'Library', d: 'Attach a PDF', mods: 'cm', code: 'KeyA', key: 'A', cmd: 'attachFile', on: '[data-cmd="attachFile"]', views: 'citations' },
    { g: 'Library', d: 'Snapshot the web page', mods: 'cm', code: 'KeyP', key: 'P', cmd: 'snapshot', on: '[data-cmd="snapshot"]', views: 'citations' },
    { g: 'Library', d: 'Open the live page', mods: 'cm', code: 'KeyL', key: 'L', cmd: 'livePage', on: '[data-cmd="livePage"]', views: 'citations' },
    { g: 'Library', d: 'Highlight the selected text', mods: 'cm', code: 'KeyH', key: 'H', cmd: 'highlight', on: '[data-cmd="highlight"]', views: 'citations' },
    { g: 'Library', d: 'Export an annotated copy', mods: 'cm', code: 'KeyE', key: 'E', cmd: 'exportAnnotated', on: '[data-cmd="exportAnnotated"]', views: 'citations' },
    { g: 'Library', d: 'Reader: bigger', mods: 'am', code: 'Equal', key: '+', cmd: 'readerIn', views: 'citations' },
    { g: 'Library', d: 'Reader: smaller', mods: 'am', code: 'Minus', key: '−', cmd: 'readerOut', views: 'citations' },
    // Go to
    { g: 'Go to', d: 'Writing', mods: 'm', code: 'Digit1', key: '1', fn: goView('writing'), on: '#nav [data-view="writing"]' },
    { g: 'Go to', d: 'Research', mods: 'm', code: 'Digit2', key: '2', fn: goView('research'), on: '#nav [data-view="research"]' },
    { g: 'Go to', d: 'Citations', mods: 'm', code: 'Digit3', key: '3', fn: goView('citations'), on: '#nav [data-view="citations"]' },
    { g: 'Go to', d: 'Show or hide the sidebar', mods: 'am', code: 'KeyS', key: 'S', fn: () => App.menu('sidebar') },
    { g: 'Go to', d: 'Show or hide the inspector', mods: 'am', code: 'KeyI', key: 'I', fn: () => App.menu('inspector') },
    { g: 'Go to', d: 'Editor only', mods: 'cm', code: 'Digit1', key: '1', click: '[data-layout="editor"]', on: '[data-layout="editor"]', views: 'writing research' },
    { g: 'Go to', d: 'Editor and preview', mods: 'cm', code: 'Digit2', key: '2', click: '[data-layout="split"]', on: '[data-layout="split"]', views: 'writing research' },
    { g: 'Go to', d: 'Preview only', mods: 'cm', code: 'Digit3', key: '3', click: '[data-layout="preview"]', on: '[data-layout="preview"]', views: 'writing research' },
    { g: 'Go to', d: 'Edit as rich text or Markdown', mods: 'cm', code: 'KeyM', key: 'M', fn: () => App.setEditMode(App.editMode === 'md' ? 'rich' : 'md'), on: '[data-editmode="md"]', views: 'writing research' },
    { g: 'Go to', d: 'Zoom the preview in', mods: 'am', code: 'Equal', key: '+', click: '#pz-in', views: 'writing' },
    { g: 'Go to', d: 'Zoom the preview out', mods: 'am', code: 'Minus', key: '−', click: '#pz-out', views: 'writing' },
    { g: 'Go to', d: 'Collapse or expand the ribbon', mods: 'am', code: 'KeyR', key: 'R', click: '#rb-collapse' },
    { g: 'Go to', d: 'Command palette (search every action)', mods: 'm', code: 'KeyK', key: 'K', fn: () => togglePalette() },
    { g: 'Go to', d: 'This list of shortcuts', mods: 'm', code: 'Slash', key: '/', fn: () => toggleSheet() },
  ];

  const GLYPH = { c: '⌃', a: '⌥', s: '⇧', m: '⌘' };
  const glyphs = k => ['c', 'a', 's', 'm'].filter(m => k.mods.includes(m)).map(m => GLYPH[m]).join('') + k.key;

  /* ------------------------------------------------------------ hints on the buttons */
  S.forEach(k => {
    if (k.on) $$(k.on).forEach(b => {
      b.insertAdjacentHTML('beforeend', '<span class="kbd">' + glyphs(k) + '</span>');
      b.title = (b.title || k.d).replace(/\s*\([^()]*[⌘⌥⌃⇧][^()]*\)\s*$/, '') + ' (' + glyphs(k) + ')';
    });
    if (k.opt) {
      const o = $('#tb-block option[value="' + k.opt + '"]');
      if (o) o.textContent += '   ' + glyphs(k);
    }
  });
  $('#tb-block').title = 'Paragraph style. Heading 1–4 are ⌥⌘1–4 and Normal is ⇧⌘N, as in Word.';

  /* ------------------------------------------------------------ the key handler */
  const wanted = e => (e.metaKey ? 'm' : '') + (e.shiftKey ? 's' : '') + (e.altKey ? 'a' : '') + (e.ctrlKey ? 'c' : '');
  const sorted = s => s.split('').sort().join('');

  document.addEventListener('keydown', e => {
    if (e.isComposing || !(e.metaKey || e.ctrlKey)) return;
    const have = sorted(wanted(e));
    const inView = x => !x.views || x.views.split(' ').includes(App.view);
    const k = S.find(x => x.code === e.code && sorted(x.mods) === have && inView(x)) ||
              S.find(x => x.code === e.code && sorted(x.mods) === have);
    if (!k || (k.builtin && k.code === 'KeyS')) return;
    if (k.views && !k.views.split(' ').includes(App.view)) return;
    if (document.querySelector('dialog[open]') && k.code !== 'Slash') return;
    if (!pal.hidden && k.code !== 'KeyK') return;      // dialogs keep their keys
    if (k.cmd === 'italic' || k.cmd === 'bold' || k.cmd === 'smallcaps') {
      if (!Rich.activeEditable()) return;                                       // plain fields: leave the key alone
    }
    e.preventDefault();
    exec(k);
  });

  function exec(k) {
    if (k.builtin) { App.saveAll(); return; }
    if (k.fn) { k.fn(); return; }
    if (k.click) { const b = $(k.click); if (b && !b.disabled) b.click(); return; }
    const b = $('#ribbon [data-cmd="' + k.cmd + '"]');
    if (b && b.disabled) return;
    if (b) b.click(); else if (App.cmd.global[k.cmd]) App.cmd.global[k.cmd]();
  }
  // Is this action usable right now (right view, button not greyed out)?
  function available(k) {
    if (k.views && !k.views.split(' ').includes(App.view)) return false;
    const sel = k.click ? $(k.click) : k.cmd ? $('#ribbon [data-cmd="' + k.cmd + '"]') : null;
    if (sel && sel.disabled) return false;
    if (k.opt && $('#tb-block').disabled) return false;
    return true;
  }

  /* ------------------------------------------------------------ cheat sheet */
  const dlg = el('dialog'); dlg.id = 'dlg-keys';
  dlg.append(el('h2', '', 'Keyboard shortcuts'));
  const grid = el('div', 'keys-grid');
  ['Document', 'Text', 'Insert', 'Research', 'Library', 'Go to'].forEach(g => {
    const col = el('div', 'keys-col'); col.append(el('h3', '', g));
    S.filter(k => k.g === g).forEach(k => {
      const row = el('div', 'keys-row'); row.append(el('span', '', k.d), el('span', 'kbd big', glyphs(k)));
      col.appendChild(row);
    });
    grid.appendChild(col);
  });
  const foot = el('div', 'dlg-actions'); const close = el('button', 'btn', 'Close'); close.dataset.close = '';
  close.onclick = () => dlg.close(); foot.appendChild(close);
  dlg.append(grid, el('div', 'hint', 'Also built in: ⌘Z undo, ⇧⌘Z redo, ⌘C/⌘X/⌘V, ⌘A select all, ⌘+ ⌘− ⌘0 zoom the window, ⌘Q quit. ' +
    'Right-click anything for the commands that fit it; hold ⌥ Option while you right-click for the system menu.'), foot);
  document.body.appendChild(dlg);
  dlg.addEventListener('mousedown', e => { if (e.target === dlg) dlg.close(); });
  function toggleSheet() { if (dlg.open) dlg.close(); else dlg.showModal(); }
  const keysBtn = $('#rb-keys');
  keysBtn.title = 'Keyboard shortcuts (⌘/)';
  keysBtn.onclick = toggleSheet;
  document.addEventListener('keydown', e => { if (dlg.open && e.key === 'Escape') dlg.close(); });
  /* ------------------------------------------------------------ command palette (⌘K) */
  const pal = el('div'); pal.id = 'palette'; pal.hidden = true;
  const box = el('div', 'pal-box');
  const input = el('input'); input.placeholder = 'Type a command, document, note or citation…'; input.spellcheck = false;
  const listEl = el('div', 'pal-list');
  box.append(input, listEl); pal.appendChild(box); document.body.appendChild(pal);
  let items = [], shown = [], sel = 0, saved = null;

  const plain = md => (md || '').replace(/\\(.)/g, '$1').replace(/\]\{[^}]*\}|[*_\[\]]/g, '');

  async function gather() {
    const out = [];
    S.forEach(k => { if (available(k)) out.push({ label: k.d, group: k.g, hint: glyphs(k), run: () => exec(k) }); });
    [['light', 'Light'], ['dark', 'Dark'], ['dark-paper', 'Dark with white page']].forEach(([id, n]) =>
      out.push({ label: 'Theme: ' + n, group: 'View', run: () => { const b = $('[data-theme-btn="' + id + '"]'); if (b) b.click(); } }));
    [['sidebar', 'Show or hide the sidebar'], ['inspector', 'Show or hide the inspector'], ['openData', 'Show data folder in Finder'],
      ['webWork', 'Open repository on GitHub'], ['openBackup', 'Show backups in Finder']].forEach(([id, n]) =>
      out.push({ label: n, group: 'View', run: () => App.menu(id) }));
    out.push({ label: 'Show all projects', group: 'Projects', run: () => App.projects.setScope('all') });
    (App.projects.list || []).forEach(p => out.push({ label: 'Project: ' + p.name, group: 'Projects', run: () => App.projects.setScope(p.id) }));
    out.push({ label: 'Show items with no project', group: 'Projects', run: () => App.projects.setScope('none') });
    (App.state.documents || []).forEach(d => out.push({ label: 'Open document: ' + d.title, group: 'Documents',
      run: async () => { await App.showView('writing'); App.views.writing.open(d.slug); } }));
    (App.state.citations || []).forEach(c => out.push({ label: 'Citation: ' + plain(c.cite).slice(0, 90), group: 'Citations', hint: c.tag,
      run: async () => { await App.showView('citations'); App.views.citations.open(c.tag); } }));
    try {
      const r = await App.api('/api/notes');
      (r.notes || []).forEach(n => out.push({ label: 'Note: ' + n.title, group: 'Research', run: () => App.views.research.open(n.id) }));
    } catch (e) { /* the palette still works without notes */ }
    return out;
  }

  function render() {
    const q = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const score = it => {
      const l = it.label.toLowerCase(), h = (it.group + ' ' + l + ' ' + (it.hint || '')).toLowerCase();
      if (!q.every(w => h.includes(w))) return -1;
      return (l.startsWith(q[0] || '') ? 2 : 0) + (l.includes(q.join(' ')) ? 1 : 0);
    };
    shown = items.map(it => [score(it), it]).filter(x => x[0] >= 0).sort((a, b) => b[0] - a[0]).map(x => x[1]).slice(0, 40);
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    listEl.innerHTML = '';
    if (!shown.length) listEl.appendChild(el('div', 'pal-empty', 'Nothing matches.'));
    shown.forEach((it, i) => {
      const row = el('div', 'pal-row' + (i === sel ? ' sel' : ''));
      row.append(el('span', 'pal-group', it.group), el('span', 'pal-label', it.label), el('span', 'kbd', it.hint || ''));
      row.onmousedown = e => { e.preventDefault(); choose(i); };
      listEl.appendChild(row);
    });
    const cur = listEl.querySelector('.sel'); if (cur) cur.scrollIntoView({ block: 'nearest' });
  }

  function closePalette(restore) {
    pal.hidden = true;
    if (restore && saved) Rich.restoreSelection(saved);
    saved = null;
  }
  function choose(i) {
    const it = shown[i]; if (!it) return;
    closePalette(true);
    it.run();
  }
  async function togglePalette() {
    if (!pal.hidden) { closePalette(true); return; }
    if (document.querySelector('dialog[open]')) return;
    saved = Rich.saveSelection();          // so Italic, Footnote… still land where your cursor was
    pal.hidden = false; input.value = ''; sel = 0; items = []; render();
    input.focus();
    items = await gather(); render();
  }
  input.addEventListener('input', () => { sel = 0; render(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); render(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); render(); }
    else if (e.key === 'Enter') { e.preventDefault(); choose(sel); }
    else if (e.key === 'Escape') { e.preventDefault(); closePalette(true); }
  });
  pal.addEventListener('mousedown', e => { if (e.target === pal) closePalette(true); });
  App.togglePalette = togglePalette;
  App.toggleShortcuts = toggleSheet;
})();
