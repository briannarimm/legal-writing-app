/* The Source panel in the Citations tab: the files attached to a citation (PDFs you add, snapshots of
 * web pages), shown in the reader (reader.js) with highlights and comments. Annotations are saved beside
 * the file in library/files/<tag>/<file>.annotations.json; the PDF itself is never changed. "Export
 * annotated" writes a copy with real PDF annotations (rwpdf, part of the Mac app).
 *
 *   App.sources.show(citation | null)
 *   App.cmd.citations: attachFile, snapshot, livePage, exportAnnotated, highlight
 */
(function () {
  'use strict';
  const { $, el, api, post, put, toast } = App;

  const work = $('#cite-work');
  const panel = $('#cite-source');
  const sel = $('#src-file');
  const view = $('#src-view');
  const list = $('#src-anns');
  const empty = $('#src-empty');
  const body = panel.querySelector('.src-body');
  let cur = null;           // the citation
  let files = [];
  let fileName = null;
  let annMtime = null;
  let reader = null;
  let saveTimer = null;
  let tools = {};

  function getReader() {
    if (!reader && window.Reader) {
      reader = new window.Reader(view, list, { onChange: anns => scheduleSave(anns) });
    }
    return reader;
  }

  function urlOf(c) { return (c && c.fields && c.fields.url) || ''; }

  async function show(c) {
    await flush();
    cur = c;
    work.classList.toggle('no-source', !c);
    if (!c) { if (reader) reader.close(); return; }
    await loadFiles();
  }

  async function loadFiles(pick) {
    if (!cur) return;
    let r;
    try { r = await api('/api/files?tag=' + encodeURIComponent(cur.tag)); } catch (e) { toast(e.message, true); return; }
    tools = r.tools || {};
    files = r.files;
    sel.innerHTML = '';
    files.forEach(f => {
      const o = el('option', '', f.name + (f.annotations ? '  (' + f.annotations + ')' : ''));
      o.value = f.name; sel.appendChild(o);
    });
    sel.hidden = !files.length;
    $('#src-export').disabled = !tools.rwpdf;
    if (!tools.rwpdf) $('#src-export').title = 'Exporting an annotated copy needs ReWord’s PDF helper, which is part of the Mac app';
    const keep = pick || (fileName && files.some(f => f.name === fileName) ? fileName : null) ||
      (files.find(f => f.kind === 'pdf' && !f.annotated) || files[0] || {}).name;
    if (!keep) { fileName = null; body.hidden = true; empty.hidden = false; $('#src-remove').disabled = true; if (reader) reader.close(); return; }
    sel.value = keep;
    await openFile(keep);
  }

  async function openFile(name) {
    await flush();
    fileName = name;
    const f = files.find(x => x.name === name);
    empty.hidden = true; body.hidden = false;
    $('#src-remove').disabled = false;
    if (!f || f.kind !== 'pdf') {
      if (reader) reader.close();
      view.innerHTML = '';
      const a = el('a', 'btn', 'Open ' + name); a.href = fileUrl(name) + '?download=1';
      const box = el('div', 'empty'); box.append(el('p', '', 'ReWord shows PDFs. Other files open in their own app.'), a);
      view.appendChild(box);
      return;
    }
    const ann = await api('/api/annotations?tag=' + encodeURIComponent(cur.tag) + '&name=' + encodeURIComponent(name));
    annMtime = ann.mtime;
    const r = getReader();
    if (!r) { setTimeout(() => openFile(name), 150); return; }      // the reader module is still loading
    try { await r.open(fileUrl(name) + '?t=' + Date.now(), ann.annotations); }
    catch (e) { view.textContent = ''; view.appendChild(el('div', 'empty', 'Couldn’t show this PDF: ' + e.message)); }
  }

  const fileUrl = name => '/files/' + encodeURIComponent(cur.tag) + '/' + encodeURIComponent(name);

  /* ------------------------------------------------------------ saving annotations */
  let pending = null;
  function scheduleSave(anns) {
    pending = { tag: cur.tag, name: fileName, anns: anns.map(a => Object.assign({}, a)) };
    clearTimeout(saveTimer);
    App.saver.status('Unsaved highlights…');
    saveTimer = setTimeout(flush, 800);
  }
  async function flush() {
    clearTimeout(saveTimer);
    if (!pending) return;
    const p = pending; pending = null;
    try {
      const r = await put('/api/annotations', { tag: p.tag, name: p.name, annotations: p.anns, mtime: annMtime, force: true });
      annMtime = r.mtime;
      p.anns.forEach(a => { delete a.dirty; });
      const opt = Array.from(sel.options).find(o => o.value === p.name);
      if (opt) opt.textContent = p.name + (r.count ? '  (' + r.count + ')' : '');
      App.saver.status('Saved ' + new Date().toLocaleTimeString());
    } catch (e) { toast('Couldn’t save the highlights: ' + e.message, true); }
  }
  App.saver.syncs.add(() => { flush(); });
  window.addEventListener('beforeunload', () => {
    if (!pending) return;
    fetch('/api/annotations', { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag: pending.tag, name: pending.name, annotations: pending.anns, force: true }) });
  });

  /* ------------------------------------------------------------ adding files */
  async function upload(fileList) {
    if (!cur) { toast('Choose a citation first.', true); return; }
    let last = null;
    for (const f of Array.from(fileList)) {
      if (f.size > 50e6 && !confirm(f.name + ' is ' + Math.round(f.size / 1e6) + ' MB. Large files make the GitHub repository slow, and GitHub refuses files over 100 MB. Attach it anyway?')) continue;
      toast('Attaching ' + f.name + '…');
      try {
        const r = await fetch('/api/attach?tag=' + encodeURIComponent(cur.tag) + '&name=' + encodeURIComponent(f.name),
          { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-ReWord': '1' }, body: f });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.statusText);
        last = j.name;
      } catch (e) { toast('Couldn’t attach ' + f.name + ': ' + e.message, true); }
    }
    if (last) { toast('Attached.'); await loadFiles(last); }
  }
  $('#src-attach').onclick = () => $('#src-input').click();
  $('#src-input').addEventListener('change', e => { upload(e.target.files); e.target.value = ''; });
  panel.addEventListener('dragover', e => { if (cur && Array.from(e.dataTransfer.types).includes('Files')) { e.preventDefault(); panel.classList.add('dragging'); } });
  panel.addEventListener('dragleave', e => { if (!panel.contains(e.relatedTarget)) panel.classList.remove('dragging'); });
  panel.addEventListener('drop', e => { e.preventDefault(); panel.classList.remove('dragging'); if (e.dataTransfer.files.length) upload(e.dataTransfer.files); });

  async function snapshot() {
    const url = urlOf(cur);
    if (!url) { toast('Add the web address (Link) to this citation first.', true); return; }
    const b = $('#src-snap'); b.disabled = true; const label = b.textContent; b.textContent = 'Saving page…';
    try {
      const r = await post('/api/snapshot', { tag: cur.tag, url });
      toast(r.how === 'webkit' ? 'Saved the page as a PDF.' : 'Saved the page’s text as a PDF (pictures aren’t included without the Mac app).');
      await loadFiles(r.name);
    } catch (e) { toast(e.message, true); }
    finally { b.disabled = false; b.textContent = label; }
  }
  $('#src-snap').onclick = snapshot;
  $('#src-live').onclick = () => { if (urlOf(cur)) window.open(urlOf(cur), '_blank'); else toast('Add the web address (Link) to this citation first.', true); };
  sel.addEventListener('change', () => openFile(sel.value));

  async function exportAnnotated() {
    if (!fileName) return;
    await flush();
    try {
      const r = await post('/api/annotations/export', { tag: cur.tag, name: fileName });
      toast('Saved ' + r.name + ' beside the original.');
      files = r.files;
      const a = document.createElement('a'); a.href = fileUrl(r.name) + '?download=1'; document.body.appendChild(a); a.click(); a.remove();
      await loadFiles(fileName);
    } catch (e) { toast(e.message, true); }
  }
  $('#src-export').onclick = exportAnnotated;
  $('#src-remove').onclick = async () => {
    if (!fileName || !confirm('Remove ' + fileName + ' from this source?\n\nIt moves to library/files/' + cur.tag + '/_trash with its highlights; nothing is deleted.')) return;
    await flush();
    try { await post('/api/file/delete', { tag: cur.tag, name: fileName }); fileName = null; await loadFiles(); } catch (e) { toast(e.message, true); }
  };
  $('#src-zoom-in').onclick = () => reader && reader.zoom(1);
  $('#src-zoom-out').onclick = () => reader && reader.zoom(-1);
  $('#src-zoom-fit').onclick = () => reader && reader.zoom(0);

  Object.assign(App.cmd.citations, {
    attachFile: () => $('#src-attach').click(),
    snapshot,
    livePage: () => $('#src-live').click(),
    exportAnnotated,
    highlight: () => { if (!reader || !reader.highlight('yellow')) toast('Select some text in the document first.', true); },
    readerIn: () => reader && reader.zoom(1),
    readerOut: () => reader && reader.zoom(-1),
    readerFit: () => reader && reader.zoom(0),
    lookup: () => { const i = document.querySelector('#cite-form .lookup input'); if (i) { i.focus(); i.select(); } else toast('Open or start a citation first.', true); },
  });

  App.sources = { show, flush, reload: () => loadFiles(fileName) };
})();
