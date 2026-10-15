/* The source reader in the Citations tab: a PDF (an attachment or a web-page snapshot) drawn with PDF.js,
 * with selectable text, highlights and comments.
 *
 *   const r = new Reader(container, listEl, { onChange(annotations) })
 *   await r.open(url, annotations)       annotations: [{id, page, rects:[[x,y,w,h]…], text, comment, color}]
 *   r.highlight(color)                   highlight the current text selection
 *   r.zoom(+1 | -1 | 0)                  bigger, smaller, fit the width
 *
 * Rects are fractions of the page measured from its top left, so highlights stay put at any zoom and
 * match what `rwpdf annotate` writes into an exported copy.
 */
import * as pdfjs from '/static/vendor/pdfjs/pdf.min.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';

const COLORS = ['yellow', 'green', 'blue', 'pink'];
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

class Reader {
  constructor(view, list, opts) {
    this.view = view; this.list = list; this.opts = opts || {};
    this.doc = null; this.task = null; this.anns = []; this.scale = 'fit'; this.drawId = 0; this.pages = [];
    this.bar = el('div', 'hl-bar'); this.bar.hidden = true;
    COLORS.forEach(c => {
      const b = el('button', 'hl-swatch ' + c); b.type = 'button'; b.title = 'Highlight (' + c + ')';
      b.addEventListener('mousedown', e => e.preventDefault());
      b.onclick = () => this.highlight(c);
      this.bar.appendChild(b);
    });
    const cm = el('button', 'hl-note', 'Comment'); cm.type = 'button'; cm.title = 'Highlight and add a comment';
    cm.addEventListener('mousedown', e => e.preventDefault());
    cm.onclick = () => { const a = this.highlight('yellow'); if (a) this.editAnn(a); };
    this.bar.appendChild(cm);
    document.body.appendChild(this.bar);
    view.addEventListener('mouseup', () => setTimeout(() => this.selectionBar(), 0));
    document.addEventListener('selectionchange', () => { if (getSelection().isCollapsed) this.bar.hidden = true; });
    view.addEventListener('scroll', () => { this.bar.hidden = true; this.closePop(); });
    let t; new ResizeObserver(() => { if (this.scale === 'fit') { clearTimeout(t); t = setTimeout(() => this.draw(), 200); } }).observe(view);
  }

  async open(url, annotations) {
    this.anns = (annotations || []).map(a => Object.assign({}, a));
    this.closePop(); this.bar.hidden = true;
    const old = this.task;
    this.task = pdfjs.getDocument({ url });
    this.doc = await this.task.promise;
    if (old) { try { await old.destroy(); } catch (e) { /* gone */ } }
    await this.draw();
    this.renderList();
  }

  close() {
    this.closePop(); this.bar.hidden = true; this.view.textContent = ''; this.list.textContent = '';
    if (this.task) { this.task.destroy().catch(() => {}); this.task = null; } this.doc = null;
  }

  zoom(dir) {
    const cur = this.scale === 'fit' ? (this.pages[0] ? this.pages[0].vp.scale : 1.3) : this.scale;
    this.scale = dir === 0 ? 'fit' : Math.max(0.5, Math.min(4, cur * (dir > 0 ? 1.2 : 1 / 1.2)));
    this.draw();
  }

  async draw() {
    if (!this.doc || !this.view.clientWidth) return;
    const id = ++this.drawId;
    const keep = this.view.scrollHeight ? this.view.scrollTop / this.view.scrollHeight : 0;
    this.view.textContent = ''; this.pages = [];
    if (this.observer) this.observer.disconnect();
    for (let n = 1; n <= this.doc.numPages; n++) {
      const page = await this.doc.getPage(n);
      if (id !== this.drawId) return;
      const natural = page.getViewport({ scale: 1 });
      const scale = this.scale === 'fit' ? Math.max(0.3, (this.view.clientWidth - 28) / natural.width) : this.scale;
      const vp = page.getViewport({ scale });
      const holder = el('div', 'rd-page'); holder.dataset.n = n;
      holder.style.width = Math.floor(vp.width) + 'px'; holder.style.height = Math.floor(vp.height) + 'px';
      holder.style.setProperty('--total-scale-factor', vp.scale);
      const hl = el('div', 'hl-layer');
      holder.appendChild(hl);
      this.view.appendChild(holder);
      this.pages.push({ n, page, vp, holder, hl });
    }
    this.view.scrollTop = keep * this.view.scrollHeight;
    this.observer = new IntersectionObserver(entries => entries.forEach(e => { if (e.isIntersecting) this.paint(+e.target.dataset.n); }),
      { root: this.view, rootMargin: '600px 0px' });
    this.pages.forEach(p => { this.observer.observe(p.holder); this.paintHighlights(p.n); });
  }

