/* GitHub and the output folder (the Publish tab).
 * One git folder is managed: "outputs" (finished PDFs/Word files, one subfolder per document).
 * The server runs git and the GitHub CLI with the sign-in you already have on this Mac; the app
 * never sees a password or token. */
(function () {
  'use strict';
  const { $, el, api, post, put, toast } = App;

  const G = App.git = { settings: null, outputs: null, project: null };
  let busy = false;

  function shortName(web) { return web ? web.replace('https://github.com/', '') : ''; }

  function statusHtml(st, kind) {
    if (!st) return '…';
    if (st.gitAvailable === false) return 'GitHub needs git, which isn\u2019t installed on this computer';
    if (!st.isRepo) return kind === 'outputs' ? 'Set up on your first Run' : 'Not a git repository';
    if (!st.remote) return '<span class="warn">Not connected to GitHub</span>';
    const bits = [];
    if (st.ahead === undefined) bits.push('not pushed yet');
    else {
      if (st.ahead) bits.push('↑' + st.ahead + ' to push');
      if (st.behind) bits.push('↓' + st.behind + ' on GitHub');
    }
    if (st.dirty) bits.push(st.dirty + ' changed');
    return '<b>' + App.esc(shortName(st.web) || st.remote.split('/').pop()) + '</b> · ' + (bits.length ? bits.join(', ') : '✓ in sync');
  }

  async function refresh() {
    try {
      const [s, o, w] = await Promise.all([api('/api/settings'), api('/api/git?repo=outputs'), api('/api/git?repo=project')]);
      G.settings = s; G.outputs = o; G.project = w;
    } catch (e) { return; }
    const path = G.settings.outputDir;
    $('#out-path').textContent = path.replace(/^.*\/(Library\/CloudStorage\/[^/]+\/)?/, '…/') || path;
    $('#out-path').title = path;
    $('#gh-out-status').innerHTML = statusHtml(G.outputs, 'outputs');
    $('#gh-out-web').disabled = !G.outputs.web;
    $('#gh-work-status').innerHTML = G.project.gitAvailable === false ? 'Offline here: this computer has no git'
      : !G.project.isRepo || !G.project.remote ? '<span class="warn">Not connected to GitHub</span>' : statusHtml(G.project, 'project');
    $('#gh-work-web').disabled = !G.project.web;
    $('#pub-auto').checked = !!G.settings.autoPush;
    const data = G.settings.dataDir || '';
    $('#data-path').textContent = data.replace(/^.*\/(Application Support\/)/, '…/$1').replace(/^\/Users\/[^/]+/, '~');
    $('#data-path').title = data;
    // finished files are part of the work repository: its Sync covers them, so hide the separate GitHub controls
    const sep = !G.settings.outputsInWork;
    $('#gh-out-group').querySelectorAll('.rb-items.col, [data-cmd="connectOutputs"]').forEach(el => { el.hidden = !sep; });
    $('#gh-out-group .rb-label').textContent = sep ? 'Outputs → GitHub' : 'Publish';
    $('#pub-auto').closest('.rb-group').hidden = !sep;    // Run already syncs the whole repository
  }
  G.refresh = refresh;

  async function guard(label, fn) {
    if (busy) { toast('Still working on the last GitHub step.', true); return; }
    busy = true; toast(label);
    try { await fn(); } catch (e) { toast(e.message, true); }
    finally { busy = false; refresh(); }
  }

  /* ------------------------------------------------------------ commands */
  const C = App.cmd.global;

  C.openData = () => post('/api/open', { repo: 'project', what: 'folder' }).catch(e => toast(e.message, true));
  C.openOutput = () => api('/api/open', { method: 'POST', body: JSON.stringify({ repo: 'outputs', what: 'folder' }) }).catch(e => toast(e.message, true));
  C.changeOutput = async () => {
    const now = (G.settings && G.settings.outputDir) || '';
    const v = prompt('Full path of the folder to put finished files in.\nIt becomes its own git repository.\n\nLeave blank to go back to the default (an "outputs" folder inside the project).', now);
    if (v === null) return;
    try { await put('/api/settings', { outputDir: v.trim() }); toast('Output folder updated.'); } catch (e) { toast(e.message, true); }
    refresh();
  };
  $('#pub-auto').addEventListener('change', async e => {
    try { await put('/api/settings', { autoPush: e.target.checked }); } catch (err) { toast(err.message, true); }
    refresh();
  });

  C.webOutputs = () => post('/api/open', { repo: 'outputs', what: 'github' }).catch(e => toast(e.message, true));

  C.webWork = () => post('/api/open', { repo: 'project', what: 'github' }).catch(e => toast(e.message, true));
  C.connectWork = () => openConnect('project');

  // Sync your work (documents, research, library and files) with its GitHub repository.
  let syncing = false;
  async function sync(reason, quiet) {
    if (syncing) return null;
    syncing = true;
    try {
      await App.saver.flush(false);
      if (App.sources) await App.sources.flush();
      const r = await post('/api/sync', { reason });
      if (!quiet || !r.ok) toast(r.message, !r.ok && !r.offline);
      if (r.changed) await App.reloadAll();
      return r;
    } catch (e) { if (!quiet) toast(e.message, true); return null; }
    finally { syncing = false; refresh(); }
  }
  C.syncWork = () => sync('sync', false);
  App.sync = sync;
  App.syncOnQuit = async () => { if (G.project && G.project.remote) await sync('quit', true); };
  // Keep this computer and GitHub in step while ReWord is open, not only on open, Run and quit, so a
  // change made elsewhere (another Mac, a Claude session's merged pull request) never sits unpulled for long.
  setInterval(() => { if (G.project && G.project.remote && !document.hidden) sync('auto', true); }, 10 * 60 * 1000);

  C.publish = () => {
    const slug = App.views.writing.current();
    if (!slug) { toast('Open a document in Writing first.', true); return; }
    guard('Copying to the output folder…', async () => {
      await App.saver.flush(false);
      const connected = !!(G.outputs && G.outputs.remote);
      const r = await post('/api/publish', { doc: slug, push: connected });
      toast(connected
        ? 'Published ' + r.copied.length + ' file' + (r.copied.length === 1 ? '' : 's') + ' to GitHub.'
        : 'Copied ' + r.copied.length + ' file' + (r.copied.length === 1 ? '' : 's') + ' to the output folder. Connect GitHub to upload them.');
    });
  };
  /* ------------------------------------------------------------ connect dialog */
  const dlg = $('#dlg-github');
  let which = 'outputs';

  async function openConnect(w) {
    which = w;
    await refresh();
    const st = G[w];
    $('#gh-title').textContent = w === 'outputs' ? 'Connect the output folder to GitHub' : 'Connect your work to GitHub';
    $('#gh-intro').textContent = w === 'outputs'
      ? 'Finished PDF, Word, HTML and text files go here, in one folder per document. This folder is its own git repository, separate from your writing.'
      : 'Your documents, research notes, citation library and the files attached to it (PDFs, snapshots, highlights). Sync brings them to any Mac where you are signed in to GitHub. Keep this repository private: it holds copies of copyrighted sources.';
    $('#gh-url').value = (st && st.remote) || '';
    $('#gh-name').value = w === 'outputs' ? 'reword-outputs' : 'reword-data';
    if (w === 'project') $('#gh-private').checked = true;
    $('#gh-error').hidden = true;
    $('#gh-create').disabled = true;
    $('#gh-cli').textContent = 'Checking the GitHub command-line tool…';
    App.openDialog(dlg);
    try {
      const gh = await api('/api/gh');
      const box = $('#gh-cli'); box.innerHTML = '';
      if (gh.installed && gh.authed) {
        box.textContent = 'Signed in to GitHub' + (gh.user ? ' as ' + gh.user : '') + '. The new repository is created in that account.';
        $('#gh-create').disabled = false;
      } else if (gh.installed) {
        box.innerHTML = 'The GitHub command-line tool is installed, but you aren’t signed in. In Terminal, run <code>gh auth login</code> (choose GitHub.com and HTTPS), then reopen this window.';
      } else {
        box.innerHTML = 'To create repositories from here, install the GitHub command-line tool. In Terminal, run <code>brew install gh</code>, then <code>gh auth login</code>. You can also create a repository on github.com and paste its address above.';
      }
    } catch (e) { $('#gh-cli').textContent = 'Couldn’t check GitHub: ' + e.message; }
  }
  C.connectOutputs = () => openConnect('outputs');

  function fail(msg) { const e = $('#gh-error'); e.textContent = msg; e.hidden = false; }

  $('#gh-connect').onclick = async () => {
    try {
      await post('/api/git/connect', { repo: which, url: $('#gh-url').value });
      dlg.close(); toast('Connected. Use ' + (which === 'outputs' ? 'Publish' : 'Sync') + ' to upload.');
      refresh();
    } catch (e) { fail(e.message); }
  };
  $('#gh-create').onclick = async () => {
    const name = $('#gh-name').value.trim();
    const priv = $('#gh-private').checked;
    if (!confirm('Create ' + (priv ? 'a private' : 'a PUBLIC') + ' repository named “' + name + '” on your GitHub account?')) return;
    $('#gh-create').disabled = true; $('#gh-error').hidden = true;
    try {
      const st = await post('/api/git/create', { repo: which, name, private: priv });
      dlg.close();
      toast('Created ' + shortName(st.web) + '. Use ' + (which === 'outputs' ? 'Publish' : 'Sync') + ' to upload.');
      refresh();
    } catch (e) { fail(e.message); $('#gh-create').disabled = false; }
  };

  App.afterRun = refresh;
})();
