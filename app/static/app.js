/* App core: helpers, the shared save manager, view switching, and the citation picker.
 * The views (writing.js, research.js, citations.js) register things to save with
 * App.saver, so autosave and the Save button behave the same everywhere.
 */
(function () {
  'use strict';
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  async function api(path, opts) {
    opts = opts || {};
    const r = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
    let j = {};
    try { j = await r.json(); } catch (e) { /* not json */ }
    if (!r.ok) { const err = new Error(j.error || r.statusText); err.status = r.status; err.data = j; throw err; }
    return j;
  }
  const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body || {}) });
  const put = (path, body) => api(path, { method: 'PUT', body: JSON.stringify(body || {}) });

  let toastTimer;
  function toast(msg, bad) {
    const t = $('#toast');
    t.textContent = msg; t.className = bad ? 'bad' : ''; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 7000 : 3500);
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* ---------------------------------------------------------- save manager */
  // item = { title, get(): string, saved: string, save(value, force): Promise, keepalive?(value): {url, body} }
  const saver = {
    items: new Map(),
    syncs: new Set(),
    timer: null,
    running: null,
    lastSaved: '',
    register(key, item) { this.items.set(key, item); },
    unregister(key) { this.items.delete(key); },
    sync() { this.syncs.forEach(fn => fn()); },
    dirtyItems() { return Array.from(this.items.values()).filter(i => i.get() !== i.saved); },
    isDirty() { return this.dirtyItems().length > 0; },
    touch() {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.flush(false), 1500);
      this.status();
    },
    status(text) {
      const e = $('#save-status');
      if (text) { e.textContent = text; return; }
      e.textContent = this.isDirty() ? 'Unsaved changes…' : (this.lastSaved ? 'Saved ' + this.lastSaved : 'All saved');
    },
    async flush(manual) {
      clearTimeout(this.timer);
      this.sync();
      if (this.running) await this.running;
      const dirty = this.dirtyItems();
      if (!dirty.length) { if (manual) { this.status(); toast('Already saved.'); } return true; }
      this.running = (async () => {
        this.status('Saving…');
        for (const item of dirty) {
          const sent = item.get();
          try {
            await item.save(sent, false);
            item.saved = sent;
          } catch (e) {
            if (e.status === 409) {
              if (confirm('“' + item.title() + '” was changed outside this app since you opened it (another editor, or git).\n\nOverwrite it with what’s here?')) {
                try { await item.save(sent, true); item.saved = sent; }
                catch (e2) { this.status('Save failed'); toast('Couldn’t save: ' + e2.message, true); return; }
              } else { this.status('Not saved: file changed on disk'); return; }
            } else { this.status('Save failed'); toast('Couldn’t save: ' + e.message, true); return; }
          }
        }
        this.lastSaved = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
        this.status();
        Object.values(App.views).forEach(v => v.afterSave && v.afterSave());
      })();
      try { await this.running; } finally { this.running = null; }
      return !this.isDirty();
    },
  };

  window.addEventListener('beforeunload', () => {
    saver.sync();
    saver.dirtyItems().forEach(i => {
      if (!i.keepalive) return;
      const k = i.keepalive(i.get());
      fetch(k.url, { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(k.body) });
    });
  });
  document.addEventListener('keydown', e => {
    // ⌘S only: ⌃⌘S (new section) and ⌥⌘S (sidebar) are other shortcuts (shortcuts.js)
    if ((e.metaKey || e.ctrlKey) && !(e.metaKey && e.ctrlKey) && !e.altKey && e.code === 'KeyS') { e.preventDefault(); window.App.saveAll(); }
  });
  $('#btn-save').onclick = () => window.App.saveAll();
  $('#btn-save-side').onclick = () => window.App.saveAll();        // Save outside Writing lives by the save status

  /* ---------------------------------------------------------- views */
  const App = window.App = {
    $, $$, el, api, post, put, toast, saver,
    // Save (button or ⌘S) does everything: save, and in Writing build the open document, copy its finished
    // files into outputs/ and sync with GitHub (the Run pipeline does all three); elsewhere save and sync.
    async saveAll() {
      if (!(await saver.flush(true))) return;
      const w = App.views.writing;
      if (App.view === 'writing' && w && w.current() && w.runAll) { w.runAll(); return; }
      if (App.sync && App.git && App.git.project && App.git.project.remote) App.sync('save', false);
    },
    esc: s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
    state: { templates: [], documents: [], citations: [], citeTypes: [], status: null },
    views: {},
    view: 'writing',
  };

  App.showView = async function (name) {
    if (name === App.view && !App._first) return;
    App._first = false;
    await saver.flush(false);
    App.view = name;
    $$('#nav button').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    ['writing', 'research', 'citations', 'verify'].forEach(v => { $('#view-' + v).hidden = v !== name; });
    $$('.writing-only').forEach(e => { e.style.display = name === 'writing' ? '' : 'none'; });
    if (App.ribbon) App.ribbon.refresh();
    const v = App.views[name];
    if (v && v.show) v.show();
  };
  $$('#nav button').forEach(b => b.onclick = () => App.showView(b.dataset.view));

  /* ---------------------------------------------------------- dialogs */
  $$('dialog [data-close]').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
  $$('dialog').forEach(d => d.addEventListener('mousedown', e => { if (e.target === d) d.close(); }));
  App.openDialog = d => { if (!d.open) d.showModal(); };

  /* ---------------------------------------------------------- shared data */
  App.loadCitations = async function () {
    const r = await api('/api/citations');
    App.state.citations = r.citations;
    App.state.citeTypes = r.types;
    App.state.citeSchema = r.schema || { types: {}, groups: [] };
    App.state.citationsLoaded = true;
    return r.citations;
  };
  App.citation = tag => App.state.citations.find(c => c.tag === tag);
  App.uniqueTag = function (base) {
    const taken = new Set(App.state.citations.map(c => c.tag));
    let t = base, i = 2;
    while (taken.has(t)) t = base + '-' + i++;
    return t;
  };
  App.suggestTag = function (citeMd, style) {
    const plain = (citeMd || '').replace(/\\(.)/g, '$1').replace(/\]\{\.smallcaps\}|[*_\[\]]/g, '');
    if (style === 'apa') {      // "Walker, M. (2017)." -> walker-2017
      const m = /^([^,(.]+)[\s\S]*?\((\d{4}|n\.d\.)/.exec(plain);
      if (m) return (m[1].trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 30) + '-' + m[2].replace(/\W/g, '')).replace(/^-/, '');
    }
    const head = plain.split(',')[0].toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40).replace(/-+$/, '');
    return head || 'source';
  };

  /* ---------------------------------------------------------- citation picker
   * App.pickCitation({ title, pickOnly, format, onPick(cite, which) })
   *   format: 'lawreview' | 'practitioner' | 'apa' | 'chicago' | 'chicago-ad' (how cites are shown, and which buttons appear)
   *   which:  'full' | 'short' (Bluebook, Chicago notes) or 'intext' | 'narrative' | 'reference' (APA, Chicago author-date), or 'pick'
   * Used to insert a cite in Writing/Research, and to choose a source for a note.
   * With multi: checkboxes and onPickMany(cites, { fromNotes }); chosen = tags ticked at the start, addLabel = the
   * button's verb ("Add"), notesOption: false hides "Start each annotation from my research notes". */
  const dlg = $('#dlg-cite');
  const cpSearch = $('#cp-search');
  const cpFormat = $('#cp-style');
  // which sources: the document's (or note's) project, or all of them
  const cpScope = el('select'); cpScope.title = 'Which sources to show';
  cpFormat.after(cpScope);
  cpScope.addEventListener('change', () => renderPicker());
  let cpOpts = null;

  // Which citation style a template uses: APA, Chicago (notes, or author-date), or Bluebook in law review or
  // practitioner type. Templates with "cite_style": "document" (the annotated bibliography) read
  // `citation-style:` from the document's details (apa · bluebook · bluebook-lawreview · chicago · chicago-author-date).
  App.citeFormat = function (t, metaMd) {
    if (t && t.cite_style === 'document') {
      const m = /^citation-style:\s*"?([\w-]+)/m.exec(metaMd || '');
      const v = m ? m[1].toLowerCase() : 'apa';
      if (v.startsWith('chicago')) return (v.includes('date') || v.endsWith('-ad')) ? 'chicago-ad' : 'chicago';
      return v.startsWith('bluebook') ? (v.includes('law') ? 'lawreview' : 'practitioner') : 'apa';
    }
    const cs = t && t.cite_style;
    if (cs === 'apa' || cs === 'chicago' || cs === 'chicago-ad') return cs;
    return (t && t.cite_typeface) || 'practitioner';
  };
  // Styles that cite in the text, in parentheses: (Walker, 2017) or (Walker 2017)
  App.isParenFormat = format => format === 'apa' || format === 'chicago-ad';

  // The form keys (citeformat.describe) for each style
  function formKey(which, format) {
    if (format === 'apa') return { intext: 'apa_intext', narrative: 'apa_narrative', reference: 'apa_reference' }[which] || 'apa_intext';
    if (format === 'chicago-ad') return { intext: 'chicago_ad_intext', narrative: 'chicago_ad_narrative', reference: 'chicago_ad_reference' }[which] || 'chicago_ad_intext';
    if (format === 'chicago') return { short: 'chicago_short', reference: 'chicago_bib' }[which] || 'chicago_note';
    const tf = format === 'lawreview' ? 'lawreview' : 'practitioner';
    if (which === 'intext') return 'apa_intext';
    if (which === 'narrative') return 'apa_narrative';
    if (which === 'reference') return 'apa_reference';
    return (which === 'short' ? 'short_' : 'bluebook_') + tf;
  }
  App.formKey = formKey;

  // The Markdown for one form of a citation (forms come from the server's formatter).
  App.citeMarkdown = function (c, which, format) {
    const f = c.forms || {};
    return (f[formKey(which, format)] || {}).md || c.cite || c.tag;
  };

  function renderPicker() {
    const list = $('#cp-list');
    list.innerHTML = '';
    const q = cpSearch.value.trim().toLowerCase();
    const format = cpFormat.value || 'practitioner';
    const shownKey = App.isParenFormat(format) ? formKey('reference', format) : formKey('full', format);
    const proj = cpScope.value;
    const items = App.state.citations.filter(c => (!proj || (c.projects || []).includes(proj)) && (!q ||
      (c.tag + ' ' + App.typeLabel(c.type) + ' ' + App.citeText(c) + ' ' + App.citeText(c, 'apa_reference')).toLowerCase().includes(q)));
    if (!items.length) {
      list.appendChild(el('div', 'empty', App.state.citations.length
        ? (cpScope.value ? 'No sources in this project match. Choose “All sources” to cite something new to it; it joins the project when you do.' : 'No citations match.')
        : 'Your library is empty. Add sources in the Citations tab (or create a research note).'));
      return;
    }
    items.forEach(c => {
      const row = el('div', 'cp-row');
      const main = el('div', 'cp-main');
      const meta = el('div', 'cp-meta');
      meta.append(el('span', 'chip', App.typeLabel(c.type)), el('code', '', c.tag));
      const cite = el('div', 'cp-cite'); cite.innerHTML = ((c.forms || {})[shownKey] || {}).html || '';
      main.append(meta, cite);
      const btns = el('div', 'cp-btns');
      const pick = (which) => { dlg.close(); cpOpts.onPick(c, which, format); };
      const btn = (label, which, primary, title) => {
        const b = el('button', 'btn small' + (primary ? ' primary' : ''), label); b.onclick = () => pick(which);
        if (title) b.title = title; btns.appendChild(b);
      };
      if (cpOpts.multi) {
        const cb = el('input'); cb.type = 'checkbox'; cb.checked = cpChosen.has(c.tag);
        cb.onchange = () => { if (cb.checked) cpChosen.add(c.tag); else cpChosen.delete(c.tag); cpCount(); };
        row.onclick = e => { if (e.target !== cb) { cb.checked = !cb.checked; cb.onchange(); } };
        row.insertBefore(cb, row.firstChild);
      } else if (cpOpts.pickOnly) btn('Choose', 'pick', true);
      else if (cpOpts.live && App.isParenFormat(format)) {
        btn('In-text', 'intext', true, App.citeText(c, formKey('intext', format)));
        btn('Narrative', 'narrative', false, App.citeText(c, formKey('narrative', format)));
      } else if (cpOpts.live) {
        btn('Insert', 'full', true, 'Inserted as a live citation: full in drafts, short forms and Id. in the final draft');
      } else if (App.isParenFormat(format)) {
        btn('In-text', 'intext', true, App.citeText(c, formKey('intext', format)));
        btn('Narrative', 'narrative', false, App.citeText(c, formKey('narrative', format)));
        btn('Reference entry', 'reference', false, 'For the References page');
      } else {
        btn('Full cite', 'full', true);
        btn('Short form', 'short', false, App.citeText(c, formKey('short', format)));
      }
      row.append(main, btns);
      list.appendChild(row);
    });
  }
  cpSearch.addEventListener('input', renderPicker);
  cpFormat.addEventListener('change', renderPicker);
  // multi-select (annotated bibliography): checkboxes and an "Add" button
  const cpChosen = new Set();
  const cpMulti = el('div', 'cp-multi'); cpMulti.hidden = true;
  const cpNotes = el('label', 'chip-check'); const cpNotesBox = el('input'); cpNotesBox.type = 'checkbox'; cpNotesBox.checked = true;
  cpNotes.append(cpNotesBox, ' Start each annotation from my research notes on that source');
  const cpAdd = el('button', 'btn primary', 'Add');
  cpAdd.onclick = () => {
    const tags = Array.from(cpChosen);
    if (!tags.length && !cpOpts.allowNone) return;
    dlg.close();
    cpOpts.onPickMany(tags.map(t => App.citation(t)).filter(Boolean), { fromNotes: cpNotesBox.checked });
  };
  cpMulti.append(cpNotes, cpAdd);
  $('#cp-list').after(cpMulti);
  function cpCount() {
    const verb = (cpOpts && cpOpts.addLabel) || 'Add', n = cpChosen.size;
    cpAdd.textContent = n ? verb + ' ' + n + ' source' + (n === 1 ? '' : 's') : verb;
    cpAdd.disabled = !n && !(cpOpts && cpOpts.allowNone);
  }
  App.pickCitation = async function (opts) {
    cpOpts = opts;
    try { await App.loadCitations(); } catch (e) { /* use what we have */ }
    $('#cp-title').textContent = opts.title || 'Insert a citation';
    cpSearch.value = '';
    cpFormat.value = opts.format || 'practitioner';
    cpChosen.clear(); (opts.chosen || []).forEach(t => { if (App.citation(t)) cpChosen.add(t); });
    cpMulti.hidden = !opts.multi; cpNotes.hidden = opts.notesOption === false; cpCount();
    // opened from a document or note in a project: start with that project's sources
    cpScope.innerHTML = '';
    const pid = opts.project && App.projects.get(opts.project) ? opts.project : '';
    if (pid) { const o = el('option', '', App.projects.name(pid) + ' sources'); o.value = pid; cpScope.appendChild(o); }
    const all = el('option', '', 'All sources'); all.value = ''; cpScope.appendChild(all);
    cpScope.hidden = !pid;
    const has = pid && App.state.citations.some(c => (c.projects || []).includes(pid));
    cpScope.value = has ? pid : '';
    renderPicker();
    App.openDialog(dlg);
    cpSearch.focus();
  };
})();