  async paint(n) {
    const p = this.pages[n - 1];
    if (!p || p.done) return;
    p.done = true;
    const dpr = window.devicePixelRatio || 1;
    const canvas = el('canvas');
    canvas.width = Math.floor(p.vp.width * dpr); canvas.height = Math.floor(p.vp.height * dpr);
    canvas.style.width = p.holder.style.width; canvas.style.height = p.holder.style.height;
    p.holder.insertBefore(canvas, p.holder.firstChild);
    p.page.render({ canvasContext: canvas.getContext('2d'), viewport: p.page.getViewport({ scale: p.vp.scale * dpr }) }).promise.catch(() => {});
    const tl = el('div', 'textLayer');
    p.holder.insertBefore(tl, p.hl);
    try { await new pdfjs.TextLayer({ textContentSource: p.page.streamTextContent(), container: tl, viewport: p.vp }).render(); }
    catch (e) { /* a page without text: highlights simply aren't possible there */ }
  }

  /* ---------------------------------------------------------------- highlights */
  selectionBar() {
    const s = getSelection();
    if (s.isCollapsed || !s.rangeCount || !this.view.contains(s.anchorNode)) { this.bar.hidden = true; return; }
    const r = s.getRangeAt(0).getBoundingClientRect();
    this.bar.hidden = false;
    this.bar.style.left = Math.max(8, Math.min(window.innerWidth - this.bar.offsetWidth - 8, r.left + r.width / 2 - this.bar.offsetWidth / 2)) + 'px';
    this.bar.style.top = Math.max(8, r.top - this.bar.offsetHeight - 8) + 'px';
  }

  highlight(color) {
    const s = getSelection();
    if (s.isCollapsed || !s.rangeCount || !this.view.contains(s.anchorNode)) return null;
    const range = s.getRangeAt(0);
    const text = s.toString().replace(/\s+/g, ' ').trim();
    const byPage = new Map();
    Array.from(range.getClientRects()).forEach(r => {
      if (r.width < 1 || r.height < 1) return;
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const p = this.pages.find(pg => { const b = pg.holder.getBoundingClientRect(); return cx >= b.left && cx <= b.right && cy >= b.top && cy <= b.bottom; });
      if (!p) return;
      const b = p.holder.getBoundingClientRect();
      if (!byPage.has(p.n)) byPage.set(p.n, []);
      byPage.get(p.n).push([(r.left - b.left) / b.width, (r.top - b.top) / b.height, r.width / b.width, r.height / b.height]);
    });
    if (!byPage.size) return null;
    let first = null;
    byPage.forEach((rects, n) => {
      const a = { id: uid(), page: n, rects: mergeLines(rects), text, comment: '', color, created: new Date().toISOString(), dirty: true };
      this.anns.push(a);
      if (!first) first = a;
      this.paintHighlights(n);
    });
    s.removeAllRanges(); this.bar.hidden = true;
    this.changed();
    return first;
  }

  paintHighlights(n) {
    const p = this.pages[n - 1];
    if (!p) return;
    p.hl.textContent = '';
    this.anns.filter(a => a.page === n).forEach(a => {
      a.rects.forEach(r => {
        const d = el('div', 'hl ' + (a.color || 'yellow') + (a.comment ? ' has-note' : ''));
        d.style.left = (r[0] * 100) + '%'; d.style.top = (r[1] * 100) + '%';
        d.style.width = (r[2] * 100) + '%'; d.style.height = (r[3] * 100) + '%';
        d.dataset.id = a.id;
        d.title = a.comment || a.text;
        d.onclick = e => { e.stopPropagation(); this.editAnn(a); };
        p.hl.appendChild(d);
      });
    });
  }

  changed() { this.renderList(); if (this.opts.onChange) this.opts.onChange(this.anns); }

