/* Writing: documents (each made from a template) with their sections, the rich-text editor,
 * footnotes, citation insertion, the live Markdown pane, and the Run / Tag buttons.
 * A document is like a OneNote notebook: pick it in the left tree, and its sections open below it.
 */
(function () {
  'use strict';
  const { $, $$, el, api, post, put, toast, saver } = App;

  const doc = $('#doc');
  const notesEl = $('#notes');
  const metaEd = $('#meta-editor');
  const mdView = $('#md-view');
  const tree = $('#tree');

  const W = {
    info: null,        // {slug, title, template}
    tmpl: null,        // template.json of the open document
    files: [],         // {file, kind, md, mtime, item}
    cur: null,         // file name open in the editor
    orphans: [],
    status: null,      // git status for this document
    outputs: [],
  };
  const noteEls = new Map();      // label -> .note element currently in the panel
  const graveyard = new Map();    // label -> .note removed from the panel (so undo can bring it back)
  let running = false;

  document.execCommand('defaultParagraphSeparator', false, 'p');

  const curFile = () => W.files.find(f => f.file === W.cur);
  const dirty = f => f.item && f.md !== f.item.saved;
  const docFormat = () => App.citeFormat(W.tmpl, ((W.files || []).find(f => f.kind === 'meta') || {}).md);
  const splitLines = () => !(W.tmpl && W.tmpl.sentence_lines === false);

  /* ---------------------------------------------------------- document tree */

  function titleOf(f) {
    if (f.kind === 'meta') return 'Details';
    const m = /^#\s+(.*?)\s*(?:\{[^}]*\})?\s*$/m.exec(f.md);
    const t = m ? m[1].replace(/\\(.)/g, '$1').replace(/\]\{\.smallcaps\}|[*_\[\]]/g, '') : '';
    return t || f.file.replace(/^\d+-|\.md$/g, '');
  }

  function docRow(d) {
    const open = W.info && d.slug === W.info.slug;
    const row = el('div', 'doc-row' + (open ? ' open' : ''));
    row.dataset.slug = d.slug;
    row.appendChild(el('span', 'caret', open ? '▾' : '▸'));
    row.appendChild(el('span', 'name', d.title));
    const ctl = el('span', 'ctl');
    const ren = el('button', '', '✎'); ren.title = 'Rename';
    ren.onclick = e => { e.stopPropagation(); renameDoc(d); };
    const del = el('button', '', '✕'); del.title = 'Delete this document (kept in documents/_trash)';
    del.onclick = e => { e.stopPropagation(); deleteDoc(d); };
    ctl.append(ren, del); row.appendChild(ctl);
    row.onclick = () => { if (!open) openDoc(d.slug); };
    App.projects.draggable(row, 'doc:' + d.slug);
    tree.appendChild(row);
    if (open) renderSections();
  }

  // One project chosen: documents grouped by template. All projects: grouped under project headings
  // (drop a document on a heading to move it there).
  function renderTree() {
    tree.innerHTML = '';
    const docs = App.state.documents.slice().sort((a, b) => b.updated - a.updated).filter(d => App.projects.inScope(d.project));
    if (!docs.length && !(App.projects.scope === 'all' && App.projects.list.length && App.state.documents.length)) {
      tree.appendChild(el('div', 'empty small', App.state.documents.length ? 'No documents in this project yet.' : 'No documents yet.'));
      return;
    }
    if (App.projects.scope === 'all' && App.projects.list.length) {
      App.projects.group(docs, d => d.project).forEach(g => {
        const h = App.projects.heading(g, 'writing', moveDoc);
        tree.appendChild(h.el);
        if (!h.folded) g.items.forEach(docRow);
        if (!h.folded && !g.items.length) tree.appendChild(el('div', 'proj-empty muted small', 'Drag documents here'));
      });
      return;
    }
    App.state.templates.map(t => ({ t, docs: docs.filter(d => d.template === t.id) })).filter(g => g.docs.length).forEach(g => {
      tree.appendChild(el('div', 'group-title', g.t.name));
      g.docs.forEach(docRow);
    });
  }

  async function moveDoc(value, pid) {
    const slug = value.startsWith('doc:') ? value.slice(4) : '';
    if (!slug) return;
    try {
      const r = await post('/api/doc/option', { slug, key: 'project', value: pid || '' });
      if (W.info && W.info.slug === slug) { W.info.project = r.info.project || ''; showDocProject(); }
      await refreshDocs();
      toast(pid ? 'Moved to ' + App.projects.name(pid) + '. Its sources were added to the project.' : 'Removed from its project.');
    } catch (e) { toast(e.message, true); }
  }
  function showDocProject() {
    const box = $('#doc-project'); box.innerHTML = '';
    if (!W.info) return;
    box.appendChild(App.projects.select(W.info.project || '', v => moveDoc('doc:' + W.info.slug, v)));
  }
  App.projects.onChange(() => { renderTree(); showDocProject(); });

  // Template: a detail you can change. Switching converts the document on the server (store.change_template):
  // citations take the new style and move between footnotes and the text as it needs, the reference list
  // follows, and the details are rebuilt from the new template. The files as they were go to _trash first.
  function showDocTemplate() {
    const sel = $('#doc-template'); sel.innerHTML = '';
    if (!W.info) return;
    const bib = !!(W.tmpl && W.tmpl.bibliography);
    App.state.templates.forEach(t => {
      if (t.bibliography && t.id !== W.info.template) return;
      const o = el('option', '', t.name); o.value = t.id; sel.appendChild(o);
    });
    sel.value = W.info.template;
    sel.disabled = bib;
    $('#doc-template-hint').textContent = bib ? 'An annotated bibliography can’t switch to another template.'
      : 'Switching converts the document: citations take the new template’s style.';
  }
  function conversionSummary(r) {
    const n = (k, one, many) => r[k] ? r[k] + ' ' + (r[k] === 1 ? one : many) : '';
    const bits = [n('to_notes', 'citation moved into a footnote', 'citations moved into footnotes'),
      n('to_text', 'footnote became a text citation', 'footnotes became text citations'),
      n('notes_kept', 'footnote with commentary stays a footnote', 'footnotes with commentary stay footnotes'),
      { added: 'a reference list was added', renamed: 'the reference list was renamed', removed: 'the empty reference list was removed',
        kept: 'your typed reference list was kept (this template doesn’t build one)' }[r.references] || ''].filter(Boolean);
    return 'Now a ' + r.name + '.' + (bits.length ? ' ' + bits.join('; ').replace(/^./, x => x.toUpperCase()) + '.' : '');
  }
  $('#doc-template').addEventListener('change', async () => {
    const sel = $('#doc-template'), tid = sel.value;
    if (!W.info || tid === W.info.template) return;
    const t = App.state.templates.find(x => x.id === tid) || { name: tid };
    if (!confirm('Switch “' + W.info.title + '” to ' + t.name + '?\n\nCitations are reformatted in the new style and moved between ' +
      'footnotes and the text as it needs. The details are rebuilt from the new template, with your old ones kept below them as ' +
      'comments. A copy of the files as they are now goes to the document’s _trash folder.')) { sel.value = W.info.template; return; }
    await saver.flush(false);
    let r;
    try { r = await post('/api/doc/template', { slug: W.info.slug, template: tid }); }
    catch (e) { toast(e.message, true); sel.value = W.info.template; return; }
    await openDoc(W.info.slug, W.cur);
    toast(conversionSummary(r));
    if (r.gaps && r.gaps.length) {
      alert('These sources format in Chicago style, but Chicago would also use details they don’t have yet. ' +
        'Add them in Citations when you can:\n\n' + r.gaps.map(g => '• ' + g.tag + ': ' + g.missing.join(', ')).join('\n'));
    }
  });

  function renderSections() {
    const sections = W.files.filter(f => f.kind === 'section');
    const box = el('ul', 'sections');
    W.files.forEach(f => {
      const li = el('li', f.file === W.cur ? 'active' : '');
      li.dataset.file = f.file;
      li.appendChild(el('span', 'name', titleOf(f)));
      if (dirty(f)) { const d = el('span', 'dot'); d.title = 'Unsaved'; li.appendChild(d); }
      if (f.kind === 'section' && W.tmpl.multi_section) {
        const ctl = el('span', 'ctl');
        const idx = sections.indexOf(f);
        const mk = (label, title, fn, disabled) => {
          const b = el('button', '', label); b.title = title; b.disabled = disabled;
          b.onclick = e => { e.stopPropagation(); fn(); }; ctl.appendChild(b);
        };
        mk('↑', 'Move up', () => moveSection(f, 'up'), idx === 0);
        mk('↓', 'Move down', () => moveSection(f, 'down'), idx === sections.length - 1);
        mk('✕', 'Remove section (kept in the document’s _trash folder)', () => deleteSection(f), false);
        li.appendChild(ctl);
      }
      li.onclick = () => selectFile(f.file);
      box.appendChild(li);
    });
    if (W.tmpl.multi_section) {
      const add = el('li', 'add', '+ Add section');
      add.onclick = addSection;
      box.appendChild(add);
    }
    tree.appendChild(box);
  }

  async function refreshDocs() {
    const s = await api('/api/state');
    App.state.templates = s.templates;
    App.state.documents = s.documents;
    renderTree();
  }

  async function addSection() {
    const title = prompt('Title of the new section:', '');
    if (title === null) return;
    await saver.flush(false);
    const r = await post('/api/section/new', { doc: W.info.slug, title });
    await openDoc(W.info.slug, r.file);
  }
  async function moveSection(f, dir) {
    await saver.flush(false);
    const r = await post('/api/section/move', { doc: W.info.slug, file: f.file, dir });
    await openDoc(W.info.slug, W.cur === f.file ? r.file : W.cur);
  }
  async function deleteSection(f) {
    if (!confirm('Remove “' + titleOf(f) + '” from this document?\n\nThe file moves to the document’s _trash folder, so it can be recovered.')) return;
    await saver.flush(false);
    await post('/api/section/delete', { doc: W.info.slug, file: f.file });
    await openDoc(W.info.slug, W.cur === f.file ? null : W.cur);
  }

  /* ---------------------------------------------------------- new / rename / delete documents */

  const ndDlg = $('#dlg-newdoc');
  let ndTemplate = null;

  function openNewDoc() {
    const cp = App.projects.get(App.projects.current());
    if (cp && cp.default_template) ndTemplate = cp.default_template;
    $('#nd-project').innerHTML = '';
    $('#nd-project').append(App.projects.select(App.projects.current(), () => {}));
    const grid = $('#tpl-grid');
    grid.innerHTML = '';
    App.state.templates.forEach(t => {
      const card = el('button', 'tpl-card' + (ndTemplate === t.id ? ' selected' : ''));
      card.type = 'button';
      card.append(el('div', 'tpl-name', t.name), el('div', 'tpl-desc', t.description),
        el('div', 'tpl-out', 'Makes: ' + t.outputs.map(o => o === 'txt' ? 'plain text' : o === 'docx' ? 'Word' : o.toUpperCase()).join(', ')));
      card.onclick = () => { ndTemplate = t.id; $$('.tpl-card', grid).forEach(c => c.classList.toggle('selected', c === card)); $('#nd-title').focus(); };
      grid.appendChild(card);
    });
    if (!ndTemplate && App.state.templates.length) { ndTemplate = App.state.templates[0].id; grid.firstChild.classList.add('selected'); }
    $('#nd-title').value = '';
    App.openDialog(ndDlg);
    $('#nd-title').focus();
  }
  $('#nd-create').onclick = async () => {
    if (!ndTemplate) { toast('Pick a template first.', true); return; }
    try {
      const r = await post('/api/doc/new', { template: ndTemplate, title: $('#nd-title').value.trim(), project: ($('#nd-project select') || {}).value || '' });
      ndDlg.close();
      await refreshDocs();
      await openDoc(r.slug);
    } catch (e) { toast(e.message, true); }
  };
  $('#nd-title').addEventListener('keydown', e => { if (e.key === 'Enter') $('#nd-create').click(); });
  $('#btn-newdoc').onclick = openNewDoc;
  $('#btn-newdoc-2').onclick = openNewDoc;

  async function renameDoc(d) {
    const t = prompt('Rename this document:', d.title);
    if (!t || t === d.title) return;
    await post('/api/doc/rename', { slug: d.slug, title: t });
    if (W.info && W.info.slug === d.slug) W.info.title = t;
    await refreshDocs();
  }
  async function deleteDoc(d) {
    if (!confirm('Delete “' + d.title + '”?\n\nIt moves to documents/_trash, so it can be recovered. Its built files are removed.')) return;
    if (W.info && W.info.slug === d.slug) { await saver.flush(false); unregisterFiles(); W.info = null; }
    await post('/api/doc/delete', { slug: d.slug });
    await refreshDocs();
    if (!W.info) {         // open the next one in the list (most recently changed, in the project shown)
      const docs = App.state.documents.slice().sort((a, b) => b.updated - a.updated);
      const next = docs.find(x => App.projects.inScope(x.project)) || docs[0];
      if (next) openDoc(next.slug); else showEmpty(true);
    }
  }

  function showEmpty(on) {
    $('#empty-writing').hidden = !on;
    App.ribbon.textEditing = !on; App.ribbon.refresh();
    $('#scroller').hidden = on;
    $('#right-pane').style.visibility = on ? 'hidden' : '';
    if (on) { W.info = null; W.tmpl = null; W.files = []; W.cur = null; renderTree(); $('#version-info').textContent = ''; }
  }

  /* ---------------------------------------------------------- opening a document */

  function unregisterFiles() {
    W.files.forEach(f => { if (f.regKey) saver.unregister(f.regKey); });
  }

  async function openDoc(slug, selectName) {
    await saver.flush(false);
    unregisterFiles();
    let r;
    try { r = await api('/api/doc?slug=' + encodeURIComponent(slug)); }
    catch (e) { toast('Couldn’t open that document: ' + e.message, true); showEmpty(App.state.documents.length === 0); return; }
    showEmpty(false);
    W.info = r.doc; W.tmpl = r.template; W.cur = null;
    showFinal(); showDocProject(); showDocTemplate();
    W.files = r.files.map(f => {
      const file = { file: f.file, kind: f.kind, md: f.md, mtime: f.mtime };
      file.item = {
        title: () => file.file, saved: f.md, get: () => file.md,
        save: async (value, force) => {
          const res = await put('/api/file', { doc: slug, file: file.file, content: value, mtime: file.mtime, force });
          file.mtime = res.mtime; applyStatus(res.status);
        },
        keepalive: value => ({ url: '/api/file', body: { doc: slug, file: file.file, content: value, mtime: file.mtime, force: true } }),
      };
      file.regKey = 'doc:' + slug + '/' + file.file;
      saver.register(file.regKey, file.item);
      return file;
    });
    W.outputs = r.outputs || [];
    applyStatus(r.status);
    applyTemplate();
    try { localStorage.setItem('lastDoc', slug); } catch (e) { /* private mode */ }
    const want = W.files.find(f => f.file === selectName) || W.files.find(f => f.kind === 'section') || W.files[0];
    selectFile(want.file, true);
    renderOutputs(W.outputs.map(o => Object.assign({}, o, { label: o.label + (o.label === 'Draft' ? ' (last build)' : '') })));
    if (!W.outputs.length) clearPreview();
    $('#wordcount').textContent = '';
    await refreshDocs();
    if (App.inspector) App.inspector.refresh();          // the window title and the inspector name this document now
  }

  function applyTemplate() {
    const t = W.tmpl;
    doc.dataset.hs = t.heading_scheme || 'none';
    if (t.bibliography) doc.dataset.bib = '1'; else delete doc.dataset.bib;
    notesEl.dataset.hs = doc.dataset.hs;
    $$('[data-cmd="footnote"]').forEach(b => { b.hidden = t.id === 'email'; });
    $('#tb-unnumbered').hidden = t.heading_scheme !== 'article';
    $('#tb-block').hidden = t.heading_scheme === 'none';
    $('#email-tools').hidden = t.id !== 'email';
    $('#btn-save').title = 'Save (⌘S): save, build ' + t.outputs.map(o => o.toUpperCase()).join(' and ') + (t.redline ? ' and the redline' : '')
      + ', copy the finished files into outputs/, and sync with GitHub';
    $('#meta-hint').textContent = t.id === 'email'
      ? 'Recipients and subject, as YAML. “Copy email” and “Open in Mail” use these.'
      : 'Document details (cover page, header, certificates), as YAML: keep the quotes and the indentation.';
  }

  /* ---------------------------------------------------------- loading a file into the editor */

  function selectFile(name, force) {
    if (!force && name === W.cur) return;
    if (W.cur) updateMd();
    W.cur = name;
    const f = curFile();
    // numbering offsets: footnotes (and article Part numbers) continue from earlier sections
    let fnOff = 0, h1Off = 0;
    for (const o of W.files) {
      if (o.file === name) break;
      if (o.kind !== 'section') continue;
      fnOff += MD.countRefs(o.md).length;
      h1Off += MD.countH1(o.md);
    }
    [doc, notesEl].forEach(e => e.style.setProperty('--fn-off', fnOff));
    doc.style.setProperty('--h1-off', h1Off);

    const isMeta = f.kind === 'meta';
    $('#meta-wrap').hidden = !isMeta;
    App.ribbon.textEditing = !isMeta; App.ribbon.refresh();
    if (isMeta) {
      metaEd.value = f.md;
      edited = false;
    } else {
      renderRich(f);
      docMd.value = f.md;
    }
    showEditMode();
    renderTree();
    renderMdPane();
  }

  // Show a section's Markdown in the rich editor (text, footnotes, live citations).
  function renderRich(f) {
    edited = false;                      // the editor shows the file exactly as it is
    const p = MD.parse(f.md);
    doc.innerHTML = p.docHtml || '<p><br></p>';
    noteEls.clear(); graveyard.clear(); notesEl.innerHTML = '';
    W.orphans = p.orphans;
    p.order.forEach(label => makeNote(label, p.notes[label] || ''));
    App.chips.refresh([doc, notesEl], docFormat());      // live citations show the library's current form
  }

  // Edit as rich text or Markdown (View → Edit as, ⌃⌘M). In Markdown mode the text box is the section's source.
  const docMd = $('#doc-md');
  function showEditMode() {
    const f = curFile();
    const isMeta = f && f.kind === 'meta';
    const md = App.editMode === 'md' && !isMeta;
    docMd.hidden = !md || !f;
    $('#page').hidden = md || isMeta;
  }
  let docMdTimer = null;
  docMd.addEventListener('input', () => {
    clearTimeout(docMdTimer);
    docMdTimer = setTimeout(() => {
      const f = curFile();
      if (!f || f.kind === 'meta' || docMd.value === f.md) return;
      f.md = docMd.value;
      renderRich(f);
      renderMdPane(); renderTree(); saver.touch();
    }, 300);
  });

  /* ---------------------------------------------------------- footnotes */

  function makeNote(label, bodyHtml) {
    const n = el('div', 'note'); n.dataset.label = label;
    const num = el('span', 'note-num'); num.title = 'Jump to the footnote mark';
    const body = el('div', 'note-body');
    body.contentEditable = 'true'; body.spellcheck = true; body.dataset.rich = 'inline';
    body.innerHTML = bodyHtml || '<div><br></div>';
    const lab = el('input', 'note-label'); lab.value = label; lab.spellcheck = false;
    lab.title = 'Footnote label (used only in the Markdown; must be unique across this document’s sections)';
    lab.onchange = () => renameNote(n, lab);
    num.onclick = () => {
      const ref = doc.querySelector('.fnref[data-label="' + CSS.escape(n.dataset.label) + '"]');
      if (ref) ref.scrollIntoView({ block: 'center', behavior: 'smooth' });
    };
    n.append(num, body, lab);
    noteEls.set(label, n);
    notesEl.appendChild(n);
    return n;
  }

  function refLabels() {
    const out = [];
    $$('.fnref', doc).forEach(r => { if (!out.includes(r.dataset.label)) out.push(r.dataset.label); });
    return out;
  }

  // keep the notes panel in step with the footnote marks in the text
  function syncNotes() {
    const want = refLabels();
    const have = Array.from(notesEl.children).map(n => n.dataset.label);
    if (want.length === have.length && want.every((l, i) => l === have[i])) return;
    have.forEach(l => {
      if (!want.includes(l)) { const n = noteEls.get(l); graveyard.set(l, n); noteEls.delete(l); n.remove(); }
    });
    want.forEach(l => {
      let n = noteEls.get(l);
      if (!n) {
        n = graveyard.get(l);
        if (n) { graveyard.delete(l); noteEls.set(l, n); } else n = makeNote(l, '');
      }
      notesEl.appendChild(n);   // appending in order re-sorts
    });
  }

  function allLabels(except) {
    const s = new Set();
    W.files.forEach(f => {
      if (f.kind !== 'section') return;
      (f.file !== W.cur ? MD.countRefs(f.md) : App.editMode === 'md' ? MD.countRefs(docMd.value) : refLabels()).forEach(l => s.add(l));
    });
    if (except) s.delete(except);
    return s;
  }
  function uniqueLabel(base) {
    const taken = allLabels();
    let l = base, i = 2;
    while (taken.has(l)) l = base + '-' + i++;
    return l;
  }

  function labelFromContext(range) {
    let text = '';
    try {
      const r = document.createRange();
      r.setStart(doc, 0); r.setEnd(range.startContainer, range.startOffset);
      text = r.toString();
    } catch (e) { /* ignore */ }
    return labelFromText(text);
  }
  function labelFromText(text) {
    const words = text.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(w => w.length > 2 &&
      !['the', 'and', 'for', 'that', 'with', 'this', 'from', 'are', 'was', 'were', 'has', 'have'].includes(w));
    const base = words.slice(-3).join('-') || (W.cur.replace(/^\d+-|\.md$/g, '') + '-note');
    return uniqueLabel(base.slice(0, 40));
  }

  function renameNote(n, input) {
    const old = n.dataset.label;
    const l = input.value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
    if (!l || l === old) { input.value = old; return; }
    if (allLabels(old).has(l)) { toast('Another footnote already uses “' + l + '”.', true); input.value = old; return; }
    $$('.fnref', doc).forEach(r => { if (r.dataset.label === old) r.dataset.label = l; });
    n.dataset.label = l; input.value = l;
    noteEls.delete(old); noteEls.set(l, n);
    onChange();
  }

  /* Markdown mode: Footnote and Cite… type the Markdown into the text box at the cursor. */
  function mdInNote() {          // is the cursor inside a footnote's text ([^label]: … and its indented lines)?
    const v = docMd.value, lines = v.slice(0, docMd.selectionStart).split('\n');
    for (let i = lines.length - 1; i >= 0; i--) {
      if (/^\[\^[^\]\s]+\]:/.test(lines[i])) return true;
      if (!(/^( {4}|\t)/.test(lines[i]) || (i < lines.length - 1 && !lines[i].trim()))) return false;
    }
    return false;
  }
  function mdFootnote(opts) {
    opts = opts || {};
    if (mdInNote()) { toast('Footnotes can’t be nested. Put the cursor in the main text.', true); return; }
    const v = docMd.value, at = docMd.selectionEnd;
    const label = opts.label ? uniqueLabel(opts.label) : uniqueLabel(labelFromText(v.slice(0, at).replace(/\[[^\]]*\]\{[^}]*\}|\[\^[^\]]*\]/g, ' ')));
    const def = '[^' + label + ']: ' + (opts.md || '');
    const head = v.slice(0, at) + '[^' + label + ']' + v.slice(at);
    docMd.value = head.replace(/\s*$/, '') + '\n\n' + def + '\n';
    const end = docMd.value.length - 1;
    docMd.focus(); docMd.setSelectionRange(end, end);
    App.chips.revealText(docMd, { tag: '', start: end, end });
    docMd.dispatchEvent(new Event('input'));
  }
  function mdCite(c, which, format) {
    const text = App.citeMarkdown(c, App.isParenFormat(format) ? (which === 'narrative' ? 'narrative' : 'intext') : 'full', format);
    const span = '[' + text + ']{.cite tag="' + c.tag + '"' + (which === 'narrative' ? ' narrative="1"' : '') + '}';
    if (W.tmpl.cite_mode === 'footnote' && !mdInNote()) { mdFootnote({ label: c.tag, md: span + '.' }); return; }
    docMd.focus();
    docMd.setRangeText(span, docMd.selectionStart, docMd.selectionEnd, 'end');
    docMd.dispatchEvent(new Event('input'));
  }

  // Insert a footnote mark at the cursor (optionally with starting text) and move into the note.
  function insertFootnote(opts) {
    opts = opts || {};
    if (App.editMode === 'md') { mdFootnote(opts); return; }
    const sel = getSelection();
    if (!sel.rangeCount || !doc.contains(sel.anchorNode) || sel.anchorNode.parentElement.closest('.raw')) {
      toast('Click in the text where the footnote should go first.', true); return;
    }
    const range = sel.getRangeAt(0);
    range.collapse(false);
    const label = opts.label ? uniqueLabel(opts.label) : labelFromContext(range);
    const span = document.createElement('span');
    span.className = 'fnref'; span.dataset.label = label; span.contentEditable = 'false';
    range.insertNode(span);
    const after = document.createRange(); after.setStartAfter(span); after.collapse(true);
    sel.removeAllRanges(); sel.addRange(after);
    syncNotes();
    const note = noteEls.get(label);
    if (opts.html) note.querySelector('.note-body').innerHTML = '<div>' + opts.html + '</div>';
    onChange();
    const body = note.querySelector('.note-body');
    body.focus();
    note.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  doc.addEventListener('click', e => {
    const r = e.target.closest && e.target.closest('.fnref');
    if (!r) return;
    const n = noteEls.get(r.dataset.label);
    if (n) { n.querySelector('.note-body').focus(); n.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
  });

  /* ---------------------------------------------------------- citations from the library */

  // Final draft: a per-document switch (document.json "final_draft"). Run then builds slug-final.* too.
  function showFinal() {
    const b = $('#btn-final'), on = !!(W.info && W.info.final_draft);
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  $('#btn-final').onclick = async () => {
    if (!W.info) { toast('Open a document first.', true); return; }
    const on = !W.info.final_draft;
    try { await post('/api/doc/option', { slug: W.info.slug, key: 'final_draft', value: on }); } catch (e) { toast(e.message, true); return; }
    W.info.final_draft = on; showFinal();
    toast(on ? 'Final draft on: the next Save also builds a copy with short forms, Id. and supra.' : 'Final draft off: Save builds the draft only.');
  };

  // Cite… inserts a live citation chip (see citechips.js). In footnote templates (the article) a cite
  // typed in the main text goes into a new footnote. Brief templates list every authority in the table of
  // authorities automatically when the document is built.
  function insertCite() {
    const f = curFile();
    if (App.editMode === 'md' && f && f.kind === 'section') {
      const at = [docMd.selectionStart, docMd.selectionEnd];
      App.pickCitation({ title: 'Insert a citation', format: docFormat(), live: true, project: W.info && W.info.project, onPick: (c, which) => {
        docMd.setSelectionRange(at[0], at[1]);
        mdCite(c, which, docFormat());
      } });
      return;
    }
    const saved = Rich.saveSelection();
    const inNote = saved && saved.el.classList && saved.el.classList.contains('note-body');
    if (!saved || (saved.el !== doc && !inNote)) { toast('Click in the text where the citation should go first.', true); return; }
    const format = docFormat();
    App.pickCitation({ title: 'Insert a citation', format, live: true, project: W.info && W.info.project, onPick: (c, which) => {
      const html = App.chips.html(c, which === 'narrative' ? { narrative: '1' } : {}, format);
      if (!inNote && W.tmpl.cite_mode === 'footnote') {
        Rich.restoreSelection(saved);
        insertFootnote({ label: c.tag, html: html + '.' });
      } else {
        Rich.insertHtml(saved, html);
      }
      App.chips.refresh([doc, notesEl], format);
      onChange();
    } });
  }

  // Annotated bibliography: add sources as entries (each a live citation on its own line, the annotation below).
  async function addEntries(list, opts) {
    const f = curFile();
    if (!f || f.kind !== 'section') { toast('Open the entries section first.', true); return; }
    updateMd();
    let notes = [];
    if (opts.fromNotes) { try { notes = (await api('/api/notes')).notes; } catch (e) { notes = []; } }
    const parts = [];
    for (const c of list) {
      let ann = 'Write the annotation here: what the source argues, how it was researched, and how you will use it.';
      if (opts.fromNotes) {
        const mine = notes.filter(n => n.citation === c.tag);
        const bodies = [];
        for (const n of mine) {
          try { const full = await api('/api/note?id=' + encodeURIComponent(n.id)); if ((full.body || '').trim()) bodies.push(full.body.trim()); } catch (e) { /* skip */ }
        }
        if (bodies.length) ann = bodies.join('\n\n').replace(/^#{1,6}\s+/gm, '').replace(/\n\[\^[^\]]+\]:[^\n]*/g, '').replace(/\[\^[^\]]+\]/g, '');
      }
      const f = docFormat();
      parts.push('[' + App.citeText(c, f === 'apa' || f.startsWith('chicago') ? App.formKey('reference', f) : 'bluebook_practitioner') + ']{.cite tag="' + c.tag + '" form="entry"}\n\n' + ann);
    }
    f.md = f.md.replace(/\s*$/, '') + '\n\n' + parts.join('\n\n') + '\n';
    renderRich(f); docMd.value = f.md;
    renderMdPane(); renderTree(); saver.touch();
    toast('Added ' + list.length + ' source' + (list.length === 1 ? '' : 's') + '. They are sorted when you Save.');
  }
  App.cmd.writing.bibAdd = () => {
    if (!W.tmpl || !W.tmpl.bibliography) { toast('Sources are added this way in an annotated bibliography. Use Cite… elsewhere.', true); return; }
    App.pickCitation({ title: 'Add sources to the bibliography', format: docFormat(), multi: true, project: W.info && W.info.project, onPickMany: addEntries });
  };

  // Click a citation chip to edit its pin cite, signal and parenthetical.
  [doc, notesEl].forEach(root => root.addEventListener('click', e => {
    const chip = e.target.closest && e.target.closest('span.cite');
    if (!chip || !W.tmpl) return;
    e.preventDefault();
    App.chips.edit(chip, { format: docFormat(), changed: () => onChange() });
  }));

  /* ---------------------------------------------------------- toolbar */

  Object.assign(App.cmd.writing, {
    footnote() {
      const f = curFile();
      if (App.editMode === 'md' && f && f.kind === 'section') mdFootnote();
      else if (Rich.activeEditable() === doc) insertFootnote();
      else toast('Footnotes can’t be nested. Put the cursor in the main text.', true);
    },
    cite: insertCite,
    unnumbered() {
      const b = Rich.currentBlock(doc);
      if (!b || b.tagName !== 'H1') { toast('Put the cursor in a top-level heading first.', true); return; }
      const toks = (b.dataset.attrs || '').split(/\s+/).filter(Boolean);
      const i = toks.indexOf('.unnumbered');
      if (i >= 0) toks.splice(i, 1); else toks.push('.unnumbered');
      if (toks.length) b.dataset.attrs = toks.join(' '); else delete b.dataset.attrs;
      onChange();
    },
    addSection() { if (W.info && W.tmpl.multi_section) addSection(); else toast('Open a document with sections first.', true); },
  });

  /* ---------------------------------------------------------- email tools */

  // The email's details (to, cc, subject) from its metadata file, with any edits in the Details box included.
  function emailMeta(key) {
    updateMd();
    const meta = (W.files.find(f => f.kind === 'meta') || { md: '' });
    const m = new RegExp('^' + key + ':\\s*"?(.*?)"?\\s*$', 'm').exec(meta.md);
    return m ? m[1].replace(/\\"/g, '"') : '';
  }
  function emailParts() {
    const clone = doc.cloneNode(true);
    $$('.raw', clone).forEach(r => r.remove());
    $$('.sc', clone).forEach(s => { s.removeAttribute('class'); s.style.fontVariant = 'small-caps'; });
    $$('.fnref,.auth', clone).forEach(s => { if (s.classList.contains('fnref')) s.remove(); else s.replaceWith(...s.childNodes); });
    clone.removeAttribute('id'); clone.removeAttribute('contenteditable'); clone.removeAttribute('style');
    $$('[contenteditable]', clone).forEach(e => e.removeAttribute('contenteditable'));
    const html = clone.innerHTML;
    const text = Array.from(clone.querySelectorAll('p,h1,h2,h3,h4,li,blockquote')).map(b => {
      b.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
      return b.textContent.trim();
    }).filter(Boolean).join('\n\n');
    return { html, text };
  }
  async function copyRich(html, text) {
    try {
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })]);
    } catch (e) {
      const box = document.createElement('div'); box.contentEditable = 'true'; box.innerHTML = html;
      box.style.cssText = 'position:fixed;left:-9999px'; document.body.appendChild(box);
      const r = document.createRange(); r.selectNodeContents(box);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      document.execCommand('copy'); box.remove();
    }
  }
  $('#em-copy').onclick = async () => { updateMd(); const p = emailParts(); await copyRich(p.html, p.text); toast('Copied. Paste it into your email.'); };
  $('#em-subject').onclick = async () => {
    const s = emailMeta('subject');
    if (!s) { toast('This email has no subject yet. Add one in its Details.', true); return; }
    await navigator.clipboard.writeText(s); toast('Subject copied.');
  };
  $('#em-mailto').onclick = () => {
    const p = emailParts();
    const q = ['subject=' + encodeURIComponent(emailMeta('subject')), 'body=' + encodeURIComponent(p.text)];
    if (emailMeta('cc')) q.unshift('cc=' + encodeURIComponent(emailMeta('cc')));
    window.location.href = 'mailto:' + encodeURIComponent(emailMeta('to')) + '?' + q.join('&');
  };

  /* ---------------------------------------------------------- Markdown pane + dirty tracking */

  // Only an edit makes the editor write a section back. Its Markdown is tidied on the way (a sentence on each line,
  // no trailing blank lines), and that should never happen to a file just because it was opened and looked at.
  let changeTimer, edited = false;
  function onChange() {
    edited = true;
    clearTimeout(changeTimer);
    changeTimer = setTimeout(() => { syncNotes(); updateMd(); }, 120);
  }
  doc.addEventListener('input', onChange);
  notesEl.addEventListener('input', onChange);
  metaEd.addEventListener('input', onChange);

  function exportCurrent() {
    const f = curFile();
    if (!f) return null;
    if (f.kind === 'meta') return metaEd.value;
    if (App.editMode === 'md') return docMd.value;
    const bodies = new Map();
    noteEls.forEach((n, l) => bodies.set(l, n.querySelector('.note-body')));
    return MD.exportMd(doc, bodies, W.orphans, { split: splitLines() });
  }

  function updateMd() {
    const f = curFile();
    if (!f) return;
    clearTimeout(changeTimer);
    if (!edited && !(App.editMode === 'md' && f.kind !== 'meta')) return;     // nothing typed here since it was opened
    const md = exportCurrent();
    if (md !== f.md) {
      f.md = md;
      if (App.editMode !== 'md' && document.activeElement !== docMd) docMd.value = md;
      renderMdPane();
      renderTree();
      saver.touch();
    }
  }
  saver.syncs.add(() => { if (App.view === 'writing') updateMd(); });

  function renderMdPane() {
    const f = curFile();
    if (!f) return;
    mdView.innerHTML = '';
    const frag = document.createDocumentFragment();
    f.md.replace(/\n$/, '').split('\n').forEach((line, i) => {
      const d = el('span', 'ln' + (/^#/.test(line) ? ' h' : /^\[\^[^\]]+\]:/.test(line) ? ' def' : ''));
      d.dataset.n = i + 1;
      d.textContent = line || ' ';
      frag.appendChild(d);
    });
    mdView.appendChild(frag);
  }

  /* ---------------------------------------------------------- live word count */
  // Counted the way the build counts (filters/wordcount.lua): every word with a letter or digit in it, body and
  // footnotes separately, leaving out sections under a {.nocount} heading. Shown in the inspector as you type.
  function wordStats() {
    let body = 0, notes = 0;
    const words = s => (s.replace(/<!--[\s\S]*?-->/g, ' ').replace(/\[\^[^\]\s]+\]/g, ' ').replace(/\]\{[^}]*\}/g, ' ')
      .replace(/\]\([^)]*\)/g, ' ').replace(/<[^>]+>/g, ' ').replace(/\\(.)/g, '$1').replace(/[[\]*_`#>]/g, ' ')
      .match(/\S+/g) || []).filter(w => /[\p{L}\p{N}]/u.test(w)).length;
    W.files.forEach(f => {
      if (f.kind !== 'section') return;
      let skip = 0, inNote = false;
      f.md.split('\n').forEach(line => {
        const h = /^(#{1,6})\s.*?(\{[^}]*\})?\s*$/.exec(line);
        if (h) {
          if (skip && h[1].length <= skip) skip = 0;
          if (!skip && h[2] && /\.nocount\b/.test(h[2])) skip = h[1].length;
        }
        if (skip) return;
        if (/^\[\^[^\]\s]+\]:/.test(line)) { inNote = true; notes += words(line.replace(/^\[\^[^\]\s]+\]:/, '')); return; }
        if (inNote && (/^( {4}|\t)/.test(line) || !line.trim())) { notes += words(line); return; }
        inNote = false;
        body += words(line);
      });
    });
    return { body, notes, limit: (W.tmpl && W.tmpl.word_limit) || 0 };
  }

  /* ---------------------------------------------------------- git status / versions */

  function applyStatus(s) {
    if (!s) return;
    W.status = s;
    // versions are saved snapshots, so they exist with or without git; only the "uncommitted" count needs it
    $('#version-info').textContent = (s.lastTag ? 'Last version ' + s.lastTag : 'No versions yet') +
      (s.repo && s.dirty ? ' \u00b7 ' + s.dirty + ' uncommitted file' + (s.dirty === 1 ? '' : 's') : '');
  }

  $('#btn-tag').onclick = async () => {
    if (running || !W.info) return;
    const name = prompt('Name this version of “' + W.info.title + '”.\nIt saves your current draft and becomes the baseline for the next redline.', (W.status && W.status.nextTag) || 'v0.1');
    if (!name) return;
    await saver.flush(false);
    try {
      const r = await post('/api/tag', { doc: W.info.slug, name: name.trim() });
      applyStatus(r.status);
      toast('Tagged ' + r.tag + '. Redlines for this document will now compare against it.');
    } catch (e) { toast(e.message, true); }
  };

  /* ---------------------------------------------------------- right pane tabs */

  function showTab(name) {
    $$('#tabs .tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    ['md', 'pdf', 'log'].forEach(n => { $('#tab-' + n).hidden = n !== name; });
    if (name === 'pdf' && window.PDFView) PDFView.refresh();
  }
  $$('#tabs .tab').forEach(t => t.onclick = () => showTab(t.dataset.tab));

  /* ---------------------------------------------------------- Run */

  const logView = $('#log-view');
  let logCount = 0;

  function appendLog(lines) {
    if (!lines.length) return;
    const atEnd = logView.scrollHeight - logView.scrollTop - logView.clientHeight < 40;
    lines.forEach(l => {
      const s = el('div', /^ERROR/.test(l) ? 'err' : /^\$ /.test(l) ? 'cmd' : /^== /.test(l) ? 'sec' : '', l);
      logView.appendChild(s);
    });
    if (atEnd) logView.scrollTop = logView.scrollHeight;
  }

  function setRunning(on, step) {
    running = on;
    $('#btn-run').disabled = on;
    $('#btn-save .lbl').textContent = on ? 'Saving…' : 'Save';
    $('#run-step').innerHTML = on ? '<span class="spinner"></span>' + (step || 'Working') : '';
    if (App.saveProgress) App.saveProgress(on, step);
  }

  async function poll(fresh) {
    if (fresh) { logView.innerHTML = ''; logCount = 0; }
    setRunning(true);
    for (;;) {
      let s;
      try { s = await api('/api/job?since=' + logCount); }
      catch (e) { await new Promise(r => setTimeout(r, 1000)); continue; }
      logCount = s.next;
      appendLog(s.lines);
      setRunning(true, s.step);
      if (s.done) { finishRun(s); return; }
      await new Promise(r => setTimeout(r, 600));
    }
  }

  function finishRun(s) {
    setRunning(false);
    if (App.saveProgress) App.saveProgress(false, null, s);
    if (App.afterRun) App.afterRun();
    if (W.info) api('/api/status?doc=' + encodeURIComponent(W.info.slug)).then(applyStatus).catch(() => {});
    const here = W.info && s.doc === W.info.slug;
    if (here && s.words) {
      const m = /=\s*([\d,]+)\s+total/.exec(s.words);
      const limit = W.tmpl && W.tmpl.word_limit;
      $('#wordcount').textContent = s.words.replace(/^Words:\s*/, '') + (limit && m ? ' (limit ' + limit.toLocaleString() + ')' : '');
    }
    if (!s.ok) {
      if (here) showTab('log');
      toast('Saved, but the build failed: ' + s.message, true);
      if (App.sync && App.git.project && App.git.project.remote) App.sync('save', true);   // still get the work to GitHub
      return;
    }
    const sy = s.sync;
    if (here) {
      renderOutputs(s.outputs); showTab('pdf');
      toast(sy && !sy.ok ? 'Saved and built, but not synced: ' + sy.message : 'Saved' + (sy ? ' and synced' : '') + '. ' + (s.words || ''), !!(sy && !sy.ok && !/offline|reach/i.test(sy.message)));
    } else toast('Finished building “' + s.doc + '”.');
    // GitHub had changes for this computer: show them (the open document may be one of them), and any clashes
    if (sy && sy.changed && App.reloadAll) App.reloadAll();
    if (sy && sy.conflicts && App.showConflicts) App.showConflicts();
  }

  function clearPreview() {
    previewSel = null;
    $('#pdf-bar').innerHTML = '';
    $('#pdf-frame').removeAttribute('src');
    $('#pdf-view').hidden = true; $('#pdf-frame').hidden = true;
    $('#pdf-empty').hidden = false;
  }

  let previewSel = null;
  const buildUrl = n => '/build/' + n.split('/').map(encodeURIComponent).join('/');

  function loadPreview() {
    if (!previewSel) return;
    const name = previewSel.value;
    const isPdf = /\.pdf$/i.test(name);
    $('#pdf-view').hidden = !isPdf;
    $('#pdf-frame').hidden = isPdf;
    if (isPdf) {
      if (!window.PDFView) { setTimeout(loadPreview, 150); return; }     // the viewer module is still loading
      PDFView.setZoom($('#view-zoom').value);
      PDFView.open(buildUrl(name) + '?t=' + Date.now());
    } else {
      $('#pdf-frame').src = buildUrl(name) + '?t=' + Date.now();          // HTML and text files
    }
  }
  App.reloadPreview = loadPreview;
  App.openPreviewInTab = () => { if (previewSel) window.open(buildUrl(previewSel.value) + App.previewFragment(), '_blank'); else toast('Nothing to preview yet. Press Save (⌘S).', true); };
  App.showPreview = () => showTab('pdf');

  function renderOutputs(outputs) {
    const bar = $('#pdf-bar'); bar.innerHTML = '';
    const viewable = outputs.filter(o => ['pdf', 'html', 'txt'].includes(o.kind));
    if (!viewable.length) { previewSel = null; clearPreview(); if (outputs.length) addDownloads(bar, outputs); return; }
    $('#pdf-empty').hidden = true;
    const sel = el('select');
    viewable.forEach(o => {
      const op = el('option', '', o.label + (viewable.filter(v => v.label === o.label).length > 1 ? ' (' + o.kind.toUpperCase() + ')' : ''));
      op.value = o.name; sel.appendChild(op);
    });
    previewSel = sel;
    sel.onchange = loadPreview;
    bar.append('Viewing: ', sel, el('span', 'spacer'));
    addDownloads(bar, outputs);
    loadPreview();
  }
  // The finished files: one Download menu instead of a row of links (the links stay, hidden, for the inspector)
  function addDownloads(bar, outputs) {
    const files = el('span', 'pdf-files');
    const kind = o => (o.kind === 'docx' ? 'Word' : o.kind === 'txt' ? 'text' : o.kind.toUpperCase());
    outputs.forEach(o => {
      const a = el('a', '', '⬇ ' + o.label + ' (' + kind(o) + ')');
      a.href = '/build/' + o.name.split('/').map(encodeURIComponent).join('/') + '?download=1';
      files.appendChild(a);
    });
    const b = el('button', 'btn small pdf-dl', 'Download ▾'); b.type = 'button';
    b.title = 'Save a copy of the finished files (they are also in outputs/ in your data folder)';
    b.onclick = () => {
      const r = b.getBoundingClientRect(), links = Array.from(files.children);
      const items = [];
      outputs.forEach((o, k) => {
        if (k && o.label !== outputs[k - 1].label) items.push('-');
        items.push({ label: o.label + ' · ' + kind(o), icon: o.kind === 'pdf' ? 'doc' : 'save', run: () => links[k].click() });
      });
      items.push('-', { label: 'Show the Finished Files in Finder', icon: 'folder', run: () => App.cmd.global.openOutput() });
      App.menu.open(r.left, r.bottom + 4, items);
    };
    bar.append(b, files);
  }

  $('#btn-run').onclick = () => runAll();
  async function runAll() {
    if (running || !W.info) return;
    if (!(await saver.flush(false))) { toast('Fix the save problem first, then press Save.', true); return; }
    try { await post('/api/run', { doc: W.info.slug }); } catch (e) { toast(e.message, true); return; }
    poll(true);
  }

  /* ---------------------------------------------------------- view hooks */

  App.views.writing = {
    newDoc: openNewDoc,
    async reload() { await refreshDocs(); if (W.info) await openDoc(W.info.slug, W.cur); else await this.show(); },
    setEditMode(m) {
      const f = curFile();
      if (f && f.kind === 'section') {
        if (m === 'md') {                       // from the rich editor to Markdown (what was typed there, if anything)
          if (edited) {
            const bodies = new Map(); noteEls.forEach((n, l) => bodies.set(l, n.querySelector('.note-body')));
            const md = MD.exportMd(doc, bodies, W.orphans, { split: splitLines() });
            if (md !== f.md) { f.md = md; saver.touch(); }
          }
          docMd.value = f.md;
        } else if (docMd.value !== f.md) {      // back: show what was typed
          f.md = docMd.value; saver.touch();
        }
        if (m !== 'md') renderRich(f);
        renderMdPane();
      }
      showEditMode();
      if (f && f.kind === 'section') (m === 'md' ? docMd : doc).focus();
    },
    open: slug => openDoc(slug),
    // "Cited in" (citations.js): open the document at that section and show the citation there.
    async reveal(u) {
      await App.showView('writing');
      if (!W.info || W.info.slug !== u.slug) await openDoc(u.slug, u.file);
      else if (W.cur !== u.file) selectFile(u.file);
      if (!W.info || W.info.slug !== u.slug || W.cur !== u.file) return;
      if ($('#view-writing').classList.contains('layout-preview')) { const b = $('[data-layout="split"]'); if (b) b.click(); }
      const ok = App.editMode === 'md' ? App.chips.revealText(docMd, u)
        : App.chips.reveal(u.where === 'footnote' ? (noteEls.get(u.label) || doc).querySelector('.note-body') || doc : doc, u);
      if (!ok) toast('That citation isn’t there any more (it may have been edited since).', true);
    },
    runAll: () => runAll(),
    info: () => W.info,
    words: () => (W.info ? wordStats() : null),
    outputs: () => W.outputs || [],
    status: () => W.status,
    showLog: () => showTab('log'),
    current: () => (W.info ? W.info.slug : null),
    // for the right-click menu (contextmenu.js)
    rename: slug => { const d = App.state.documents.find(x => x.slug === slug); if (d) renameDoc(d); },
    remove: slug => { const d = App.state.documents.find(x => x.slug === slug); if (d) deleteDoc(d); },
    move: (slug, pid) => moveDoc('doc:' + slug, pid),
    sections: () => W.files.map(f => ({ file: f.file, kind: f.kind, title: titleOf(f) })),
    multiSection: () => !!(W.tmpl && W.tmpl.multi_section),
    headingScheme: () => (W.tmpl && W.tmpl.heading_scheme) || 'none',
    selectSection: file => selectFile(file),
    moveSection: (file, dir) => { const f = W.files.find(x => x.file === file); if (f) moveSection(f, dir); },
    removeSection: file => { const f = W.files.find(x => x.file === file); if (f) deleteSection(f); },
    addSection: () => { if (W.info && W.tmpl.multi_section) addSection(); },
    async show() {
      try { await refreshDocs(); } catch (e) { toast('Couldn’t load documents: ' + e.message, true); return; }
      if (W.info && !App.state.documents.find(d => d.slug === W.info.slug)) { W.info = null; }
      if (!W.info) {
        let last = null;
        try { last = localStorage.getItem('lastDoc'); } catch (e) { /* ignore */ }
        const pick = App.state.documents.find(d => d.slug === last) || App.state.documents[0];
        if (pick) await openDoc(pick.slug); else showEmpty(true);
      }
      renderTree();
    },
    afterSave() { renderTree(); },
    async resumeJob() {
      const job = await api('/api/job?since=0');
      if (job.running) poll(true);
    },
  };
})();
