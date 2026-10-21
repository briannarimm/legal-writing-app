/* Shared rich-text pieces: formatting commands, paste cleaning, and the one-line rich
 * field used for citations. Everything that is editable carries data-rich="block" or
 * data-rich="inline" so one toolbar and one paste handler work across the whole app.
 * Italics, bold and small caps are real formatting here and become Markdown on save
 * (*italic*, **bold**, [small caps]{.smallcaps}), which Pandoc turns into the right type
 * in the PDF and Word file.
 */
(function (global) {
  'use strict';
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Chrome's insertHTML flattens a fragment that is a single element (a lone <span class="sc">
  // loses its class and becomes inline CSS; <span data-tag> loses everything). Adding a
  // zero-width marker after the HTML makes it keep the structure; the marker is removed after.
  const MARK = '\u200b';
  function insertHtmlKeepingSpans(html) {
    document.execCommand('insertHTML', false, html + MARK);
    const s = getSelection();
    if (!s.rangeCount) return;
    const root = (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement).closest('[data-rich]');
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const i = n.nodeValue.indexOf(MARK);
      if (i >= 0) {
        const prev = n.previousSibling;
        if (i === 0 && prev && prev.nodeType === 1 && (prev.classList.contains('auth') || prev.classList.contains('cite'))) {
          // The marker sits right after an authority mark: keep it as a (hidden) place for the
          // caret outside the mark, so typing a comma or pin cite doesn't extend the mark.
          const keep = document.createRange();
          keep.setStart(n, MARK.length); keep.collapse(true);
          const ks = getSelection(); ks.removeAllRanges(); ks.addRange(keep);
        } else n.deleteData(i, 1);        // deleteData keeps the caret where it was
        break;
      }
    }
    // If the caret ended up at the very end of an authority mark, step out of it so that
    // whatever is typed next (a comma, a pin cite) isn't swallowed into the mark.
    const sel = getSelection();
    if (sel.rangeCount && sel.isCollapsed) {
      const node = sel.anchorNode;
      const a = (node.nodeType === 1 ? node : node.parentElement).closest('.auth');
      if (a) {
        const tail = document.createRange();
        tail.selectNodeContents(a);
        tail.setStart(node, sel.anchorOffset);
        if (tail.toString() === '') {
          // Chrome snaps a caret at the boundary back inside the element, so park it in a
          // zero-width text node just after the mark. md.js strips these when saving.
          let z = a.nextSibling;
          if (!(z && z.nodeType === 3 && z.nodeValue.startsWith(MARK))) {
            z = document.createTextNode(MARK);
            a.after(z);
          }
          const after = document.createRange();
          after.setStart(z, MARK.length); after.collapse(true);
          sel.removeAllRanges(); sel.addRange(after);
        }
      }
    }
  }

  function activeEditable() {
    const a = document.activeElement;
    if (a && a.closest && a.closest('[data-rich]')) return a.closest('[data-rich]');
    const s = getSelection();
    if (s.rangeCount) {
      const el = s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement;
      return el && el.closest('[data-rich]');
    }
    return null;
  }

  // Large-and-small caps: wrap or unwrap the selection (via insertHTML so Undo still works).
  function toggleSmallCaps() {
    const sel = getSelection();
    if (!sel.rangeCount) return;
    const range = sel.getRangeAt(0);
    const anc = range.commonAncestorContainer;
    const inSc = (anc.nodeType === 1 ? anc : anc.parentElement).closest('.sc');
    if (inSc) {
      const r = document.createRange(); r.selectNodeContents(inSc);
      sel.removeAllRanges(); sel.addRange(r);
      insertHtmlKeepingSpans(inSc.innerHTML);
      return;
    }
    if (range.collapsed) return;
    const tmp = document.createElement('div');
    tmp.appendChild(range.cloneContents());
    insertHtmlKeepingSpans('<span class="sc">' + tmp.innerHTML + '</span>');
  }

  function format(cmd) {
    const el = activeEditable();
    if (!el) return false;
    const a = getSelection().anchorNode;
    if (a && (a.nodeType === 1 ? a : a.parentElement).closest('.raw')) return true;   // pass-through blocks stay plain
    if (cmd === 'italic' || cmd === 'bold') document.execCommand(cmd);
    else if (cmd === 'smallcaps') toggleSmallCaps();
    else return false;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  // Turn clipboard HTML into text with only italics, bold, small caps and paragraph breaks.
  function cleanPaste(html) {
    const t = document.createElement('div'); t.innerHTML = html;
    t.querySelectorAll('script,style,meta,link,title').forEach(n => n.remove());
    const out = [];
    (function walk(n, fmt) {
      n.childNodes.forEach(c => {
        if (c.nodeType === 3) {
          let s = esc(c.nodeValue.replace(/[\s ]+/g, ' '));
          if (!s) return;
          if (fmt.sc) s = '<span class="sc">' + s + '</span>';
          if (fmt.em) s = '<em>' + s + '</em>';
          if (fmt.b) s = '<strong>' + s + '</strong>';
          out.push(s); return;
        }
        if (c.nodeType !== 1) return;
        const st = (c.getAttribute('style') || '').toLowerCase();
        const f = Object.assign({}, fmt);
        if (/^(I|EM|CITE)$/.test(c.tagName) || /font-style:\s*italic/.test(st)) f.em = true;
        if (/^(B|STRONG)$/.test(c.tagName) || /font-weight:\s*(bold|[6-9]00)/.test(st)) f.b = true;
        if (/small-caps/.test(st)) f.sc = true;
        if (c.tagName === 'BR') { out.push('\n'); return; }
        const block = /^(P|DIV|H[1-6]|LI|BLOCKQUOTE|TR|UL|OL)$/.test(c.tagName);
        if (block && out.length && out[out.length - 1] !== '\n\n') out.push('\n\n');
        walk(c, f);
        if (block && out[out.length - 1] !== '\n\n') out.push('\n\n');
      });
    })(t, {});
    return out.join('').replace(/(\n\n)+/g, '\n\n').replace(/^\n+|\n+$/g, '');
  }

  function onPaste(e) {
    const target = e.target.closest && e.target.closest('[data-rich]');
    if (!target) return;
    e.preventDefault();
    const cd = e.clipboardData;
    const raw = e.target.closest('.raw');
    if (raw) {
      // a pass-through block (a table, LaTeX…) is plain Markdown: its line breaks are part of it
      const text = (cd.getData('text/plain') || '').replace(/\r\n?/g, '\n');
      if (text) document.execCommand('insertText', false, text);
      target.dispatchEvent(new Event('input', { bubbles: true }));
      return;
    }
    const html = cd.getData('text/html');
    const s = html ? cleanPaste(html) : esc(cd.getData('text/plain')).replace(/\r/g, '');
    if (!s) return;
    const parts = s.split('\n\n').map(p => p.replace(/\n/g, ' '));
    const block = target.dataset.rich === 'block';
    insertHtmlKeepingSpans(block && parts.length > 1 ? parts.join('</p><p>') : parts.join(' '));
    target.dispatchEvent(new Event('input', { bubbles: true }));
  }
  document.addEventListener('paste', onPaste);
  document.addEventListener('drop', e => { if (e.target.closest && e.target.closest('[data-rich]')) e.preventDefault(); });

  // Toolbar buttons keep the text selection (mousedown is cancelled) and run a command.
  // `extra` handles commands this module doesn't know (footnote, cite, ...).
  function wireToolbar(toolbar, extra) {
    toolbar.querySelectorAll('button[data-cmd]').forEach(b => {
      b.addEventListener('mousedown', e => e.preventDefault());
      b.addEventListener('click', () => {
        const cmd = b.dataset.cmd;
        if (format(cmd)) return;
        if (extra && extra[cmd]) extra[cmd]();
      });
    });
  }

  // A one-line rich-text field (cite, short form). Returns { el, get, set, focus, onInput, editor }.
  function inlineField(label, opts) {
    opts = opts || {};
    const wrap = document.createElement('div');
    wrap.className = 'field';
    const head = document.createElement('div');
    head.className = 'field-head';
    const lab = document.createElement('label');
    lab.textContent = label;
    const tools = document.createElement('span');
    tools.className = 'mini-tools';
    tools.innerHTML = '<button type="button" data-cmd="italic" title="Italic (⌘I)"><i>I</i></button>' +
      '<button type="button" data-cmd="bold" title="Bold (⌘B)"><b>B</b></button>' +
      '<button type="button" data-cmd="smallcaps" title="Large and small caps"><span class="sc">Sc</span></button>';
    head.append(lab, tools);
    const ed = document.createElement('div');
    ed.className = 'rich-inline';
    ed.contentEditable = 'true';
    ed.spellcheck = opts.spellcheck !== false;
    ed.dataset.rich = 'inline';
    if (opts.placeholder) ed.dataset.placeholder = opts.placeholder;
    ed.addEventListener('keydown', e => { if (e.key === 'Enter') e.preventDefault(); });
    wrap.append(head, ed);
    wireToolbar(tools);
    const hintEl = document.createElement('div'); hintEl.className = 'hint'; hintEl.textContent = opts.hint || '';
    if (opts.hint) wrap.appendChild(hintEl);
    return {
      el: wrap, editor: ed,
      describe(l, placeholder, hint) {          // relabel the field (the citation form changes with the style)
        lab.textContent = l; ed.dataset.placeholder = placeholder || '';
        hintEl.textContent = hint || ''; if (hint && !hintEl.isConnected) wrap.appendChild(hintEl);
      },
      get: () => MD.inlineFromEl(ed),
      set: md => { ed.innerHTML = MD.inlineHtml(md); },
      focus: () => ed.focus(),
      onInput: cb => ed.addEventListener('input', cb),
    };
  }

  // Remember where the cursor was (a dialog steals focus), then put it back and insert HTML there.
  function saveSelection() {
    const el = activeEditable();
    const s = getSelection();
    if (!el || !s.rangeCount) return null;
    return { el, range: s.getRangeAt(0).cloneRange() };
  }
  function restoreSelection(saved) {
    if (!saved) return false;
    saved.el.focus();
    const s = getSelection();
    s.removeAllRanges(); s.addRange(saved.range);
    return true;
  }
  function insertHtml(saved, html) {
    if (!restoreSelection(saved)) return false;
    insertHtmlKeepingSpans(html);
    saved.el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  // The block (paragraph, heading, quote) the cursor is in, within `root`.
  function currentBlock(root) {
    const s = getSelection();
    if (!s.rangeCount) return null;
    let el = s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement;
    while (el && el !== root) {
      if (/^(P|H[1-6]|BLOCKQUOTE|LI)$/.test(el.tagName)) {
        return el.tagName === 'P' && el.parentElement.tagName === 'BLOCKQUOTE' ? el.parentElement : el;
      }
      el = el.parentElement;
    }
    return null;
  }

  // The paragraph-style <select> in the ribbon (Body text / headings / quote). It applies to
  // whichever block editor (a document or a research note) you were last typing in.
  function wireBlockSelect(select) {
    const isBlockEditor = el => el && (el.id === 'doc' || el.id === 'note-body');
    let last = null;
    function sync() {
      const b = last && last.isConnected ? currentBlock(last) : null;
      const v = b ? b.tagName.toLowerCase() : 'p';
      const opts = Array.from(select.options).map(o => o.value);
      select.value = opts.includes(v) ? v : 'p';
    }
    document.addEventListener('selectionchange', () => {
      const a = activeEditable();
      if (isBlockEditor(a)) { last = a; sync(); }
    });
    select.addEventListener('change', () => {
      const root = last;
      if (!root || !root.isConnected || root.offsetParent === null) { sync(); return; }
      const v = select.value;
      root.focus();
      const b = currentBlock(root);
      if (b && b.tagName === 'BLOCKQUOTE' && v !== 'blockquote') {
        document.execCommand('outdent'); document.execCommand('formatBlock', false, 'p');
      } else document.execCommand('formatBlock', false, v);
      root.dispatchEvent(new Event('input', { bubbles: true }));
      sync();
    });
  }

  // Ribbon buttons for lists and block quotes. They act on the document or research note you're typing in.
  function blockRoot() {
    const a = activeEditable();
    return a && (a.id === 'doc' || a.id === 'note-body') ? a : null;
  }
  function changed(root) { root.dispatchEvent(new Event('input', { bubbles: true })); }
  function list(kind) {
    const root = blockRoot();
    if (!root) return false;
    root.focus();
    document.execCommand(kind === 'ol' ? 'insertOrderedList' : 'insertUnorderedList');
    changed(root);
    return true;
  }
  function quote() {
    const root = blockRoot();
    if (!root) return false;
    root.focus();
    const b = currentBlock(root);
    if (b && b.tagName === 'BLOCKQUOTE') { document.execCommand('outdent'); document.execCommand('formatBlock', false, 'p'); }
    else document.execCommand('formatBlock', false, 'blockquote');
    changed(root);
    return true;
  }

  global.Rich = { list, quote, activeEditable, format, toggleSmallCaps, cleanPaste, wireToolbar, inlineField, esc,
                  saveSelection, restoreSelection, insertHtml, insertHtmlKeepingSpans, currentBlock, wireBlockSelect };
})(window);
