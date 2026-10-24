/* ReSuite: ReWord with RePublish, RePDF and the ReSuite hub (app/suite.py does the work).
 *
 *   the ReWord badge at the top of the sidebar   the suite menu: the other apps, Make Slides / Poster /
 *                                                Handout in RePublish, Open the finished PDF in RePDF,
 *                                                Show the suite project in ReSuite
 *   App.suite.menu(name)     the same commands from the Mac menu bar (main.swift: App.menu('suite:<name>'))
 *   App.suite.link(href)     a reword:// link (main.swift passes them in): open?doc=, project?id=,
 *                            new?project=, handoff?file=…&make=note
 *
 * Everything here is optional: without the other apps (or outside the Mac app) ReWord works as before.
 */
(function () {
  'use strict';
  const { $, api, post, toast } = App;
  const S = App.suite = { available: false, project: null, pdf: false };
  const APPS = [
    { id: 'hub', name: 'ReSuite', key: '0' },
    { id: 'reword', name: 'ReWord', key: '1' },
    { id: 'republish', name: 'RePublish', key: '2' },
    { id: 'repdf', name: 'RePDF', key: '3' },
  ];
  const MAKES = { slides: 'Slides', poster: 'a poster', handout: 'a handout' };
  const img = id => '/static/suite/' + id + '.png';
  const W = () => App.views.writing;
  const slug = () => (W() && W().current ? W().current() : null);
  const title = () => { const i = W() && W().info && W().info(); return i ? i.title : ''; };

  async function refresh() {
    try {
      const s = slug();
      Object.assign(S, { project: null, pdf: false }, await api('/api/suite' + (s ? '?doc=' + encodeURIComponent(s) : '')));
    } catch (e) { /* the menu still shows the apps */ }
  }

  function missing(r) {
    if (r && r.installed === false) toast(r.name + ' isn’t on this Mac yet, so its download page is opening.');
    return r && r.installed === false;
  }

  async function launch(id) {
    if (id === 'reword') return;
    try { missing(await post('/api/suite/open', { app: id })); } catch (e) { toast(e.message, true); }
  }

  async function make(what) {
    const s = slug();
    if (!s) { toast('Open a document first, then make ' + MAKES[what] + ' from it in RePublish.', true); return; }
    try {
      if (App.saver && App.saver.flush) await App.saver.flush(false);      // RePublish gets what's on screen
      const r = await post('/api/suite/handoff', { doc: s, make: what });
      if (!missing(r)) toast('RePublish is making ' + MAKES[what].replace(/^S/, 's') + ' from “' + title() + '”.');
    } catch (e) { toast(e.message, true); }
  }

  async function openPdf() {
    const s = slug();
    if (!s) { toast('Open a document first.', true); return; }
    try { missing(await post('/api/suite/open', { app: 'repdf', doc: s })); } catch (e) { toast(e.message, true); }
  }

  async function showProject() {
    await refresh();
    if (!S.project) { await launch('hub'); return; }
    try { missing(await post('/api/suite/open', { app: 'hub', project: S.project.id })); } catch (e) { toast(e.message, true); }
  }

  S.menu = function (name) {
    if (name === 'slides' || name === 'poster' || name === 'handout') return make(name);
    if (name === 'pdf') return openPdf();
    if (name === 'project') return showProject();
    if (APPS.some(a => a.id === name)) return launch(name);
    return null;
  };

  S.items = function () {
    const off = !S.available, s = slug();
    const items = [{ header: 'ReSuite' }];
    APPS.forEach(a => items.push({ label: a.id === 'hub' ? 'ReSuite Hub' : a.name, img: img(a.id), kbd: '⌃⌥⌘' + a.key,
      disabled: off && a.id !== 'reword', run: () => launch(a.id) }));
    items.push('-');
    items.push({ header: s ? 'From “' + title() + '”' : 'From a document' });
    items.push({ label: 'Make Slides in RePublish', icon: 'run', disabled: off || !s, run: () => make('slides') });
    items.push({ label: 'Make a Poster in RePublish', icon: 'run', disabled: off || !s, run: () => make('poster') });
    items.push({ label: 'Make a Handout in RePublish', icon: 'run', disabled: off || !s, run: () => make('handout') });
    items.push({ label: 'Open Finished PDF in RePDF', icon: 'open', disabled: off || !S.pdf,
      title: S.pdf ? '' : 'Save the document to build its PDF first', run: openPdf });
    if (S.project) {
      items.push('-');
      items.push({ label: 'Show “' + S.project.name + '” in ReSuite', img: img('hub'), run: showProject });
    }
    if (off) items.push('-', { header: 'The other ReSuite apps run on a Mac' });
    return items;
  };

  // the badge at the top of the sidebar opens the suite menu
  const badge = $('#suite-switch');
  if (badge) {
    badge.onclick = async () => {
      await refresh();
      const r = badge.getBoundingClientRect();
      App.menu.open(r.left, r.bottom + 4, S.items());
    };
  }

  /* ------------------------------------------------------------ links from the other apps */
  function parse(href) {
    let u;
    try { u = new URL(href); } catch (e) { return null; }
    if (u.protocol !== 'reword:') return null;
    // reword://open?doc=x has host "open"; reword:open?doc=x has the action in the path
    const action = (u.hostname || u.pathname.replace(/^\/+/, '')).toLowerCase();
    return { action, q: u.searchParams };
  }

  S.link = async function (href) {
    const l = parse(href);
    if (!l) return false;
    const P = App.projects, project = l.q.get('project') || l.q.get('id') || '';
    try {
      if (l.action === 'open' && l.q.get('doc')) {
        const d = l.q.get('doc');
        if (!(App.state.documents || []).some(x => x.slug === d)) { toast('That document isn’t in ReWord any more.', true); return true; }
        await App.showView('writing');
        await W().open(d);
      } else if (l.action === 'project') {
        if (!P.get(project)) { toast('That project isn’t in ReWord any more.', true); return true; }
        P.setScope(project);
        await App.showView('writing');
      } else if (l.action === 'new') {
        if (project && P.get(project)) P.setScope(project);
        await App.cmd.global.newDoc();
      } else if (l.action === 'handoff') {
        const scope = P.scope !== 'all' && P.scope !== 'none' ? P.scope : '';
        const r = await post('/api/suite/receive', { file: l.q.get('file') || '', project: scope });
        await App.views.research.open(r.note.id);
        toast('Made a research note from the highlights in “' + r.note.title.replace(/^Highlights: /, '') + '”.');
      } else {
        await App.showView(App.view || 'writing');
      }
    } catch (e) { toast(e.message, true); }
    return true;
  };

  // A link can arrive before the page has finished starting; main.swift asks again until it's ready.
  S.ready = () => !!App.booted;
  refresh();
})();
