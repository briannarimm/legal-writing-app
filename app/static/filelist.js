/* A source's files, one line each, above the reader (Citations, Research and Verify use it). A source can have
 * many PDFs: translations, versions, and for an edited book each chapter's PDF. Each file can carry a label
 * ("English translation", "2019 version") and, in an edited book, the chapter it belongs to; both are saved in
 * library/files/<tag>/_files.json. More than three files: the open one shows, and the rest drop down from "All N".
 *
 *   const strip = App.FileStrip(container, { onPick(name), onChanged(files) })
 *   strip.render(citation, files, openName, chapter)   chapter = the chapter being cited (its files come first)
 *   App.preferredFile(files, chapter)                   the file to open first for a citation (to that chapter)
 */
(function () {
  'use strict';
  const { el, post, toast } = App;

  // The file to open first: the chapter's own PDF, else the whole book's, else any PDF, else any file.
  App.preferredFile = function (files, chapter) {
    const pdf = (files || []).filter(f => f.kind === 'pdf' && !f.annotated);
    const pick = (chapter && pdf.find(f => f.chapter === chapter)) || pdf.find(f => !f.chapter) || pdf[0] || (files || [])[0];
    return pick ? pick.name : null;
  };

  // a chapter's number in the book (as entered), else its place in the list
  function chapterNo(c, id) {
    const list = (c && c.chapters) || [];
    const k = list.findIndex(ch => ch.id === id);
    return k < 0 ? null : (Number(list[k].number) || null);
  }

  // Files in the order to show them: the cited chapter's, the whole book's, then each chapter's in book order.
  function ordered(c, files, chapter) {
    const rank = f => f.chapter ? (f.chapter === chapter ? 0 : 2 + (chapterNo(c, f.chapter) || 999)) : 1;
    return files.slice().sort((a, b) => rank(a) - rank(b) || (a.annotated - b.annotated) || a.name.localeCompare(b.name));
  }

  App.FileStrip = function (container, opts) {
    const box = el('div', 'ns-cards file-strip');
    container.appendChild(box);
    let st = { c: null, files: [], open: null, chapter: '' }, dropOpen = false;

    function card(f) {
      const row = el('div', 'ns-card file-card' + (f.name === st.open ? ' active' : ''));
      const n = f.chapter ? chapterNo(st.c, f.chapter) : null;
      const kind = f.chapter ? (n ? 'Ch. ' + n : 'Chapter') : f.snapshot ? 'Snapshot' : f.annotated ? 'Annotated' : (f.kind || 'file').toUpperCase();
      const chip = el('span', 'chip', kind);
      if (f.chapter) {
        const ch = ((st.c && st.c.chapters) || []).find(x => x.id === f.chapter);
        chip.title = ch ? ch.label : 'Chapter ' + f.chapter + ' (not in the book any more)';
      }
      const name = el('span', 'ns-card-cite file-name', f.label || f.name);
      name.title = f.label ? f.label + ' · ' + f.name : f.name;
      row.append(chip, name);
      if (f.annotations) { const a = el('span', 'ns-files', f.annotations + ' ✎'); a.title = f.annotations + ' highlight' + (f.annotations === 1 ? '' : 's') + ' and comments'; row.appendChild(a); }
      const ed = el('button', 'ns-unlink file-edit', '⋯'); ed.type = 'button';
      ed.title = App.hasChapters(st.c) ? 'Name this file, or say which chapter it is' : 'Name this file (translation, version…)';
      ed.onclick = e => { e.stopPropagation(); editMeta(f, row); };
      row.appendChild(ed);
      row.onclick = () => { dropOpen = false; if (f.name !== st.open) opts.onPick(f.name); else draw(); };
      return row;
    }

    function draw() {
      box.innerHTML = '';
      const files = ordered(st.c, st.files, st.chapter);
      box.classList.toggle('many', files.length > 3);
      box.hidden = !files.length;
      if (files.length <= 3) { files.forEach(f => box.appendChild(card(f))); return; }
      const cur = el('div', 'ns-current');
      const open = files.find(f => f.name === st.open) || files[0];
      const more = el('button', 'btn small ns-more', (dropOpen ? '▴ ' : '▾ ') + 'All ' + files.length + ' files'); more.type = 'button';
      more.onclick = e => { e.stopPropagation(); dropOpen = !dropOpen; draw(); };
      cur.append(card(open), more);
      box.appendChild(cur);
      if (dropOpen) {
        const drop = el('div', 'ns-drop');
        files.forEach(f => drop.appendChild(card(f)));
        box.appendChild(drop);
      }
    }
    document.addEventListener('mousedown', e => { if (dropOpen && !box.contains(e.target)) { dropOpen = false; draw(); } });

    // the little form for one file: its label, and its chapter in an edited book
    let pop = null;
    function closePop() { if (pop) { pop.remove(); pop = null; } }
    document.addEventListener('mousedown', e => { if (pop && !pop.contains(e.target)) closePop(); });
    function editMeta(f, anchor) {
      closePop();
      const c = st.c;
      pop = el('div', 'chip-pop file-pop');
      pop.appendChild(el('div', 'chip-head', f.name));
      const lab = el('input'); lab.value = f.label || ''; lab.placeholder = 'English translation · 2019 version · Ch. 3';
      const r1 = el('label', 'chip-row'); r1.append(el('span', '', 'Label'), lab); pop.appendChild(r1);
      let chSel = null;
      if (App.hasChapters(c)) {
        chSel = el('select');
        const w = el('option', '', 'The whole book (or not one chapter)'); w.value = ''; chSel.appendChild(w);
        (c.chapters || []).forEach(ch => { const o = el('option', '', ch.label); o.value = ch.id; chSel.appendChild(o); });
        if (f.chapter && !(c.chapters || []).some(ch => ch.id === f.chapter)) { const o = el('option', '', f.chapter + ' (not in the book any more)'); o.value = f.chapter; chSel.appendChild(o); }
        chSel.value = f.chapter || '';
        const r2 = el('label', 'chip-row'); r2.append(el('span', '', 'Chapter'), chSel); pop.appendChild(r2);
      }
      pop.appendChild(el('div', 'hint', 'The label shows instead of the file name. ' + (chSel ? 'A chapter’s PDF opens when you check a citation to that chapter.' : '')));
      const row = el('div', 'row');
      const cancel = el('button', 'btn small', 'Cancel'); cancel.type = 'button'; cancel.onclick = closePop;
      const save = el('button', 'btn small primary', 'Save'); save.type = 'button';
      save.onclick = async () => {
        try {
          const r = await post('/api/file/meta', { tag: c.tag, name: f.name, label: lab.value.trim(), chapter: chSel ? chSel.value : undefined });
          closePop();
          st.files = r.files; draw();
          if (opts.onChanged) opts.onChanged(r.files);
        } catch (e) { toast(e.message, true); }
      };
      lab.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save.click(); } else if (e.key === 'Escape') closePop(); });
      row.append(cancel, save);
      pop.appendChild(row);
      document.body.appendChild(pop);
      const r = anchor.getBoundingClientRect(), w = Math.min(380, window.innerWidth - 24);
      pop.style.width = w + 'px';
      pop.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left)) + 'px';
      const below = r.bottom + 6, h = pop.offsetHeight;
      pop.style.top = (below + h < window.innerHeight - 8 ? below : Math.max(8, r.top - h - 6)) + 'px';
      lab.focus();
    }

    return {
      render(c, files, open, chapter) { st = { c, files: files || [], open, chapter: chapter || '' }; draw(); },
      clear() { st = { c: null, files: [], open: null, chapter: '' }; closePop(); draw(); },
    };
  };
})();
