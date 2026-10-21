/* The Verify tab: check every citation in a project against its source, one card at a time.
 *   Left: the citation in context (the text a footnote supports, the footnote or paragraph with the citation
 *   marked, its pinpoint). Right: the source's PDF or web-page snapshot in the reader, with highlights.
 *   Approve (A) or send back (F, with an optional reason); ← → move between cards. At the end, the summary
 *   lists what was sent back, and "Sent back" walks through just those to fix them.
 * Results are kept per project in projects/verification/<project>.json (store.verification); an approval stops
 * counting when the citation or the words before it change.
 *
 *   App.views.verify.show() / reload()
 */
(function () {
  'use strict';
  const { $, $$, el, api, post, put, toast } = App;

  const V = {
    pid: '', slug: '', items: [], mode: 'all',
    order: [], pos: 0,              // the cards in this pass (indexes into items) and where we are
    done: false,                    // showing the summary
    reader: null, tag: null, files: [], fileName: null, annMtime: null,
  };
  const remember = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { /* ignore */ } return null; };
  V.mode = remember('verifyMode') || 'all';

  const projSel = $('#vf-project'), docSel = $('#vf-doc');
  const work = $('#vf-work'), empty = $('#vf-empty'), card = $('#vf-card'), doneBox = $('#vf-done');

  /* ------------------------------------------------------------ loading */
  function fillProjects() {
    projSel.innerHTML = '';
    App.projects.list.forEach(p => { const o = el('option', '', p.name); o.value = p.id; projSel.appendChild(o); });
    const w = App.views.writing, info = w && w.info && w.info();
    const want = V.pid && App.projects.get(V.pid) ? V.pid : App.projects.current() || remember('verifyProject') || (info && info.project) || '';
    V.pid = App.projects.get(want) ? want : (App.projects.list[0] || {}).id || '';
    projSel.value = V.pid;
  }

  async function load(keepKey) {
    if (!V.pid) { V.items = []; render(); return; }
    let r;
    try { r = await api('/api/verify?project=' + encodeURIComponent(V.pid) + (V.slug ? '&doc=' + encodeURIComponent(V.slug) : '')); }
    catch (e) { toast('Couldn’t load the citations: ' + e.message, true); return; }
    V.items = r.items;
    docSel.innerHTML = '';
    const all = el('option', '', r.documents.length === 1 ? r.documents[0].title : 'All ' + r.documents.length + ' documents'); all.value = '';
    docSel.appendChild(all);
    if (r.documents.length > 1) r.documents.forEach(d => { const o = el('option', '', d.title); o.value = d.slug; docSel.appendChild(o); });
    if (V.slug && !r.documents.some(d => d.slug === V.slug)) V.slug = '';
    docSel.value = V.slug;
    docSel.hidden = r.documents.length < 2;
    makeOrder(keepKey);
    render();
  }

  // The cards in this pass. The list is fixed when the pass starts, so approving a card in "Not checked"
  // doesn't pull it out from under you.
  function makeOrder(keepKey) {
    const want = it => V.mode === 'todo' ? !it.status : V.mode === 'failed' ? it.status === 'failed' : true;
    V.order = V.items.map((it, i) => i).filter(i => want(V.items[i]));
    const at = keepKey ? V.order.findIndex(i => V.items[i].key === keepKey) : -1;
    V.pos = at >= 0 ? at : Math.min(V.pos, Math.max(0, V.order.length - 1));
    if (!keepKey) V.pos = 0;
    V.done = !V.order.length && V.items.length > 0;
  }

  const cur = () => (V.done || !V.order.length ? null : V.items[V.order[V.pos]]);
  const counts = () => {
    const c = { approved: 0, failed: 0, todo: 0 };
    V.items.forEach(it => { if (it.status === 'approved') c.approved++; else if (it.status === 'failed') c.failed++; else c.todo++; });
    return c;
  };

  /* ------------------------------------------------------------ drawing */
  function render() {
    $$('[data-vf-mode]').forEach(b => b.classList.toggle('active', b.dataset.vfMode === V.mode));
    renderSide();
    if (!App.projects.list.length || !V.pid) {
      work.hidden = true; empty.hidden = false;
      empty.innerHTML = '';
      empty.append(el('p', '', 'Verify works on a project: it walks through every citation in the project’s documents.'),
        el('p', 'muted small', 'Make a project (⌃⌘J) and put a document in it, then come back here.'));
      return;
    }
    if (!V.items.length) {
      work.hidden = true; empty.hidden = false;
      empty.innerHTML = '';
      empty.append(el('p', '', 'No citations to check in ' + (V.slug ? 'this document' : 'this project’s documents') + ' yet.'),
        el('p', 'muted small', 'Citations inserted with Cite… (⌃⌘C) show up here, one card each.'));
      return;
    }
    work.hidden = false; empty.hidden = true;
    renderProgress();
    if (V.done || !cur()) { card.hidden = true; doneBox.hidden = false; renderDone(); closeSource(); return; }
    card.hidden = false; doneBox.hidden = true;
    renderCard(cur());
  }

  function renderSide() {
    const c = counts();
    const tally = $('#vf-tally');
    tally.innerHTML = '';
    if (V.items.length) {
      const chip = (n, label, cls) => { const s = el('span', 'vf-chip ' + cls); s.append(el('b', '', String(n)), ' ' + label); return s; };
      tally.append(chip(c.approved, 'approved', 'ok'), chip(c.failed, 'sent back', 'bad'), chip(c.todo, 'to check', 'todo'));
    }
    const list = $('#vf-list');
    list.innerHTML = '';
    let lastDoc = null;
    const showing = cur();
    V.items.forEach((it, i) => {
      if (it.slug !== lastDoc && !V.slug) { list.appendChild(el('div', 'vf-doc-head', it.doc)); lastDoc = it.slug; }
      const row = el('button', 'vf-row' + (it === showing ? ' on' : '')); row.type = 'button';
      row.append(el('span', 'vf-dot ' + (it.status || 'todo')), el('span', 'vf-row-loc', where(it)), el('span', 'vf-row-text', it.text || it.tag));
      row.title = (it.status === 'failed' ? 'Sent back' + (it.reason ? ': ' + it.reason : '') : it.status === 'approved' ? 'Approved' : 'Not checked yet');
      row.onclick = () => jumpTo(i);
      list.appendChild(row);
    });
    const on = list.querySelector('.vf-row.on');
    if (on) on.scrollIntoView({ block: 'nearest' });
  }

  function renderProgress() {
    const bar = $('#vf-bar');
    bar.innerHTML = '';
    V.order.forEach((i, n) => {
      const it = V.items[i];
      const s = el('button', 'vf-seg ' + (it.status || 'todo') + (n === V.pos && !V.done ? ' on' : '')); s.type = 'button';
      s.title = where(it) + ' · ' + (it.text || it.tag);
      s.onclick = () => { V.done = false; V.pos = n; render(); };
      bar.appendChild(s);
    });
    const label = V.mode === 'failed' ? 'sent back' : V.mode === 'todo' ? 'not checked' : '';
    $('#vf-count').textContent = V.done ? 'Summary' : (V.pos + 1) + ' of ' + V.order.length + (label ? ' ' + label : '');
  }

  const where = it => (it.where === 'footnote' ? (it.number ? 'n.' + it.number : 'Footnote') : it.section || 'Text');

  // Plain words with the citation marked, trimmed to a readable length around it.
  function quote(box, before, mid, after) {
    box.innerHTML = '';
    const b = before.length > 700 ? '…' + before.slice(-700).replace(/^\S*\s/, '') : before;
    const a = after.length > 400 ? after.slice(0, 400).replace(/\s\S*$/, '') + '…' : after;
    box.append(b ? b + (/^[.,;:)]/.test(mid.textContent || '') ? '' : ' ') : '', mid, a && !/^[.,;:)]/.test(a) ? ' ' + a : a);
  }

  // Where the last sentence of some text starts (after ". " and the like, not inside "v. " or "U.S. ").
  function lastSentence(text) {
    const re = /[.!?]["”’')\]]*\s+(?=["“‘(]?[A-Z])/g;
    let at = 0, m;
    while ((m = re.exec(text))) {
      if (m.index === text.length - 1) break;
      const word = text.slice(0, m.index + 1).split(/\s/).pop();
      if (/^(v|vs|U\.S|Inc|Co|Corp|No|Nos|Mr|Mrs|Ms|Dr|St|Id|id|e\.g|i\.e|cf|Cf|al|art|Art|sec|Sec|ch|Ch|App|Cir|Ct|Supp|Rev|L|J)\.$/.test(word) || /^[A-Z]\.$/.test(word)) continue;
      if (m.index + m[0].length < text.length) at = m.index + m[0].length;
    }
    return at;
  }

  function renderCard(it) {
    const loc = $('#vf-loc');
    loc.innerHTML = '';
    loc.append(el('b', '', it.doc), el('span', '', it.section),
      el('span', 'vf-where', it.where === 'footnote' ? (it.number ? 'Footnote ' + it.number : 'Footnote') : 'In the text'));
    const st = $('#vf-state');
    st.innerHTML = '';
    if (it.status === 'approved') st.appendChild(el('div', 'vf-badge ok', '✓ Approved' + (it.at ? ' ' + when(it.at) : '')));
    if (it.status === 'failed') {
      const b = el('div', 'vf-badge bad');
      b.append(el('b', '', '✕ Sent back' + (it.at ? ' ' + when(it.at) : '')), it.reason ? el('div', 'vf-why', it.reason) : '');
      if (it.edited) b.appendChild(el('div', 'vf-note', 'You’ve edited this citation since. Check it again, and approve it if it’s fixed.'));
      st.appendChild(b);
    }
    if (it.was === 'approved') st.appendChild(el('div', 'vf-badge warn', 'You approved this before, but the citation or the text before it has changed since. Check it again.'));
    if (it.missing) st.appendChild(el('div', 'vf-badge bad', 'This source isn’t in your library any more (tag “' + it.tag + '”).'));

    const sup = it.supports;
    $('#vf-supports-box').hidden = !sup;
    if (sup) {
      // the sentence the footnote hangs on stands out from the rest of its paragraph
      const cut = lastSentence(sup[0]);
      const claim = el('span', 'vf-claim', sup[0].slice(cut));
      claim.appendChild(el('sup', 'vf-fn', String(it.number || '*')));
      quote($('#vf-supports'), sup[0].slice(0, cut).trimEnd(), claim, sup[1]);
    }
    $('#vf-cite-label').textContent = it.where === 'footnote' ? 'The footnote' : 'The citation in its paragraph';
    const m = el('mark');
    if (it.html) m.innerHTML = it.html; else m.textContent = it.text || it.tag;
    quote($('#vf-context'), it.before, m, it.after);

    const facts = $('#vf-facts');
    facts.innerHTML = '';
    const fact = (k, v, cls) => { if (!v) return; facts.append(el('dt', '', k), el('dd', cls || '', v)); };
    fact('Pinpoint', it.pin, 'vf-pin');
    fact('Signal', it.signal);
    fact('Parenthetical', it.paren);
    if (!it.pin && it.kind === 'cite') fact('Pinpoint', 'none given', 'muted');
    if (it.kind === 'auth') fact('Kind', 'typed citation (not linked to the library’s formatting)');

    const failBtn = $('#vf-fail'), okBtn = $('#vf-ok');
    failBtn.classList.toggle('on', it.status === 'failed');
    okBtn.classList.toggle('on', it.status === 'approved');
    $('#vf-prev').disabled = V.pos === 0;
    $('#vf-next').textContent = V.pos >= V.order.length - 1 ? 'Finish →' : 'Next →';
    hideReason();
    showSource(it.missing ? null : it.tag);
  }

  function when(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const today = new Date().toDateString() === d.toDateString();
    return today ? 'at ' + d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'on ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function renderDone() {
    const c = counts();
    doneBox.innerHTML = '';
    const head = el('div', 'vf-done-head');
    const all = c.todo === 0;
    head.append(el('h2', '', all ? (c.failed ? 'Every citation is checked' : 'Every citation checks out') : 'Summary'),
      el('p', 'muted', c.approved + ' approved · ' + c.failed + ' sent back · ' + c.todo + ' not checked yet' +
        ' (' + (V.slug ? 'this document' : App.projects.name(V.pid)) + ')'));
    const row = el('div', 'row');
    if (c.failed) { const b = el('button', 'btn primary', 'Fix the ' + c.failed + ' sent back'); b.onclick = () => setMode('failed'); row.appendChild(b); }
    if (c.todo) { const b = el('button', 'btn' + (c.failed ? '' : ' primary'), 'Check the ' + c.todo + ' left'); b.onclick = () => setMode('todo'); row.appendChild(b); }
    const again = el('button', 'btn', 'Go through all of them'); again.onclick = () => setMode('all'); row.appendChild(again);
    head.appendChild(row);
    doneBox.appendChild(head);
    const failed = V.items.filter(it => it.status === 'failed');
    if (!failed.length) return;
    doneBox.appendChild(el('h3', 'vf-sec', 'Sent back'));
    failed.forEach(it => {
      const r = el('div', 'vf-fail-row');
      const loc = el('div', 'uses-loc');
      loc.append(el('span', '', it.doc), el('span', 'uses-where', where(it) + (it.section && it.where === 'footnote' ? ' · ' + it.section : '')));
      if (it.edited) loc.appendChild(el('span', 'vf-edited', 'edited since'));
      const q = el('div', 'uses-quote');
      const m = el('mark'); if (it.html) m.innerHTML = it.html; else m.textContent = it.text || it.tag;
      q.append(m);
      r.append(loc, q, el('div', 'vf-why' + (it.reason ? '' : ' muted'), it.reason || 'No reason noted.'));
      const btns = el('div', 'row');
      const go = el('button', 'btn small', 'Go to it in the document'); go.onclick = () => goTo(it);
      const look = el('button', 'btn small', 'Look again'); look.onclick = () => { setMode('failed', it.key); };
      btns.append(go, look);
      r.appendChild(btns);
      doneBox.appendChild(r);
    });
  }

  /* ------------------------------------------------------------ the source (right side) */
  function getReader() {
    if (!V.reader && window.Reader) V.reader = new window.Reader($('#vf-view'), $('#vf-anns'), { onChange: anns => scheduleSave(anns) });
    return V.reader;
  }
  function closeSource() { flush(); if (V.reader) V.reader.close(); V.tag = null; }

  function renderSourceHead(tag) {
    const h = $('#vf-src-head');
    h.innerHTML = '';
    const c = tag && App.citation(tag);
    if (!c) { h.appendChild(el('div', 'muted', tag ? 'Source not found in the library.' : '')); return; }
    const top = el('div', 'vf-src-top');
    top.append(el('span', 'chip', App.typeLabel ? App.typeLabel(c.type) : c.type), el('code', '', c.tag));
    const full = el('div', 'vf-src-cite');
    full.innerHTML = ((c.forms || {}).bluebook_practitioner || (c.forms || {}).apa_reference || {}).html || App.esc(App.citeText ? App.citeText(c) : c.tag);
    h.append(top, full);
  }

  async function showSource(tag) {
    renderSourceHead(tag);
    if (tag === V.tag && V.fileName) return;          // same source as the last card: keep the page and the scroll
    await flush();
    V.tag = tag; V.fileName = null;
    if (!tag) { V.files = []; noFile(); return; }
    await loadFiles();
  }

  async function loadFiles(pick) {
    const tag = V.tag;
    let r;
    try { r = await api('/api/files?tag=' + encodeURIComponent(tag)); } catch (e) { toast(e.message, true); return; }
    if (tag !== V.tag) return;
    V.files = r.files;
    const sel = $('#vf-file');
    sel.innerHTML = '';
    V.files.forEach(f => { const o = el('option', '', f.name + (f.annotations ? '  (' + f.annotations + ')' : '')); o.value = f.name; sel.appendChild(o); });
    sel.hidden = !V.files.length;
    const keep = pick || (V.files.find(f => f.kind === 'pdf' && !f.annotated) || V.files[0] || {}).name;
    if (!keep) { noFile(); return; }
    sel.value = keep;
    await openFile(keep);
  }

  function noFile() {
    if (V.reader) V.reader.close();
    $('#vf-src-body').hidden = true;
    const box = $('#vf-src-empty');
    box.hidden = false; box.innerHTML = '';
    const c = V.tag && App.citation(V.tag);
    const url = c && c.fields && c.fields.url;
    if (!V.tag) { box.appendChild(el('p', '', 'There’s no source to show for this citation.')); return; }
    box.appendChild(el('p', '', 'No file for this source yet.'));
    box.appendChild(el('p', 'muted small', url ? 'Save a snapshot of its web page to read it here, or open the live page.' : 'Attach a PDF of it to read it here, or drop one on this side.'));
    if (url) { const a = el('a', 'vf-url', url); a.href = url; a.target = '_blank'; box.appendChild(a); }
  }

  const fileUrl = name => '/files/' + encodeURIComponent(V.tag) + '/' + encodeURIComponent(name);
  async function openFile(name) {
    await flush();
    V.fileName = name;
    const f = V.files.find(x => x.name === name);
    $('#vf-src-empty').hidden = true; $('#vf-src-body').hidden = false;
    const view = $('#vf-view');
    if (!f || f.kind !== 'pdf') {
      if (V.reader) V.reader.close();
      view.innerHTML = '';
      const a = el('a', 'btn', 'Open ' + name); a.href = fileUrl(name) + '?download=1';
      const box = el('div', 'empty'); box.append(el('p', '', 'ReWord shows PDFs. Other files open in their own app.'), a);
      view.appendChild(box);
      return;
    }
    const tag = V.tag;
    const ann = await api('/api/annotations?tag=' + encodeURIComponent(tag) + '&name=' + encodeURIComponent(name));
    if (tag !== V.tag || name !== V.fileName) return;
    V.annMtime = ann.mtime;
    const r = getReader();
    if (!r) { setTimeout(() => { if (tag === V.tag) openFile(name); }, 150); return; }      // the reader module is still loading
    try { await r.open(fileUrl(name) + '?t=' + Date.now(), ann.annotations); }
    catch (e) { view.textContent = ''; view.appendChild(el('div', 'empty', 'Couldn’t show this PDF: ' + e.message)); }
  }

  // highlights made while checking are saved like the ones in Citations
  let pending = null, saveTimer = null;
  function scheduleSave(anns) {
    pending = { tag: V.tag, name: V.fileName, anns: anns.map(a => Object.assign({}, a)) };
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flush, 800);
  }
  async function flush() {
    clearTimeout(saveTimer);
    if (!pending) return;
    const p = pending; pending = null;
    try { const r = await put('/api/annotations', { tag: p.tag, name: p.name, annotations: p.anns, mtime: V.annMtime, force: true }); V.annMtime = r.mtime; }
    catch (e) { toast('Couldn’t save the highlights: ' + e.message, true); }
  }
  App.saver.syncs.add(() => { flush(); });

  $('#vf-file').addEventListener('change', e => openFile(e.target.value));
  $('#vf-zoom-in').onclick = () => V.reader && V.reader.zoom(1);
  $('#vf-zoom-out').onclick = () => V.reader && V.reader.zoom(-1);
  $('#vf-zoom-fit').onclick = () => V.reader && V.reader.zoom(0);
  $('#vf-live').onclick = () => {
    const c = V.tag && App.citation(V.tag), url = c && c.fields && c.fields.url;
    if (url) window.open(url, '_blank'); else toast('This source has no web address. Add one in Citations.', true);
  };
  $('#vf-snap').onclick = async () => {
    const c = V.tag && App.citation(V.tag), url = c && c.fields && c.fields.url;
    if (!url) { toast('This source has no web address. Add one in Citations.', true); return; }
    const b = $('#vf-snap'); b.disabled = true; const label = b.textContent; b.textContent = 'Saving page…';
    try { const r = await post('/api/snapshot', { tag: V.tag, url }); toast('Saved the page as a PDF.'); await loadFiles(r.name); }
    catch (e) { toast(e.message, true); }
    finally { b.disabled = false; b.textContent = label; }
  };
  async function upload(list) {
    if (!V.tag) return;
    let last = null;
    for (const f of Array.from(list)) {
      try {
        const r = await fetch('/api/attach?tag=' + encodeURIComponent(V.tag) + '&name=' + encodeURIComponent(f.name),
          { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-ReWord': '1' }, body: f });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.statusText);
        last = j.name;
      } catch (e) { toast('Couldn’t attach ' + f.name + ': ' + e.message, true); }
    }
    if (last) { toast('Attached.'); await loadFiles(last); }
  }
  $('#vf-attach').onclick = () => { if (V.tag) $('#vf-input').click(); else toast('This citation has no source in the library.', true); };
  $('#vf-input').addEventListener('change', e => { upload(e.target.files); e.target.value = ''; });
  const right = $('.vf-right');
  right.addEventListener('dragover', e => { if (V.tag && Array.from(e.dataTransfer.types).includes('Files')) { e.preventDefault(); right.classList.add('dragging'); } });
  right.addEventListener('dragleave', e => { if (!right.contains(e.relatedTarget)) right.classList.remove('dragging'); });
  right.addEventListener('drop', e => { e.preventDefault(); right.classList.remove('dragging'); if (e.dataTransfer.files.length) upload(e.dataTransfer.files); });

  /* ------------------------------------------------------------ deciding */
  async function record(it, status, reason) {
    const before = { status: it.status, reason: it.reason, at: it.at, edited: it.edited, was: it.was };
    Object.assign(it, { status, reason: reason || '', at: new Date().toISOString(), edited: false });
    delete it.was;
    try {
      await put('/api/verify', { project: V.pid, key: it.key, status, reason: reason || '', sig: it.sig, tag: it.tag, doc: it.slug });
    } catch (e) {
      Object.assign(it, before);
      toast('Couldn’t save that: ' + e.message, true);
      render();
      return false;
    }
    return true;
  }

  async function approve() {
    const it = cur();
    if (!it) return;
    if (await record(it, 'approved')) advance();
  }

  function showReason() {
    const it = cur();
    if (!it) return;
    $('#vf-reason').hidden = false;
    const t = $('#vf-reason-text');
    t.value = it.status === 'failed' ? it.reason || '' : '';
    t.focus(); t.select();
  }
  function hideReason() { $('#vf-reason').hidden = true; }
  async function sendBack() {
    const it = cur();
    if (!it) return;
    const reason = $('#vf-reason-text').value.trim();
    hideReason();
    if (await record(it, 'failed', reason)) advance();
  }

  function advance() {
    if (V.pos < V.order.length - 1) { V.pos++; render(); return; }
    V.done = true; render();
  }
  function back() { if (V.done) { V.done = false; V.pos = V.order.length - 1; } else if (V.pos > 0) V.pos--; render(); }

  function jumpTo(i) {
    let n = V.order.indexOf(i);
    if (n < 0) { V.mode = 'all'; remember('verifyMode', 'all'); makeOrder(); n = V.order.indexOf(i); }
    V.done = false; V.pos = Math.max(0, n); render();
  }

  function setMode(mode, key) {
    V.mode = mode; remember('verifyMode', mode);
    makeOrder(key);
    if (key) V.pos = Math.max(0, V.order.findIndex(i => V.items[i].key === key));
    V.done = !V.order.length;
    render();
  }

  async function goTo(it) {
    V.lastKey = it.key;
    await App.views.writing.reveal({ slug: it.slug, file: it.file, tag: it.tag, where: it.where, label: it.label, k: it.k, start: it.start, end: it.end });
    const t = $('#toast');
    if (t.hidden || t.className !== 'bad') toast('Fix it here, then come back with ⌘4: Verify picks up where you left off.');
  }

  $('#vf-ok').onclick = approve;
  $('#vf-fail').onclick = showReason;
  $('#vf-reason-ok').onclick = sendBack;
  $('#vf-reason-cancel').onclick = hideReason;
  $('#vf-reason-text').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendBack(); }
    if (e.key === 'Escape') { e.preventDefault(); hideReason(); }
  });
  $('#vf-prev').onclick = back;
  $('#vf-next').onclick = advance;
  $('#vf-goto').onclick = () => { const it = cur(); if (it) goTo(it); };
  $('#vf-open-cite').onclick = async () => { const it = cur(); if (it && !it.missing) { await App.showView('citations'); App.views.citations.open(it.tag); } };
  $('#vf-summary-btn').onclick = () => { V.done = true; render(); };
  $('#vf-reset').onclick = async () => {
    const what = V.slug ? 'this document' : 'the project “' + App.projects.name(V.pid) + '”';
    if (!confirm('Start over on ' + what + '?\n\nEvery approval and every citation you sent back (with its reason) is forgotten.')) return;
    try { await post('/api/verify/reset', { project: V.pid, doc: V.slug }); } catch (e) { toast(e.message, true); return; }
    V.mode = 'all'; remember('verifyMode', 'all');
    await load();
  };
  $$('[data-vf-mode]').forEach(b => b.onclick = () => setMode(b.dataset.vfMode));
  projSel.onchange = async () => { V.pid = projSel.value; V.slug = ''; remember('verifyProject', V.pid); await flush(); V.tag = null; await load(); };
  docSel.onchange = async () => { V.slug = docSel.value; await load(); };

  // A approve, F send back, ← → move; only when not typing somewhere
  document.addEventListener('keydown', e => {
    if (App.view !== 'verify' || e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
    if (document.querySelector('dialog[open]')) return;
    const t = e.target;
    if (t && (t.closest('input, textarea, select, [contenteditable="true"]'))) return;
    if (work.hidden) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); if (!V.done) advance(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); back(); }
    else if (!cur()) return;
    else if (e.key === 'a' || e.key === 'A') { e.preventDefault(); approve(); }
    else if (e.key === 'f' || e.key === 'F') { e.preventDefault(); showReason(); }
  });

  App.projects.onChange(() => { if (App.view === 'verify') { const was = V.pid; fillProjects(); if (V.pid !== was) { V.slug = ''; load(); } } });

  App.views.verify = {
    async show() {
      fillProjects();
      const it = cur(), key = (it && it.key) || V.lastKey;
      V.lastKey = null;
      await load(key);                                // pick up edits made in Writing since, at the same card
    },
    async reload() { const it = cur(); await load(it && it.key); },
    afterSave() {},
  };
})();
