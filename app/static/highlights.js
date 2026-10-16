/* Highlight colors: twelve of them, each with a label you choose (Holding, Dicta, Quote…).
 * The labels are shared by every project (library/highlights.json) and set in project setup.
 *   App.highlights.colors   [{id, hex, label}]
 *   App.highlights.name(id) the label, or the color's name when it has none
 *   App.highlights.save(labels) {id: label}
 *   App.highlights.onChange(fn)
 */
(function () {
  'use strict';
  const { api, put } = App;
  const DEFAULT = [['yellow', '#ffd60a'], ['green', '#5fcf7a'], ['blue', '#6aaeff'], ['pink', '#ff7fbf'], ['orange', '#ffa043'],
    ['red', '#ff6161'], ['purple', '#a98bff'], ['teal', '#2fc7bf'], ['lime', '#b5e655'], ['brown', '#c79a6b'], ['gray', '#a7b0ba'],
    ['indigo', '#6f86ff']];
  const H = App.highlights = { colors: DEFAULT.map(([id, hex]) => ({ id, hex, label: '' })), listeners: [] };
  const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
  H.get = id => H.colors.find(c => c.id === id) || H.colors[0];
  H.name = id => { const c = H.get(id); return c.label || cap(c.id); };
  H.onChange = fn => H.listeners.push(fn);

  // one stylesheet for every place a color shows: highlights, swatches, list items, menu swatches
  const style = document.createElement('style');
  document.head.appendChild(style);
  function paintCss() {
    style.textContent = H.colors.map(c => {
      const n = parseInt(c.hex.slice(1), 16), rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(',');
      return `.hl.${c.id}{background:rgba(${rgb},.45)}.hl-swatch.${c.id},.ctx-swatch.${c.id}{background:${c.hex}}.ann-item.${c.id}{border-color:${c.hex}}`;
    }).join('\n');
  }
  function fire() { paintCss(); H.listeners.forEach(fn => { try { fn(); } catch (e) { console.error(e); } }); }
  H.load = async () => { try { H.colors = (await api('/api/highlights')).colors; } catch (e) { /* keep defaults */ } fire(); };
  H.save = async labels => { H.colors = (await put('/api/highlights', { labels })).colors; fire(); };

  // The twelve colors with a text field each: used in project setup.
  H.editor = function () {
    const box = document.createElement('div');
    box.className = 'hl-labels';
    H.colors.forEach(c => {
      const row = document.createElement('label');
      row.className = 'hl-label-row';
      const sw = document.createElement('span'); sw.className = 'hl-swatch ' + c.id;
      const inp = document.createElement('input'); inp.value = c.label; inp.placeholder = cap(c.id); inp.maxLength = 40;
      inp.dataset.color = c.id; inp.setAttribute('aria-label', 'Label for ' + c.id);
      row.append(sw, inp);
      box.appendChild(row);
    });
    box.values = () => Object.fromEntries([...box.querySelectorAll('input')].map(i => [i.dataset.color, i.value.trim()]));
    return box;
  };
  paintCss();
  H.load();
})();
