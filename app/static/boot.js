/* Start-up: load templates, documents and the citation library, then open the Writing view. */
(async function () {
  'use strict';
  // Commands that work from any view: jump to the right place, then start the "new" flow.
  App.cmd.global.newDoc = async () => { await App.showView('writing'); App.views.writing.newDoc(); };
  App.cmd.global.newNote = async () => { await App.showView('research'); App.views.research.newNote(); };
  App.cmd.global.newCite = async () => { await App.showView('citations'); App.views.citations.open('+'); };

  // After a sync brought in changes from GitHub: reload the lists and whatever is open.
  App.reloadAll = async function () {
    const s = await App.api('/api/state');
    App.state.templates = s.templates; App.state.documents = s.documents;
    await App.projects.load();
    await App.loadCitations();
    const v = App.views[App.view];
    if (v && v.reload) await v.reload(); else if (v && v.show) await v.show();
  };

  // Tell the server this window is alive. When it closes, the server (if it was started by the
  // app launcher) shuts itself down; a reload says goodbye and pings again straight away.
  let missed = 0;
  const ping = () => fetch('/api/ping').then(() => { missed = 0; }).catch(() => {
    // The server only stops by itself when the window has been gone a while (or you quit it),
    // but if it ever does, say so instead of failing quietly.
    if (++missed === 3) {
      document.getElementById('save-status').textContent = 'ReWord stopped. Close this window and open the app again.';
      App.toast('ReWord stopped running in the background. Your work was saved; reopen the app to continue.', true);
    }
  });
  ping(); setInterval(ping, 5000);
  window.addEventListener('pagehide', () => {
    try { navigator.sendBeacon('/api/bye', new Blob(['{}'], { type: 'application/json' })); } catch (e) { /* ignore */ }
  });

  try {
    const s = await App.api('/api/state');
    App.state.templates = s.templates;
    App.state.documents = s.documents;
    await App.projects.load();
    await App.loadCitations();
    App._first = true;
    await App.showView('writing');
    let mode = 'rich';
    try { mode = localStorage.getItem('editMode') || 'rich'; } catch (e) { /* ignore */ }
    App.setEditMode(mode);
    App.saver.status('All saved');
    await App.views.writing.resumeJob();
    await App.git.refresh();
    // pull what changed on your other computers (only when the work repo is connected to GitHub)
    if (App.git.project && App.git.project.remote) App.sync('open', true);
    App.showConflicts();          // choices left open from an earlier sync
  } catch (e) {
    document.getElementById('save-status').textContent = 'Couldn’t reach the app server';
    App.toast('Couldn’t load: ' + e.message, true);
  }
})();