  renderList() {
    this.list.textContent = '';
    this.list.appendChild(el('div', 'ann-head', this.anns.length ? this.anns.length + ' highlight' + (this.anns.length === 1 ? '' : 's') : 'No highlights yet'));
    if (!this.anns.length) {
      this.list.appendChild(el('div', 'hint', 'Select text in the document, then pick a color. Click a highlight to add a comment.'));
      return;
    }
    this.anns.slice().sort((a, b) => a.page - b.page || a.rects[0][1] - b.rects[0][1]).forEach(a => {
      const item = el('div', 'ann-item ' + (a.color || 'yellow'));
      item.appendChild(el('div', 'ann-page', 'p. ' + a.page));
      item.appendChild(el('div', 'ann-text', '“' + (a.text.length > 220 ? a.text.slice(0, 220) + '…' : a.text) + '”'));
      if (a.comment) item.appendChild(el('div', 'ann-comment', a.comment));
      item.onclick = () => this.reveal(a);
      this.list.appendChild(item);
    });
  }

  reveal(a) {
    const p = this.pages[a.page - 1];
    if (!p) return;
    this.view.scrollTop = p.holder.offsetTop + a.rects[0][1] * p.holder.offsetHeight - 80;
    setTimeout(() => {
      p.hl.querySelectorAll('[data-id="' + a.id + '"]').forEach(d => { d.classList.add('flash'); setTimeout(() => d.classList.remove('flash'), 900); });
    }, 50);
  }

  closePop() { if (this.pop) { this.pop.remove(); this.pop = null; } }

  editAnn(a) {
    this.closePop();
    const pop = this.pop = el('div', 'chip-pop ann-pop');
    pop.appendChild(el('div', 'ann-text', '“' + (a.text.length > 300 ? a.text.slice(0, 300) + '…' : a.text) + '” (p. ' + a.page + ')'));
    const ta = el('textarea'); ta.rows = 4; ta.placeholder = 'Your comment'; ta.value = a.comment || '';
    ta.addEventListener('input', () => { a.comment = ta.value; a.dirty = true; this.paintHighlights(a.page); this.changed(); });
    pop.appendChild(ta);
    const row = el('div', 'row');
    COLORS.forEach(c => {
      const b = el('button', 'hl-swatch ' + c + (a.color === c ? ' on' : '')); b.type = 'button'; b.title = c;
      b.onclick = () => { a.color = c; a.dirty = true; this.paintHighlights(a.page); this.changed(); row.querySelectorAll('.hl-swatch').forEach(x => x.classList.toggle('on', x === b)); };
      row.appendChild(b);
    });
    const copy = el('button', 'btn small', 'Copy quote'); copy.type = 'button';
    copy.onclick = async () => { try { await navigator.clipboard.writeText('“' + a.text + '”'); copy.textContent = 'Copied'; } catch (e) { /* no clipboard */ } };
    const del = el('button', 'btn small danger', 'Delete'); del.type = 'button';
    del.onclick = () => { this.anns = this.anns.filter(x => x !== a); this.paintHighlights(a.page); this.closePop(); this.changed(); };
    const done = el('button', 'btn small primary', 'Done'); done.type = 'button'; done.onclick = () => this.closePop();
    row.append(copy, del, done);
    pop.appendChild(row);
    document.body.appendChild(pop);
    const p = this.pages[a.page - 1];
    const box = p ? p.hl.querySelector('[data-id="' + a.id + '"]') : null;
    const r = box ? box.getBoundingClientRect() : this.view.getBoundingClientRect();
    const w = Math.min(380, window.innerWidth - 24);
    pop.style.width = w + 'px';
    pop.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left)) + 'px';
    const h = pop.offsetHeight;
    pop.style.top = (r.bottom + 8 + h < window.innerHeight ? r.bottom + 8 : Math.max(8, r.top - h - 8)) + 'px';
    ta.focus();
    const away = e => { if (this.pop && !this.pop.contains(e.target)) { this.closePop(); document.removeEventListener('mousedown', away, true); } };
    setTimeout(() => document.addEventListener('mousedown', away, true), 0);
  }
}

// Text spans give one rect per span; join the ones on the same line into one box.
function mergeLines(rects) {
  const out = [];
  rects.slice().sort((a, b) => a[1] - b[1] || a[0] - b[0]).forEach(r => {
    const last = out[out.length - 1];
    if (last && Math.abs(last[1] - r[1]) < r[3] * 0.5 && r[0] <= last[0] + last[2] + 0.02) {
      const x0 = Math.min(last[0], r[0]), x1 = Math.max(last[0] + last[2], r[0] + r[2]);
      const y0 = Math.min(last[1], r[1]), y1 = Math.max(last[1] + last[3], r[1] + r[3]);
      last[0] = x0; last[1] = y0; last[2] = x1 - x0; last[3] = y1 - y0;
    } else out.push(r.slice());
  });
  return out;
}

window.Reader = Reader;
