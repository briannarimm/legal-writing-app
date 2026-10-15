/* Markdown <-> editor HTML, for the subset of Pandoc Markdown this article uses:
 * paragraphs, headings (# to ####, with {.unnumbered}), *italics*, **bold**,
 * [small caps]{.smallcaps}, [links](url), `code`, block quotes, simple lists,
 * and [^label] footnotes.
 *
 * Anything else (tables, raw LaTeX, HTML comments, math, citations...) is kept as
 * a "raw" block, shown as plain text in the editor and written back untouched,
 * so nothing is ever silently rewritten or lost.
 *
 * Export puts each sentence of a body paragraph on its own line, so git diffs
 * and redlines show which sentence changed. Pandoc joins them back up.
 */
(function (global) {
  'use strict';

  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const escAttr = s => esc(s).replace(/"/g, '&quot;');

  /* ===================== Markdown -> HTML ===================== */

  function matchBracket(s, i) {
    let depth = 0;
    for (let k = i; k < s.length; k++) {
      const c = s[k];
      if (c === '\\') { k++; continue; }
      if (c === '[') depth++;
      else if (c === ']') { depth--; if (depth === 0) return k; }
    }
    return -1;
  }

  function findClose(s, from, c, d) {
    for (let k = from; k < s.length; k++) {
      if (s[k] === '\\') { k++; continue; }
      if (s[k] === c) {
        let r = 1;
        while (s[k + r] === c) r++;
        const prev = s[k - 1];
        const ok = r === d && k > from && !/\s/.test(prev) && !(c === '_' && /\w/.test(s[k + r] || ''));
        if (ok) return k;
        k += r - 1;
      }
    }
    return -1;
  }

  const CITE_ATTRS = ['tag', 'pin', 'signal', 'paren', 'narrative', 'form'];
  function citeChip(attrs, html) {
    let a = '';
    CITE_ATTRS.forEach(k => { if (attrs[k]) a += ' data-' + k + '="' + escAttr(attrs[k]) + '"'; });
    return '<span class="cite" contenteditable="false"' + a + '>' + html + '</span>';
  }
  function citeAttrs(el) {
    const q = v => '"' + v.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
    return CITE_ATTRS.filter(k => el.dataset[k]).map(k => ' ' + k + '=' + q(el.dataset[k])).join('');
  }

  // Returns { html, lossy }. lossy = contains something we can't round-trip.
  function inlineToHtml(src) {
    let lossy = false;
    function parse(s) {
      let out = '';
      let i = 0;
      while (i < s.length) {
        const c = s[i];
        if (c === '\\') {
          const n = s[i + 1];
          if (n === '\n') { out += '<br>'; i += 2; continue; }
          if (n && /[!-\/:-@\[-`{-~]/.test(n)) { out += esc(n); i += 2; continue; }
          out += '\\'; i++; continue;
        }
        if (c === '[') {
          const fm = /^\[\^([^\]\s]+)\]/.exec(s.slice(i));
          if (fm) {
            out += '<span class="fnref" data-label="' + escAttr(fm[1]) + '" contenteditable="false"></span>';
            i += fm[0].length; continue;
          }
          const close = matchBracket(s, i);
          if (close > 0) {
            const inner = s.slice(i + 1, close);
            const rest = s.slice(close + 1);
            let m;
            if (rest.startsWith('{.smallcaps}')) {
              out += '<span class="sc">' + parse(inner) + '</span>';
              i = close + 1 + '{.smallcaps}'.length; continue;
            }
            if ((m = /^\{\.cite((?:\s+[a-z]+="(?:\\.|[^"\\])*")*)\s*\}/.exec(rest))) {
              // a live citation: the attributes point at the library; the text is what the chip last showed
              const attrs = {};
              m[1].replace(/([a-z]+)="((?:\\.|[^"\\])*)"/g, (all, k, v) => { attrs[k] = v.replace(/\\(.)/g, '$1'); return ''; });
              if (!attrs.tag) { lossy = true; out += '['; i++; continue; }
              out += citeChip(attrs, parse(inner));
              i = close + 1 + m[0].length; continue;
            }
            if ((m = /^\{\.auth tag="([^"]+)"\}/.exec(rest))) {
              out += '<span class="auth" data-tag="' + escAttr(m[1]) + '" title="Listed in the table of authorities">' + parse(inner) + '</span>';
              i = close + 1 + m[0].length; continue;
            }
            if ((m = /^\(([^()\s]*)\)/.exec(rest))) {
              out += '<a href="' + escAttr(m[1]) + '">' + parse(inner) + '</a>';
              i = close + 1 + m[0].length; continue;
            }
          }
          // A bracket that isn't a footnote, span or link is just text ([T]he, [sic], [date]).
          // Only syntax we can't round-trip (citations, other attributes) makes the paragraph raw.
          if (close > 0) {
            const inner = s.slice(i + 1, close), rest = s.slice(close + 1);
            if (rest.startsWith('{') || /^-?@/.test(inner) || rest.startsWith('[')) lossy = true;
          }
          out += '['; i++; continue;
        }
        if (c === '*' || c === '_') {
          let run = 1;
          while (s[i + run] === c) run++;
          const d = Math.min(run, 3);
          const intraword = c === '_' && i > 0 && /\w/.test(s[i - 1]);
          const opener = !intraword && s[i + d] !== undefined && !/\s/.test(s[i + d]);
          const j = opener ? findClose(s, i + d, c, d) : -1;
          if (j > 0) {
            const inner = parse(s.slice(i + d, j));
            out += d === 1 ? '<em>' + inner + '</em>'
                 : d === 2 ? '<strong>' + inner + '</strong>'
                 : '<strong><em>' + inner + '</em></strong>';
            i = j + d; continue;
          }
          out += c.repeat(run); i += run; continue;
        }
        if (c === '`') {
          const j = s.indexOf('`', i + 1);
          if (j > 0) { out += '<code>' + esc(s.slice(i + 1, j)) + '</code>'; i = j + 1; continue; }
        }
        if (c === '<' && /[A-Za-z\/!]/.test(s[i + 1] || '')) lossy = true;
        if (c === '$' || c === '^' || c === '~') lossy = true;
        out += esc(c);
        i++;
      }
      return out;
    }
    const html = parse(src);
    return { html, lossy };
  }

  function rawBlockHtml(text, kind) {
    return '<div class="raw" data-kind="' + kind + '" contenteditable="plaintext-only">' + esc(text) + '</div>';
  }

  const RAW_START = /^(\||:::|```|~~~|\\begin|\\[a-zA-Z]+\{|(-{3,}|\*{3,}|_{3,})\s*$|<|\[[^\]]+\]:\s|Table:|\s{4,}\S|\t)/;

  function paragraphLines(lines) {
    // join soft line breaks with a space; a trailing backslash is a hard break
    let s = '';
    lines.forEach((ln, idx) => {
      const t = ln.trim();
      if (idx > 0) s += /\\$/.test(s) ? '\n' : ' ';
      s += t;
    });
    return s.replace(/\\\n/g, '\\\n');
  }

  function paragraphToHtml(lines, tag) {
    const text = paragraphLines(lines);
    const r = inlineToHtml(text);
    if (r.lossy) return null;
    return '<' + tag + '>' + r.html + '</' + tag + '>';
  }

  function blockToHtml(lines) {
    const first = lines[0];
    // HTML comment at the top of a block: keep it raw, parse the rest separately
    if (/^<!--/.test(first)) {
      const joined = lines.join('\n');
      const end = joined.indexOf('-->');
      if (end >= 0) {
        const commentLines = joined.slice(0, end + 3).split('\n');
        const rest = joined.slice(end + 3).replace(/^\n+/, '');
        let html = rawBlockHtml(commentLines.join('\n'), 'comment');
        if (rest.trim()) html += blockToHtml(rest.split('\n'));
        return html;
      }
      return rawBlockHtml(joined, 'raw');
    }
    const raw = () => rawBlockHtml(lines.join('\n'), 'raw');

    const h = /^(#{1,6})\s+(.*?)\s*(?:\{([^}]*)\})?\s*$/.exec(first);
    if (h && lines.length === 1) {
      const level = h[1].length;
      if (level > 4) return raw();
      const r = inlineToHtml(h[2].replace(/\s+#+$/, ''));
      if (r.lossy) return raw();
      return '<h' + level + (h[3] ? ' data-attrs="' + escAttr(h[3].trim()) + '"' : '') + '>' + r.html + '</h' + level + '>';
    }
    if (h && lines.length > 1) {
      return blockToHtml([first]) + blockToHtml(lines.slice(1));
    }
    if (RAW_START.test(first)) return raw();

    if (lines.every(l => /^>/.test(l))) {
      const inner = lines.map(l => l.replace(/^> ?/, ''));
      const paras = [];
      let cur = [];
      inner.forEach(l => { if (l.trim() === '') { if (cur.length) paras.push(cur); cur = []; } else cur.push(l); });
      if (cur.length) paras.push(cur);
      const htmls = paras.map(p => RAW_START.test(p[0]) || /^[#>]/.test(p[0]) ? null : paragraphToHtml(p, 'p'));
      if (htmls.length && htmls.every(Boolean)) return '<blockquote>' + htmls.join('') + '</blockquote>';
      return raw();
    }

    const li = /^([-*+]|\d+[.)])\s+/;
    if (li.test(first)) {
      const ordered = /^\d/.test(first);
      const items = [];
      let ok = true;
      lines.forEach(l => {
        if (li.test(l)) {
          if (/^\d/.test(l) !== ordered) ok = false;
          items.push([l.replace(li, '')]);
        } else if (/^\s+([-*+]|\d+[.)])\s/.test(l)) ok = false;   // nested list
        else items[items.length - 1].push(l);
      });
      if (ok) {
        const htmls = items.map(it => {
          const r = inlineToHtml(paragraphLines(it));
          return r.lossy ? null : '<li>' + r.html + '</li>';
        });
        if (htmls.every(Boolean)) return (ordered ? '<ol>' : '<ul>') + htmls.join('') + (ordered ? '</ol>' : '</ul>');
      }
      return raw();
    }

    return paragraphToHtml(lines, 'p') || raw();
  }

  // Returns { docHtml, notes: {label: html}, order: [labels referenced], orphans: [{label, md}] }
  function parse(md) {
    const lines = md.replace(/\r\n?/g, '\n').split('\n');
    const bodyLines = [];
    const defs = {};      // label -> array of paragraphs (each array of lines)
    const defOrder = [];
    for (let i = 0; i < lines.length; i++) {
      const m = /^\[\^([^\]\s]+)\]:[ \t]?(.*)$/.exec(lines[i]);
      if (!m) { bodyLines.push(lines[i]); continue; }
      const label = m[1];
      const paras = [[m[2]]];
      let j = i + 1;
      while (j < lines.length) {
        if (/^( {4}|\t)\S/.test(lines[j])) { paras[paras.length - 1].push(lines[j].trim()); j++; continue; }
        if (lines[j].trim() === '') {
          let k = j;
          while (k < lines.length && lines[k].trim() === '') k++;
          if (k < lines.length && /^( {4}|\t)\S/.test(lines[k])) { paras.push([]); j = k; continue; }
        }
        break;
      }
      defs[label] = paras;
      defOrder.push(label);
      i = j - 1;
    }

    // split body into blocks on blank lines (not inside fenced code)
    const blocks = [];
    let cur = [];
    let fence = false;
    bodyLines.forEach(ln => {
      if (/^(```|~~~)/.test(ln)) fence = !fence;
      if (!fence && ln.trim() === '') { if (cur.length) blocks.push(cur); cur = []; }
      else cur.push(ln);
    });
    if (cur.length) blocks.push(cur);

    const docHtml = blocks.map(blockToHtml).join('');

    const order = [];
    const re = /<span class="fnref" data-label="([^"]*)"/g;
    let m;
    while ((m = re.exec(docHtml))) {
      const lab = m[1].replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
      if (!order.includes(lab)) order.push(lab);
    }
    const notes = {};
    const orphans = [];
    defOrder.forEach(label => {
      const paras = defs[label].filter(p => p.length);
      let html = '';
      let lossy = false;
      const parts = paras.map(p => {
        const r = inlineToHtml(paragraphLines(p));
        if (r.lossy) lossy = true;
        return r.html;
      });
      if (lossy) html = rawBlockHtml(paras.map(p => p.join(' ')).join('\n\n'), 'raw');
      else html = parts.map(x => '<div>' + x + '</div>').join('');
      if (order.includes(label)) notes[label] = html;
      else orphans.push({ label, md: noteMdFromParas(paras) });
    });
    return { docHtml, notes, order, orphans };
  }

  function noteMdFromParas(paras) {
    return paras.map((p, i) => (i ? '    ' : '') + p.join(' ')).join('\n\n');
  }

  /* ===================== HTML -> Markdown ===================== */

  const BLOCK_TAGS = new Set(['P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'UL', 'OL', 'LI']);

  function escText(s) {
    // Brackets are left alone unless they could be read as syntax: [^note], [@cite], ](url), ]{attrs}, ][ref].
    return s.replace(/[\\`*<$^~@]/g, '\\$&')
      // underscores: leave blank-fill runs ("__", "____") alone; escape the rest so they can't italicize
      .replace(/_+/g, (m, off, str) => (m.length >= 2 && !/\w/.test(str[off - 1] || ' ') && !/\w/.test(str[off + m.length] || ' '))
        ? m : m.replace(/_/g, '\\_'))
      .replace(/\[(?=[\^@])/g, '\\[')
      .replace(/\](?=[(\[{])/g, '\\]');
  }

  function wrap(inner, d) {
    const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner);
    if (!m[2]) return m[1] + m[3];
    return m[1] + d + m[2] + d + m[3];
  }

  function inlineMd(node, inEm, inStrong) {
    let out = '';
    node.childNodes.forEach(ch => {
      if (ch.nodeType === 3) { out += escText(ch.nodeValue.replace(/\u200b/g, '').replace(/[\u00a0\s]+/g, ' ')); return; }
      if (ch.nodeType !== 1) return;
      const t = ch.tagName;
      if (ch.classList.contains('fnref')) out += '[^' + ch.dataset.label + ']';
      else if (t === 'EM' || t === 'I') out += inEm ? inlineMd(ch, true, inStrong) : wrap(inlineMd(ch, true, inStrong), '*');
      else if (t === 'STRONG' || t === 'B') out += inStrong ? inlineMd(ch, inEm, true) : wrap(inlineMd(ch, inEm, true), '**');
      else if (ch.classList.contains('cite')) {
        const inner = inlineMd(ch, false, false).trim();
        out += '[' + (inner || ch.dataset.tag) + ']{.cite' + citeAttrs(ch) + '}';
      }
      else if (ch.classList.contains('auth')) {
        const inner = inlineMd(ch, inEm, inStrong);
        out += inner.trim() ? '[' + inner + ']{.auth tag="' + ch.dataset.tag + '"}' : inner;
      }
      else if (ch.classList.contains('sc') || /small-caps/.test(ch.getAttribute('style') || '')) {
        const inner = inlineMd(ch, inEm, inStrong);
        const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner);
        out += m[2] ? m[1] + '[' + m[2] + ']{.smallcaps}' + m[3] : inner;
      }
      else if (t === 'A') out += '[' + inlineMd(ch, inEm, inStrong) + '](' + (ch.getAttribute('href') || '') + ')';
      else if (t === 'CODE') out += '`' + ch.textContent + '`';
      else if (t === 'BR') out += '\\\n';
      else out += inlineMd(ch, inEm, inStrong);
    });
    return out;
  }

  // merge adjacent identical inline wrappers (<em>a</em><em>b</em>) so we never emit *a**b*
  function mergeAdjacent(root) {
    const sameKind = (a, b) => a.nodeType === 1 && b.nodeType === 1 && a.tagName === b.tagName &&
      (a.tagName !== 'SPAN' || (a.className === b.className && a.classList.contains('sc'))) &&
      ['EM', 'I', 'STRONG', 'B', 'SPAN'].includes(a.tagName) && !a.classList.contains('fnref');
    (function walk(n) {
      let c = n.firstChild;
      while (c) {
        const next = c.nextSibling;
        if (next && sameKind(c, next)) { while (next.firstChild) c.appendChild(next.firstChild); next.remove(); continue; }
        if (c.nodeType === 1) walk(c);
        c = c.nextSibling;
      }
    })(root);
  }

  // Sentence-per-line splitting.
  const ABBR = new Set(('v vs no nos inc corp co ltd cir supp app dist ct cl cf mr mrs ms dr st mo stat rev ann sec art ch jr sr ' +
    'fed reg ed eds op pp para paras cong sess univ assn dep dept comm ex rel ill cal tex pa ky wash mass conn okla kan neb ' +
    'ariz fla ga ind md mich minn miss mont nev tenn va wis wyo pt vol cmt subsec e.g i.e etc').split(' '));

  function splitSentences(text) {
    const re = /([.?!])((?:["'”’)\]*_]|\[\^[^\]\s]+\])*)([ \t]+)(?=["“‘'(*_\[]*[A-Z])/g;
    let out = '';
    let last = 0;
    let m;
    while ((m = re.exec(text))) {
      const before = text.slice(0, m.index);
      // not inside [brackets] (small caps, links) or *italics* (the closing brackets right after
      // the period count as closed, so "[Probably yes.] The..." splits)
      const upto = before + m[1] + m[2];
      let depth = 0, stars = 0;
      for (let k = 0; k < upto.length; k++) {
        const c = upto[k];
        if (c === '\\') { k++; continue; }
        if (c === '[' || c === '{') depth++;
        else if (c === ']' || c === '}') depth--;
        else if (c === '*') stars++;
      }
      if (depth > 0 || stars % 2 === 1) continue;
      if (m[1] === '.') {
        const word = (before.match(/(\S+)$/) || [''])[0].replace(/^[*_(\[“"'‘]+/, '').replace(/[*_)\]]+$/, '');
        const w = word.replace(/\.$/, '').toLowerCase();
        if (ABBR.has(w) || /^[A-Za-z]$/.test(w) || /^([A-Za-z]\.)+[A-Za-z]$/.test(w)) continue;
        if (/^[ivxlc]+$/i.test(w) && /^[IVXLC]+$/.test(word.replace(/\.$/, ''))) continue; // roman numerals: "Part II. The"
      }
      const end = m.index + m[1].length + m[2].length;
      out += text.slice(last, end) + '\n';
      last = m.index + m[0].length;
    }
    return out + text.slice(last);
  }

  function escLineStart(line) {
    return line.replace(/^(#{1,6})(?=\s|$)/, '\\$1')
      .replace(/^>/, '\\>')
      .replace(/^([-+])(?=\s)/, '\\$1')
      .replace(/^(\d+)([.)])(?=\s)/, '$1\\$2')
      .replace(/^(```|~~~|:::)/, '\\$1');
  }

  function paragraphMd(el, split) {
    const clone = el.cloneNode(true);
    mergeAdjacent(clone);
    let s = inlineMd(clone).replace(/(\\\n)+$/, '').replace(/^\s+/, '').replace(/[ \t]+$/g, '');
    s = s.replace(/[ \t]{2,}/g, ' ').replace(/ ?\n ?/g, '\n');
    if (!s.trim()) return '';
    if (split) s = s.split('\n').map(splitSentences).join('\n');
    return s.split('\n').map(escLineStart).join('\n');
  }

  function oneLine(el) {
    const clone = el.cloneNode(true);
    mergeAdjacent(clone);
    return inlineMd(clone).replace(/\\\n/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function blocksMd(container, split) {
    const out = [];
    let inlineRun = null;
    const flush = () => {
      if (inlineRun) {
        const s = paragraphMd(inlineRun, split);
        if (s) out.push(s);
        inlineRun = null;
      }
    };
    container.childNodes.forEach(n => {
      if (n.nodeType === 1 && n.classList.contains('raw')) {
        flush();
        const txt = n.textContent.replace(/\n+$/, '');
        if (txt.trim()) out.push(txt);
      } else if (n.nodeType === 1 && BLOCK_TAGS.has(n.tagName)) {
        flush();
        const t = n.tagName;
        if (/^H[1-6]$/.test(t)) {
          const txt = oneLine(n);
          if (txt) out.push('#'.repeat(+t[1]) + ' ' + txt + (n.dataset.attrs ? ' {' + n.dataset.attrs + '}' : ''));
        } else if (t === 'BLOCKQUOTE') {
          const inner = blocksMd(n, split).join('\n\n');
          if (inner.trim()) out.push(inner.split('\n').map(l => l ? '> ' + l : '>').join('\n'));
        } else if (t === 'UL' || t === 'OL') {
          const items = [];
          n.querySelectorAll(':scope > li').forEach((li, i) => {
            const txt = oneLine(li);
            if (txt) items.push((t === 'UL' ? '- ' : (i + 1) + '. ') + txt);
          });
          if (items.length) out.push(items.join('\n'));
        } else if (t === 'P' || t === 'DIV') {
          if (n.querySelector(':scope > p, :scope > div, :scope > ul, :scope > ol, :scope > h1, :scope > h2, :scope > h3, :scope > h4')) {
            blocksMd(n, split).forEach(x => out.push(x));
          } else {
            const s = paragraphMd(n, split);
            if (s) out.push(s);
          }
        }
      } else if (n.nodeType === 3 || n.nodeType === 1) {
        if (!inlineRun) inlineRun = document.createElement('p');
        inlineRun.appendChild(n.cloneNode(true));
      }
    });
    flush();
    return out;
  }

  function noteMd(bodyEl) {
    const raw = bodyEl.querySelector(':scope > .raw');
    if (raw) {
      return raw.textContent.split(/\n\n/).map((p, i) => (i ? '    ' : '') + p.replace(/\n/g, ' ').trim()).join('\n\n');
    }
    const paras = blocksMd(bodyEl, false).map(s => s.replace(/\n/g, ' '));
    return paras.map((p, i) => (i ? '    ' : '') + p).join('\n\n');
  }

  // docEl: the editor; noteBodies: Map(label -> note body element); orphans from parse()
  function exportMd(docEl, noteBodies, orphans, opts) {
    const parts = blocksMd(docEl, !(opts && opts.split === false));
    const labels = [];
    docEl.querySelectorAll('.fnref').forEach(r => {
      if (!labels.includes(r.dataset.label)) labels.push(r.dataset.label);
    });
    labels.forEach(label => {
      const body = noteBodies.get(label);
      const text = body ? noteMd(body) : '';
      parts.push('[^' + label + ']: ' + text);
    });
    (orphans || []).forEach(o => {
      if (!labels.includes(o.label)) parts.push('[^' + o.label + ']: ' + o.md);
    });
    return parts.join('\n\n') + '\n';
  }

  /* ===================== counting (for numbering across files) ===================== */

  function countRefs(md) {
    const labels = [];
    md.split('\n').forEach(l => {
      if (/^\[\^[^\]]+\]:/.test(l) || /^( {4}|\t)/.test(l)) return;
      const re = /\[\^([^\]\s]+)\]/g;
      let m;
      while ((m = re.exec(l))) if (!labels.includes(m[1])) labels.push(m[1]);
    });
    return labels;
  }

  function countH1(md) {
    return md.split('\n').filter(l => /^# /.test(l) && !/\{[^}]*unnumbered[^}]*\}\s*$/.test(l)).length;
  }

  // A single line of inline Markdown <-> HTML, for the citation and note fields.
  function inlineFromEl(el) { return oneLine(el); }
  function inlineHtml(md) { return inlineToHtml(md || '').html; }

  global.MD = { parse, exportMd, splitSentences, countRefs, countH1, rawBlockHtml, esc, inlineFromEl, inlineHtml, citeChip };
})(window);
