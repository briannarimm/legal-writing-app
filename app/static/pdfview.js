/* PDF preview, drawn with PDF.js so the zoom setting works the same everywhere (the browsers' own
 * built-in PDF viewers each handle zoom differently, and some ignore it).
 *
 *   PDFView.open(url)      load (or reload) a PDF into the preview and draw it
 *   PDFView.setZoom(z)     'fit' (fit the pane's width) or a percentage such as 100 or 125
 *   PDFView.refresh()      redraw, for example when the pane becomes visible
 *
 * 100% means actual size: a Letter page is 8.5 inches wide at the screen's 96 pixels per inch. */
import * as pdfjs from '/static/vendor/pdfjs/pdf.min.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';

const view = document.getElementById('pdf-view');
let doc = null;
let task = null;          // the loading task: it is what owns the document and can free it
let docUrl = '';
let zoom = 100;
let drawId = 0;
let observer = null;

function scaleFor(page) {
  const natural = page.getViewport({ scale: 1 });
  if (zoom === 'fit') return Math.max(0.2, (view.clientWidth - 32) / natural.width);
  return (zoom / 100) * (96 / 72);
}

async function drawNow() {
  if (!doc || !view.clientWidth) return;               // hidden panes have no width; redrawn when shown
  const id = ++drawId;
  const keep = view.scrollHeight ? view.scrollTop / view.scrollHeight : 0;
  if (observer) observer.disconnect();
  view.textContent = '';
  const dpr = window.devicePixelRatio || 1;
  const holders = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    if (id !== drawId) return;
    const vp = page.getViewport({ scale: scaleFor(page) });
    const holder = document.createElement('div');
    holder.className = 'pdf-page';
    holder.style.width = Math.floor(vp.width) + 'px';
    holder.style.height = Math.floor(vp.height) + 'px';
    holder.dataset.n = n;
    view.appendChild(holder);
    holders.push({ holder, page, vp });
  }
  view.scrollTop = keep * view.scrollHeight;
  // draw pages as they come into view, so a long brief doesn't render all at once
  observer = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      const item = holders[+e.target.dataset.n - 1];
      if (item.done) continue;
      item.done = true;
      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(item.vp.width * dpr);
      canvas.height = Math.floor(item.vp.height * dpr);
      canvas.style.width = item.holder.style.width;
      canvas.style.height = item.holder.style.height;
      item.holder.appendChild(canvas);
      item.page.render({ canvasContext: canvas.getContext('2d'), viewport: item.page.getViewport({ scale: item.vp.scale * dpr }),
                         transform: null }).promise.catch(() => {});
    }
  }, { root: view, rootMargin: '800px 0px' });
  holders.forEach(h => observer.observe(h.holder));
}

// A redraw can be superseded (zoom changed again, new file loaded); swallow that, show anything else.
async function draw() {
  try { await drawNow(); }
  catch (e) { if (!/destroy|cancel/i.test(String((e && e.message) || e))) console.error(e); }
}

async function open(url) {
  const key = url.split('?')[0];
  try {
    const data = await (await fetch(url)).arrayBuffer();
    const nextTask = pdfjs.getDocument({ data });
    const next = await nextTask.promise;
    drawId++;                      // stop any redraw still working on the old file
    const old = task;
    doc = next; task = nextTask; docUrl = key;
    if (old) { try { await old.destroy(); } catch (e) { /* already gone */ } }
    await draw();
  } catch (e) {
    view.textContent = '';
    const msg = document.createElement('div');
    msg.className = 'empty';
    msg.textContent = 'Couldn’t show this PDF: ' + e.message;
    view.appendChild(msg);
  }
}

let resizeTimer;
new ResizeObserver(() => { if (zoom === 'fit') { clearTimeout(resizeTimer); resizeTimer = setTimeout(draw, 150); } }).observe(view);

// The zoom actually in effect, as a percentage (for 'fit', whatever fit works out to).
function percent() {
  if (zoom !== 'fit') return zoom;
  const first = view.querySelector('.pdf-page');
  return first ? Math.round((parseFloat(first.style.width) / 816) * 100) : 100;
}

window.PDFView = {
  percent,
  open,
  setZoom(z) { zoom = z === 'fit' ? 'fit' : parseInt(z, 10) || 100; draw(); },
  refresh() { draw(); },
};
