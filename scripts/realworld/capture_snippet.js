// AMT real-world exemplar capture, rwk-capture-1 (2026-11-02; file format rwk-capture-1, auto-scroll before capture).
// Paste the whole file into the DevTools console of the page you want to save, press Enter,
// type a file name at the prompt. Chrome downloads one JSON file.
//
// What it saves: the rendered DOM after the page's scripts ran (open shadow roots included,
// as <template shadowrootmode>), the page URL (query values hashed as below), viewport
// size, device pixel ratio, timestamp, user agent, the text of stylesheets the page lets it
// read, and per-element facts for the offline analyser (data-rwk-* attributes: hidden or not,
// font size and weight of text, box of images, tables and layout containers).
//
// What it removes or masks before the download (in a copy; the open page is not changed
// except for data-rwk-* attributes that exist for a few milliseconds while it reads styles):
//   - every <script> and <noscript> element, HTML comments, <base>, on* handler attributes,
//     nonce, integrity, srcdoc;
//   - <meta> elements whose name, property or http-equiv mentions csrf, token, nonce,
//     session, user, account, email, refresh;
//   - the value of every input (except the visible text of submit/reset/button inputs), the
//     text of every textarea, the content of contenteditable regions;
//   - query values and fragments of every URL (href, src, srcset, action, ...) become salted
//     hashes (h1x9k2...): two links to different destinations stay different within this
//     file, but the salt is random per capture and not saved, so the values cannot be
//     recovered or matched across files; parameter names stay; in-page anchors such as
//     href="#main" are kept;
//   - in page text and in visible-text/URL attributes: e-mail addresses -> [email],
//     runs of 6 or more digits (order, account, phone, card numbers) -> zeros,
//     token-like strings of 32+ letters/digits -> [token].
// It does not read cookies, localStorage, sessionStorage or IndexedDB and sends nothing over
// the network. It cannot recognise personal names or street addresses in page text: capture
// logged out, or logged in with a test account that holds no real personal data.
// Not captured: closed shadow roots, iframe contents, canvas pixels, stylesheets the page
// does not let scripts read (cross-origin CSS); the data-rwk-* facts stand in for them.

