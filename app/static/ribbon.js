/* The ribbon, the theme switch, and the view settings (layout, preview zoom, text size).
 * Ribbon buttons carry data-cmd="name". Formatting commands (italic, bold, small caps) go to
 * whatever you're editing; everything else is looked up in App.cmd[<current view>] and then
 * App.cmd.global, which the views fill in. */
(function () {
  'use strict';
  const { $, $$, toast } = App;
  App.cmd = { global: {}, writing: {}, research: {}, citations: {}, verify: {} };

  /* ------------------------------------------------------------ icons */
  const T = (x, y, size, txt, fam) => '<text x="' + x + '" y="' + y + '" font-size="' + size + '" font-family="' + (fam || 'Georgia,serif') +
    '" stroke="none" fill="currentColor">' + txt + '</text>';
  const ICONS = {
    save: '<path d="M5 4h11l3 3v13H5z M8 4v5h7V4 M8 20v-6h8v6"/>',
    run: '<path d="M7 5l12 7-12 7z"/>',
    tag: '<path d="M3 12V4h8l9 9-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>',
    plus: '<path d="M12 5v14 M5 12h14"/>',
    footnote: T(3, 19, 17, 'a') + T(13, 11, 10, '1', 'sans-serif'),
    cite: T(3, 22, 28, '“”'),
    doc: '<path d="M6 3h9l4 4v14H6z M14 3v5h5"/>',
    note: '<path d="M5 4h14v16H5z M8 9h8 M8 13h8 M8 17h5"/>',
    copy: '<path d="M9 9h11v11H9z M5 15V4h11"/>',
    mail: '<path d="M3 6h18v12H3z M3 7l9 6 9-6"/>',
    upload: '<path d="M12 16V5 M7 10l5-5 5 5 M5 20h14"/>',
    folder: '<path d="M3 7h6l2 2h10v10H3z"/>',
    projects: '<path d="M3 6h7l2 2h9v11H3z M3 10h18"/>',
    search: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    clip: '<path d="M8 12.5l6.5-6.5a3 3 0 0 1 4.2 4.2L10 19a5 5 0 0 1-7-7l8-8"/>',
    camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17 M12 3.5c3 3 3 14 0 17 M12 3.5c-3 3-3 14 0 17"/>',
    marker: '<path d="M14 4l6 6-8 8H6v-6z M4 21h9"/>',
    download: '<path d="M12 4v11 M7 10l5 5 5-5 M5 20h14"/>',
    sync: '<path d="M20 12a8 8 0 0 1-14 5.3 M4 12a8 8 0 0 1 14-5.3 M18 3v4h-4 M6 21v-4h4"/>',
    books: '<path d="M4 4h4v16H4z M9 4h4v16H9z M14.5 5l3.8-1 3.2 15.5-3.8 1z"/>',
    final: '<path d="M6 3h9l4 4v14H6z M14 3v5h5 M9 14l2.5 2.5L16 12"/>',
  };
  $$('#ribbon [data-ic]').forEach(b => {
    b.insertAdjacentHTML('afterbegin', '<svg viewBox="0 0 24 24" class="ic" aria-hidden="true">' + (ICONS[b.dataset.ic] || '') + '</svg>');
  });

  /* ------------------------------------------------------------ tabs */
  const ribbon = $('#ribbon');
  function showTab(name) {
    $$('.rb-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    $$('.rb-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === name));
    try { localStorage.setItem('ribbonTab', name); } catch (e) { /* ignore */ }
    if (name === 'view' && App.git) App.git.refresh();
  }
  $$('.rb-tab').forEach(t => t.addEventListener('click', () => {
    ribbon.classList.remove('collapsed'); $('#rb-collapse').textContent = '▴';
    showTab(t.dataset.tab);
  }));
  $('#rb-collapse').onclick = () => {
    const c = ribbon.classList.toggle('collapsed');
    $('#rb-collapse').textContent = c ? '▾' : '▴';
    $('#rb-collapse').title = c ? 'Expand the ribbon' : 'Collapse the ribbon';
  };
  try { const t = localStorage.getItem('ribbonTab'); if (t) showTab(t); } catch (e) { /* ignore */ }

  /* ------------------------------------------------------------ commands */
  App.cmd.global.ul = () => { if (!Rich.list('ul')) toast('Click in the text first.', true); };
  App.cmd.global.ol = () => { if (!Rich.list('ol')) toast('Click in the text first.', true); };
  App.cmd.global.quote = () => { if (!Rich.quote()) toast('Click in the text first.', true); };

  function run(cmd) {
    if (['italic', 'bold', 'smallcaps'].includes(cmd)) {
      if (!Rich.format(cmd)) toast('Click in the text first.', true);
      return;
    }
    const fn = (App.cmd[App.view] || {})[cmd] || App.cmd.global[cmd];
    if (fn) fn(); else toast('That isn’t available here.', true);
  }
  $$('#ribbon [data-cmd], #inspector [data-cmd]').forEach(b => {
    b.addEventListener('mousedown', e => e.preventDefault());      // keep the text selection
    b.addEventListener('click', () => run(b.dataset.cmd));
  });
  Rich.wireBlockSelect($('#tb-block'));

  // Which controls make sense where. Called when the view or document changes.
  const TEXT_CMDS = ['italic', 'bold', 'smallcaps', 'ul', 'ol', 'quote', 'footnote', 'cite', 'unnumbered'];
  // Contextual tabs (Research, Library) show only in their view, like Word's picture or table tabs; going to
  // that view opens its tab, and leaving it goes back to Home.
  let lastView = null;
  function contextTabs(view) {
    $$('.rb-tab[data-for-view]').forEach(t => { t.hidden = t.dataset.forView !== view; });
    if (view === lastView) return;
    lastView = view;
    const ctx = $('.rb-tab[data-for-view="' + view + '"]');
    const active = $('.rb-tab.active');
    if (ctx) showTab(ctx.dataset.tab);
    else if (active && active.dataset.forView) showTab('home');
  }

  App.ribbon = {
    run,                    // run a ribbon command by name (the right-click menu uses it too)
    textEditing: true,      // false while the Writing view shows a document's Details box
    refresh() {
      const view = App.view;
      contextTabs(view);
      $$('#ribbon [data-views]').forEach(e => { e.disabled = !e.dataset.views.split(' ').includes(view); });
      const textOk = !(view === 'writing' && App.ribbon.textEditing === false);
      $$('#ribbon [data-cmd]').forEach(e => {
        if (!TEXT_CMDS.includes(e.dataset.cmd)) return;
        const allowed = !e.dataset.views || e.dataset.views.split(' ').includes(view);
        e.disabled = !(allowed && textOk);
      });
      $('#tb-block').disabled = !(['writing', 'research'].includes(view) && textOk);
      $('#email-tools').style.display = view === 'writing' ? '' : 'none';
    },
  };

  /* ------------------------------------------------------------ theme */
  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('theme', t); } catch (e) { /* ignore */ }
    $$('[data-theme-btn]').forEach(b => b.classList.toggle('active', b.dataset.themeBtn === t));
    // the Mac window's title bar follows (main.swift); nothing happens in a browser
    try { window.webkit.messageHandlers.reword.postMessage({ action: 'theme', theme: t }).catch(() => {}); } catch (e) { /* not the Mac app */ }
  }
  $$('[data-theme-btn]').forEach(b => b.addEventListener('click', () => setTheme(b.dataset.themeBtn)));
  setTheme(document.documentElement.dataset.theme || 'light');

  /* ------------------------------------------------------------ view settings */
  const writingView = $('#view-writing');
  function setLayout(l) {
    ['editor', 'split', 'preview'].forEach(n => {
      writingView.classList.toggle('layout-' + n, n === l);
      $('#note-split').classList.toggle('layout-' + n, n === l);
    });
    $$('[data-layout]').forEach(b => b.classList.toggle('active', b.dataset.layout === l));
    try { localStorage.setItem('layout', l); } catch (e) { /* ignore */ }
    if (l === 'preview') App.showPreview && App.showPreview();
  }
  $$('[data-layout]').forEach(b => b.addEventListener('click', () => setLayout(b.dataset.layout)));

  // Edit as rich text or Markdown (Writing and Research). Both versions stay in sync; the views do the work.
  App.editMode = 'rich';
  App.setEditMode = function (m) {
    App.editMode = m === 'md' ? 'md' : 'rich';
    $$('[data-editmode]').forEach(b => b.classList.toggle('active', b.dataset.editmode === App.editMode));
    try { localStorage.setItem('editMode', App.editMode); } catch (e) { /* ignore */ }
    Object.values(App.views).forEach(v => v && v.setEditMode && v.setEditMode(App.editMode));
  };
  $$('[data-editmode]').forEach(b => b.addEventListener('click', () => App.setEditMode(b.dataset.editmode)));
  let layout = 'split';
  try { layout = localStorage.getItem('layout') || 'split'; } catch (e) { /* ignore */ }
  setLayout(layout);

  // The PDF viewers in Chrome and Edge honor these hints; Safari opens at its own default.
  const zoomSel = $('#view-zoom');
  try { zoomSel.value = localStorage.getItem('previewZoom') || '100'; } catch (e) { /* ignore */ }
  if (!zoomSel.value) zoomSel.value = '100';
  App.previewFragment = () => zoomSel.value === 'fit' ? '#view=FitH&navpanes=0' : '#zoom=' + zoomSel.value + '&navpanes=0';
  const pzVal = $('#pz-val');
  const showZoom = () => { pzVal.textContent = (zoomSel.value === 'fit' ? 'Fit' : zoomSel.value + '%'); };
  zoomSel.addEventListener('change', () => {
    try { localStorage.setItem('previewZoom', zoomSel.value); } catch (e) { /* ignore */ }
    showZoom();
    if (window.PDFView && !$('#pdf-view').hidden) PDFView.setZoom(zoomSel.value);   // PDFs just rescale
    else if (App.reloadPreview) App.reloadPreview();                                // other previews reload
  });
  // + and − on the preview step through these sizes; the ribbon's zoom menu follows along
  const STEPS = [50, 75, 100, 125, 150, 200, 300, 400];
  function stepZoom(dir) {
    const now = window.PDFView ? PDFView.percent() : parseInt(zoomSel.value, 10) || 100;
    const next = dir > 0 ? STEPS.find(s => s > now + 1) : [...STEPS].reverse().find(s => s < now - 1);
    if (!next) return;
    if (![...zoomSel.options].some(o => o.value === String(next))) {
      const o = document.createElement('option'); o.value = String(next); o.textContent = next + '%';
      const after = [...zoomSel.options].find(x => x.value !== 'fit' && parseInt(x.value, 10) > next);
      zoomSel.insertBefore(o, after || null);
    }
    zoomSel.value = String(next);
    zoomSel.dispatchEvent(new Event('change'));
  }
  $('#pz-in').onclick = () => stepZoom(1);
  $('#pz-out').onclick = () => stepZoom(-1);
  pzVal.onclick = () => { zoomSel.value = 'fit'; zoomSel.dispatchEvent(new Event('change')); };
  showZoom();
  $('#view-newtab').onclick = () => { if (App.openPreviewInTab) App.openPreviewInTab(); };

  // Draggable divider between the editor and the right pane (Markdown / preview).
  const splitter = $('#splitter');
  function setSplit(pct) {
    pct = Math.max(20, Math.min(80, pct));
    // fr units can't be calculated in CSS, so hand the two column sizes over directly
    writingView.style.setProperty('--ed-w', pct + 'fr');
    writingView.style.setProperty('--right-w', (100 - pct) + 'fr');
    try { localStorage.setItem('split', String(pct)); } catch (e) { /* ignore */ }
  }
  try { const v = parseFloat(localStorage.getItem('split')); if (v) setSplit(v); } catch (e) { /* ignore */ }
  splitter.addEventListener('mousedown', e => {
    e.preventDefault();
    document.body.classList.add('dragging');
    const rect = writingView.getBoundingClientRect();
    const side = writingView.contains($('#tree-pane')) ? $('#tree-pane').getBoundingClientRect().width : 0;
    const move = ev => setSplit(((ev.clientX - rect.left - side) / (rect.width - side - 6)) * 100);
    const up = () => { document.body.classList.remove('dragging'); document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  });
  splitter.addEventListener('dblclick', () => setSplit(50));

  const SCALES = [0.85, 0.95, 1, 1.1, 1.25, 1.4, 1.6];
  function setScale(i) {
    i = Math.max(0, Math.min(SCALES.length - 1, i));
    document.documentElement.style.setProperty('--page-scale', SCALES[i]);
    try { localStorage.setItem('pageScale', String(SCALES[i])); } catch (e) { /* ignore */ }
    return i;
  }
  let scaleIdx = 2;
  try { const s = parseFloat(localStorage.getItem('pageScale')); if (s && SCALES.includes(s)) scaleIdx = SCALES.indexOf(s); } catch (e) { /* ignore */ }
  $('#size-down').onclick = () => { scaleIdx = setScale(scaleIdx - 1); };
  $('#size-up').onclick = () => { scaleIdx = setScale(scaleIdx + 1); };
  $('#size-reset').onclick = () => { scaleIdx = setScale(2); };

  App.ribbon.refresh();
})();
