/* The 1.2 window: a floating glass sidebar (views, project, the current view's list), one toolbar,
 * an inspector on the right, and a small panel under Save that shows each step of a save.
 *   App.menu(name)          run a command from the Mac menu bar (main.swift calls it)
 *   App.saveProgress(on, step, result)   writing.js reports the save's steps here
 *   App.inspector.refresh() redraw the inspector
 */
(function () {
  'use strict';
  const { $, $$, el, toast } = App;
  const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } return null; };

  /* ------------------------------------------------------------ sidebar */
  // Each view's list moves into the one glass sidebar; CSS shows the one for the current view.
  const slot = $('#side-slot');
  [['writing', '#tree-pane'], ['research', '#view-research > .sidebar'], ['citations', '#view-citations > .sidebar'], ['verify', '#view-verify > .sidebar']].forEach(([v, sel]) => {
    const n = $(sel);
    if (n) { n.dataset.forView = v; slot.appendChild(n); }
  });
  // In a narrow window the sidebar floats over the page (style.css): it starts hidden there, closes when
  // you click the page, and showing or hiding it doesn't change what a wide window remembers.
  const narrow = matchMedia('(max-width: 900px)');
  function setSide(show) {
    document.body.classList.toggle('side-hidden', !show);
    if (!narrow.matches) store('sidebar', show ? '1' : '0');
  }
  const fitSide = () => setSide(!narrow.matches && store('sidebar') !== '0');
  $('#btn-hide-side').onclick = () => setSide(false);
  $('#btn-show-side').onclick = () => setSide(true);
  narrow.addEventListener('change', fitSide);
  $('#main-col').addEventListener('mousedown', e => {
    if (narrow.matches && !document.body.classList.contains('side-hidden') && !e.target.closest('#btn-show-side')) setSide(false);
  });
  $('#glass-side').addEventListener('click', e => {
    if (narrow.matches && e.target.closest('#nav button, .list-item, .sections li, .vf-row')) setSide(false);
  });
  fitSide();

  // the current view, for CSS (toolbar groups, sidebar list) and the title
  const show = App.showView;
  App.showView = async function (name) {
    await show.call(App, name);
    document.body.dataset.view = App.view;
    refreshTitle();
    App.inspector.refresh();
  };
  document.body.dataset.view = App.view || 'writing';

  function refreshTitle() {
    const w = App.views.writing, info = w && w.info && w.info();
    const t = App.view === 'writing' ? (info ? info.title : 'Writing') : App.view === 'research' ? 'Research' : App.view === 'verify' ? 'Verify' : 'Citations';
    $('#tb-doc-title').textContent = t;
    document.title = t === 'ReWord' ? 'ReWord' : t + ' · ReWord';
    // under the title: the document's versions in Writing; elsewhere what the view holds (24 notes, 8 of 263 checked)
    const v = App.views[App.view], sub = App.view !== 'writing' && v && v.subtitle ? v.subtitle() : '';
    if ($('#tb-sub').textContent !== sub) $('#tb-sub').textContent = sub;
  }

  /* ------------------------------------------------------------ inspector */
  const insp = $('#inspector');
  const I = App.inspector = {};
  function setInspector(on) {
    insp.hidden = !on;
    document.body.classList.toggle('insp-open', on);
    $('#btn-inspector').classList.toggle('active', on);
    store('inspector', on ? '1' : '0');
    if (on) I.refresh();
  }
  $('#btn-inspector').onclick = () => setInspector(insp.hidden);
  $$('[data-insp]').forEach(b => b.onclick = () => showPanel(b.dataset.insp));
  function showPanel(name) {
    $$('[data-insp]').forEach(b => b.classList.toggle('active', b.dataset.insp === name));
    $$('[data-insp-panel]').forEach(p => { p.hidden = p.dataset.inspPanel !== name; });
    store('inspPanel', name);
    if (name === 'files' && App.git) App.git.refresh();
  }
  // Final draft and Details live in the inspector now (the buttons keep their wiring when they move)
  const docButtons = $('#insp-doc-buttons');
  const fin = $('#btn-final');
  if (fin) { fin.classList.remove('writing-only'); docButtons.appendChild(fin); }
  const details = el('button', 'rb-btn sm', 'Details…');
  details.type = 'button'; details.title = 'Edit the title page details (metadata) of this document';
  details.onclick = () => { const d = $('#tree .sections li[data-file="metadata.yaml"], #tree li.meta'); if (d) d.click(); else toast('Open the document’s Details in the sidebar.', true); };
  docButtons.appendChild(details);

  I.refresh = function () {
    refreshTitle();
    if (insp.hidden) return;
    const w = App.views.writing, info = w && w.info && w.info();
    const tpl = info && (App.state.templates || []).find(t => t.id === info.template);
    $('#insp-title').textContent = info ? info.title : 'None open';
    $('#insp-template').textContent = tpl ? tpl.name : '';
    $('#insp-project').textContent = info && info.project ? App.projects.name(info.project) : 'None';
    $('#insp-version').textContent = $('#version-info').textContent;
    const ws = w && w.words && w.words(), n = x => x.toLocaleString();
    $('#insp-words').textContent = !ws ? '' : n(ws.body) + (ws.notes ? ' + ' + n(ws.notes) + ' in footnotes' : '') +
      (ws.limit ? ' (limit ' + n(ws.limit) + ')' : '');
    $('#insp-words').classList.toggle('over', !!(ws && ws.limit && ws.body + ws.notes > ws.limit));
    $('#insp-words').title = 'Counted as you type. Save gives the exact count from the finished document, which also counts a reference list built from your citations.';
    // rebuild the download buttons only when they change (rebuilding mid-click would swallow the click)
    const links = $$('#pdf-bar a');
    const sig = links.map(a => a.href + '|' + a.textContent).join('\n');
    if (sig === outSig) return;
    outSig = sig;
    const out = $('#insp-outputs');
    out.innerHTML = '';
    if (!links.length) out.appendChild(el('span', 'muted small', 'Press Save to build.'));
    links.forEach(a => {
      const b = el('a', 'rb-btn sm', a.textContent.replace(/^⬇\s*/, ''));
      b.href = a.href; out.appendChild(b);
    });
  };
  let outSig = null;
  // keep it current without wiring into every view: small, and only while open
  setInterval(() => { if (!document.hidden) I.refresh(); }, 1500);
  showPanel(store('inspPanel') || 'doc');
  setInspector(store('inspector') === '1');

  /* ------------------------------------------------------------ the Save panel */
  // Save does four things; this panel shows them as they happen, then fades.
  const STEPS = [
    ['save', 'Saved', /snapshot|saving/i],
    ['build', 'Built', /build|redline|pdf|word|typeset/i],
    ['copy', 'Copied to outputs', /output/i],
    ['sync', 'Synced with GitHub', /sync|github|push/i],
  ];
  const panel = $('#save-panel');
  let reached = -1, hideT = null;
  function paint(cur, result) {
    panel.innerHTML = '';
    STEPS.forEach(([id, label], i) => {
      let done = result ? (result.ok ? true : i < cur) : i < cur;
      const now = !result && i === cur;
      let skipped = false;
      if (result && result.ok && id === 'sync') {          // say what really happened with GitHub
        const sy = result.sync;
        if (!sy) { done = false; skipped = true; label = 'Not connected to GitHub'; }
        else if (!sy.ok) { done = false; skipped = true; label = /offline|reach/i.test(sy.message) ? 'Not synced (offline)' : 'Not synced'; }
      }
      const row = el('div', 'sp-step' + (done ? ' done' : '') + (now ? ' now' : '') + (skipped ? ' skipped' : ''));
      row.appendChild(el('span', 'sp-mark', done ? '✓' : skipped ? '–' : ''));
      row.appendChild(el('span', '', now ? label.replace(/^Saved$/, 'Saving').replace(/^Built$/, 'Building').replace(/^Copied/, 'Copying').replace(/^Synced/, 'Syncing') + '…' : label));
      panel.appendChild(row);
    });
    if (result && !result.ok) {
      const err = el('div', 'sp-err', 'Build failed: ' + (result.message || 'see the log'));
      const log = el('button', 'btn small', 'Show log'); log.type = 'button';
      log.onclick = () => App.views.writing.showLog();
      panel.append(err, log);
    }
  }
  function place() {
    // under Save in Writing; a build still running after you move to another view reports beside its Save instead
    const b = $('#btn-save'), side = $('#btn-save-side');
    const r = b.getBoundingClientRect();
    if (r.width) { panel.style.left = Math.max(8, r.left) + 'px'; panel.style.top = (r.bottom + 8) + 'px'; panel.style.bottom = ''; return; }
    const s = side.getBoundingClientRect();
    panel.style.left = Math.max(8, s.left) + 'px'; panel.style.top = ''; panel.style.bottom = Math.max(8, window.innerHeight - s.top + 8) + 'px';
  }
  App.saveProgress = function (on, step, result) {
    clearTimeout(hideT);
    place();
    if (on) {
      const i = STEPS.findIndex(s => s[2].test(step || ''));
      if (i > reached) reached = i;
      if (reached < 0) reached = 0;
      panel.hidden = false;
      paint(reached);
      return;
    }
    if (result) {
      paint(STEPS.length, result);
      hideT = setTimeout(() => { panel.hidden = true; }, result.ok ? 2500 : 12000);
    }
    reached = -1;
    I.refresh();
  };
  panel.addEventListener('click', e => { if (e.target === panel) panel.hidden = true; });

  /* ------------------------------------------------------------ the Mac menu bar */
  // Insert and View moved from the ribbon to the menu bar. main.swift calls App.menu('<name>').
  const MENU = {
    'layout:editor': () => clickSel('[data-layout="editor"]'),
    'layout:split': () => clickSel('[data-layout="split"]'),
    'layout:preview': () => clickSel('[data-layout="preview"]'),
    'edit:rich': () => App.setEditMode('rich'),
    'edit:md': () => App.setEditMode('md'),
    'theme:light': () => clickSel('[data-theme-btn="light"]'),
    'theme:dark': () => clickSel('[data-theme-btn="dark"]'),
    'theme:dark-paper': () => clickSel('[data-theme-btn="dark-paper"]'),
    'sidebar': () => setSide(document.body.classList.contains('side-hidden')),
    'inspector': () => setInspector(insp.hidden),
    'textBigger': () => clickSel('#size-up'),
    'textSmaller': () => clickSel('#size-down'),
    'textReset': () => clickSel('#size-reset'),
    'save': () => App.saveAll(),
    'view:writing': () => App.showView('writing'),
    'view:research': () => App.showView('research'),
    'view:citations': () => App.showView('citations'),
    'view:verify': () => App.showView('verify'),
  };
  function clickSel(sel) { const b = $(sel); if (b) b.click(); }
  const rightClick = App.menu;         // contextmenu.js: App.menu.open(x, y, items) / App.menu.close()
  App.menu = function (name) {
    if (MENU[name]) { MENU[name](); return true; }
    if (name.startsWith('suite:') && App.suite) { App.suite.menu(name.slice(6)); return true; }   // suite.js
    App.ribbon.run(name);              // any ribbon command: footnote, cite, bibAdd, addSection, newDoc, openData, …
    return true;
  };
  if (rightClick) Object.assign(App.menu, rightClick);
  // Tell the menu bar which items are checked (layout, edit mode, theme)
  App.menuState = () => ({
    layout: ($('[data-layout].active') || {}).dataset ? $('[data-layout].active').dataset.layout : 'split',
    edit: App.editMode, theme: document.documentElement.dataset.theme,
    sidebar: !document.body.classList.contains('side-hidden'), inspector: !insp.hidden,
  });
})();
