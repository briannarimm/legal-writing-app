/* Citations: the shared library, and the citation form (also used when creating a research note).
 * A citation is a source type plus structured fields (authors, title, reporter, court, date…). The
 * server formats it (app/citeformat.py) as Bluebook in law review and practitioner type and as APA 7,
 * so one entry works in every document. The form shows all of those forms live while you type.
 * Paste a DOI, ISBN or web address into "Look up" to fill the fields in from free public sources.
 */
(function () {
  'use strict';
  const { $, el, api, post, put, toast, saver } = App;

  const schema = () => App.state.citeSchema || { types: {}, groups: [] };
  App.typeLabel = t => ((schema().types[t] || {}).label || t);
  App.citeText = (c, form) => ((c.forms && c.forms[form || 'bluebook_practitioner']) || {}).text || c.tag;

  const slug = s => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  const plain = md => (md || '').replace(/\\(.)/g, '$1').replace(/\]\{\.smallcaps\}|[*_[\]]/g, '');

  // A tag suggestion from the fields: walker-2017, south-dakota-v-wayfair, 42-usc-1983 …
  function suggestTag(type, f) {
    const year = ((f.date || '').match(/\d{4}/) || [''])[0];
    const who = (f.authors || [])[0] || (f.editors || [])[0];
    let base = '';
    if (type === 'case') base = slug(plain(f.name)).replace(/-(inc|llc|co|corp|ltd)$/, '');
    else if (type === 'statute' || type === 'regulation') base = slug([f.title_no, f.code || (type === 'regulation' ? 'cfr' : ''), f.section].join(' '));
    else if (type === 'constitution') base = slug((f.jurisdiction || 'us') + ' const ' + (f.provision || ''));
    else if (type === 'rule') base = slug((f.source || '') + ' ' + (f.number || ''));
    else if (type === 'restatement') base = slug((f.title || '') + ' ' + (f.section || ''));
    else if (type === 'bill' || type === 'committee_report') base = slug((f.chamber || '') + ' ' + (f.number || '') + ' ' + (f.session || ''));
    else if (type === 'record') base = slug('record ' + (f.abbrev || ''));
    else if (who) base = slug(who.family || who.literal || who.given) + (year ? '-' + year : '');
    if (!base) base = slug(plain(f.title || f.text || f.book_title || '').split(/\s+/).slice(0, 4).join(' '));
    return (base || 'source').slice(0, 48).replace(/-+$/, '');
  }

  /* ------------------------------------------------------------ authors editor */
  function AuthorsField(f, fire) {
    const wrap = el('div', 'field wide');
    const head = el('div', 'field-head'); head.append(el('label', '', f.label.replace(/\*$/, '')));
    const rows = el('div', 'people');
    const actions = el('div', 'row');
    const addP = el('button', 'btn small', '+ Person'); addP.type = 'button';
    const addO = el('button', 'btn small', '+ Organization'); addO.type = 'button';
    actions.append(addP, addO);
    wrap.append(head, rows, actions);
    if (f.hint) wrap.appendChild(el('div', 'hint', f.hint));

    function row(p) {
      const r = el('div', 'person');
      const org = !!p.literal;
      const inputs = {};
      const mk = (k, ph, cls) => { const i = el('input', cls || ''); i.placeholder = ph; i.value = p[k] || ''; i.spellcheck = false; i.addEventListener('input', fire); inputs[k] = i; return i; };
      if (org) r.append(mk('literal', 'Organization name', 'grow'));
      else r.append(mk('given', 'First and middle names'), mk('family', 'Last name'), mk('suffix', 'Jr.', 'tiny'));
      const up = el('button', 'icon-btn', '↑'); up.type = 'button'; up.title = 'Move up';
      const rm = el('button', 'icon-btn', '✕'); rm.type = 'button'; rm.title = 'Remove';
      up.onclick = () => { if (r.previousSibling) { rows.insertBefore(r, r.previousSibling); fire(); } };
      rm.onclick = () => { r.remove(); fire(); };
      r.append(up, rm);
      r._get = () => { const o = {}; Object.keys(inputs).forEach(k => { const v = inputs[k].value.trim(); if (v) o[k] = v; }); return o; };
      r._focus = () => (inputs.given || inputs.literal).focus();
      return r;
    }
    addP.onclick = () => { const r = row({}); rows.appendChild(r); r._focus(); fire(); };
    addO.onclick = () => { const r = row({ literal: '' }); rows.appendChild(r); r._focus(); fire(); };
    return {
      el: wrap,
      get: () => Array.from(rows.children).map(r => r._get()).filter(o => Object.keys(o).length),
      set: v => { rows.innerHTML = ''; (Array.isArray(v) ? v : []).forEach(p => rows.appendChild(row(p))); },
    };
  }

  /* ------------------------------------------------------------ one field */
  function Field(f, fire) {
    const label = f.label.replace(/\*$/, '');
    const req = /\*$/.test(f.label);
    if (f.kind === 'authors') return AuthorsField(f, fire);
    if (f.kind === 'rich') {
      const r = Rich.inlineField(label + (req ? ' *' : ''), { hint: f.hint || '' });
      r.el.classList.add('wide');
      r.onInput(fire);
      return { el: r.el, get: r.get, set: v => r.set(v || '') };
    }
    const wrap = el('div', 'field');
    const head = el('div', 'field-head'); head.append(el('label', '', label + (req ? ' *' : '')));
    wrap.appendChild(head);
    let input;
    if (f.kind === 'select') {
      input = el('select');
      (f.options || []).forEach(o => { const op = el('option', '', o); op.value = o; input.appendChild(op); });
      input.addEventListener('change', fire);
    } else if (f.kind === 'bool') {
      const lab = el('label', 'check');
      input = el('input'); input.type = 'checkbox';
      input.addEventListener('change', fire);
      lab.append(input, ' ' + (f.hint || label));
      wrap.appendChild(lab);
      return { el: wrap, get: () => input.checked, set: v => { input.checked = v === undefined ? !!f.default : !!v; } };
    } else {
      input = el('input'); input.spellcheck = f.key === 'title_apa';
      input.addEventListener('input', fire);
      if (f.kind === 'date') input.placeholder = '2021 · June 23, 2021';
      if (f.key === 'url') { input.placeholder = 'https://…'; wrap.classList.add('wide'); }
    }
    wrap.appendChild(input);
    if (f.hint) wrap.appendChild(el('div', 'hint', f.hint));
    return { el: wrap, get: () => input.value, set: v => { input.value = v || (f.kind === 'select' && f.options ? f.options[0] : ''); } };
  }

  /* ------------------------------------------------------------ the form */
  App.CiteForm = function (opts) {
    const mode = (opts && opts.mode) || 'new';
    const root = el('div', 'cite-form');
    const listeners = [];
    let type = null, controls = {}, tagTouched = mode === 'edit', previewTimer = null;
    const fire = () => { listeners.forEach(f => f()); schedulePreview(); if (!tagTouched && type) tag.value = App.uniqueTag(suggestTag(type, collect())); };

    // Look up
    const look = el('div', 'lookup');
    const lookIn = el('input'); lookIn.placeholder = 'Paste a DOI, ISBN or web address to fill in the fields'; lookIn.spellcheck = false;
    const lookBtn = el('button', 'btn small', 'Look up'); lookBtn.type = 'button';
    const lookMsg = el('div', 'hint');
    look.append(el('div', 'lookup-row'), lookMsg);
    look.firstChild.append(lookIn, lookBtn);
    async function doLookup() {
      const q = lookIn.value.trim();
      if (!q) { lookIn.focus(); return; }
      lookBtn.disabled = true; lookMsg.textContent = 'Looking it up…'; lookMsg.className = 'hint';
      try {
        const r = await post('/api/lookup', { query: q });
        const keep = type ? collect() : {};
        setType(r.type);
        const fields = Object.assign({}, r.fields);
        Object.keys(keep).forEach(k => { if (!fields[k] && keep[k] && keep[k].length !== 0) fields[k] = keep[k]; });
        fill(fields);
        lookMsg.textContent = 'Filled in from ' + r.source + '. Check every field: lookups are often incomplete (Bluebook abbreviations, proper capitalization).';
        fire();
      } catch (e) { lookMsg.textContent = e.message; lookMsg.className = 'hint warn'; }
      finally { lookBtn.disabled = false; }
    }
    lookBtn.onclick = doLookup;
    lookIn.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); doLookup(); } });

    // Step 1: the kind of source
    const chooser = el('div', 'type-choice');
    chooser.appendChild(el('div', 'hint', 'What kind of source is it?'));
    schema().groups.forEach(gname => {
      const items = Object.entries(schema().types).filter(([, t]) => t.group === gname);
      if (!items.length) return;
      const grp = el('div', 'type-group');
      grp.appendChild(el('div', 'type-group-name', gname));
      const btns = el('div', 'type-btns');
      items.forEach(([id, t]) => {
        const b = el('button', 'type-btn', t.label); b.type = 'button';
        b.onclick = () => { setType(id); fire(); const first = fieldsBox.querySelector('input, [contenteditable]'); if (first) first.focus(); };
        btns.appendChild(b);
      });
      grp.appendChild(btns);
      chooser.appendChild(grp);
    });

    // Step 2: the fields
    const bar = el('div', 'style-bar');
    const typeSel = el('select');
    Object.entries(schema().types).forEach(([id, t]) => { const o = el('option', '', t.group + ' · ' + t.label); o.value = id; typeSel.appendChild(o); });
    typeSel.addEventListener('change', () => { const v = collect(); setType(typeSel.value); fill(v); fire(); });
    bar.append(el('span', 'muted small', 'Type'), typeSel);
    const fieldsBox = el('div', 'cf-grid');

    const tagWrap = el('div', 'field');
    const tagHead = el('div', 'field-head'); tagHead.append(el('label', '', 'Tag'));
    const tag = el('input'); tag.spellcheck = false; tag.placeholder = 'walker-2017';
    tagWrap.append(tagHead, tag, el('div', 'hint', mode === 'new'
      ? 'The name you pick this source by while writing. Lowercase letters, numbers and dashes. It can’t be changed later.'
      : 'The name you pick this source by while writing. It can’t be changed.'));
    if (mode === 'edit') tag.disabled = true;
    tag.addEventListener('input', () => { tagTouched = true; listeners.forEach(f => f()); });

    // Manual overrides, for the rare citation the rules don't produce correctly
    const over = el('details', 'overrides');
    over.appendChild(el('summary', '', 'Exceptions: type a citation by hand'));
    over.appendChild(el('div', 'hint', 'Only if the automatic form is wrong for this source. Anything typed here replaces the automatic version everywhere.'));
    const ovBB = Rich.inlineField('Bluebook full citation', {}); const ovShort = Rich.inlineField('Bluebook short form', {}); const ovAPA = Rich.inlineField('APA reference entry', {});
    [ovBB, ovShort, ovAPA].forEach(r => { r.onInput(fire); over.appendChild(r.el); });

    // Live preview
    const prev = el('div', 'cite-preview');
    const pinIn = el('input', 'pin-try'); pinIn.placeholder = 'Try a pin cite (page, §, ¶)';
    pinIn.addEventListener('input', () => schedulePreview());
    const prevBody = el('div', 'cp-forms');
    const prevHead = el('div', 'cp-head'); prevHead.append(el('b', '', 'How it will look'), pinIn);
    prev.append(prevHead, prevBody);

    // Projects this source belongs to. Citing it in a project's document or note adds that project
    // automatically (marked "auto"); you can add or remove projects here.
    let projs = mode === 'new' && App.projects.current() ? [App.projects.current()] : [];
    let projAuto = [];
    const projListeners = [];
    const projWrap = el('div', 'field proj-field');
    const projHead = el('div', 'field-head'); projHead.append(el('label', '', 'Projects'));
    const projBox = el('div', 'proj-chips');
    projWrap.append(projHead, projBox, el('div', 'hint', 'Citing this source in a project’s document or note adds it to that project automatically.'));
    function renderProjs() {
      projBox.innerHTML = '';
      projs.filter(id => App.projects.get(id)).forEach(id => {
        const chip = el('span', 'proj-chip');
        chip.append(App.projects.dot(id), el('span', '', App.projects.name(id)));
        if (projAuto.includes(id)) { const a = el('span', 'muted small', 'auto'); a.title = 'Added because it is cited in this project'; chip.appendChild(a); }
        const x = el('button', '', '×'); x.type = 'button'; x.title = 'Remove from this project';
        x.onclick = () => { projs = projs.filter(p => p !== id); projAuto = projAuto.filter(p => p !== id); renderProjs(); projListeners.forEach(f => f(projs)); };
        chip.appendChild(x);
        projBox.appendChild(chip);
      });
      const others = App.projects.list.filter(p => !projs.includes(p.id));
      if (others.length) {
        const add = el('select', 'proj-add');
        const o0 = el('option', '', '+ Add to project…'); o0.value = ''; add.appendChild(o0);
        others.forEach(p => { const o = el('option', '', p.name); o.value = p.id; add.appendChild(o); });
        add.onchange = () => { if (!add.value) return; projs = projs.concat([add.value]); renderProjs(); projListeners.forEach(f => f(projs)); };
        projBox.appendChild(add);
      } else if (!App.projects.list.length) {
        projBox.appendChild(el('span', 'muted small', 'No projects yet (Home → Projects).'));
      }
    }
    renderProjs();

    const step2 = el('div', 'cite-step2');
    step2.append(bar, fieldsBox, tagWrap, projWrap, over, prev);
    root.append(look, chooser, step2);

    function setType(t) {
      if (!schema().types[t]) t = 'other';
      type = t; typeSel.value = t;
      fieldsBox.innerHTML = ''; controls = {};
      schema().types[t].fields.forEach(f => { const c = Field(f, fire); controls[f.key] = c; fieldsBox.appendChild(c.el); });
      chooser.hidden = true; step2.hidden = false;
    }
    function collect() {
      const out = {};
      Object.entries(controls).forEach(([k, c]) => { const v = c.get(); if (v !== '' && v !== false && !(Array.isArray(v) && !v.length)) out[k] = v; });
      const o1 = ovBB.get(), o2 = ovShort.get(), o3 = ovAPA.get();
      if (o1) out._override_bluebook = o1; if (o2) out._override_short = o2; if (o3) out._override_apa = o3;
      return out;
    }
    function fill(fields) {
      Object.entries(controls).forEach(([k, c]) => c.set(fields[k]));
      ovBB.set(fields._override_bluebook || ''); ovShort.set(fields._override_short || ''); ovAPA.set(fields._override_apa || '');
      over.open = !!(fields._override_bluebook || fields._override_short || fields._override_apa);
    }

    const FORMS = [['bluebook_lawreview', 'Bluebook · law review footnote'], ['bluebook_practitioner', 'Bluebook · brief or memo'],
      ['short_lawreview', 'Short form · law review'], ['short_practitioner', 'Short form · brief or memo'],
      ['apa_reference', 'APA 7 · reference list'], ['apa_intext', 'APA 7 · in-text'], ['apa_narrative', 'APA 7 · narrative'],
      ['chicago_note', 'Chicago · note'], ['chicago_short', 'Chicago · shortened note'], ['chicago_bib', 'Chicago · bibliography'],
      ['chicago_ad_reference', 'Chicago author-date · reference list'], ['chicago_ad_intext', 'Chicago author-date · in-text']];
    function schedulePreview() {
      if (!type) return;
      clearTimeout(previewTimer);
      previewTimer = setTimeout(async () => {
        let r;
        try { r = await post('/api/citation/preview', { type, fields: collect(), pin: pinIn.value }); } catch (e) { return; }
        prevBody.innerHTML = '';
        if (r.missing && r.missing.length) prevBody.appendChild(el('div', 'hint warn', 'Still needed: ' + r.missing.join(', ')));
        if (r.chicago_missing && r.chicago_missing.length) prevBody.appendChild(el('div', 'hint', 'Chicago would also use: ' + r.chicago_missing.join(', ')));
        FORMS.forEach(([k, label]) => {
          const row = el('div', 'cp-form');
          const v = el('div', 'cp-cite'); v.innerHTML = (r.forms[k] || {}).html || '';
          row.append(el('div', 'cp-label', label), v);
          prevBody.appendChild(row);
        });
      }, 180);
    }

    if (mode === 'new' && opts && opts.type) setType(opts.type);
    else step2.hidden = true;

    return {
      el: root,
      get: () => Object.assign({ tag: tag.value.trim(), type, fields: type ? collect() : {} }, mode === 'new' ? { projects: projs } : {}),
      setProjects(list, auto) { projs = (list || []).slice(); projAuto = (auto || []).slice(); renderProjs(); },
      onProjects: f => projListeners.push(f),
      set(c) {
        setType(c.type || 'other');
        fill(c.fields || {});
        tag.value = c.tag || '';
        tagTouched = mode === 'edit' || !!c.tag;
        schedulePreview();
      },
      onChange: f => listeners.push(f),
      focus: () => (type ? (fieldsBox.querySelector('input, [contenteditable]') || tag) : lookIn).focus(),
      validate() {
        const v = this.get();
        if (!type) return 'Choose what kind of source it is first (or look it up).';
        if (!Object.keys(v.fields).length) return 'Fill in the citation first.';
        if (!/^[a-z0-9][a-z0-9-]{0,60}$/.test(v.tag)) return 'The tag can use lowercase letters, numbers and dashes (for example walker-2017).';
        if (mode === 'new' && App.citation(v.tag)) return 'A citation tagged “' + v.tag + '” already exists. Choose another tag.';
        return '';
      },
    };
  };

  /* ------------------------------------------------------------ the view */
  const list = $('#cite-list');
  const search = $('#ct-search');
  const filter = $('#ct-filter');
  const editor = $('#cite-work');
  const empty = $('#cite-empty');
  let selected = null;       // tag, or '' for none, or '+' for a new citation
  let form = null;
  let regKey = null;

  function renderFilter() {
    if (filter.options.length > 1) return;
    schema().groups.forEach(gname => {
      const og = document.createElement('optgroup'); og.label = gname;
      Object.entries(schema().types).filter(([, t]) => t.group === gname).forEach(([id, t]) => {
        const o = el('option', '', t.label); o.value = id; og.appendChild(o);
      });
      filter.appendChild(og);
    });
  }

  function renderList() {
    list.innerHTML = '';
    const q = search.value.trim().toLowerCase(), ft = filter.value;
    const items = App.state.citations.filter(c => App.projects.citeInScope(c) && (!ft || c.type === ft) &&
      (!q || (c.tag + ' ' + App.citeText(c) + ' ' + App.citeText(c, 'apa_reference')).toLowerCase().includes(q)));
    if (!items.length) {
      list.appendChild(el('div', 'empty small', App.state.citations.length ? (App.projects.scope === 'all' ? 'No citations match.' : 'No sources in this project match.') : 'No citations yet.'));
    }
    items.forEach(c => {
      const row = el('div', 'list-item' + (c.tag === selected ? ' active' : ''));
      row.dataset.tag = c.tag;
      const top = el('div', 'li-top'); top.append(el('span', 'chip', App.typeLabel(c.type)), el('code', '', c.tag));
      if (c.missing && c.missing.length) top.appendChild(el('span', 'warn small', '•'));
      const dots = el('span', 'proj-dots');
      (c.projects || []).filter(id => App.projects.get(id)).forEach(id => { const d = App.projects.dot(id); d.title = App.projects.name(id); dots.appendChild(d); });
      top.appendChild(dots);
      const body = el('div', 'li-body'); body.innerHTML = (c.forms.bluebook_practitioner || {}).html || '';
      row.append(top, body);
      row.onclick = () => select(c.tag);
      list.appendChild(row);
    });
  }
  search.addEventListener('input', renderList);
  filter.addEventListener('change', renderList);

  function clearEditor() {
    if (regKey) { saver.unregister(regKey); regKey = null; }
    $('#cite-form').innerHTML = '';
    $('#cite-actions').innerHTML = '';
    $('#cite-notes').innerHTML = '';
  }

  async function select(tag) {
    await saver.flush(false);
    clearEditor();
    selected = tag;
    if (!tag) { editor.hidden = true; empty.hidden = false; App.sources.show(null); renderList(); return; }
    editor.hidden = false; empty.hidden = true;

    if (tag === '+') {
      App.sources.show(null);
      $('#cite-heading').textContent = 'New citation';
      form = App.CiteForm({ mode: 'new' });
      $('#cite-form').appendChild(form.el);
      const err = el('div', 'error'); err.hidden = true;
      const create = el('button', 'btn primary', 'Create citation');
      const cancel = el('button', 'btn', 'Cancel');
      cancel.onclick = () => select('');
      create.onclick = async () => {
        const msg = form.validate();
        if (msg) { err.textContent = msg; err.hidden = false; return; }
        try {
          const c = await post('/api/citation/new', form.get());
          await App.loadCitations();
          toast('Added ' + c.tag + ' to your library.');
          select(c.tag);
        } catch (e) { err.textContent = e.message; err.hidden = false; }
      };
      $('#cite-actions').append(create, cancel);
      $('#cite-form').appendChild(err);
      form.focus();
      renderList();
      return;
    }

    const c = App.citation(tag);
    if (!c) { select(''); return; }
    $('#cite-heading').textContent = c.tag;
    App.sources.show(c);
    form = App.CiteForm({ mode: 'edit' });
    form.set(c);
    form.setProjects(c.projects, c.projects_auto);
    form.onProjects(async list => {
      try {
        const r = await post('/api/citation/projects', { tag: c.tag, projects: list });
        Object.assign(c, { projects: r.projects, projects_auto: r.projects_auto });
        renderList();
      } catch (e) { toast(e.message, true); }
    });
    $('#cite-form').appendChild(form.el);
    const snapshot = () => { const v = form.get(); return JSON.stringify({ type: v.type, fields: v.fields }); };
    const item = {
      title: () => c.tag, saved: snapshot(),
      get: () => snapshot(),
      save: async (value, force) => {
        const v = JSON.parse(value);
        const r = await put('/api/citation', Object.assign({ tag: c.tag }, v, { mtime: c.mtime, force }));
        Object.assign(c, r);
        renderList();
      },
      keepalive: value => ({ url: '/api/citation', body: Object.assign({ tag: c.tag }, JSON.parse(value), { mtime: c.mtime, force: true }) }),
    };
    regKey = 'cite:' + tag;
    saver.register(regKey, item);
    form.onChange(() => saver.touch());

    const del = el('button', 'btn small danger', 'Delete citation');
    del.onclick = () => deleteCitation(c.tag);
    $('#cite-actions').appendChild(del);
    renderLinkedNotes(c);
    renderList();
  }

  async function renderLinkedNotes(c) {
    const box = $('#cite-notes');
    box.innerHTML = '';
    box.appendChild(el('h3', '', 'Research notes about this source'));
    let notes = [];
    try { notes = (await api('/api/notes')).notes.filter(n => n.citation === c.tag); } catch (e) { /* ignore */ }
    if (selected !== c.tag) return;
    if (!notes.length) box.appendChild(el('div', 'muted small', 'None yet.'));
    notes.forEach(n => {
      const a = el('a', 'link-item', n.title);
      a.href = '#'; a.onclick = e => { e.preventDefault(); App.views.research.open(n.id); };
      box.appendChild(a);
    });
    const start = el('button', 'btn small', '+ Start a note about this source');
    start.onclick = () => startNote(c);
    box.appendChild(start);
  }

  async function startNote(c) {
    try {
      const n = await post('/api/note/new', { title: App.citeText(c).slice(0, 80) || c.tag, citation: c.tag, project: App.projects.current() });
      App.views.research.open(n.id);
    } catch (e) { toast(e.message, true); }
  }

  async function deleteCitation(tag) {
    if (!confirm('Delete the citation “' + tag + '”?\n\nText already written keeps its citations as typed. Notes linked to it will show the source as missing. The file moves to library/citations/_trash.')) return;
    if (selected === tag && regKey) { saver.unregister(regKey); regKey = null; }
    try { await post('/api/citation/delete', { tag }); } catch (e) { toast(e.message, true); return; }
    await App.loadCitations();
    toast('Deleted ' + tag + '.');
    if (selected === tag) select(''); else renderList();
  }

  $('#btn-newcite').onclick = () => select('+');
  App.projects.onChange(() => renderList());

  App.views.citations = {
    async show() {
      try { await App.loadCitations(); } catch (e) { toast('Couldn’t load citations: ' + e.message, true); }
      renderFilter();
      if (selected && selected !== '+' && !App.citation(selected)) selected = '';
      renderList();
      if (selected === null || selected === '') { editor.hidden = true; empty.hidden = false; }
    },
    open(tag) { return select(tag); },
    remove: tag => deleteCitation(tag),
    startNote: tag => { const c = App.citation(tag); if (c) startNote(c); },
    async reload() { await this.show(); if (selected && selected !== '+') await select(selected); },
    afterSave() { renderList(); },
    renderList() { renderList(); },
  };
})();
