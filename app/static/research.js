/* Research: OneNote-style notes. Each note is a rich-text page with a title, an optional topic,
 * and an optional source from the citation library. Creating a note asks for the source's
 * citation details, so a note and its citation are born together.
 */
(function () {
  'use strict';
  const { $, $$, el, api, post, put, toast, saver } = App;

  const listEl = $('#note-list');
  const search = $('#rs-search');
  const editorEl = $('#note-editor');
  const emptyEl = $('#note-empty');
  const titleIn = $('#note-title');
  const topicIn = $('#note-topic');
  const body = $('#note-body');
  const sourceBox = $('#note-source');
  const mdEd = $('#note-md');
  const richEl = $('#note-rich');
  const renderEl = $('#note-render');

  let notes = [];          // list entries (no bodies)
  let loaded = false;      // until the first list arrives, say so rather than "No notes yet"
  let cur = null;          // the open note: { id, mtime, citation, ... }
  let value = '';          // cached serialized state of the open note
  let regKey = null;
  let bodyTimer = null;

  /* ------------------------------------------------------------ list */
  function plain(md) { return (md || '').replace(/\\(.)/g, '$1').replace(/\]\{\.smallcaps\}|\]\{\.auth[^}]*\}|[*_\[\]]/g, ''); }

  // A note's citation style comes from its project (APA, Bluebook brief/memo or law review); else brief/memo.
  function noteFormat(n) {
    const p = App.projects.get(((n || cur) || {}).project);
    const st = p && p.citation_style;
    return st === 'apa' ? 'apa' : st === 'bluebook-lawreview' ? 'lawreview' : st === 'chicago' ? 'chicago'
      : st === 'chicago-author-date' ? 'chicago-ad' : 'practitioner';
  }

  function noteRow(n) {
    const row = el('div', 'list-item' + (cur && cur.id === n.id ? ' active' : ''));
    row.dataset.id = n.id;
    row.appendChild(el('div', 'li-title', n.title));
    if (n.citation) row.appendChild(el('div', 'li-sub', n.citation));
    row.onclick = () => select(n.id);
    App.projects.draggable(row, 'note:' + n.id);
    listEl.appendChild(row);
  }
  function byTopic(items) {
    const groups = new Map();
    items.forEach(n => { const k = n.topic || ''; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(n); });
    return Array.from(groups.keys()).sort((a, b) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b))).map(k => [k, groups.get(k)]);
  }

  // One project: notes grouped by topic. All projects: under project headings, then topics.
  function renderList() {
    listEl.innerHTML = '';
    if (!loaded) { listEl.appendChild(el('div', 'empty small', 'Loading…')); return; }
    const q = search.value.trim().toLowerCase();
    const items = notes.filter(n => App.projects.inScope(n.project) &&
      (!q || (n.title + ' ' + n.topic + ' ' + n.snippet + ' ' + n.citation).toLowerCase().includes(q)));
    if (!items.length) listEl.appendChild(el('div', 'empty small', notes.length ? 'No notes here.' : 'No notes yet.'));
    if (App.projects.scope === 'all' && App.projects.list.length) {
      App.projects.group(items, n => n.project).forEach(g => {
        const h = App.projects.heading(g, 'research', moveNote);
        listEl.appendChild(h.el);
        if (h.folded) return;
        if (!g.items.length) listEl.appendChild(el('div', 'proj-empty muted small', 'Drag notes here'));
        byTopic(g.items).forEach(([k, ns]) => { listEl.appendChild(el('div', 'group-title sub', k || 'No topic')); ns.forEach(noteRow); });
      });
    } else {
      byTopic(items).forEach(([k, ns]) => { listEl.appendChild(el('div', 'group-title', k || 'No topic')); ns.forEach(noteRow); });
    }
    const dl = $('#topic-list');
    dl.innerHTML = '';
    Array.from(new Set(notes.map(n => n.topic).filter(Boolean))).sort().forEach(t => { const o = el('option'); o.value = t; dl.appendChild(o); });
  }

  async function moveNote(value, pid) {
    const id = value.startsWith('note:') ? value.slice(5) : '';
    if (!id) return;
    await saver.flush(false);
    try {
      const r = await post('/api/note/project', { id, project: pid || '' });
      const entry = notes.find(x => x.id === id); if (entry) entry.project = r.project;
      if (cur && cur.id === id) { cur.project = r.project; cur.mtime = r.mtime; showNoteProject(); App.chips.refresh([body], noteFormat()); scheduleRender(); }
      renderList();
      toast(pid ? 'Moved to ' + App.projects.name(pid) + '. Its sources were added to the project.' : 'Removed from its project.');
    } catch (e) { toast(e.message, true); }
  }
  function showNoteProject() {
    const box = $('#note-project'); box.innerHTML = '';
    if (cur) box.appendChild(App.projects.select(cur.project || '', v => moveNote('note:' + cur.id, v)));
  }
  App.projects.onChange(() => { renderList(); showNoteProject(); });

  search.addEventListener('input', renderList);

  async function loadList() {
    notes = (await api('/api/notes')).notes;
    loaded = true;
    renderList();
  }

  /* ------------------------------------------------------------ the open note */
  // The note's Markdown. In rich-text mode it comes from the editor (footnote texts are kept from the last
  // parse, since the rich note editor shows footnote marks but not their text); in Markdown mode the
  // text box is the source of truth.
  let parsed = { notes: {}, order: [], orphans: [] };
  function richMd() {
    const bodies = new Map();
    parsed.order.forEach(l => { const d = document.createElement('div'); d.innerHTML = parsed.notes[l] || ''; bodies.set(l, d); });
    return MD.exportMd(body, bodies, parsed.orphans, { split: false });
  }
  function exportBody() { return App.editMode === 'md' ? mdEd.value : richMd(); }
  function loadBody(md) {
    parsed = MD.parse(md || '');
    body.innerHTML = parsed.docHtml || '<p><br></p>';
    App.chips.refresh([body], noteFormat());
    if (document.activeElement !== mdEd) mdEd.value = md || '';
  }

  // The page view on the right: rendered by Pandoc on the server (footnotes, live citations), or by the
  // editor's own parser when Pandoc isn't available.
  let renderTimer = null, renderSeq = 0;
  function scheduleRender() {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(async () => {
      if (!cur) return;
      const seq = ++renderSeq, md = exportBody();
      $('#note-render-state').textContent = 'updating…';
      let html;
      try { html = (await post('/api/render', { md, format: noteFormat() })).html; }
      catch (e) {
        const p = MD.parse(md);
        html = p.docHtml + (p.order.length ? '<section class="footnotes"><ol>' + p.order.map(l => '<li>' + (p.notes[l] || '') + '</li>').join('') + '</ol></section>' : '');
      }
      if (seq !== renderSeq) return;
      renderEl.innerHTML = '<h1 class="render-title">' + App.esc(titleIn.value.trim() || 'Untitled note') + '</h1>' + html;
      $('#note-render-state').textContent = '';
    }, 350);
  }
  function snapshot() {
    return JSON.stringify({ title: titleIn.value.trim(), topic: topicIn.value.trim(), citation: cur ? cur.citation : '', body: exportBody() });
  }
  function refreshValue() { if (cur) value = snapshot(); }
  function changed() {
    clearTimeout(bodyTimer);
    bodyTimer = setTimeout(() => {
      refreshValue(); saver.touch();
      if (App.editMode !== 'md' && document.activeElement !== mdEd) mdEd.value = richMd();
      scheduleRender();
    }, 150);
  }
  let mdTimer = null;
  mdEd.addEventListener('input', () => {
    clearTimeout(mdTimer);
    mdTimer = setTimeout(() => { parsed = MD.parse(mdEd.value); body.innerHTML = parsed.docHtml || '<p><br></p>'; changed(); }, 250);
  });
  function showMode() {
    const md = App.editMode === 'md';
    mdEd.hidden = !md; richEl.hidden = md;
  }
  saver.syncs.add(() => { clearTimeout(bodyTimer); refreshValue(); });

  async function select(id) {
    await saver.flush(false);
    if (regKey) { saver.unregister(regKey); regKey = null; }
    cur = null;
    if (!id) { editorEl.hidden = true; emptyEl.hidden = false; renderList(); return; }
    let n;
    try { n = await api('/api/note?id=' + encodeURIComponent(id)); }
    catch (e) { toast('Couldn’t open that note: ' + e.message, true); return; }
    cur = n;
    emptyEl.hidden = true; editorEl.hidden = false;
    titleIn.value = n.title; topicIn.value = n.topic;
    loadBody(n.body || '');
    showNoteProject();
    showMode();
    scheduleRender();
    renderSource();
    value = snapshot();
    const item = {
      title: () => cur ? cur.title : 'note', saved: value,
      get: () => value,
      save: async (v, force) => {
        const d = JSON.parse(v);
        const r = await put('/api/note', Object.assign({ id: n.id, mtime: n.mtime, force }, d));
        n.mtime = r.mtime; n.title = r.title; n.topic = r.topic;
        const entry = notes.find(x => x.id === n.id);
        if (entry) Object.assign(entry, { title: r.title, topic: r.topic, citation: r.citation, updated: r.updated });
      },
      keepalive: v => ({ url: '/api/note', body: Object.assign({ id: n.id, mtime: n.mtime, force: true }, JSON.parse(v)) }),
    };
    regKey = 'note:' + n.id;
    saver.register(regKey, item);
    renderList();
  }

  titleIn.addEventListener('input', changed);
  topicIn.addEventListener('input', changed);
  body.addEventListener('input', changed);

  async function deleteNote(id) {
    const n = cur && cur.id === id ? cur : notes.find(x => x.id === id);
    if (!n || !confirm('Delete the note “' + n.title + '”?\n\nThe file moves to research/_trash.')) return;
    const open = cur && cur.id === id;
    if (open) { saver.unregister(regKey); regKey = null; cur = null; }
    try { await post('/api/note/delete', { id }); } catch (e) { toast(e.message, true); return; }
    await loadList();
    if (open) select('');
  }
  $('#note-delete').onclick = () => { if (cur) deleteNote(cur.id); };

  /* ------------------------------------------------------------ the source card */
  function renderSource() {
    sourceBox.innerHTML = '';
    const tag = cur && cur.citation;
    const c = tag ? App.citation(tag) : null;
    if (tag) {
      const top = el('div', 'li-top');
      top.append(el('span', 'chip', c ? App.typeLabel(c.type) : 'missing'), el('code', '', tag));
      const cite = el('div', 'li-body'); cite.innerHTML = c ? ((c.forms.bluebook_practitioner || {}).html || '') : '<i>This citation is no longer in the library.</i>';
      const acts = el('div', 'row');
      if (c) { const o = el('button', 'btn small', 'Open in Citations'); o.onclick = () => { App.showView('citations').then(() => App.views.citations.open(tag)); }; acts.appendChild(o); }
      const ch = el('button', 'btn small', 'Change…'); ch.onclick = linkExisting;
      const un = el('button', 'btn small', 'Unlink'); un.onclick = () => setCitation('');
      acts.append(ch, un);
      sourceBox.append(top, cite, acts);
    } else {
      sourceBox.appendChild(el('div', 'muted small', 'No source linked to this note.'));
      const acts = el('div', 'row');
      const a = el('button', 'btn small', 'Link a source…'); a.onclick = linkExisting;
      const b = el('button', 'btn small', '+ New source…'); b.onclick = newSourceInline;
      acts.append(a, b);
      sourceBox.appendChild(acts);
    }
  }

  function setCitation(tag) { cur.citation = tag; renderSource(); refreshValue(); saver.touch(); }
  function linkExisting() {
    App.pickCitation({ title: 'Choose the source for this note', pickOnly: true, onPick: c => setCitation(c.tag) });
  }
  function newSourceInline() {
    sourceBox.innerHTML = '';
    const form = App.CiteForm({ mode: 'new' });
    const err = el('div', 'error'); err.hidden = true;
    const ok = el('button', 'btn primary small', 'Add to Citations and link');
    const no = el('button', 'btn small', 'Cancel');
    no.onclick = renderSource;
    ok.onclick = async () => {
      const m = form.validate();
      if (m) { err.textContent = m; err.hidden = false; return; }
      try {
        const c = await post('/api/citation/new', form.get());
        await App.loadCitations();
        setCitation(c.tag);
        toast('Added ' + c.tag + ' to your library.');
      } catch (e) { err.textContent = e.message; err.hidden = false; }
    };
    const row = el('div', 'row'); row.append(ok, no);
    sourceBox.append(form.el, err, row);
    form.focus();
  }

  /* ------------------------------------------------------------ editor toolbar */
  // Cite… in a note inserts a live citation (the page view shows it in full, brief/memo style).
  App.cmd.research.cite = () => {
    if (!cur) { toast('Open a note first.', true); return; }
    if (App.editMode === 'md') {
      const at = [mdEd.selectionStart, mdEd.selectionEnd];
      App.pickCitation({ title: 'Insert a citation', format: noteFormat(), live: true, project: cur && cur.project, onPick: (c, which) => {
        const f = noteFormat(), narrative = which === 'narrative';
        const md = '[' + App.citeMarkdown(c, App.isParenFormat(f) ? (narrative ? 'narrative' : 'intext') : 'full', f) + ']{.cite tag="' + c.tag + '"' + (narrative ? ' narrative="1"' : '') + '}';
        mdEd.setRangeText(md, at[0], at[1], 'end'); mdEd.focus();
        mdEd.dispatchEvent(new Event('input'));
      } });
      return;
    }
    const saved = Rich.saveSelection();
    App.pickCitation({ title: 'Insert a citation', format: noteFormat(), live: true, project: cur && cur.project, onPick: (c, which) => {
      const html = App.chips.html(c, which === 'narrative' ? { narrative: '1' } : {}, noteFormat());
      if (!Rich.insertHtml(saved, html)) { body.focus(); Rich.insertHtmlKeepingSpans(html); }
      App.chips.refresh([body], noteFormat());
      changed();
    } });
  };
  body.addEventListener('click', e => {
    const chip = e.target.closest && e.target.closest('span.cite');
    if (!chip) return;
    e.preventDefault();
    App.chips.edit(chip, { format: noteFormat(), changed: () => changed() });
  });

  /* ------------------------------------------------------------ new note dialog */
  const dlg = $('#dlg-newnote');
  let nnForm = null;
  let nnPicked = null;

  function nnMode() { return ($('input[name="nn-src"]:checked') || {}).value || 'new'; }
  function nnUpdate() {
    const m = nnMode();
    $('#nn-new').hidden = m !== 'new';
    $('#nn-existing').hidden = m !== 'existing';
    $('#nn-error').hidden = true;
  }
  $$('input[name="nn-src"]').forEach(r => r.addEventListener('change', nnUpdate));
  $('#nn-pick').onclick = () => App.pickCitation({ title: 'Choose the source for this note', pickOnly: true, onPick: c => {
    nnPicked = c;
    const box = $('#nn-picked'); box.hidden = false; box.innerHTML = '';
    box.append(el('code', '', c.tag));
    const t = el('div', 'li-body'); t.innerHTML = (c.forms.bluebook_practitioner || {}).html || ''; box.appendChild(t);
    App.openDialog(dlg);
  } });

  function newNote() {
    $('#nn-title').value = ''; $('#nn-topic').value = '';
    $('input[name="nn-src"][value="new"]').checked = true;
    nnPicked = null; $('#nn-picked').hidden = true;
    nnForm = App.CiteForm({ mode: 'new' });
    $('#nn-new').innerHTML = ''; $('#nn-new').appendChild(nnForm.el);
    nnUpdate();
    App.openDialog(dlg);
    $('#nn-title').focus();
  }

  $('#nn-create').onclick = async () => {
    const err = $('#nn-error');
    const fail = m => { err.textContent = m; err.hidden = false; };
    const mode = nnMode();
    let title = $('#nn-title').value.trim();
    let citation = '';
    try {
      if (mode === 'new') {
        const m = nnForm.validate();
        if (m) return fail(m);
        const c = await post('/api/citation/new', nnForm.get());
        citation = c.tag;
        if (!title) title = App.citeText(c).slice(0, 80);
        await App.loadCitations();
      } else if (mode === 'existing') {
        if (!nnPicked) return fail('Choose a citation, or pick “No source”.');
        citation = nnPicked.tag;
        if (!title) title = App.citeText(nnPicked).slice(0, 80);
      }
      if (!title) return fail('Give the note a title.');
      const n = await post('/api/note/new', { title, topic: $('#nn-topic').value.trim(), citation, project: App.projects.current() });
      dlg.close();
      await App.showView('research');
      await loadList();
      await select(n.id);
      body.focus();
    } catch (e) { fail(e.message); }
  };
  $('#btn-newnote').onclick = newNote;

  async function exportNote(format) {
    if (!cur) return;
    await saver.flush(false);
    toast(format === 'pdf' ? 'Making the PDF…' : 'Making the Word file…');
    try {
      const r = await post('/api/note/export', { id: cur.id, format, style: noteFormat() });
      const a = document.createElement('a');
      a.href = '/build/' + r.path.split('/').map(encodeURIComponent).join('/') + '?download=1';
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { toast(e.message, true); }
  }
  $('#note-export-docx').onclick = () => exportNote('docx');
  $('#note-export-pdf').onclick = () => exportNote('pdf');
  App.cmd.research.exportPdf = () => exportNote('pdf');
  App.cmd.research.exportDocx = () => exportNote('docx');

  App.views.research = {
    async reload() { await loadList(); if (cur) await select(cur.id); },
    setEditMode(m) {
      if (cur) {
        if (m === 'md') mdEd.value = richMd();        // switching to Markdown: start from the rich editor
        else loadBody(mdEd.value);                     // back to rich text: show what was typed
        refreshValue();
      }
      showMode();
      if (cur) (m === 'md' ? mdEd : body).focus();
    },
    async show() {
      try { await Promise.all([loadList(), App.loadCitations()]); } catch (e) { toast('Couldn’t load notes: ' + e.message, true); }
      if (cur) renderSource();
    },
    async open(id) { await App.showView('research'); await loadList(); await select(id); },
    // "Cited in" (citations.js): open the note and show the citation. The rich note editor shows footnote marks
    // but not their text, so a citation inside a footnote is shown in the Markdown editor.
    async reveal(id, u) {
      await this.open(id);
      if (!cur || cur.id !== id) return;
      if ($('#note-split').classList.contains('layout-preview')) { const b = $('[data-layout="split"]'); if (b) b.click(); }
      if (u.where === 'footnote' && App.editMode !== 'md') {
        App.setEditMode('md');
        toast('This citation is in a footnote, so it’s shown in Markdown. ⌃⌘M goes back to rich text.');
      }
      const ok = App.editMode === 'md' ? App.chips.revealText(mdEd, u) : App.chips.reveal(body, u);
      if (!ok) toast('That citation isn’t there any more (it may have been edited since).', true);
    },
    // for the right-click menu (contextmenu.js)
    current: () => (cur ? cur.id : null),
    note: id => notes.find(x => x.id === id) || null,
    remove: id => deleteNote(id),
    move: (id, pid) => moveNote('note:' + id, pid),
    newNote,
    afterSave() { renderList(); },
    subtitle() {                        // under the title bar's "Research"
      if (!loaded) return '';
      const n = notes.filter(x => App.projects.inScope(x.project)).length;
      return n + ' note' + (n === 1 ? '' : 's') + (App.projects.current() ? ' in ' + App.projects.name(App.projects.current()) : '');
    },
  };
})();
