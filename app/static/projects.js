/* Projects: a grouping across Writing, Research and Citations.
 *   A document or note belongs to one project (or none); a citation to any number. Citing a source in a
 *   project's document or note adds it to that project automatically (add-only; the server does it).
 *   The switcher in the title bar picks what the tabs show: All projects (grouped under project
 *   headings), one project, or No project. New things are created in the current project.
 *
 *   App.projects.scope        'all' | 'none' | <project id>
 *   App.projects.inScope(pid) for a document or note
 *   App.projects.citeInScope(c)
 *   App.projects.group(items, pidOf)  -> [{id, name, color, items}] (All view)
 *   App.projects.heading(group, onDrop) a collapsible, droppable group heading
 *   App.projects.select(value, onChange) a Project menu
 *   App.projects.onChange(fn)  re-render when the scope or the project list changes
 */
(function () {
  'use strict';
  const { $, el, api, post, put, toast } = App;

  const P = App.projects = { list: [], colors: [], scope: 'all', listeners: [] };
  try { P.scope = localStorage.getItem('projectScope') || 'all'; } catch (e) { /* ignore */ }
  const collapsed = new Set();
  try { JSON.parse(localStorage.getItem('projectCollapsed') || '[]').forEach(x => collapsed.add(x)); } catch (e) { /* ignore */ }

  P.get = id => P.list.find(p => p.id === id) || null;
  P.name = id => (P.get(id) || {}).name || '';
  P.color = id => (P.get(id) || {}).color || '#9aa0a6';
  P.current = () => (P.scope !== 'all' && P.scope !== 'none' && P.get(P.scope)) ? P.scope : '';
  P.inScope = pid => P.scope === 'all' || (P.scope === 'none' ? !pid || !P.get(pid) : pid === P.scope);
  P.citeInScope = c => P.scope === 'all' || (P.scope === 'none' ? !(c.projects || []).some(x => P.get(x)) : (c.projects || []).includes(P.scope));
  P.onChange = fn => P.listeners.push(fn);
  const fire = () => { renderSwitcher(); P.listeners.forEach(fn => { try { fn(); } catch (e) { console.error(e); } }); };

  P.load = async function () {
    try { const r = await api('/api/projects'); P.list = r.projects; P.colors = r.colors; } catch (e) { /* keep what we have */ }
    if (P.scope !== 'all' && P.scope !== 'none' && !P.get(P.scope)) P.scope = 'all';
    fire();
  };
  P.setScope = function (s) {
    P.scope = s;
    try { localStorage.setItem('projectScope', s); } catch (e) { /* ignore */ }
    fire();
  };

  P.dot = id => { const d = el('span', 'proj-dot'); d.style.background = id ? P.color(id) : 'transparent'; if (!id) d.classList.add('none'); return d; };

  // Group items by project for the All view: projects in name order, then "No project".
  P.group = function (items, pidOf) {
    const out = P.list.map(p => ({ id: p.id, name: p.name, color: p.color, items: [] }));
    const none = { id: '', name: 'No project', color: '', items: [] };
    items.forEach(it => { const g = out.find(x => x.id === pidOf(it)); (g || none).items.push(it); });
    // every project gets a heading (so an empty one can be dropped onto); "No project" only when used
    return out.concat(none.items.length ? [none] : []);
  };

  // A group heading: click to fold; drop a document or note on it to move it into that project.
  P.heading = function (g, view, onDrop) {
    const key = view + ':' + (g.id || '_none');
    const h = el('div', 'proj-head' + (collapsed.has(key) ? ' folded' : ''));
    h.dataset.project = g.id;
    h.append(el('span', 'caret', collapsed.has(key) ? '▸' : '▾'), P.dot(g.id), el('span', 'proj-name', g.name), el('span', 'proj-count muted', String(g.items.length)));
    h.onclick = () => {
      if (collapsed.has(key)) collapsed.delete(key); else collapsed.add(key);
      try { localStorage.setItem('projectCollapsed', JSON.stringify(Array.from(collapsed))); } catch (e) { /* ignore */ }
      fire();
    };
    if (onDrop) {
      h.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('text/x-reword')) { e.preventDefault(); h.classList.add('drop'); } });
      h.addEventListener('dragleave', () => h.classList.remove('drop'));
      h.addEventListener('drop', e => { e.preventDefault(); h.classList.remove('drop'); const v = e.dataTransfer.getData('text/x-reword'); if (v) onDrop(v, g.id); });
    }
    return { el: h, folded: collapsed.has(key) };
  };
  P.draggable = (row, value) => {
    if (P.scope !== 'all') return;
    row.draggable = true;
    row.addEventListener('dragstart', e => { e.dataTransfer.setData('text/x-reword', value); e.dataTransfer.effectAllowed = 'move'; });
  };

  // A "Project" menu for a document or note.
  P.select = function (value, onChange) {
    const s = el('select', 'proj-select');
    const none = el('option', '', 'No project'); none.value = ''; s.appendChild(none);
    P.list.forEach(p => { const o = el('option', '', p.name); o.value = p.id; s.appendChild(o); });
    s.value = P.get(value) ? value : '';
    s.onchange = () => onChange(s.value);
    return s;
  };

  /* ------------------------------------------------------------ the switcher (title bar) */
  const sw = $('#project-switch');
  const swBtn = el('button', 'proj-btn'); swBtn.type = 'button'; swBtn.title = 'Which project to show (⌃⌘J to manage projects)';
  sw.appendChild(swBtn);
  let menu = null;
  function renderSwitcher() {
    swBtn.innerHTML = '';
    const label = P.scope === 'all' ? 'All projects' : P.scope === 'none' ? 'No project' : P.name(P.scope);
    swBtn.append(P.scope === 'all' ? el('span', 'proj-dot all') : P.dot(P.scope === 'none' ? '' : P.scope), el('span', 'proj-label', label), el('span', 'muted', '▾'));
  }
  function closeMenu() { if (menu) { menu.remove(); menu = null; } }
  swBtn.onclick = () => {
    if (menu) { closeMenu(); return; }
    menu = el('div', 'proj-menu');
    const item = (label, scope, dot) => {
      const b = el('button', 'proj-item' + (P.scope === scope ? ' on' : '')); b.type = 'button';
      b.append(dot, el('span', '', label));
      b.onclick = () => { closeMenu(); P.setScope(scope); };
      menu.appendChild(b);
    };
    item('All projects', 'all', el('span', 'proj-dot all'));
    P.list.forEach(p => item(p.name, p.id, P.dot(p.id)));
    item('No project', 'none', P.dot(''));
    menu.appendChild(el('div', 'proj-sep'));
    const mg = el('button', 'proj-item'); mg.type = 'button'; mg.textContent = 'Manage projects…'; mg.onclick = () => { closeMenu(); P.manage(); };
    const nw = el('button', 'proj-item'); nw.type = 'button'; nw.textContent = 'New project…'; nw.onclick = () => { closeMenu(); P.manage('+'); };
    menu.append(mg, nw);
    document.body.appendChild(menu);
    const r = swBtn.getBoundingClientRect();
    menu.style.left = r.left + 'px'; menu.style.top = (r.bottom + 4) + 'px';
  };
  document.addEventListener('mousedown', e => { if (menu && !menu.contains(e.target) && !swBtn.contains(e.target)) closeMenu(); });

  /* ------------------------------------------------------------ the project manager */
  const dlg = el('dialog'); dlg.id = 'dlg-projects';
  document.body.appendChild(dlg);
  dlg.addEventListener('mousedown', e => { if (e.target === dlg) dlg.close(); });
  let editing = null;

  const STYLES = [['', 'Template default'], ['apa', 'APA 7th'], ['bluebook', 'Bluebook (briefs, memos)'], ['bluebook-lawreview', 'Bluebook (law review)'],
    ['chicago', 'Chicago (notes and bibliography)'], ['chicago-author-date', 'Chicago (author-date)']];
  function render() {
    dlg.innerHTML = '';
    dlg.appendChild(el('h2', '', 'Projects'));
    const wrap = el('div', 'pm-wrap');
    const side = el('div', 'pm-list');
    P.list.forEach(p => {
      const b = el('button', 'proj-item' + (editing === p.id ? ' on' : '')); b.type = 'button';
      b.append(P.dot(p.id), el('span', '', p.name));
      b.onclick = () => { editing = p.id; render(); };
      side.appendChild(b);
    });
    const add = el('button', 'btn small wide primary-soft', '+ New project'); add.type = 'button';
    add.onclick = () => { editing = '+'; render(); };
    side.appendChild(add);
    const form = el('div', 'pm-form');
    if (!editing) {
      form.appendChild(el('div', 'empty', P.list.length ? 'Choose a project to edit it.' : 'No projects yet. A project groups the documents, notes and sources for one piece of work (a paper, a case, a class).'));
    } else {
      const p = editing === '+' ? { name: '', color: P.colors[P.list.length % (P.colors.length || 1)] || '#3b6fd4', description: '', default_template: '', citation_style: '' } : Object.assign({}, P.get(editing));
      const field = (label, input, hint) => { const f = el('label', 'block-label'); f.append(label, input); if (hint) f.appendChild(el('div', 'hint', hint)); form.appendChild(f); return input; };
      const name = field('Name', Object.assign(el('input'), { value: p.name, placeholder: 'e.g. Standing article, Torts II paper' }));
      const colors = el('div', 'pm-colors');
      (P.colors.length ? P.colors : ['#3b6fd4']).forEach(c => {
        const b = el('button', 'pm-color' + (p.color === c ? ' on' : '')); b.type = 'button'; b.style.background = c;
        b.onclick = () => { p.color = c; colors.querySelectorAll('.pm-color').forEach(x => x.classList.toggle('on', x === b)); };
        colors.appendChild(b);
      });
      const cl = el('div', 'block-label'); cl.append('Color', colors); form.appendChild(cl);
      const desc = field('Description', Object.assign(el('textarea'), { value: p.description || '', rows: 3, placeholder: 'What it is, deadlines, whatever helps' }));
      const tpl = el('select');
      [['', 'Ask each time']].concat(App.state.templates.map(t => [t.id, t.name])).forEach(([v, l]) => { const o = el('option', '', l); o.value = v; tpl.appendChild(o); });
      tpl.value = p.default_template || '';
      field('Default template', tpl, 'Preselected when you start a document in this project.');
      const st = el('select');
      STYLES.forEach(([v, l]) => { const o = el('option', '', l); o.value = v; st.appendChild(o); });
      st.value = p.citation_style || '';
      field('Citation style', st, 'Used by annotated bibliographies and research notes in this project.');
      const hl = App.highlights.editor();
      const hlBox = el('div', 'block-label');
      hlBox.append('Highlight labels', hl, el('div', 'hint', 'Name what each highlight color means, like Holding, Dicta or Quote to use. The labels are shared by all your projects.'));
      form.appendChild(hlBox);
      const err = el('div', 'error'); err.hidden = true; form.appendChild(err);
      const row = el('div', 'dlg-actions');
      if (editing !== '+') {
        const del = el('button', 'btn danger', 'Delete project'); del.type = 'button';
        del.onclick = async () => {
          if (!confirm('Delete the project “' + p.name + '”?\n\nIts documents, notes and sources are kept; they just won’t belong to it anymore.')) return;
          try { await post('/api/project/delete', { id: editing }); editing = null; if (P.scope === p.id) P.setScope('all'); await P.load(); render(); await App.reloadAll(); }
          catch (e) { err.textContent = e.message; err.hidden = false; }
        };
        row.appendChild(del);
      }
      row.appendChild(el('span', 'spacer'));
      const close = el('button', 'btn', 'Close'); close.type = 'button'; close.onclick = () => dlg.close();
      const save = el('button', 'btn primary', editing === '+' ? 'Create project' : 'Save'); save.type = 'button';
      save.onclick = async () => {
        const data = { name: name.value.trim(), color: p.color, description: desc.value, default_template: tpl.value, citation_style: st.value };
        if (!data.name) { err.textContent = 'Give the project a name.'; err.hidden = false; return; }
        try {
          const r = editing === '+' ? await post('/api/project/new', data) : await put('/api/project', Object.assign({ id: editing }, data));
          await App.highlights.save(hl.values());
          const created = editing === '+';
          editing = r.id; await P.load(); render();
          if (created) { P.setScope(r.id); toast('Created “' + r.name + '”. New documents, notes and sources go into it while it’s selected.'); }
          else toast('Saved.');
        } catch (e) { err.textContent = e.message; err.hidden = false; }
      };
      row.append(close, save);
      form.appendChild(row);
      setTimeout(() => name.focus(), 0);
    }
    wrap.append(side, form);
    dlg.appendChild(wrap);
  }
  P.manage = function (which) {
    editing = which || P.current() || (P.list[0] && P.list[0].id) || '+';
    render();
    App.openDialog(dlg);
  };

  App.cmd.global.manageProjects = () => P.manage();
  App.cmd.global.newProject = () => P.manage('+');
  renderSwitcher();
})();
