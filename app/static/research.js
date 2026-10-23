/* Research: OneNote-style notes. Each note is a rich-text page with a title, an optional topic,
 * and any number of sources from the citation library (a source can be linked to many notes too).
 * Beside the note, every linked source is shown as a card, with the chosen one's file in the reader,
 * as in Citations. New sources can be added to the library from the note, or while creating it.
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
  const mdEd = $('#note-md');
  const richEl = $('#note-rich');

  let notes = [];          // list entries (no bodies)
  let loaded = false;      // until the first list arrives, say so rather than "No notes yet"
  let cur = null;          // the open note: { id, mtime, citations: [tag…], ... }
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
    const tags = n.citations || [];
    if (tags.length) row.appendChild(el('div', 'li-sub', tags.length > 2 ? tags.slice(0, 2).join(', ') + ' +' + (tags.length - 2) : tags.join(', ')));
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
      (!q || (n.title + ' ' + n.topic + ' ' + n.snippet + ' ' + (n.citations || []).join(' ')).toLowerCase().includes(q)));
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
      if (cur && cur.id === id) { cur.project = r.project; cur.mtime = r.mtime; showNoteProject(); App.chips.refresh([body], noteFormat()); renderCards(); }
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

  function snapshot() {
    return JSON.stringify({ title: titleIn.value.trim(), topic: topicIn.value.trim(), citations: cur ? cur.citations : [], body: exportBody() });
  }
  function refreshValue() { if (cur) value = snapshot(); }
  function changed() {
    clearTimeout(bodyTimer);
    bodyTimer = setTimeout(() => {
      refreshValue(); saver.touch();
      if (App.editMode !== 'md' && document.activeElement !== mdEd) mdEd.value = richMd();
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
    if (!id) { editorEl.hidden = true; emptyEl.hidden = false; closeSource(); renderList(); return; }
    let n;
    try { n = await api('/api/note?id=' + encodeURIComponent(id)); }
    catch (e) { toast('Couldn’t open that note: ' + e.message, true); return; }
    n.citations = n.citations || (n.citation ? [n.citation] : []);
    cur = n;
    emptyEl.hidden = true; editorEl.hidden = false;
    titleIn.value = n.title; topicIn.value = n.topic;
    loadBody(n.body || '');
    showNoteProject();
    showMode();
    closeNewForm();
    renderPane(true);
    value = snapshot();
    const item = {
      title: () => cur ? cur.title : 'note', saved: value,
      get: () => value,
      save: async (v, force) => {
        const d = JSON.parse(v);
        const r = await put('/api/note', Object.assign({ id: n.id, mtime: n.mtime, force }, d));
        n.mtime = r.mtime; n.title = r.title; n.topic = r.topic;
        const entry = notes.find(x => x.id === n.id);
        if (entry) Object.assign(entry, { title: r.title, topic: r.topic, citations: r.citations, citation: r.citation, updated: r.updated });
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
    if (open) { saver.unregister(regKey); regKey = null; cur = null; closeSource(); }
    try { await post('/api/note/delete', { id }); } catch (e) { toast(e.message, true); return; }
    await loadList();
    if (open) select('');
  }
  $('#note-delete').onclick = () => { if (cur) deleteNote(cur.id); };

  /* ------------------------------------------------------------ linked citations (the right side) */
  // One card per linked source; the chosen card's files are shown in the reader below, with its highlights,
  // as in Citations and Verify (highlights made here are saved with the source and show up there too).
  const S = { tag: null, files: [], fileName: null, annMtime: null, reader: null };
  const fileCounts = new Map();           // tag -> number of files, for the cards
  const linked = () => (cur ? cur.citations : []);

  function shownForm(c) {
    const f = noteFormat(), forms = c.forms || {};
    const k = App.isParenFormat(f) ? App.formKey('reference', f) : App.formKey('full', f);
    const v = forms[k] && !/^\(not listed/.test(forms[k].text || '') ? forms[k] : (forms.bluebook_practitioner || {});
    return v.html || App.esc(App.citeText(c));
  }

  function renderCards() {
    const box = $('#ns-cards');
    box.innerHTML = '';
    const tags = linked();
    $('#ns-count').textContent = tags.length ? '(' + tags.length + ')' : '';
    box.classList.toggle('none', !tags.length);
    if (!tags.length) {
      const none = el('div', 'ns-none');
      none.append(el('p', '', 'No citations linked to this note.'),
        el('p', 'small', 'Link the sources this note is about, or add new ones to Citations from here. Each one shows here with its PDF or saved web page.'));
      const row = el('div', 'row');
      const a = el('button', 'btn small', 'Link sources…'); a.onclick = linkExisting;
      const b = el('button', 'btn small', '+ New source…'); b.onclick = () => openNewForm();
      row.append(a, b); none.appendChild(row);
      box.appendChild(none);
      return;
    }
    tags.forEach(tag => {
      const c = App.citation(tag);
      const card = el('div', 'ns-card' + (tag === S.tag ? ' active' : '') + (c ? '' : ' missing'));
      card.dataset.tag = tag;
      const top = el('div', 'ns-card-top');
      top.append(el('span', 'chip', c ? App.typeLabel(c.type) : 'missing'), el('code', '', tag));
      const n = fileCounts.get(tag);
      if (n !== undefined) top.appendChild(el('span', 'ns-files', n ? n + ' file' + (n === 1 ? '' : 's') : 'no file'));
      const cite = el('div', 'ns-card-cite');
      if (c) cite.innerHTML = shownForm(c); else cite.innerHTML = '<i>This citation is no longer in the library.</i>';
      const x = el('button', 'ns-unlink', '×'); x.title = 'Unlink ' + tag + ' from this note (the citation stays in your library)';
      x.onclick = e => { e.stopPropagation(); setCitations(linked().filter(t => t !== tag)); };
      card.append(top, cite, x);
      card.onclick = () => choose(tag);
      box.appendChild(card);
    });
  }

  // first = a note was just opened: show its first source
  function renderPane(first) {
    const tags = linked();
    if (first || !tags.includes(S.tag)) choose(tags[0] || null);
    else renderCards();
  }

  function setCitations(tags) {
    cur.citations = tags;
    renderPane();
    refreshValue(); saver.touch();
  }

  function linkExisting() {
    if (!cur) return;
    App.pickCitation({ title: 'Link sources to this note', multi: true, chosen: linked(), notesOption: false, addLabel: 'Link', allowNone: true,
      project: cur.project, onPickMany: list => {
        const picked = new Set(list.map(c => c.tag));
        const keep = linked().filter(t => picked.has(t) || !App.citation(t));     // a missing source is only unlinked with its ×
        list.forEach(c => { if (!keep.includes(c.tag)) keep.push(c.tag); });
        const added = keep.filter(t => !linked().includes(t));
        setCitations(keep);
        if (added.length) choose(added[added.length - 1]);
      } });
  }

  // New sources from the note: add one and link it, or keep the form open for the next.
  let newForm = null;
  function closeNewForm() { newForm = null; const b = $('#ns-newform'); b.hidden = true; b.innerHTML = ''; }
  function openNewForm() {
    if (!cur) return;
    const box = $('#ns-newform');
    box.innerHTML = ''; box.hidden = false;
    newForm = App.CiteForm({ mode: 'new' });
    const err = el('div', 'error'); err.hidden = true;
    const ok = el('button', 'btn primary small', 'Add to Citations and link');
    const more = el('button', 'btn small', 'Add, link and start another');
    const no = el('button', 'btn small', 'Close');
    no.onclick = closeNewForm;
    const add = async again => {
      const m = newForm.validate();
      if (m) { err.textContent = m; err.hidden = false; return; }
      try {
        const c = await post('/api/citation/new', newForm.get());
        await App.loadCitations();
        if (!cur) return;
        setCitations(linked().concat([c.tag]));
        choose(c.tag);
        toast('Added ' + c.tag + ' to your library and linked it.');
        if (again) openNewForm(); else closeNewForm();
      } catch (e) { err.textContent = e.message; err.hidden = false; }
    };
    ok.onclick = () => add(false);
    more.onclick = () => add(true);
    const row = el('div', 'row'); row.append(ok, more, no);
    box.append(el('div', 'pane-label-text', 'New source'), newForm.el, err, row);
    newForm.focus();
  }
  $('#ns-link').onclick = linkExisting;
  $('#ns-new').onclick = () => openNewForm();

  /* the chosen source's files */
  function getReader() {
    if (!S.reader && window.Reader) S.reader = new window.Reader($('#ns-view'), $('#ns-anns'), { onChange: anns => scheduleSave(anns) });
    return S.reader;
  }
  function closeSource() { flushAnns(); if (S.reader) S.reader.close(); S.tag = null; S.fileName = null; $('#ns-source').hidden = true; }

  async function choose(tag) {
    if (tag === S.tag && S.fileName) { renderCards(); return; }
    await flushAnns();
    S.tag = tag; S.fileName = null;
    renderCards();
    const card = tag && $('#ns-cards .ns-card[data-tag="' + tag + '"]');
    if (card) card.scrollIntoView({ block: 'nearest' });
    if (!tag) { $('#ns-source').hidden = true; if (S.reader) S.reader.close(); return; }
    $('#ns-source').hidden = false;
    await loadFiles();
  }

  async function loadFiles(pick) {
    const tag = S.tag;
    if (!tag) return;
    let r = { files: [] };
    if (App.citation(tag)) {
      try { r = await api('/api/files?tag=' + encodeURIComponent(tag)); } catch (e) { toast(e.message, true); return; }
    }
    if (tag !== S.tag) return;
    S.files = r.files;
    fileCounts.set(tag, S.files.filter(f => !f.annotated).length);
    renderCards();
    const sel = $('#ns-file');
    sel.innerHTML = '';
    S.files.forEach(f => { const o = el('option', '', f.name + (f.annotations ? '  (' + f.annotations + ')' : '')); o.value = f.name; sel.appendChild(o); });
    sel.hidden = !S.files.length;
    const keep = pick || (S.files.find(f => f.kind === 'pdf' && !f.annotated) || S.files[0] || {}).name;
    if (!keep) { noFile(); return; }
    sel.value = keep;
    await openFile(keep);
  }

  function noFile() {
    if (S.reader) S.reader.close();
    $('#ns-src-body').hidden = true;
    const box = $('#ns-src-empty');
    box.hidden = false; box.innerHTML = '';
    const c = S.tag && App.citation(S.tag);
    if (!c) { box.appendChild(el('p', '', 'This citation is no longer in the library, so there’s nothing to show.')); return; }
    const url = c.fields && c.fields.url;
    box.appendChild(el('p', '', 'No file for this source yet.'));
    box.appendChild(el('p', 'muted small', url ? 'Save a snapshot of its web page to read it here, or open the live page.' : 'Attach a PDF of it to read it here, or drop one on this side.'));
    if (url) { const a = el('a', 'vf-url', url); a.href = url; a.target = '_blank'; box.appendChild(a); }
  }

  const fileUrl = name => '/files/' + encodeURIComponent(S.tag) + '/' + encodeURIComponent(name);
  async function openFile(name) {
    await flushAnns();
    S.fileName = name;
    const f = S.files.find(x => x.name === name);
    $('#ns-src-empty').hidden = true; $('#ns-src-body').hidden = false;
    const view = $('#ns-view');
    if (!f || f.kind !== 'pdf') {
      if (S.reader) S.reader.close();
      view.innerHTML = '';
      const a = el('a', 'btn', 'Open ' + name); a.href = fileUrl(name) + '?download=1';
      const box = el('div', 'empty'); box.append(el('p', '', 'ReWord shows PDFs. Other files open in their own app.'), a);
      view.appendChild(box);
      return;
    }
    const tag = S.tag;
    let ann;
    try { ann = await api('/api/annotations?tag=' + encodeURIComponent(tag) + '&name=' + encodeURIComponent(name)); }
    catch (e) { toast(e.message, true); return; }
    if (tag !== S.tag || name !== S.fileName) return;
    S.annMtime = ann.mtime;
    const r = getReader();
    if (!r) { setTimeout(() => { if (tag === S.tag) openFile(name); }, 150); return; }      // the reader module is still loading
    try { await r.open(fileUrl(name) + '?t=' + Date.now(), ann.annotations); }
    catch (e) { view.textContent = ''; view.appendChild(el('div', 'empty', 'Couldn’t show this PDF: ' + e.message)); }
  }

  // highlights made beside a note are saved with the source, like the ones in Citations
  let pendingAnns = null, annTimer = null;
  function scheduleSave(anns) {
    pendingAnns = { tag: S.tag, name: S.fileName, anns: anns.map(a => Object.assign({}, a)) };
    clearTimeout(annTimer);
    annTimer = setTimeout(flushAnns, 800);
  }
  async function flushAnns() {
    clearTimeout(annTimer);
    if (!pendingAnns) return;
    const p = pendingAnns; pendingAnns = null;
    try { const r = await put('/api/annotations', { tag: p.tag, name: p.name, annotations: p.anns, mtime: S.annMtime, force: true }); S.annMtime = r.mtime; }
    catch (e) { toast('Couldn’t save the highlights: ' + e.message, true); }
  }
  saver.syncs.add(() => { flushAnns(); });
  window.addEventListener('beforeunload', () => {
    if (!pendingAnns) return;
    fetch('/api/annotations', { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag: pendingAnns.tag, name: pendingAnns.name, annotations: pendingAnns.anns, force: true }) });
  });

  const srcUrl = () => { const c = S.tag && App.citation(S.tag); return (c && c.fields && c.fields.url) || ''; };
  $('#ns-file').addEventListener('change', e => openFile(e.target.value));
  $('#ns-zoom-in').onclick = () => S.reader && S.reader.zoom(1);
  $('#ns-zoom-out').onclick = () => S.reader && S.reader.zoom(-1);
  $('#ns-zoom-fit').onclick = () => S.reader && S.reader.zoom(0);
  $('#ns-live').onclick = () => { if (srcUrl()) window.open(srcUrl(), '_blank'); else toast('This source has no web address. Add one in Citations.', true); };
  $('#ns-open-cite').onclick = () => { const t = S.tag; if (t && App.citation(t)) App.showView('citations').then(() => App.views.citations.open(t)); };
  $('#ns-snap').onclick = async () => {
    if (!srcUrl()) { toast('This source has no web address. Add one in Citations.', true); return; }
    const b = $('#ns-snap'); b.disabled = true; const label = b.textContent; b.textContent = 'Saving page…';
    try { const r = await post('/api/snapshot', { tag: S.tag, url: srcUrl() }); toast(r.how === 'webkit' ? 'Saved the page as a PDF.' : 'Saved the page’s text as a PDF.'); await loadFiles(r.name); }
    catch (e) { toast(e.message, true); }
    finally { b.disabled = false; b.textContent = label; }
  };
  async function upload(list) {
    if (!S.tag || !App.citation(S.tag)) return;
    let last = null;
    for (const f of Array.from(list)) {
      if (f.size > 50e6 && !confirm(f.name + ' is ' + Math.round(f.size / 1e6) + ' MB. Large files make the GitHub repository slow, and GitHub refuses files over 100 MB. Attach it anyway?')) continue;
      try {
        const r = await fetch('/api/attach?tag=' + encodeURIComponent(S.tag) + '&name=' + encodeURIComponent(f.name),
          { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-ReWord': '1' }, body: f });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.statusText);
        last = j.name;
      } catch (e) { toast('Couldn’t attach ' + f.name + ': ' + e.message, true); }
    }
    if (last) { toast('Attached.'); await loadFiles(last); }
  }
  $('#ns-attach').onclick = () => { if (S.tag && App.citation(S.tag)) $('#ns-input').click(); else toast('Choose a source in the library first.', true); };
  $('#ns-input').addEventListener('change', e => { upload(e.target.files); e.target.value = ''; });
  const srcPane = $('#ns-source');
  srcPane.addEventListener('dragover', e => { if (S.tag && Array.from(e.dataTransfer.types).includes('Files')) { e.preventDefault(); srcPane.classList.add('dragging'); } });
  srcPane.addEventListener('dragleave', e => { if (!srcPane.contains(e.relatedTarget)) srcPane.classList.remove('dragging'); });
  srcPane.addEventListener('drop', e => { e.preventDefault(); srcPane.classList.remove('dragging'); if (e.dataTransfer.files.length) upload(e.dataTransfer.files); });

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
  // Sources for the new note: ones already in Citations, and new ones (added to Citations when the note is
  // created). The new-source form starts open, since most notes are about a source.
  const dlg = $('#dlg-newnote');
  let nnForm = null;
  let nnItems = [];          // [{ c }] already in the library, or [{ data }] to add

  const hasContent = f => !!(f && f.get().type && Object.keys(f.get().fields || {}).length);
  function nnTaken(tag) { return !!App.citation(tag) || nnItems.some(x => (x.c ? x.c.tag : x.data.tag) === tag); }
  function nnRender() {
    const box = $('#nn-list'); box.innerHTML = '';
    nnItems.forEach((x, i) => {
      const row = el('div', 'nn-item');
      const cite = el('div', 'nn-item-cite');
      if (x.c) cite.innerHTML = ((x.c.forms || {}).bluebook_practitioner || {}).html || App.esc(App.citeText(x.c));
      else { const f = x.data.fields || {}; cite.textContent = App.typeLabel(x.data.type) + ': ' + plain(f.name || f.title || f.text || f.case_name || f.number || x.data.tag); }
      const rm = el('button', 'ns-unlink', '×'); rm.title = 'Don’t link this source'; rm.type = 'button';
      rm.onclick = () => { nnItems.splice(i, 1); nnRender(); };
      row.append(el('span', 'chip', x.c ? 'in Citations' : 'new'), el('code', '', x.c ? x.c.tag : x.data.tag), cite, rm);
      box.appendChild(row);
    });
  }
  function nnShowForm(on) {
    $('#nn-new-box').hidden = !on;
    $('#nn-add-new').hidden = on;
    $('#nn-new').innerHTML = '';
    nnForm = on ? App.CiteForm({ mode: 'new' }) : null;
    if (nnForm) { $('#nn-new').appendChild(nnForm.el); }
    $('#nn-new-label').textContent = nnItems.some(x => x.data) ? 'Another new source' : 'New source (it’s added to Citations when you create the note)';
  }
  // the open form's source, checked, into the list: '' when done, else the problem
  function nnQueue() {
    const m = nnForm.validate();
    if (m) return m;
    const v = nnForm.get();
    if (nnTaken(v.tag)) return 'Another source here already uses the tag “' + v.tag + '”. Choose another tag.';
    nnItems.push({ data: v });
    return '';
  }
  $('#nn-queue').onclick = () => {
    const err = $('#nn-error');
    const m = nnQueue();
    if (m) { err.textContent = m; err.hidden = false; return; }
    err.hidden = true;
    nnRender(); nnShowForm(true); nnForm.focus();
  };
  $('#nn-new-close').onclick = () => { $('#nn-error').hidden = true; nnShowForm(false); };
  $('#nn-add-new').onclick = () => { nnShowForm(true); nnForm.focus(); };
  $('#nn-pick').onclick = () => App.pickCitation({ title: 'Choose the sources for this note', multi: true, notesOption: false, addLabel: 'Choose', allowNone: true,
    chosen: nnItems.filter(x => x.c).map(x => x.c.tag), project: App.projects.current(), onPickMany: list => {
      nnItems = list.map(c => ({ c })).concat(nnItems.filter(x => x.data));
      nnRender();
    } });

  function newNote() {
    $('#nn-title').value = ''; $('#nn-topic').value = '';
    nnItems = []; nnRender();
    nnShowForm(true);
    $('#nn-error').hidden = true;
    App.openDialog(dlg);
    $('#nn-title').focus();
  }

  $('#nn-create').onclick = async () => {
    const err = $('#nn-error');
    const fail = m => { err.textContent = m; err.hidden = false; };
    err.hidden = true;
    if (hasContent(nnForm)) {            // a source typed into the open form counts, as before
      const m = nnQueue();
      if (m) return fail(m);
      nnShowForm(false);
      nnRender();
    }
    let title = $('#nn-title').value.trim();
    const btn = $('#nn-create'); btn.disabled = true;
    try {
      let added = false;
      for (let i = 0; i < nnItems.length; i++) {
        if (nnItems[i].c) continue;
        const c = await post('/api/citation/new', nnItems[i].data);
        nnItems[i] = { c };               // if a later one fails, trying again doesn't add this one twice
        added = true;
      }
      if (added) { await App.loadCitations(); nnRender(); }
      const tags = nnItems.map(x => x.c.tag);
      if (!title && nnItems.length) title = App.citeText(nnItems[0].c).slice(0, 80);
      if (!title) return fail('Give the note a title.');
      const n = await post('/api/note/new', { title, topic: $('#nn-topic').value.trim(), citations: tags, project: App.projects.current() });
      dlg.close();
      await App.showView('research');
      await loadList();
      await select(n.id);
      body.focus();
    } catch (e) { fail(e.message); }
    finally { btn.disabled = false; }
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
      if (cur) renderCards();
      if (App.inspector) App.inspector.refresh();          // the title bar's "24 notes"
    },
    async open(id) { await App.showView('research'); await loadList(); await select(id); },
    // "Cited in" (citations.js): open the note and show the citation. The rich note editor shows footnote marks
    // but not their text, so a citation inside a footnote is shown in the Markdown editor.
    async reveal(id, u) {
      await this.open(id);
      if (!cur || cur.id !== id) return;
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
    linkSources: () => linkExisting(),
    newSource: () => openNewForm(),
    afterSave() { renderList(); },
    subtitle() {                        // under the title bar's "Research"
      if (!loaded) return '';
      const n = notes.filter(x => App.projects.inScope(x.project)).length;
      return n + ' note' + (n === 1 ? '' : 's') + (App.projects.current() ? ' in ' + App.projects.name(App.projects.current()) : '');
    },
  };
})();