function rwkCapture(opts) {
  opts = opts || {};
  const VERSION = 'rwk-capture-1';
  const RE_EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/g;
  const RE_DIGITS = /\d(?:[ \-]?\d){5,}/g;
  const RE_TOKEN = /[A-Za-z0-9_\-]{32,}/g;
  const RE_META = /csrf|token|nonce|session|user|account|email|refresh/i;
  const URL_ATTRS = new Set(['href', 'src', 'action', 'formaction', 'poster', 'cite', 'data', 'ping', 'xlink:href', 'background', 'longdesc', 'data-src', 'data-href', 'data-url']);
  const TEXT_ATTRS = /^(title|alt|aria-label|aria-description|aria-valuetext|aria-roledescription|placeholder|value|content|label|data-.*)$/;
  const BOX_SEL = 'img,svg,picture,video,canvas,iframe,table,[role],header,nav,main,footer,aside,section,article,form,' +
    '[class*="head" i],[class*="nav" i],[class*="menu" i],[class*="foot" i],[class*="side" i],[class*="main" i],[class*="content" i],' +
    '[id*="head" i],[id*="nav" i],[id*="foot" i],[id*="side" i],[id*="main" i],[id*="content" i]';
  const stats = {elements: 0, shadow_roots: 0, scripts_removed: 0, values_cleared: 0, emails: 0, digit_runs: 0, tokens: 0, urls_stripped: 0,
                 css_inlined: 0, css_unreadable: 0, adopted_sheets: 0};

  // ---- 1. walk the live tree (light DOM + open shadow roots), document order
  const live = [], roots = [];
  (function walk(parent) {
    for (const el of parent.children) {
      live.push(el);
      if (el.shadowRoot) { roots.push(el.shadowRoot); walk(el.shadowRoot); }
      walk(el.tagName === 'TEMPLATE' ? {children: []} : el);
    }
  })({children: [document.documentElement]});
  stats.elements = live.length; stats.shadow_roots = roots.length;

  // ---- 2. stamp computed facts on the live elements (removed again in step 4)
  const r1 = v => Math.round(v);
  const sx = window.scrollX, sy = window.scrollY;
  const stamped = [];
  const stamp = (el, k, v) => { el.setAttribute(k, v); stamped.push([el, k]); };
  live.forEach((el, i) => {
    let cs;
    try { cs = getComputedStyle(el); } catch (e) { return; }
    if (cs.display === 'none') { stamp(el, 'data-rwk-d', 'none'); return; }
    const pv = el.parentElement ? getComputedStyle(el.parentElement).visibility : 'visible';
    if (cs.visibility !== 'visible') stamp(el, 'data-rwk-v', 'h');
    else if (pv !== 'visible') stamp(el, 'data-rwk-v', 'v');
    let own = '';
    for (const c of el.childNodes) if (c.nodeType === 3) own += c.data;
    if (own.trim()) stamp(el, 'data-rwk-f', `${parseFloat(cs.fontSize).toFixed(1)}|${cs.fontWeight}|${cs.display}|${cs.textAlign}`);
    if (el.matches && el.matches(BOX_SEL)) {
      const b = el.getBoundingClientRect();
      stamp(el, 'data-rwk-box', `${r1(b.x + sx)},${r1(b.y + sy)},${r1(b.width)},${r1(b.height)}`);
      if (!own.trim() && el.matches('table,[role]')) stamp(el, 'data-rwk-f', `${parseFloat(cs.fontSize).toFixed(1)}|${cs.fontWeight}|${cs.display}|${cs.textAlign}`);
    }
    if (el.shadowRoot) stamp(el, 'data-rwk-sr', String(roots.indexOf(el.shadowRoot)));
  });
  const linkSheets = [...document.querySelectorAll('link[rel~="stylesheet" i]')].map(l => {
    try { return l.sheet ? [...l.sheet.cssRules].map(r => r.cssText).join('\n') : null; } catch (e) { return null; }
  });
  const sheetText = s => { try { return [...s.cssRules].map(r => r.cssText).join('\n'); } catch (e) { return null; } };
  const docAdopted = (document.adoptedStyleSheets || []).map(sheetText).filter(Boolean);
  const rootAdopted = roots.map(r => (r.adoptedStyleSheets || []).map(sheetText).filter(Boolean));

  // ---- 3. serialise (with the stamps), 4. remove the stamps from the live page
  let html;
  const de = document.documentElement;
  const openTag = '<html' + [...de.attributes].map(a => ` ${a.name}="${a.value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}"`).join('') + '>';
  try {
    html = typeof de.getHTML === 'function'
      ? openTag + de.getHTML({serializableShadowRoots: true, shadowRoots: roots}) + '</html>'
      : de.outerHTML;
  } finally {
    for (const [el, k] of stamped) el.removeAttribute(k);
  }

  // ---- 5. parse the copy (declarative shadow roots attach) and scrub it
  const doc = typeof Document.parseHTMLUnsafe === 'function'
    ? Document.parseHTMLUnsafe('<!DOCTYPE html>' + html)
    : new DOMParser().parseFromString('<!DOCTYPE html>' + html, 'text/html');
  const maskText = s => s
    .replace(RE_EMAIL, () => { stats.emails++; return '[email]'; })
    .replace(RE_TOKEN, () => { stats.tokens++; return '[token]'; })
    .replace(RE_DIGITS, m => { stats.digit_runs++; return m.replace(/\d/g, '0'); });
  // query values and fragments -> salted hashes: links to different destinations stay different
  // within this file; the salt is random per capture and not saved, so hashes cannot be reversed
  // or matched across files
  const SALT = (window.crypto && crypto.getRandomValues) ? crypto.getRandomValues(new Uint32Array(1))[0] : Math.floor(Math.random() * 4294967295);
  const hash = str => { let x = (0x811c9dc5 ^ SALT) >>> 0; for (let i = 0; i < str.length; i++) { x ^= str.charCodeAt(i); x = Math.imul(x, 0x01000193) >>> 0; } return 'h' + x.toString(36); };
  const stripUrl = v => {
    const t = v.trim();
    if (/^#[\w\-]{0,40}$/.test(t)) return t;
    if (/^data:/i.test(t)) return t;
    if (/^mailto:/i.test(t)) return 'mailto:[email]';
    if (/^tel:/i.test(t)) return 'tel:0';
    if (/^javascript:/i.test(t)) return 'javascript:';
    if (/^blob:/i.test(t)) return 'blob:';
    const cut = t.search(/[?#]/);
    if (cut < 0) return t;
    stats.urls_stripped++;
    const base = t.slice(0, cut), rest = t.slice(cut);
    const hi = rest.indexOf('#');
    const query = hi >= 0 ? rest.slice(0, hi) : rest, frag = hi >= 0 ? rest.slice(hi + 1) : null;
    let out = base;
    if (query.length > 1) out += '?' + query.slice(1).split('&').filter(Boolean).map(kv => {
      const i = kv.indexOf('='); const k = i >= 0 ? kv.slice(0, i) : kv;
      return maskText(k).slice(0, 40) + (i >= 0 ? '=' + hash(kv.slice(i + 1)) : '');
    }).join('&');
    if (frag !== null) out += '#' + hash(frag);
    return out;
  };
  const scrubTree = (root) => {
    const all = [...root.querySelectorAll('*')];
    for (const el of all) {
      const tag = el.tagName.toLowerCase();
      if (tag === 'script' || tag === 'noscript' || tag === 'base') { el.remove(); stats.scripts_removed++; continue; }
      if (tag === 'meta' && RE_META.test((el.getAttribute('name') || '') + ' ' + (el.getAttribute('property') || '') + ' ' + (el.getAttribute('http-equiv') || ''))) { el.remove(); continue; }
      if (tag === 'template' && el.content) scrubTree(el.content);
      if (el.shadowRoot) scrubTree(el.shadowRoot);
      for (const a of [...el.attributes]) {
        const n = a.name.toLowerCase();
        if (n.startsWith('on') || n === 'nonce' || n === 'integrity' || n === 'srcdoc') { el.removeAttribute(a.name); continue; }
        if (n.startsWith('data-rwk-')) continue;
        let v = a.value;
        if (URL_ATTRS.has(n)) v = stripUrl(v);
        else if (n === 'srcset' || n === 'imagesrcset') v = v.split(',').map(c => { const [u, ...d] = c.trim().split(/\s+/); return [stripUrl(u || ''), ...d].join(' '); }).join(', ');
        if (URL_ATTRS.has(n) || n === 'srcset' || TEXT_ATTRS.test(n)) { if (!/^data:/i.test(v)) v = maskText(v); }
        if (v !== a.value) el.setAttribute(a.name, v);
      }
      if (tag === 'input') {
        const ty = (el.getAttribute('type') || 'text').toLowerCase();
        if (!['submit', 'reset', 'button', 'image'].includes(ty) && el.hasAttribute('value')) { el.removeAttribute('value'); stats.values_cleared++; }
      }
      if (tag === 'textarea' && el.textContent) { el.textContent = ''; stats.values_cleared++; }
      const ce = el.getAttribute('contenteditable');
      if (ce !== null && ce.toLowerCase() !== 'false' && el.childNodes.length) { el.replaceChildren(); stats.values_cleared++; }
    }
    const tw = (root.ownerDocument || root).createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_COMMENT);
    const comments = [];
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (n.nodeType === 8) { comments.push(n); continue; }
      const p = n.parentNode && n.parentNode.nodeName;
      if (p === 'STYLE') continue;
      const m = maskText(n.data);
      if (m !== n.data) n.data = m;
    }
    comments.forEach(c => c.remove());
  };
  scrubTree(doc);
  // readable linked stylesheets become <style> elements in place; unreadable ones stay links
  const docLinks = [...doc.querySelectorAll('link[rel~="stylesheet" i]')];
  docLinks.forEach((l, i) => {
    const text = i < linkSheets.length ? linkSheets[i] : null;
    if (text === null) { stats.css_unreadable++; return; }
    const st = doc.createElement('style');
    st.setAttribute('data-rwk-css-from', l.getAttribute('href') || '');
    st.textContent = text; l.replaceWith(st); stats.css_inlined++;
  });
  for (const t of docAdopted) { const st = doc.createElement('style'); st.setAttribute('data-rwk-adopted', 'document'); st.textContent = t; doc.head.appendChild(st); stats.adopted_sheets++; }
  // adopted sheets of shadow roots go into the matching root (host stamped data-rwk-sr=k)
  const hostsIn = (root, out) => { for (const el of root.querySelectorAll('[data-rwk-sr]')) { out.push(el); if (el.shadowRoot) hostsIn(el.shadowRoot, out); } return out; };
  for (const host of hostsIn(doc, [])) {
    const k = +host.getAttribute('data-rwk-sr');
    const target = host.shadowRoot || (host.querySelector(':scope > template[shadowrootmode]') || {}).content;
    if (!target || !rootAdopted[k]) continue;
    for (const t of rootAdopted[k]) { const st = doc.createElement('style'); st.setAttribute('data-rwk-adopted', 'shadow'); st.textContent = t; target.appendChild(st); stats.adopted_sheets++; }
  }
  const docRoots = [];
  (function collect(r) { for (const el of r.querySelectorAll('*')) if (el.shadowRoot) { docRoots.push(el.shadowRoot); collect(el.shadowRoot); } })(doc);
  const dEl = doc.documentElement;
  const outHtml = typeof dEl.getHTML === 'function'
    ? '<html' + [...dEl.attributes].map(a => ` ${a.name}="${a.value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')}"`).join('') + '>' +
      dEl.getHTML({serializableShadowRoots: true, shadowRoots: docRoots}) + '</html>'
    : dEl.outerHTML;

  const rec = {
    format: VERSION,
    url: stripUrl(location.href),
    title: maskText(document.title),
    captured_at: new Date().toISOString(),
    user_agent: navigator.userAgent,
    viewport: {width: window.innerWidth, height: window.innerHeight, device_pixel_ratio: window.devicePixelRatio,
               scroll_x: sx, scroll_y: sy, doc_width: de.scrollWidth, doc_height: de.scrollHeight},
    compat_mode: document.compatMode,
    doctype: document.doctype ? document.doctype.name : null,
    lang: de.getAttribute('lang'),
    stats: stats,
    html: outHtml,
  };
  if (!opts.download) return rec;
  const host = location.hostname.replace(/^www\./, '').replace(/[^\w.-]/g, '');
  const stampStr = rec.captured_at.slice(0, 16).replace(/[-:]/g, '').replace('T', '-');
  const guess = `CATEGORY__${host}__PAGETYPE`;
  let base = opts.name || window.prompt('File name: category__site__pagetype (see CAPTURE.md)', guess);
  if (!base) { console.log('rwk: cancelled'); return null; }
  base = base.replace(/[^\w.\-]/g, '_');
  const blob = new Blob([JSON.stringify(rec)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${base}__${stampStr}.rwk.json`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  console.log('rwk: saved', a.download, JSON.stringify(stats));
  return a.download;
}
// Lazy loading: by default scroll down the page in viewport-sized steps (at most
// RWK_MAX_STEPS, default 40, so endless feeds stop), wait for content, return to the top,
// then capture. Set window.RWK_AUTOSCROLL = false before running to capture as the page is.
(async () => {
  if (window.RWK_AUTOSCROLL !== false) {
    const maxSteps = window.RWK_MAX_STEPS || 40;
    const step = Math.max(200, Math.floor(window.innerHeight * 0.8));
    let atEnd = 0;
    for (let i = 0; i < maxSteps && atEnd < 3; i++) {
      window.scrollBy(0, step);
      await new Promise(r => setTimeout(r, 400));
      const bottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
      atEnd = bottom ? atEnd + 1 : 0;
    }
    window.scrollTo(0, 0);
    await new Promise(r => setTimeout(r, 800));
  }
  rwkCapture({download: true});
})();
