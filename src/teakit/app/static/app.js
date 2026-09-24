/* ==========================================================================
   teakit application.
   Vanilla JS, no framework, no build step, no network. The Python side owns
   every number; this file owns presentation and nothing else.
   ========================================================================== */
'use strict';

/* ----------------------------- utilities ------------------------------- */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const k of kids.flat()) {
    if (k === null || k === undefined || k === false) continue;
    n.appendChild(typeof k === 'string' || typeof k === 'number'
      ? document.createTextNode(String(k)) : k);
  }
  return n;
}

function fmt(v, dp) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (dp !== undefined) return v.toLocaleString(undefined,
    { minimumFractionDigits: dp, maximumFractionDigits: dp });
  if (a >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (a >= 1e3) return Math.round(v).toLocaleString();
  if (a >= 1)   return v.toFixed(2);
  if (a > 0)    return v.toPrecision(3);
  return '0';
}
/* Currency symbol for whatever the project is being reported in. Falls back to
   the ISO code, which is what a report should carry anyway when the glyph is
   ambiguous — CNY and JPY share ¥. */
const curCode = () => state.project?.currency || 'USD';
const curSym = () => (state.meta?.currencies?.[curCode()]) || curCode();

/* Compact — for charts, the title block and anywhere space is tight. */
const money = v => curSym() + fmt(v);

/* Full precision, grouped, never abbreviated. Table cells use this: an
   equipment cost shown as "12.7M" is the complaint, not the feature. */
function moneyFull(v, dp = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return curSym() + v.toLocaleString(undefined,
    { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
/* Exact value for a tooltip, so the compact form is never the only source. */
const moneyExact = v => (v === null || v === undefined || Number.isNaN(v))
  ? '' : `${curSym()}${v.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${curCode()}`;

const pct = v => (v * 100).toFixed(v * 100 < 10 ? 2 : 1) + '%';

/* A physical rate, grouped, with only the decimals it actually has. fmt(v, 4)
   turns 5200 into "5,200.0000", which reads as false precision on a figure
   somebody typed as a round number. */
const fmtRate = v => (v === null || v === undefined || Number.isNaN(v)) ? '—'
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 });

/* ------------------------- option presentation -------------------------
   Dropdown labels are written the way they would be written in the report:
   capitalised and spelled out, never a bare identifier. Acronyms, unit
   symbols, currency codes and anything carrying a digit stay exactly as
   written — "CEPCI", "DOE/NETL-2002/1169", "USGC", "NPV", "MACRS", "kW",
   "150 psig" are not sentence text, and re-casing them makes them harder to
   read, not easier. */
const KEEP_CASE = /^(?:[A-Z0-9][A-Z0-9&/.~+%_-]*|\S*\d\S*)$/;

/* Unit symbols and abbreviations whose case is meaningful. They pass through
   a label untouched: "MW" is not "Mw", and "psig" is not "Psig". */
const KEEP_LOWER = new Set([
  'psig', 'psia', 'psi', 'bar', 'barg', 'kPa', 'MPa', 'in', 'ft', 'mm', 'cm',
  'kg', 'lb', 'lbs', 'h', 'hr', 'yr', 'kW', 'MW', 'GW', 'kWh', 'MWh', 'GJ',
  'MJ', 'Btu', 'gpm', 'scfm', 'acfm', 'rpm', 'tonne', 'tonnes', 'gal',
  'acre', 'acres', 'incl', 'excl', 'approx', 'max', 'min', 'avg', 'vs',
]);

/* Words a title leaves in lower case unless they open or close it. */
const MINOR_WORDS = new Set([
  'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into',
  'nor', 'of', 'on', 'onto', 'or', 'over', 'per', 'the', 'to', 'up', 'via',
  'with', 'without',
]);

/* Split a word into the punctuation around it and the word itself, so the
   word can be judged on its own and its punctuation put back where it was. */
const WORD_PARTS = /^(["'([‘“]*)(.*?)(["')\].,;:’”]*)$/;

/* Title Case, for a short option label: "solid-fluid processing" becomes
   "Solid-Fluid Processing". Long descriptive text uses sentenceLabel instead —
   title-casing a whole sentence reads as a headline, not as a choice. */
function optLabel(text) {
  const words = String(text).split(/\s+/);
  const last = words.length - 1;
  return words.map((w, i) => {
    const m = WORD_PARTS.exec(w);
    const pre = m ? m[1] : '', core = m ? m[2] : w, post = m ? m[3] : '';
    if (!core) return w;
    if (KEEP_LOWER.has(core)) return w;                    // psig, kW, incl.
    if (KEEP_CASE.test(core)) return w;                    // NETL, CEPCI, 150F
    if (/[a-z]/.test(core) && /[A-Z]/.test(core.slice(1))) return w;  // McCabe
    const lower = core.toLowerCase();
    if (i !== 0 && i !== last && MINOR_WORDS.has(lower)) return pre + lower + post;
    // Each part of a hyphenated or slashed compound is capitalised too.
    return pre + lower.replace(/(^|[-/])([a-z])/g,
      (_, sep, ch) => sep + ch.toUpperCase()) + post;
  }).join(' ');
}

/* Sentence case: capitalise the opening word and leave the rest alone. Right
   for anything that reads as a phrase — an equipment description, a service
   condition — where Title Case Would Look Like This. */
function sentenceLabel(text) {
  const t = String(text).trim();
  if (!t) return t;
  const m = WORD_PARTS.exec(t.split(/\s+/)[0]);
  const pre = m ? m[1] : '', core = m ? m[2] : t;
  if (!core || KEEP_LOWER.has(core) || KEEP_CASE.test(core)) return t;
  return t.slice(0, pre.length) + core.charAt(0).toUpperCase() +
         t.slice(pre.length + 1);
}

/* --- names the library stores as identifiers, spelled out for a reader ---
   Display only: the value on the <option> is still the key the API expects,
   so nothing downstream sees the difference. */
const MATERIAL_LABEL = {
  'carbon steel': 'Carbon steel',
  'ss410': 'Stainless steel 410',
  'ss304': 'Stainless steel 304',
  'ss316': 'Stainless steel 316',
  'ss310': 'Stainless steel 310',
  'rubber-lined steel': 'Rubber-lined steel',
  'bronze': 'Bronze',
  'monel': 'Monel',
};
const materialLabel = k => MATERIAL_LABEL[k] || optLabel(k);

/* The distributive-factor keys are precise and unreadable:
   "gas_gt400F_gt150psig" is a filename, not a choice. */
const SERVICE_LABEL = {
  'liquid_slurry_lt150psig': 'Liquid and slurry, below 150 psig',
  'liquid_slurry_gt150psig': 'Liquid and slurry, above 150 psig',
  'gas_lt400F_lt150psig': 'Gas, below 400 °F and 150 psig',
  'gas_lt400F_gt150psig': 'Gas, below 400 °F, above 150 psig',
  'gas_gt400F_lt150psig': 'Gas, above 400 °F, below 150 psig',
  'gas_gt400F_gt150psig': 'Gas, above 400 °F and 150 psig',
  'solids_lt400F': 'Solids, below 400 °F',
  'solids_gt400F': 'Solids, above 400 °F',
  'solids_gas_lt400F_lt150psig': 'Solids and gas, below 400 °F and 150 psig',
  'solids_gas_gt400F_gt150psig': 'Solids and gas, above 400 °F and 150 psig',
};
const serviceLabel = k => SERVICE_LABEL[k] || sentenceLabel(String(k)
  .replace(/_/g, ' ')
  .replace(/\blt(\d+)/g, 'below $1')
  .replace(/\bgt(\d+)/g, 'above $1')
  .replace(/(\d)F\b/g, '$1 °F')
  .replace(/(\d)psig\b/g, '$1 psig'));

/* Sensitivity metrics are three-letter keys. Spell them out once, here. */
const METRIC_LABEL = {
  'msp': 'MSP — minimum selling price',
  'npv': 'NPV — net present value',
  'irr': 'IRR — internal rate of return',
  'toc': 'TOC — total overnight cost',
  'tasc': 'TASC — total as-spent capital',
  'tpc': 'TPC — total plant cost',
  'bec': 'BEC — bare erected cost',
  'opex': 'Operating cost — total per year',
  'opex_fixed': 'Operating cost — fixed only',
  'opex_variable': 'Operating cost — variable only',
  'capital_component': 'Capital component of the levelised cost',
  'payback': 'Payback period',
};
const metricLabel = k => METRIC_LABEL[k] || optLabel(String(k).replace(/_/g, ' '));

const ROLE_LABEL = { primary: 'Primary', coproduct: 'Co-product',
                     byproduct: 'By-product' };

/* The costing methods are API keys, and "dcf" printed on a title block reads
   as a typo. They are acronyms in every document that quotes them. */
const METHOD_LABEL = { dcf: 'DCF', fcr: 'FCR', crf: 'CRF', simple: 'Simple' };
const methodLabel = k => METHOD_LABEL[k] || optLabel(String(k));
const STREAM_BASIS_LABEL = { hour: 'Per operating hour', year: 'Per year' };

/* Help text for one option, from the library. teakit.methods owns every one of
   these strings so the interface, the report and the workbook cannot drift. */
const optHelp = (field, value) =>
  (state.meta?.option_help?.[field] || {})[String(value)] || '';

/* Hang the help on the <option> as a native tooltip, and print the selected
   option's help under the control. Between them a user meets an explanation
   before choosing rather than after being surprised by the answer. */
/* Every note painter registered by describeSelect. Loading a project or a
   demo sets the selects programmatically, which fires no event, so the notes
   have to be repainted explicitly — otherwise the line under "nominal" goes on
   describing "real", which is worse than no note at all. */
const optNotePainters = [];

function describeSelect(sel, field) {
  if (!sel) return;
  sel.dataset.help = field;
  Array.from(sel.options).forEach(o => {
    const h = optHelp(field, o.value);
    if (h) o.title = h;
  });
  let note = sel.parentElement?.querySelector('.opt-note');
  if (!note) {
    note = el('span', { class: 'note opt-note' });
    sel.insertAdjacentElement('afterend', note);
  }
  const paint = () => { note.textContent = optHelp(field, sel.value); };
  sel.addEventListener('change', paint);
  sel.addEventListener('input', paint);
  optNotePainters.push(paint);
  paint();
}

function paintOptionNotes() {
  optNotePainters.forEach(fn => fn());
}

/* A small "?" beside a label that opens a persistent explanation. Used where
   the field itself needs explaining, not just its options. */
function infoTip(text) {
  return el('button', {
    class: 'tip', type: 'button', title: text, 'aria-label': text,
    onclick: e => {
      e.preventDefault();
      const box = e.target.closest('.f, .par')?.querySelector('.tip-body');
      if (box) box.classList.toggle('on');
    }
  }, '?');
}

let toastTimer;
function toast(msg, ms = 2600) {
  const t = $('#toast');
  t.textContent = msg; t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('on'), ms);
}

let busyDepth = 0;
function busy(on) {
  busyDepth = Math.max(0, busyDepth + (on ? 1 : -1));
  $('#busy').classList.toggle('on', busyDepth > 0);
}

async function api(name, payload = {}) {
  busy(true);
  try {
    const r = await fetch('/api/' + name, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'request failed');
    return j;
  } finally { busy(false); }
}

/* --------------------------- path access ------------------------------- */
function getPath(obj, path) {
  return path.split('.').reduce((o, k) => (o === null || o === undefined ? o : o[k]), obj);
}
function setPath(obj, path, val) {
  const parts = path.split('.');
  let o = obj;
  for (const p of parts.slice(0, -1)) {
    if (o[p] === null || o[p] === undefined) o[p] = {};
    o = o[p];
  }
  o[parts[parts.length - 1]] = val;
}

/* ------------------------------- state --------------------------------- */
const state = {
  meta: null,
  project: null,
  result: null,
  charts: {},
  //: The utility figures, kept apart from the standard set because they are
  //: about what the plant consumes rather than what it costs.
  utilityCharts: {},
  //: Which utility the distribution view is showing. Presentation only, and
  //: held so a re-run does not throw the reader back to the first utility.
  udUtility: '',
  rev: 0,
  stale: true,
  laborMode: 'rule',
  // Which operating-time preset supplied the hours, so the note under the
  // control can attribute them. Presentation only — it is not part of the
  // project and is dropped whenever the project is replaced.
  opPreset: null,
  sensKind: 'tornado',
  tornadoParams: [],
  explanation: [],
  infoTab: 'guide',
};

function touch() {                     // inputs changed: the stamp is superseded
  if (!state.stale) { state.stale = true; paintBlock(); }
}

/* ======================================================================= */
/*                              chart renderer                             */
/* ======================================================================= */
const PAL_LIGHT = ['#1b6b73', '#d98324', '#4a7c59', '#8c4a5f', '#3d5a80',
                   '#a68a3f', '#6b4e71', '#2a9d8f', '#bc6c25', '#577590',
                   '#9c6644', '#43658b'];
const PAL_DARK  = ['#4fb3bf', '#f0a04b', '#7cb083', '#c98099', '#7a9ec9',
                   '#d4b36a', '#a78bb0', '#5fd0c3', '#e8975a', '#89a7c4',
                   '#c99a78', '#7a9cc6'];
const NEG = '#b3402f';
const isDark = () => document.documentElement.dataset.theme === 'dark';
const pal = () => (isDark() ? PAL_DARK : PAL_LIGHT);
const TH = () => isDark()
  ? { fg: '#e8eded', muted: '#9db0b3', grid: '#2b3a3d', axis: '#5d7276' }
  : { fg: '#1c2b2d', muted: '#5d6f72', grid: '#dfe6e6', axis: '#8fa3a5' };

const clip = (s, n) => (String(s).length <= n ? String(s)
  : String(s).slice(0, n - 1).trimEnd() + '\u2026');
const esc = s => String(s).replace(/[<>&"]/g, c =>
  ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));

function ticks(lo, hi, n = 5) {
  if (hi === lo) hi = lo + 1;
  const raw = (hi - lo) / n;
  const mag = Math.pow(10, Math.floor(Math.log10(Math.abs(raw) || 1)));
  let step = 10 * mag;
  for (const m of [1, 2, 2.5, 5, 10]) if (raw / mag <= m) { step = m * mag; break; }
  const out = []; let v = Math.floor(lo / step) * step;
  while (v <= hi + step * 0.5) { out.push(+v.toFixed(12)); v += step; }
  return out;
}

/* How much room a title takes above the plot.

   The title used to be drawn into the same box as the chart and the plot
   margins were sized to dodge it, which held only until a bar reached the top
   of its axis — then its value label ran into the heading. The title now gets
   a band of its own and the plot is translated below it, so the two cannot
   collide whatever the data does.

   A donut is the exception, and deliberately: it is drawn off-centre with its
   legend filling the right-hand side, so the top-left corner is empty and the
   title belongs in it. Giving it a band would only shrink the ring. */
const TITLE_BAND = 30;
const titleBand = spec =>
  (spec.title && spec.kind !== 'donut') ? TITLE_BAND : 0;

function renderChart(spec, W = 760, H = 400) {
  const th = TH(), P = pal(), o = [];
  o.push(`<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet"
    font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Arial,sans-serif">`);
  const titleH = titleBand(spec);
  if (spec.title) o.push(`<text x="14" y="${titleH ? 21 : 24}" font-size="14"
    font-weight="600" fill="${th.fg}">${esc(spec.title)}</text>`);
  const noteH = spec.note ? 18 : 0;
  if (spec.note) o.push(`<text x="14" y="${H - 6}" font-size="10.5"
    fill="${th.muted}">${esc(spec.note)}</text>`);
  const h = H - noteH - titleH;
  const k = spec.kind;
  if (titleH) o.push(`<g transform="translate(0,${titleH})">`);
  if (k === 'bar' || k === 'waterfall') o.push(...cBars(spec, W, h, th, P));
  else if (k === 'stacked_bar') o.push(...cStacked(spec, W, h, th, P));
  else if (k === 'donut') o.push(...cDonut(spec, W, h, th, P));
  else if (k === 'line' || k === 'scatter') o.push(...cLine(spec, W, h, th, P));
  else if (k === 'tornado') o.push(...cTornado(spec, W, h, th, P));
  else if (k === 'histogram') o.push(...cHist(spec, W, h, th, P));
  else if (k === 'heatmap') o.push(...cHeat(spec, W, h, th, P));
  if (titleH) o.push('</g>');
  o.push('</svg>');
  return o.join('');
}

function yAxis(o, x0, y0, x1, y1, tk, sc, th, label) {
  for (const t of tk) {
    const y = sc(t);
    o.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}"
      stroke="${th.grid}"/>`);
    o.push(`<text x="${x0 - 6}" y="${(y + 4).toFixed(1)}" font-size="10"
      text-anchor="end" fill="${th.muted}">${fmt(t)}</text>`);
  }
  if (label) o.push(`<text x="13" y="${((y0 + y1) / 2).toFixed(0)}" font-size="10"
    fill="${th.muted}" text-anchor="middle"
    transform="rotate(-90 13 ${((y0 + y1) / 2).toFixed(0)})">${esc(label)}</text>`);
}

function cBars(spec, W, H, th, P) {
  const o = [], L = 72, R = 18, T = 20, B = 104;
  const x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const vals = spec.values, wf = spec.kind === 'waterfall';
  const totals = new Set((spec.meta && spec.meta.totals) || []);
  let bars = [], lo, hi;
  if (wf) {
    let run = 0;
    spec.labels.forEach((lb, i) => {
      if (totals.has(lb)) { bars.push([0, vals[i]]); run = vals[i]; }
      else { bars.push([run, run + vals[i]]); run += vals[i]; }
    });
    lo = Math.min(0, ...bars.map(b => Math.min(...b)));
    hi = Math.max(...bars.map(b => Math.max(...b)));
  } else {
    lo = Math.min(0, ...vals); hi = Math.max(...vals, 1);
  }
  const tk = ticks(lo, hi), lt = Math.min(...tk), ht = Math.max(...tk);
  const sc = v => y1 - (v - lt) / ((ht - lt) || 1) * (y1 - y0);
  yAxis(o, x0, y0, x1, y1, tk, sc, th, spec.y_label);
  const n = Math.max(vals.length, 1), slot = (x1 - x0) / n, bw = Math.min(slot * 0.68, 58);
  spec.labels.forEach((lb, i) => {
    const cx = x0 + slot * (i + 0.5);
    let top, bot, col;
    if (wf) {
      const [a, b] = bars[i];
      top = sc(Math.max(a, b)); bot = sc(Math.min(a, b));
      col = totals.has(lb) ? P[0] : (vals[i] >= 0 ? P[1] : NEG);
    } else {
      top = sc(Math.max(vals[i], 0)); bot = sc(Math.min(vals[i], 0));
      col = vals[i] >= 0 ? P[i % P.length] : NEG;
    }
    o.push(`<rect x="${(cx - bw / 2).toFixed(1)}" y="${top.toFixed(1)}"
      width="${bw.toFixed(1)}" height="${Math.max(bot - top, 1.2).toFixed(1)}"
      fill="${col}" rx="2"><title>${esc(lb)}: ${fmt(vals[i])}</title></rect>`);
    if (n <= 18) o.push(`<text x="${cx.toFixed(1)}" y="${(top - 5).toFixed(1)}"
      font-size="9" text-anchor="middle" fill="${th.fg}">${fmt(vals[i])}</text>`);
    o.push(`<text x="${cx.toFixed(1)}" y="${(y1 + 11).toFixed(1)}" font-size="9.5"
      fill="${th.muted}" text-anchor="end"
      transform="rotate(-38 ${cx.toFixed(1)} ${(y1 + 11).toFixed(1)})"
      >${esc(clip(lb, 28))}</text>`);
  });
  o.push(`<line x1="${x0}" y1="${sc(0).toFixed(1)}" x2="${x1}" y2="${sc(0).toFixed(1)}"
    stroke="${th.axis}" stroke-width="1.2"/>`);
  return o;
}

function cStacked(spec, W, H, th, P) {
  const o = [], L = 72, R = 18, T = 34, B = 66;
  const x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const n = Math.max(spec.labels.length, 1);
  const ov = spec.meta && spec.meta.overlay;
  const pos = [], neg = [];
  for (let i = 0; i < n; i++) {
    pos.push(spec.series.reduce((s, ser) => s + Math.max(ser.values[i], 0), 0));
    neg.push(spec.series.reduce((s, ser) => s + Math.min(ser.values[i], 0), 0));
  }
  const hi = Math.max(...pos, ov ? Math.max(...ov.values) : 0);
  const lo = Math.min(0, ...neg, ov ? Math.min(...ov.values) : 0);
  const tk = ticks(lo, hi), lt = Math.min(...tk), ht = Math.max(...tk);
  const sc = v => y1 - (v - lt) / ((ht - lt) || 1) * (y1 - y0);
  yAxis(o, x0, y0, x1, y1, tk, sc, th, spec.y_label);
  const slot = (x1 - x0) / n, bw = Math.min(slot * 0.7, 66);
  for (let i = 0; i < n; i++) {
    const cx = x0 + slot * (i + 0.5);
    let up = 0, dn = 0;
    spec.series.forEach((ser, j) => {
      const v = ser.values[i]; let top, bot;
      if (v >= 0) { top = sc(up + v); bot = sc(up); up += v; }
      else { top = sc(dn); bot = sc(dn + v); dn += v; }
      o.push(`<rect x="${(cx - bw / 2).toFixed(1)}" y="${top.toFixed(1)}"
        width="${bw.toFixed(1)}" height="${Math.max(bot - top, 0.8).toFixed(1)}"
        fill="${ser.color || P[j % P.length]}" rx="1.5">
        <title>${esc(ser.name)}: ${fmt(v)}</title></rect>`);
    });
    const step = Math.max(1, Math.ceil(n / 14));
    if (i % step === 0) o.push(`<text x="${cx.toFixed(1)}" y="${(y1 + 14).toFixed(1)}"
      font-size="9.5" text-anchor="middle" fill="${th.muted}"
      >${esc(clip(spec.labels[i], 14))}</text>`);
  }
  if (ov) {
    const pts = ov.values.map((v, i) =>
      `${(x0 + slot * (i + 0.5)).toFixed(1)},${sc(v).toFixed(1)}`).join(' ');
    o.push(`<polyline points="${pts}" fill="none" stroke="${ov.color || P[1]}"
      stroke-width="2.2"/>`);
  }
  o.push(`<line x1="${x0}" y1="${sc(0).toFixed(1)}" x2="${x1}" y2="${sc(0).toFixed(1)}"
    stroke="${th.axis}" stroke-width="1.2"/>`);
  let lx = x0;
  [...spec.series, ...(ov ? [ov] : [])].forEach((s, j) => {
    o.push(`<rect x="${lx}" y="${T - 20}" width="10" height="10"
      fill="${s.color || P[j % P.length]}" rx="2"/>`);
    o.push(`<text x="${lx + 14}" y="${T - 11}" font-size="10"
      fill="${th.muted}">${esc(s.name)}</text>`);
    lx += 22 + 6.2 * s.name.length;
  });
  return o;
}

function cDonut(spec, W, H, th, P) {
  const o = [];
  const total = spec.values.reduce((s, v) => s + Math.abs(v), 0) || 1;
  const cx = W * 0.27, cy = H * 0.55;
  const r = Math.min(W * 0.20, H * 0.34), ri = r * 0.58;
  let a = -Math.PI / 2;
  spec.values.forEach((v, i) => {
    const f = Math.abs(v) / total, a2 = a + f * 2 * Math.PI, lg = f > 0.5 ? 1 : 0;
    const p = (rad, ang) => `${(cx + rad * Math.cos(ang)).toFixed(2)} ${(cy + rad * Math.sin(ang)).toFixed(2)}`;
    o.push(`<path d="M ${p(r, a)} A ${r} ${r} 0 ${lg} 1 ${p(r, a2)}
      L ${p(ri, a2)} A ${ri} ${ri} 0 ${lg} 0 ${p(ri, a)} Z"
      fill="${P[i % P.length]}"><title>${esc(spec.labels[i])}: ${fmt(v)} (${(f * 100).toFixed(1)}%)</title></path>`);
    a = a2;
  });
  o.push(`<text x="${cx.toFixed(0)}" y="${(cy - 1).toFixed(0)}" font-size="14"
    font-weight="600" text-anchor="middle" fill="${th.fg}"
    >${fmt(spec.values.reduce((s, v) => s + v, 0))}</text>`);
  o.push(`<text x="${cx.toFixed(0)}" y="${(cy + 14).toFixed(0)}" font-size="10"
    text-anchor="middle" fill="${th.muted}">total</text>`);
  let ly = 54;
  spec.labels.forEach((lb, i) => {
    o.push(`<rect x="${(W * 0.52).toFixed(0)}" y="${ly - 9}" width="10" height="10"
      fill="${P[i % P.length]}" rx="2"/>`);
    o.push(`<text x="${(W * 0.52 + 16).toFixed(0)}" y="${ly}" font-size="11"
      fill="${th.fg}">${esc(clip(lb, 32))}</text>`);
    o.push(`<text x="${W - 16}" y="${ly}" font-size="11" text-anchor="end"
      fill="${th.muted}">${(Math.abs(spec.values[i]) / total * 100).toFixed(1)}%</text>`);
    ly += 18;
  });
  return o;
}

function cLine(spec, W, H, th, P) {
  const o = [], L = 72, R = 22, T = 20, B = 54;
  const x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const xs = spec.x, ys = spec.y;
  if (!xs.length) return o;
  const xlo = Math.min(...xs), xhi = Math.max(...xs);
  const tk = ticks(Math.min(...ys), Math.max(...ys));
  const ylo = Math.min(...tk), yhi = Math.max(...tk);
  const sy = v => y1 - (v - ylo) / ((yhi - ylo) || 1) * (y1 - y0);
  const sx = v => x0 + (v - xlo) / ((xhi - xlo) || 1) * (x1 - x0);
  yAxis(o, x0, y0, x1, y1, tk, sy, th, spec.y_label);
  for (const t of ticks(xlo, xhi, 6)) if (t >= xlo && t <= xhi)
    o.push(`<text x="${sx(t).toFixed(1)}" y="${y1 + 15}" font-size="10"
      text-anchor="middle" fill="${th.muted}">${fmt(t)}</text>`);
  if (spec.kind !== 'scatter')
    o.push(`<polyline points="${xs.map((a, i) => `${sx(a).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join(' ')}"
      fill="none" stroke="${P[0]}" stroke-width="2.4" stroke-linejoin="round"/>`);
  xs.forEach((a, i) => o.push(`<circle cx="${sx(a).toFixed(1)}" cy="${sy(ys[i]).toFixed(1)}"
    r="3" fill="${P[0]}"><title>${fmt(a)} → ${fmt(ys[i])}</title></circle>`));
  const m = spec.meta && spec.meta.marker;
  if (m) {
    o.push(`<line x1="${sx(m[0]).toFixed(1)}" y1="${y0}" x2="${sx(m[0]).toFixed(1)}"
      y2="${y1}" stroke="${P[1]}" stroke-width="1.4" stroke-dasharray="4 3"/>`);
    o.push(`<text x="${(sx(m[0]) + 5).toFixed(1)}" y="${y0 + 12}" font-size="10"
      fill="${P[1]}">base</text>`);
  }
  if (spec.x_label) o.push(`<text x="${((x0 + x1) / 2).toFixed(0)}" y="${y1 + 34}"
    font-size="10.5" text-anchor="middle" fill="${th.muted}">${esc(spec.x_label)}</text>`);
  return o;
}

function cTornado(spec, W, H, th, P) {
  const o = [], L = 192, R = 58, T = 38, B = 34;
  const x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const base = (spec.meta && spec.meta.base) || 0;
  const los = spec.series[0].values, his = spec.series[1].values;
  let lo = Math.min(...los, ...his, base), hi = Math.max(...los, ...his, base);
  const pad = (hi - lo) * 0.08 || Math.abs(base) * 0.1 || 1;
  lo -= pad; hi += pad;
  const sx = v => x0 + (v - lo) / (hi - lo) * (x1 - x0);
  const n = Math.max(spec.labels.length, 1);
  const rh = (y1 - y0) / n, bh = Math.min(rh * 0.62, 24);
  for (const t of ticks(lo, hi, 5)) if (t >= lo && t <= hi) {
    o.push(`<line x1="${sx(t).toFixed(1)}" y1="${y0}" x2="${sx(t).toFixed(1)}"
      y2="${y1}" stroke="${th.grid}"/>`);
    o.push(`<text x="${sx(t).toFixed(1)}" y="${y1 + 15}" font-size="10"
      text-anchor="middle" fill="${th.muted}">${fmt(t)}</text>`);
  }
  spec.labels.forEach((lb, i) => {
    const cy = y0 + rh * (i + 0.5), bx = sx(base);
    const a = sx(los[i]), b = sx(his[i]);
    const prm = (spec.meta.params || [])[i] || {};
    o.push(`<rect x="${Math.min(a, bx).toFixed(1)}" y="${(cy - bh / 2).toFixed(1)}"
      width="${Math.abs(bx - a).toFixed(1)}" height="${bh.toFixed(1)}" fill="${P[0]}"
      opacity="0.9" rx="2"><title>low ${fmt(prm.low)} → ${fmt(los[i])}</title></rect>`);
    o.push(`<rect x="${Math.min(b, bx).toFixed(1)}" y="${(cy - bh / 2).toFixed(1)}"
      width="${Math.abs(b - bx).toFixed(1)}" height="${bh.toFixed(1)}" fill="${P[1]}"
      opacity="0.9" rx="2"><title>high ${fmt(prm.high)} → ${fmt(his[i])}</title></rect>`);
    o.push(`<text x="${L - 10}" y="${(cy + 4).toFixed(1)}" font-size="11"
      text-anchor="end" fill="${th.fg}">${esc(clip(lb, 28))}</text>`);
    o.push(`<text x="${x1 + 6}" y="${(cy + 4).toFixed(1)}" font-size="10"
      fill="${th.muted}">${(spec.values[i] / (base || 1) * 100).toFixed(0)}%</text>`);
  });
  o.push(`<line x1="${sx(base).toFixed(1)}" y1="${y0 - 6}" x2="${sx(base).toFixed(1)}"
    y2="${y1}" stroke="${th.fg}" stroke-width="1.6"/>`);
  o.push(`<text x="${sx(base).toFixed(1)}" y="${y0 - 10}" font-size="10"
    text-anchor="middle" fill="${th.fg}">base ${fmt(base)}</text>`);
  return o;
}

function cHist(spec, W, H, th, P) {
  const o = [], L = 60, R = 18, T = 20, B = 54;
  const x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const ed = spec.x, ct = spec.values;
  if (ed.length < 2) return o;
  const tk = ticks(0, Math.max(...ct) || 1, 4), ht = Math.max(...tk);
  const sy = v => y1 - v / (ht || 1) * (y1 - y0);
  const sx = v => x0 + (v - ed[0]) / ((ed[ed.length - 1] - ed[0]) || 1) * (x1 - x0);
  yAxis(o, x0, y0, x1, y1, tk, sy, th, 'trials');
  ct.forEach((c, i) => {
    const a = sx(ed[i]), b = sx(ed[i + 1]);
    o.push(`<rect x="${a.toFixed(1)}" y="${sy(c).toFixed(1)}"
      width="${Math.max(b - a - 1, 1).toFixed(1)}" height="${(y1 - sy(c)).toFixed(1)}"
      fill="${P[0]}" opacity="0.85"><title>${fmt(ed[i])}–${fmt(ed[i + 1])}: ${c}</title></rect>`);
  });
  Object.entries((spec.meta && spec.meta.markers) || {}).forEach(([nm, v]) => {
    o.push(`<line x1="${sx(v).toFixed(1)}" y1="${y0}" x2="${sx(v).toFixed(1)}"
      y2="${y1}" stroke="${P[1]}" stroke-width="1.6" stroke-dasharray="5 3"/>`);
    o.push(`<text x="${sx(v).toFixed(1)}" y="${y0 - 4}" font-size="10"
      text-anchor="middle" fill="${P[1]}">${esc(nm)}</text>`);
  });
  for (const t of ticks(ed[0], ed[ed.length - 1], 5))
    if (t >= ed[0] && t <= ed[ed.length - 1])
      o.push(`<text x="${sx(t).toFixed(1)}" y="${y1 + 15}" font-size="10"
        text-anchor="middle" fill="${th.muted}">${fmt(t)}</text>`);
  if (spec.x_label) o.push(`<text x="${((x0 + x1) / 2).toFixed(0)}" y="${y1 + 34}"
    font-size="10.5" text-anchor="middle" fill="${th.muted}">${esc(spec.x_label)}</text>`);
  return o;
}

function cHeat(spec, W, H, th) {
  const o = [], L = 72, R = 76, T = 20, B = 54;
  const x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const flat = spec.z.flat().filter(v => v !== null && !Number.isNaN(v));
  if (!flat.length) return o;
  const lo = Math.min(...flat), hi = Math.max(...flat);
  const ny = spec.z.length, nx = spec.z[0].length;
  const cw = (x1 - x0) / nx, ch = (y1 - y0) / ny;
  const col = v => {
    const t = (v - lo) / ((hi - lo) || 1);
    let r, g, b;
    if (t < 0.5) { const f = t * 2; r = 27 + f * 218; g = 107 + f * 134; b = 115 + f * 107; }
    else { const f = (t - 0.5) * 2; r = 245 - f * 28; g = 241 - f * 110; b = 222 - f * 186; }
    return `rgb(${r | 0},${g | 0},${b | 0})`;
  };
  for (let i = 0; i < ny; i++) for (let j = 0; j < nx; j++) {
    const v = spec.z[i][j];
    if (v === null || Number.isNaN(v)) continue;
    o.push(`<rect x="${(x0 + j * cw).toFixed(1)}" y="${(y1 - (i + 1) * ch).toFixed(1)}"
      width="${(cw + 0.5).toFixed(1)}" height="${(ch + 0.5).toFixed(1)}" fill="${col(v)}"
      ><title>${fmt(spec.x[j])}, ${fmt(spec.y[i])}: ${fmt(v)}</title></rect>`);
  }
  for (let j = 0; j < nx; j += Math.max(1, Math.floor(nx / 6)))
    o.push(`<text x="${(x0 + (j + 0.5) * cw).toFixed(1)}" y="${y1 + 15}" font-size="10"
      text-anchor="middle" fill="${th.muted}">${fmt(spec.x[j])}</text>`);
  for (let i = 0; i < ny; i += Math.max(1, Math.floor(ny / 6)))
    o.push(`<text x="${x0 - 6}" y="${(y1 - (i + 0.5) * ch + 4).toFixed(1)}" font-size="10"
      text-anchor="end" fill="${th.muted}">${fmt(spec.y[i])}</text>`);
  for (let s = 0; s < 11; s++)
    o.push(`<rect x="${x1 + 18}" y="${(y1 - (s + 1) * (y1 - y0) / 11).toFixed(1)}"
      width="14" height="${((y1 - y0) / 11 + 0.5).toFixed(1)}"
      fill="${col(lo + (hi - lo) * s / 10)}"/>`);
  o.push(`<text x="${x1 + 36}" y="${y1}" font-size="10" fill="${th.muted}">${fmt(lo)}</text>`);
  o.push(`<text x="${x1 + 36}" y="${y0 + 10}" font-size="10" fill="${th.muted}">${fmt(hi)}</text>`);
  if (spec.x_label) o.push(`<text x="${((x0 + x1) / 2).toFixed(0)}" y="${y1 + 34}"
    font-size="10.5" text-anchor="middle" fill="${th.muted}">${esc(spec.x_label)}</text>`);
  if (spec.y_label) o.push(`<text x="15" y="${((y0 + y1) / 2).toFixed(0)}" font-size="10.5"
    fill="${th.muted}" text-anchor="middle"
    transform="rotate(-90 15 ${((y0 + y1) / 2).toFixed(0)})">${esc(spec.y_label)}</text>`);
  return o;
}

/* One figure: the chart, a width control, and a way to get it out.

   Width is per figure and remembered by title, because which chart wants the
   full width is a property of the chart — a cash flow with thirty years of
   bars is unreadable at half width, and a four-slice donut is silly at full.
   The choice survives a re-run, which is when it would otherwise be lost. */
const figWide = {};
const figKey = spec => (spec.title || spec.kind || 'chart');

function figure(spec, w, h) {
  const key = figKey(spec);
  const box = el('div', { class: 'fig' });

  const draw = () => {
    const wide = !!figWide[key];
    box.classList.toggle('wide', wide);
    // A wide figure gets a wider viewBox rather than a stretched one: bars
    // and labels are laid out in the viewBox's own coordinates, so scaling a
    // narrow drawing up just makes the text huge.
    const svg = renderChart(spec, wide ? (w || 880) * 1.9 : (w || 880),
                            wide ? Math.round((h || 400) * 1.08) : (h || 400));
    box.innerHTML = svg;
    box.appendChild(tools);
  };

  const tools = el('div', { class: 'fig-tools' },
    el('button', {
      class: 'btn sm', title: 'Show this figure at half width or across the ' +
                             'whole page',
      onclick: e => {
        figWide[key] = !figWide[key];
        draw();
        e.stopPropagation();
      }
    }, 'Width'),
    el('button', {
      class: 'btn sm', title: 'Save this figure as an SVG file',
      onclick: () => saveChartSvg(spec, w, h)
    }, 'SVG'));

  draw();
  box._spec = spec;
  box._redraw = draw;
  return box;
}

/* Save one figure.

   It used to hand a blob to an <a download>, which does nothing at all inside
   the desktop window — the same interface runs in an embedded WebView2/WebKit
   view, where that anchor is inert, so the button was silent and looked
   broken. It now goes through the same path as every other export: into the
   report folder when one is set, to the browser otherwise, and it says which
   either way rather than failing quietly. */
async function saveChartSvg(spec, w, h) {
  const wide = !!figWide[figKey(spec)];
  const filename =
    (spec.title || 'chart').replace(/[^a-z0-9]+/gi, '-').toLowerCase()
      .replace(/^-|-$/g, '') + '.svg';
  const content = '<?xml version="1.0" encoding="UTF-8"?>\n' +
    renderChart(spec, wide ? 1760 : 900, wide ? 500 : 460)
      .replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ');

  if (destMode() === 'folder') {
    try {
      const res = await api('workspace_save',
        { filename, content, encoding: 'text' });
      workspaceInfo = res;
      paintDest();
      if ($('#dlg-files') && $('#dlg-files').open) paintFiles();
      toast(`Saved ${res.saved.name} to ${res.saved.dir}`, 4500);
      return;
    } catch (e) {
      download(filename, content, 'image/svg+xml');
      toast(`Could not write to the report folder — ${e.message} ` +
            `${filename} was downloaded instead.`, 7000);
      return;
    }
  }
  download(filename, content, 'image/svg+xml');
  toast('Downloaded ' + filename);
}

/* ======================================================================= */
/*                                  forms                                  */
/* ======================================================================= */
function bindFields() {
  $$('[data-path]').forEach(inp => {
    const path = inp.dataset.path;
    const isPct = inp.hasAttribute('data-pct');
    const type = inp.dataset.type;
    const read = () => {
      let v;
      if (inp.type === 'checkbox') v = inp.checked;
      else if (inp.type === 'number') {
        v = inp.value === '' ? null : parseFloat(inp.value);
        if (v !== null && isPct) v = v / 100;
        if (v !== null && type === 'int') v = Math.round(v);
      } else {
        v = inp.value;
        if (type === 'int') v = parseInt(v, 10);
      }
      setPath(state.project, path, v);
      touch();
      if (inp.dataset.after) FIELD_HOOKS[inp.dataset.after]?.();
    };
    inp.addEventListener('change', read);
    if (inp.type === 'number' || inp.type === 'text' || inp.tagName === 'TEXTAREA')
      inp.addEventListener('input', read);
  });
}

const FIELD_HOOKS = {};

/* ------------------------------ currency ------------------------------- */
/* The engine computes in USD and converts the finished result. Changing the
   currency therefore has to re-run, not just relabel — that is the bug where
   switching currency left the equipment costs untouched. */

/* Rates last fetched from the server, code -> units per USD. */
let rateTable = null;

async function loadRates(live) {
  const j = await api('exchange_rates', live === undefined ? {} : { live });
  rateTable = j;
  return j;
}

/* Set the project rate for `code` from the table, then re-run if there is a
   result on screen so every figure moves together. */
async function applyCurrency(code, { live, announce = true } = {}) {
  const p = state.project;
  // run() repaints everything; only paint by hand when there is nothing to run.
  const repaint = async () => {
    paintFields();
    if (state.result) await run();
    else { paintEquipment(); paintStreams(); paintBlock(); }
  };
  if (code === 'USD') {
    p.exchange_rate = 1;
    p.exchange_rate_source = 'USD base';
    await repaint();
    return;
  }
  try {
    const j = (live || !rateTable) ? await loadRates(live) : rateTable;
    const rate = j.rates?.[code];
    if (!rate) throw new Error(`no rate available for ${code}`);
    p.exchange_rate = rate;
    p.exchange_rate_source = j.source;
    await repaint();
    if (announce) {
      toast(`${code}: ${fmt(rate, 4)} per USD — ${j.source}` +
            (j.note ? ` (${j.note})` : ''), j.note ? 5200 : 2900);
    }
  } catch (e) {
    // Keep the currency selection; the user can still type a rate by hand.
    toast(`Could not set a ${code} rate: ${e.message}. Enter one by hand.`, 5200);
    paintFields();
  }
}

/* ---------------------------------------------------------------------
   Operating time, restated.

   Hours and capacity factor are multiplied together against every hourly
   rate, and the preset names quote a percentage that is the *stream* factor —
   the hours as a share of the calendar year — not the capacity factor. With
   nothing on screen saying so, a preset called "(85%)" that leaves the
   capacity factor at 100% reads as a bug. This is the line that says so.
   --------------------------------------------------------------------- */
const CALENDAR_HOURS = 8760;

function paintOperatingTime() {
  const note = $('#op-note');
  if (!note) return;
  const opx = state.project.opex || {};
  const hours = Number(opx.operating_hours) || 0;
  const cf = opx.capacity_factor === null || opx.capacity_factor === undefined
    ? 1 : Number(opx.capacity_factor);
  const hoursField = $('#f-hours'), cfField = $('#f-cf');
  if (hoursField) hoursField.title = optHelp('operating_time', 'operating_hours');
  if (cfField) cfField.title = optHelp('operating_time', 'capacity_factor');

  if (!hours) {
    note.innerHTML = 'Set the operating hours — with none, every hourly rate ' +
                     'costs nothing.';
    note.className = 'msg warn';
    return;
  }

  const stream = hours / CALENDAR_HOURS;
  const full = hours * cf;
  note.className = 'msg note';
  note.innerHTML =
    `<b>${fmt(hours, 0)} h/yr</b> is a stream factor of ` +
    `<b>${(stream * 100).toFixed(1)}%</b> of the 8,760-hour calendar year — ` +
    `how much of the year the plant is available. At a capacity factor of ` +
    `<b>${pct(cf)}</b> it produces the equivalent of ` +
    `<b>${fmt(full, 0)}</b> full-load hours, and that is the number every ` +
    `hourly rate is multiplied by.` +
    (state.opPreset
      ? `<br><span class="muted">From ${esc(state.opPreset.name)}` +
        `${state.opPreset.source ? ' — ' + esc(state.opPreset.source) : ''}. ` +
        `The percentage in that name is the stream factor and is already in ` +
        `the hours; it is not the capacity factor, and setting both to it ` +
        `would count the derate twice.</span>`
      : '');

  if (stream > 1) {
    note.className = 'msg warn';
    note.innerHTML += `<br><b>Check</b> — ${fmt(hours, 0)} hours is more than ` +
                      'the 8,760 in a year.';
  }
}

/* The provenance line under the rate box. */
function paintRateNote() {
  const p = state.project;
  const note = $('#rate-note');
  const unit = $('#f-rate-unit');
  if (!note) return;
  const code = p.currency || 'USD';
  if (unit) unit.textContent = code === 'USD' ? 'per USD' : `${code} per USD`;
  $('#f-rate').disabled = code === 'USD';
  $('#btn-rate').disabled = code === 'USD';
  if (code === 'USD') {
    note.textContent = 'USD is the engineering basis — no conversion applied.';
    note.classList.remove('warn');
    return;
  }
  const src = p.exchange_rate_source || 'manual';
  const stale = rateTable?.stale_days;
  note.textContent = `1 USD = ${p.exchange_rate} ${code} · ${src}` +
    (stale != null && rateTable?.as_of ? ` · ${rateTable.as_of}` : '') +
    '. Edit it for the project, or press Update for today’s ECB rate.';
  note.classList.toggle('warn', stale != null && stale > 30);
}

/* ---------------------------------------------------------------------
   The cost index.

   Everything in the estimate is moved between dollar-years by the ratio of
   two CEPCI values, and until now not one of them appeared anywhere in the
   interface — the single number the whole capital estimate rests on was
   invisible. This is that table: the years this study actually touches, what
   each is used for, the published value, and your own value where you have
   one. Values you set are saved with the project, so re-opening a study
   reproduces the number it was quoted on rather than whatever ships today.

   The shipped series ends in 2025 and will not be extended — Chemical
   Engineering took the CEPCI behind a subscription in September 2024 — so a
   study costed in 2030 dollars has no index and must be given one. Such a
   year appears with an empty, required cell rather than a guess.
   --------------------------------------------------------------------- */
const cepciOverrides = () => (state.project.cepci_overrides ||= {});
/* JSON has no integer keys, so the table round-trips as strings. One accessor
   pair, so nothing in here has to remember which side of the wire it is on. */
const cepciKey = y => String(Math.round(Number(y)));
const cepciPublished = y => (state.meta.cepci || {})[cepciKey(y)];
const cepciSet = y => {
  const v = cepciOverrides()[cepciKey(y)];
  return (v === undefined || v === null || v === '') ? null : Number(v);
};
const cepciOf = y => {
  const v = cepciSet(y);
  return v !== null && !Number.isNaN(v) ? v : (cepciPublished(y) ?? null);
};
const cepciEdited = y => {
  const v = cepciSet(y);
  return v !== null && !Number.isNaN(v) && v !== cepciPublished(y);
};

/* The dollar-year one equipment item is escalated *from*.

   The same rule EquipmentItem.evaluate applies: a catalogue correlation is
   quoted in the catalogue's basis year unless the item overrides it; anything
   you priced yourself is quoted in its own year, and in the project's
   dollar-year when you have not said otherwise. Getting this wrong is what
   put 1998 in the table for a study built entirely out of vendor quotes. */
function eqBaseYear(r) {
  const own = Number(r.base_year);
  if (own > 0) return own;
  return r.mode === 'catalogue'
    ? Number(state.meta.basis_year)
    : Number(state.project.dollar_year);
}

/* The years this project escalates through: the dollar-year, the year every
   equipment item is priced in, and anything you have already put a value
   against. Listing the whole 1964-2050 range instead would bury the two or
   three that matter — and listing the catalogue's 1998 basis when nothing in
   the list uses a catalogue correlation is just as unhelpful. */
function cepciYearsInUse() {
  const p = state.project;
  const ys = new Set();
  if (p.dollar_year) ys.add(Number(p.dollar_year));
  (p.equipment || []).forEach(r => ys.add(eqBaseYear(r)));
  Object.keys(cepciOverrides()).forEach(k => ys.add(Number(k)));
  return [...ys].filter(y => Number.isFinite(y) && y > 0).sort((a, b) => a - b);
}

/* What each row is for, so the table reads as part of this study rather than
   as an extract from a reference book. */
function cepciUsedFor(y) {
  const p = state.project;
  const uses = [];
  const year = Number(y);
  if (year === Number(p.dollar_year)) uses.push('this estimate');
  const items = (p.equipment || []).filter(r => eqBaseYear(r) === year);
  const cat = items.filter(r => r.mode === 'catalogue');
  if (cat.length && year === Number(state.meta.basis_year)) {
    uses.push(`catalogue correlations (${cat.length})`);
  }
  const own = items.filter(r => r.mode !== 'catalogue' ||
                                year !== Number(state.meta.basis_year));
  if (own.length) {
    const tags = own.map(r => r.tag);
    uses.push(tags.length > 4
      ? `${tags.slice(0, 4).join(', ')} +${tags.length - 4}` : tags.join(', '));
  }
  return uses.join(' · ') || 'set for this project';
}

/* The longest escalation any item in the study actually goes through, and
   what it is escalating. Reporting the 1998 span on a list of last year's
   vendor quotes was simply wrong. */
function longestEscalation() {
  const to = Number(state.project.dollar_year);
  let worst = null;
  (state.project.equipment || []).forEach(r => {
    const from = eqBaseYear(r);
    if (!(from > 0) || from === to) return;
    if (!worst || Math.abs(to - from) > Math.abs(to - worst.from)) {
      worst = { from, tag: r.tag, mode: r.mode };
    }
  });
  return worst;
}

function paintCepci() {
  const t = $('#cepci-table');
  if (!t) return;
  const years = cepciYearsInUse();
  t.innerHTML = '';
  t.appendChild(el('thead', {}, el('tr', {},
    el('th', { title: optHelp('cost_index', 'dollar_year') }, 'Year'),
    el('th', {}, 'Used for'),
    el('th', { class: 'n', title: optHelp('cost_index', 'cepci') }, 'CEPCI'),
    el('th', { class: 'n', title: optHelp('cost_index', 'provisional') }, 'Published'),
    el('th', {}, ''))));

  const tb = el('tbody');
  years.forEach(y => {
    const pub = cepciPublished(y);
    const prov = (state.meta.cepci_provisional || {})[cepciKey(y)];
    const foot = el('td', {});
    const input = el('input', {
      type: 'number', step: '0.1', min: '0',
      value: cepciOf(y) ?? '',
      placeholder: pub != null ? fmt(pub, 1) : 'required',
      title: optHelp('cost_index', 'override'),
      oninput: e => {
        const v = e.target.value === '' ? null : parseFloat(e.target.value);
        // A value identical to the published one is not an override; storing
        // it would leave the project carrying a "change" that changes nothing.
        if (v === null || Number.isNaN(v) || v === pub) {
          delete cepciOverrides()[cepciKey(y)];
        } else {
          cepciOverrides()[cepciKey(y)] = v;
        }
        touch(); mark(); paintCepciNote(); paintYearNote();
      }
    });

    /* Marked in place rather than by repainting the table: a repaint on every
       keystroke takes the caret out of the cell being typed in. */
    function mark() {
      const on = cepciEdited(y);
      // "The project carries a value here" and "that value differs from the
      // published one" are different states: the reset follows the first, the
      // badge the second, so a row seeded with the published figure can still
      // be taken back off the list.
      const held = cepciSet(y) !== null;
      input.classList.toggle('edited', on);
      foot.innerHTML = '';
      if (on) foot.appendChild(el('span', { class: 'pill warn xs' }, 'edited'));
      if (held) {
        foot.appendChild(el('button', {
          class: 'btn xs', type: 'button',
          title: pub != null ? `Put ${y} back to the published ${fmt(pub, 1)}`
                             : `Clear the value set for ${y}`,
          onclick: () => {
            delete cepciOverrides()[cepciKey(y)];
            touch(); paintCepci(); paintYearNote();
          }
        }, 'reset'));
      } else if (pub == null) {
        foot.appendChild(el('span', { class: 'pill warn xs' }, 'needed'));
      }
    }

    tb.appendChild(el('tr', {},
      el('td', {}, fmtYear(y)),
      el('td', {}, cepciUsedFor(y)),
      el('td', { class: 'n' }, input),
      el('td', { class: 'n', title: prov || '' },
        pub == null ? el('span', { class: 'unit' }, 'not published')
          : el('span', {}, fmt(pub, 1),
               prov ? el('span', { class: 'pill xs', title: prov }, 'est.') : null)),
      foot));
    mark();
  });
  t.appendChild(tb);

  const add = $('#cepci-add');
  if (add) {
    const listed = new Set(years.map(Number));
    add.innerHTML = '';
    add.appendChild(el('option', { value: '' }, 'Add another year…'));
    (state.meta.cepci_years || []).slice().reverse()
      .filter(y => !listed.has(Number(y)))
      .forEach(y => add.appendChild(el('option', { value: y },
        cepciPublished(y) != null ? `${y} — ${fmt(cepciPublished(y), 1)}`
                                  : `${y} — no published value`)));
  }
  paintCepciNote();
}

function paintCepciNote() {
  const box = $('#cepci-note');
  if (!box) return;
  const to = Number(state.project.dollar_year);
  const missing = cepciYearsInUse().filter(y => cepciOf(y) == null);
  box.className = 'msg ' + (missing.length ? 'warn' : 'note');
  if (missing.length) {
    const published = Object.keys(state.meta.cepci || {}).map(Number);
    box.innerHTML = `<b>No index for ${missing.map(fmtYear).join(', ')}.</b> ` +
      'The estimate cannot be escalated to or from ' +
      (missing.length > 1 ? 'those years' : 'that year') +
      ' until you supply a value above. The published series stops at ' +
      `${published.length ? Math.max(...published) : '—'}.`;
    return;
  }
  // The span reported is the longest one this study actually contains, named
  // by the item that carries it — not the catalogue's 1998 basis regardless
  // of whether anything is on it.
  const worst = longestEscalation();
  if (!worst) {
    box.innerHTML = (state.project.equipment || []).length
      ? `Everything in this study is already quoted in ${fmtYear(to)} dollars, ` +
        'so nothing is escalated and the index above does not move the answer.'
      : 'Add equipment and the years it is priced in appear here.';
    return;
  }
  const i0 = cepciOf(worst.from), i1 = cepciOf(to);
  if (!(i0 > 0) || !(i1 > 0)) { box.innerHTML = ''; return; }
  const span = Math.abs(to - worst.from);
  box.className = 'msg ' + (span > 15 ? 'warn' : 'note');
  const what = worst.mode === 'catalogue'
    ? 'the catalogue correlations' : `${esc(worst.tag)}`;
  box.innerHTML =
    `The longest escalation in this study is ${what}, ` +
    `<b>${fmtYear(worst.from)} → ${fmtYear(to)}</b>, at ` +
    `${fmt(i1, 1)} / ${fmt(i0, 1)} = <b>×${(i1 / i0).toFixed(3)}</b>. ` +
    (span > 15
      ? `Cost engineers advise against escalating more than about five years ` +
        `on one index, and this spans ${span}. Treat the capital estimate as ` +
        `AACE Class 5.`
      : `That is ${span} year${span === 1 ? '' : 's'}; cost engineers advise ` +
        `against much more than five on a single index.`);
}

/* The dollar-year select is where a study most often acquires a year with no
   index, so it says which ones those are as soon as the year is chosen. */
function paintYearNote() {
  const note = $('#year-note');
  if (!note) return;
  const y = Number(state.project.dollar_year);
  const v = cepciOf(y);
  note.classList.toggle('warn', v == null);
  note.textContent = v == null
    ? `No CEPCI for ${fmtYear(y)} — set one in Cost index below.`
    : `CEPCI ${fmt(v, 1)}` + (cepciEdited(y) ? ' (set for this project)' : '');
}

/* ------------------------- installation factor -------------------------
   All three installation methods come to one multiplier, and the only place
   it appeared was a note under Results after a run — so a study could be
   built on a factor of 2.42 that nobody had ever seen. This computes it from
   the factor tables the API ships, so it is on screen while the method is
   being chosen, and offers to hand it over as an editable number. */
function installationFactor() {
  const c = state.project.capital, m = state.meta;
  if (c.installation_method === 'factor') {
    const f = Number(c.installation_factor);
    return f > 0 ? f : null;
  }
  if (c.installation_method === 'lang') {
    const f = (m.lang_factors || {})[c.lang_type];
    // Lang factors are quoted against *delivered* cost, so the FOB-to-delivered
    // step is part of the multiplier teakit actually applies.
    return f ? f * (m.lang_delivery_factor || 1.10) : null;
  }
  const bulks = (m.loh_distributive || {})[c.loh_service];
  const setting = (m.loh_setting_factors || {})[c.loh_setting];
  if (!bulks || setting === undefined) return null;
  let f = 1 + setting;
  Object.values(bulks).forEach(([mat, lab]) => { f += mat + mat * lab; });
  return f;
}

/* ------------------ installation factors by equipment type -------------
   The three plant-wide methods multiply the whole purchased total by one
   number, which cannot tell a pump from a crusher. This one resolves a factor
   for each item from its equipment type, and this table is where those
   factors are read and changed. Same arithmetic as the library's
   Project.type_installation_factor, from the same shipped tables, so what is
   on screen is what the estimate will use. */
const typeFactorOverrides = () =>
  (state.project.capital.type_installation_factors ||= {});

/* The DOE/NETL factor for one equipment type. Where the report does not name
   the type, the plant-level service and setting class stand in — and the row
   says which half was borrowed rather than presenting a borrowed number as
   this type's own. */
function typeInstallation(type) {
  const cfg = state.project.capital, m = state.meta;
  const rec = eqTypeRec(type) || {};
  const service = rec.service || cfg.loh_service;
  const setting = rec.setting || cfg.loh_setting;
  const bulks = (m.loh_distributive || {})[service];
  const settingF = (m.loh_setting_factors || {})[setting];
  let dflt = null;
  if (bulks && settingF !== undefined) {
    dflt = 1 + settingF;
    Object.values(bulks).forEach(([mat, lab]) => { dflt += mat + mat * lab; });
  }
  const borrowed = [];
  if (!rec.service) borrowed.push('service regime');
  if (!rec.setting) borrowed.push('setting-labour class');
  const set = typeFactorOverrides()[type];
  const edited = set !== undefined && set !== null && set !== '' && Number(set) > 0;
  return { type, default: dflt, factor: edited ? Number(set) : dflt,
           edited, borrowed, service, setting, known: !borrowed.length };
}

/* Which types the table lists: the ones actually in the equipment list, plus
   anything already overridden. Listing all twenty-seven would bury the four
   that matter to this study. */
function typesInUse() {
  const seen = [];
  (state.project.equipment || []).forEach(r => {
    if (r.cost_is_installed) return;   // never meets an installation factor
    const t = eqCategoryOf(r);
    if (!seen.includes(t)) seen.push(t);
  });
  Object.keys(typeFactorOverrides()).forEach(t => {
    if (!seen.includes(t)) seen.push(t);
  });
  return seen.sort();
}

function paintInstallTypes() {
  const box = $('#inst-types');
  const t = $('#inst-type-table');
  if (!box || !t) return;
  const on = state.project.capital.installation_method === 'type';
  box.style.display = on ? '' : 'none';
  if (!on) return;

  const types = typesInUse();
  t.innerHTML = '';
  t.appendChild(el('thead', {}, el('tr', {},
    el('th', {}, 'Equipment type'),
    el('th', { class: 'n' }, 'Items'),
    el('th', { class: 'n', title: optHelp('installation_by_type', 'factor') },
       'Factor × purchased'),
    el('th', { class: 'n' }, 'Published'),
    el('th', {}, 'Basis'),
    el('th', {}, ''))));

  const tb = el('tbody');
  if (!types.length) {
    tb.appendChild(el('tr', {}, el('td', { colspan: '6',
      style: 'color:var(--muted);padding:10px 8px' },
      'No equipment yet. Add items and their types appear here.')));
  }
  types.forEach(type => {
    const rec = typeInstallation(type);
    const n = (state.project.equipment || [])
      .filter(r => !r.cost_is_installed && eqCategoryOf(r) === type).length;
    const foot = el('td', {});
    const input = el('input', {
      type: 'number', step: '0.05', min: '1',
      value: rec.factor != null ? +rec.factor.toFixed(3) : '',
      placeholder: rec.default != null ? rec.default.toFixed(3) : 'required',
      title: optHelp('installation_by_type', 'factor'),
      oninput: e => {
        const v = e.target.value === '' ? null : parseFloat(e.target.value);
        // A value identical to the published one is not an override; storing
        // it would leave the study carrying a change that changes nothing.
        if (v === null || Number.isNaN(v) ||
            (rec.default != null && Math.abs(v - rec.default) < 5e-4)) {
          delete typeFactorOverrides()[type];
        } else {
          typeFactorOverrides()[type] = v;
        }
        touch(); mark(); paintInstallNote();
      }
    });

    // Marked in place: a repaint on every keystroke takes the caret with it.
    function mark() {
      const now = typeInstallation(type);
      input.classList.toggle('edited', now.edited);
      foot.innerHTML = '';
      if (now.edited) {
        foot.appendChild(el('span', { class: 'pill warn xs' }, 'edited'));
        foot.appendChild(el('button', {
          class: 'btn xs', type: 'button',
          title: `Put ${type} back to the published ` +
                 `${now.default != null ? now.default.toFixed(3) : 'value'}`,
          onclick: () => {
            delete typeFactorOverrides()[type];
            touch(); paintInstallTypes(); paintInstallNote();
          }
        }, 'reset'));
      }
    }

    const basis = rec.known
      ? `${serviceLabel(rec.service)} · ${rec.setting} setting`
      : `${serviceLabel(rec.service)} · ${rec.setting} setting — ` +
        `${rec.borrowed.join(' and ')} from the plant default`;

    tb.appendChild(el('tr', {},
      el('td', {}, type),
      el('td', { class: 'n' }, String(n)),
      el('td', { class: 'n' }, input),
      el('td', { class: 'n' },
        rec.default != null ? `×${rec.default.toFixed(3)}` : '—'),
      el('td', { class: 'basis-cell',
                 title: rec.known ? '' : optHelp('installation_by_type', 'unknown') },
        basis),
      foot));
    mark();
  });
  t.appendChild(tb);
}

function paintInstallNote() {
  const box = $('#inst-note');
  if (!box) return;
  paintInstallTypes();
  box.innerHTML = '';
  box.className = 'msg note';

  /* The per-type method has no single factor to quote before a run — it has
     as many as there are kinds of machine — so it reports the spread, and
     the weighted average only once there is a result to take it from. */
  if (state.project.capital.installation_method === 'type') {
    const recs = typesInUse().map(typeInstallation)
      .filter(r => r.factor != null);
    if (recs.length) {
      const lo = Math.min(...recs.map(r => r.factor));
      const hi = Math.max(...recs.map(r => r.factor));
      box.appendChild(el('span', {},
        el('b', {}, `Installation factors ×${lo.toFixed(3)} to ` +
                    `×${hi.toFixed(3)} `),
        `across ${recs.length} equipment type${recs.length === 1 ? '' : 's'}. `));
    } else {
      box.appendChild(el('span', {}, 'Add equipment to see its installation ' +
        'factors. '));
    }
    const rr = state.result;
    if (rr && rr.purchased_equipment_cost > 0) {
      box.appendChild(el('span', {},
        `On the last run they took ${moneyFull(rr.purchased_equipment_cost)} of ` +
        `purchased equipment to ${moneyFull(rr.bec)} of bare erected cost, ` +
        `×${(rr.installation_factor || 1).toFixed(3)} overall` +
        (rr.installed_direct
          ? `, plus ${moneyFull(rr.installed_direct)} entered at an installed price`
          : '') + '. '));
    }
    box.appendChild(el('span', { class: 'note', style: 'display:block;margin-top:5px' },
      optHelp('installation_method', 'type')));
    return;
  }

  const f = installationFactor();
  if (f == null) {
    box.textContent = 'Choose a service and a setting class to see what the ' +
      'installation step comes to.';
    return;
  }
  const share = (1 - 1 / f) * 100;
  box.appendChild(el('span', {},
    el('b', {}, `Installation factor ×${f.toFixed(3)}. `),
    `Bulk material and construction labour are ${share.toFixed(0)}% of the ` +
    `installed cost; the machines themselves are the other ` +
    `${(100 - share).toFixed(0)}%. `));

  const r = state.result;
  if (r && r.purchased_equipment_cost > 0) {
    box.appendChild(el('span', {},
      `On the last run that took ${moneyFull(r.purchased_equipment_cost)} of ` +
      `purchased equipment to ${moneyFull(r.bec)} of bare erected cost` +
      (r.installed_direct
        ? `, including ${moneyFull(r.installed_direct)} entered at an installed price`
        : '') + '. '));
  }
  if (state.project.capital.installation_method !== 'factor') {
    box.appendChild(el('button', {
      class: 'btn xs', type: 'button', style: 'margin-left:4px',
      title: `Switch to a single user-supplied factor, starting at ${f.toFixed(3)}, ` +
             'so you can type your own',
      onclick: () => {
        state.project.capital.installation_method = 'factor';
        state.project.capital.installation_factor = +f.toFixed(3);
        touch(); paintFields();
        toast(`Installation is now a single factor of ${f.toFixed(3)} — ` +
              'edit it above');
      }
    }, 'Edit this factor'));
  }
  box.appendChild(el('span', { class: 'note', style: 'display:block;margin-top:5px' },
    optHelp('installation', 'effective_factor')));
}

/* ------------------------------- land ---------------------------------
   The field held an amount of money with no unit on it and a note about
   $3,000/acre underneath, which read as though an area were wanted. It is an
   amount; the acreage beside it is an optional way of working that amount
   out, and only one of the two can be in charge at a time. */
function paintLandNote() {
  const note = $('#land-note');
  if (!note) return;
  const c = state.project.capital || {};
  const acres = Number(c.land_area_acres) || 0;
  const rate = Number(c.land_cost_per_acre) || 0;
  note.textContent = acres > 0
    ? `${fmt(acres, 0)} acres × ${moneyFull(rate)}/acre = ` +
      `${moneyFull(acres * rate)}. Clear the area to type an amount directly.`
    : 'An amount of money, not an area. Not depreciable, and a DCF run ' +
      'returns it in the final year.';
}

/* Which of the installation sub-fields belong on screen.

   This used to live inside paintFields(), which the installation-method
   dropdown does not call — so choosing "single user-supplied factor" left the
   distributive-factor selects up and the factor input hidden, and the factor
   had nowhere to be typed. It is its own function now, and the dropdown calls
   it. */
function paintConditionalFields() {
  const im = state.project.capital.installation_method;
  $$('[data-when]').forEach(n =>
    n.style.display = n.dataset.when === im ? '' : 'none');
}

function paintFields() {
  $$('[data-path]').forEach(inp => {
    const v = getPath(state.project, inp.dataset.path);
    if (inp.type === 'checkbox') inp.checked = !!v;
    else if (v === null || v === undefined) inp.value = '';
    else if (inp.hasAttribute('data-pct')) inp.value = +(v * 100).toFixed(4);
    else inp.value = v;
  });
  paintConditionalFields();
  // labour derived figure
  const lb = state.project.opex.labor;
  if (lb) {
    const hc = (lb.operators_per_shift || 0) * (lb.shift_coverage || 4.8);
    const cost = hc * (lb.operator_salary || 0) *
      (1 + (lb.burden_frac || 0) + (lb.supervision_frac || 0));
    $('#labor-calc').innerHTML = hc
      ? `<b>${hc.toFixed(1)}</b> employees, roughly <b>${money(cost)}/yr</b> fully
         loaded before overhead. Headcount scales far more weakly than capacity —
         a plant twice the size rarely needs twice the operators.`
      : 'Set operators per shift to size the payroll.';
  }
  paintOperatingTime();
  paintRateNote();
  paintOptionNotes();
  paintCepci();
  paintYearNote();
  paintInstallNote();
  paintLandNote();
  const loc = (state.meta.locations || []).find(l => l.name === state.project.location);
  $('#loc-note').textContent = loc
    ? `capital ×${loc.factor.toFixed(2)}, labour ×${loc.labor.toFixed(2)}${loc.note ? ' — ' + loc.note : ''}`
    : '';
  $('#method-note').textContent = {
    dcf: 'Most rigorous. Solves the price that returns exactly your discount rate.',
    fcr: 'NETL convention. Charges the FCR against TASC, not TOC.',
    simple: 'Screening only — charges no cost of capital and will understate by 30–50%.'
  }[state.project.method] || '';
  const cv = state.meta.fixed_conventions[state.project.opex.convention];
  $('#conv-note').textContent = cv ? cv.slice(0, 150) : '';
  $('#alloc-note').innerHTML = {
    'byproduct credit': 'Secondary revenue is subtracted from total cost. Standard for an incidental output with a market price — but if credits approach total cost the answer becomes a byproduct price forecast.',
    'market value': 'Cost split in proportion to revenue. Needs a reference price for the primary product, which teakit reports alongside the result.',
    'mass': 'Cost split by tonnes out. Defensible only when a tonne of each product is worth roughly the same.',
    'energy': 'Cost split by heating value. The convention in fuels work and required by several fuel regulations. Set the energy content on each product.'
  }[state.project.products.method] || '';
}

/* ------------------------------ equipment ------------------------------
   Every row is a summary line plus a parameter panel you can open. The panel
   is the point: "exponent 0.6072" means nothing on its own, so each parameter
   carries what it is, what unit it is in, what the catalogue default is, and a
   way back to that default. Overridden values are marked, because an estimate
   in which you cannot see what has been changed is not reviewable. */
const MODE_LABEL = {
  catalogue: 'Catalogue', custom: 'User correlation', direct: 'Direct price'
};

/* Tags whose parameter panel is open. Keyed by tag rather than index so the
   panel stays with its item when rows are added or removed above it. */
const eqOpen = new Set();

/* What an item rolls up under when nothing has been typed — the same rule
   EquipmentItem.effective_category applies on the Python side. */
function eqCategoryOf(r) {
  if (r.category) return r.category.trim();
  if (r.mode === 'catalogue' && r.kind) {
    // Resolve the alias first, exactly as EquipmentItem.effective_category
    // does: "separator" is a name for vessel_horizontal_150psig, and rolling
    // it up as its own type would put a row in the installation-factor table
    // that the estimate never reads.
    const key = ((state.meta || {}).alias_map || {})[r.kind] || r.kind;
    const family = String(key).split('_')[0];
    return ((state.meta || {}).category_labels || {})[family] || family;
  }
  return { direct: 'direct price', custom: 'user correlation' }[r.mode] || 'other';
}

const catRec = key => (state.meta.equipment || []).find(m => m.key === key) || null;
const catUnit = key => (catRec(key) || {}).unit;
const eqHelp = k => optHelp('equipment_param', k);

/* The catalogue's own values for a line, or null when there is no catalogue
   entry behind it. This is what "reset to default" resets to. */
function eqDefaults(r) {
  const m = r.mode === 'catalogue' ? catRec(r.kind) : null;
  if (!m) return null;
  return {
    base_cost: m.base_cost, base_size: m.base_size, exponent: m.exponent,
    base_year: state.meta.basis_year, size_unit: m.unit
  };
}

/* Parameters that are null until you set one, so any value at all is a
   departure from the catalogue. */
const EQ_OVERRIDE_KEYS = ['base_cost', 'base_size', 'exponent', 'base_year'];

/* Parameters that always hold a value, so they have only been changed when
   they differ from this. */
const EQ_PLAIN_DEFAULTS = {
  quantity: 1, spare: 0, material: 'carbon steel', cost_is_installed: false,
};

/* Everything on this item that differs from what the catalogue would supply.
   One function feeds all three consumers that have to agree: the "edited"
   badge on the row, the pill beside a parameter, and whether "Reset all
   parameters to default" is live. They disagreed before — the button read a
   narrower list than the panel could edit, and never woke up. */
function eqEdited(r) {
  const out = [];
  // Only a catalogue item has something to have departed *from*. A direct
  // price and a user correlation are the user's own numbers end to end, so
  // "edited" on one of those was measuring them against a catalogue that was
  // never consulted — and marking a vendor quote as a departure from a
  // default it does not have is noise, not review information.
  if (!eqDefaults(r)) return out;
  EQ_OVERRIDE_KEYS.forEach(k => {
    if (r[k] !== null && r[k] !== undefined && r[k] !== '') out.push(k);
  });
  for (const [k, def] of Object.entries(EQ_PLAIN_DEFAULTS)) {
    const v = (r[k] === null || r[k] === undefined) ? def : r[k];
    if (typeof def === 'boolean' ? Boolean(v) !== def : v !== def) out.push(k);
  }
  return out;
}

/* A year is an identifier, not a quantity: 1998, never "1,998". fmt() puts a
   thousands separator on everything, which is right for money and wrong here,
   and "compared with 2,025" is what it looked like on screen. */
const fmtYear = v => String(Math.round(Number(v)));

/* Put every one of them back. Tag, size, section and note are deliberately
   untouched: they are what this item *is*, not how the catalogue prices it. */
function eqResetAll(r) {
  EQ_OVERRIDE_KEYS.forEach(k => { r[k] = null; });
  for (const [k, def] of Object.entries(EQ_PLAIN_DEFAULTS)) r[k] = def;
}

/* Readable names for the parameters, used by the guide, the reset tooltips
   and the "edited" badge. */
const PARAM_TITLE = {
  tag: 'Tag', kind: 'Correlation', size: 'Size', size_unit: 'Size unit',
  base_cost: 'Base cost', base_size: 'Base size', exponent: 'Exponent n',
  base_year: 'Cost basis year', direct_cost: 'Quoted price',
  quantity: 'Quantity', spare: 'Installed spares', material: 'Material',
  section: 'Plant section', cost_is_installed: 'Price includes installation',
  note: 'Note or description',
};
const paramTitle = k => PARAM_TITLE[k] || optLabel(String(k).replace(/_/g, ' '));
const paramNames = keys => keys.map(k => paramTitle(k).toLowerCase()).join(', ');

/* ------------------------- equipment types ----------------------------
   What kind of machine an item is. It is not the correlation (that is one
   specific machine) and not the plant section (that is where it sits): it is
   what lets teakit offer a scaling exponent and an installation factor for an
   item with no catalogue entry behind it — a vendor quote, or your own
   correlation. The list and the evidence behind each entry come from the
   library, so the exponent on screen is the one the estimate will use. */
const eqTypeRec = name => (state.meta.equipment_types || [])
  .find(t => t.type === String(name || '').trim().toLowerCase()) || null;

/* The exponent to offer for a type, and a sentence saying where it came from.
   An unknown type is not an error — you are allowed to write "quench tower" —
   it falls back to the six-tenths rule and says so. */
function typeExponent(name) {
  const rec = eqTypeRec(name);
  if (rec) return rec;
  return { type: name, exponent: state.meta.six_tenths ?? 0.6,
           basis: 'six-tenths rule', fitted: null, n_fitted: 0,
           typical: null, low: null, high: null,
           source: optHelp('exponent_basis', 'six-tenths rule') };
}

/* Both numbers, for the line under the exponent field. Showing only one would
   hide the disagreement, and a rotary dryer fits at 0.95 against a quoted
   0.45 — that gap is information, not noise. */
function exponentEvidence(name) {
  const r = typeExponent(name);
  const bits = [];
  if (r.fitted != null) {
    bits.push(`fitted ${r.fitted.toFixed(3)} from ${r.n_fitted} ` +
              `correlation${r.n_fitted === 1 ? '' : 's'}`);
  }
  if (r.typical != null) {
    bits.push(`literature ${r.typical.toFixed(2)}` +
              (r.low != null ? ` (${r.low.toFixed(2)}–${r.high.toFixed(2)})` : ''));
  }
  if (!bits.length) bits.push('no published value for this type');
  return bits.join(' · ');
}

/* A control that offers the known types and still lets you write your own.
   A <select> alone would refuse "quench tower"; a bare text field would leave
   every user to invent their own spelling of "heat exchanger" and lose the
   exponent and the installation factor that go with it. */
function eqTypeControl(r, onChanged) {
  const known = (state.meta.equipment_types || []).map(t => t.type);
  const current = (r.category || '').trim();
  const free = current && !known.includes(current.toLowerCase());

  /* What the type was before this edit, held here rather than read back off
     the item: `oninput` has already written the new value by the time
     `change` fires, so asking the item what it used to be always answers
     "what it is now" — and the exponent then never moved. */
  let previous = current;

  const input = el('input', {
    class: 'txt', type: 'text', value: current, list: 'equipment-types',
    placeholder: eqCategoryOf(r),
    title: 'Pick one of the known types, or write your own. A known type ' +
           'brings its scaling exponent and its installation factor with it.',
    onchange: e => {
      const before = previous;
      previous = e.target.value.trim();
      r.category = previous;
      onChanged(before, previous);
    },
    oninput: e => { r.category = e.target.value.trim(); touch(); }
  });
  input.dataset.free = free ? '1' : '';
  return input;
}

/* ---------------------------------------------------------------------
   One parameter control: label, help, input, default, reset.
   `def` is the catalogue default or undefined when there is none.
   --------------------------------------------------------------------- */
function paramField(r, key, opt = {}) {
  const def = opt.def;
  const hasDef = def !== undefined && def !== null;
  /* Two kinds of parameter, and conflating them is what made every quantity
     read as "edited": an *override* field (base cost, exponent, base year) is
     null until you set it, so any value at all is a change from the catalogue;
     a *plain* field (quantity, spares) always holds a value, so it has only
     been changed when it differs from the default. */
  const isOverride = opt.override !== false;
  const fmtDef = opt.fmtDef || (v => (typeof v === 'number' ? fmt(v, opt.dp) : v));
  const isEdited = () => {
    const v = r[key];
    if (!hasDef || v === null || v === undefined || v === '') return false;
    return isOverride ? true : v !== def;
  };

  const wrap = el('div', { class: 'par' });
  const pill = el('span', { class: 'pill warn xs' }, 'edited');
  const label = el('label', {}, opt.label,
    opt.unit ? el('span', { class: 'u' }, opt.unit) : null);
  const foot = el('div', { class: 'par-foot' });

  const set = r[key] !== null && r[key] !== undefined;
  const shown = set ? r[key] : (hasDef ? def : '');

  const input = opt.type === 'text'
    ? el('input', {
        type: 'text', class: 'txt', value: shown ?? '',
        placeholder: opt.placeholder || '',
        oninput: e => { r[key] = e.target.value; touch(); mark(); paintEqSummary(); }
      })
    : el('input', {
        type: 'number', step: String(opt.step ?? 'any'),
        value: shown === '' ? '' : shown, min: opt.min,
        placeholder: hasDef ? String(fmtDef(def)) : (opt.placeholder || ''),
        oninput: e => {
          const v = e.target.value === '' ? null : parseFloat(e.target.value);
          r[key] = (v !== null && Number.isNaN(v)) ? null : v;
          touch(); mark(); repaintEqRow(r);
        }
      });

  /* Update this one control in place. Rebuilding the whole panel on every
     keystroke would take the caret with it, and leaving it alone would mean an
     override shows no sign of being one until some unrelated repaint. */
  function mark() {
    const on = isEdited();
    syncEqDetail(r);                     // keep "Reset all" honest as you type
    wrap.classList.toggle('on', on);
    input.classList.toggle('edited', on);
    if (on && !pill.isConnected) label.appendChild(pill);
    if (!on && pill.isConnected) pill.remove();

    foot.innerHTML = '';
    if (hasDef) {
      foot.appendChild(el('span', {
        class: 'par-def', title: opt.footTitle || null },
        (on ? `default ${fmtDef(def)}` : (isOverride ? 'catalogue default' : 'default')) +
        (opt.foot ? ` · ${opt.foot}` : '')));
      if (on) {
        foot.appendChild(el('button', {
          class: 'btn xs', type: 'button',
          title: `Put ${opt.label} back to ${fmtDef(def)}`,
          // An override field goes back to null so the catalogue supplies it
          // again; a plain field has to be given the default value itself.
          onclick: () => {
            r[key] = isOverride ? null : def;
            touch(); paintEquipment();
          }
        }, 'reset'));
      }
    } else if (opt.required) {
      foot.appendChild(el('span', { class: 'par-def req' }, 'required'));
    }
  }

  /* The explanation is not printed under every parameter of every open row —
     that is the same forty sentences repeated down the page, which is what
     made the panel unreadable. It lives once, in the parameter guide, and
     reaches the individual control as its tooltip. */
  if (opt.help) { input.title = opt.help; label.title = opt.help; }

  wrap.appendChild(label);
  wrap.appendChild(input);
  wrap.appendChild(foot);
  mark();
  return wrap;
}

/* Redraw only what a parameter change can move: this row's cost is stale
   until the next run, so the cell is marked rather than silently wrong. */
function repaintEqRow(r) {
  const tr = $(`#eq-table tr[data-tag="${CSS.escape(r.tag)}"]`);
  if (tr) {
    tr.querySelectorAll('td.n.cost').forEach(td => td.classList.add('stale'));
    // Keep the row's "edited" badge honest while the panel below it is open.
    const basis = tr.children[2];
    const over = eqEdited(r);
    let badge = basis && basis.querySelector('.pill.warn');
    if (over.length && basis && !badge) {
      basis.appendChild(el('span', { class: 'pill warn xs' }, 'edited'));
      badge = basis.querySelector('.pill.warn');
    }
    if (badge) {
      if (!over.length) badge.remove();
      else badge.title = `Changed from the catalogue: ${paramNames(over)}`;
    }
  }
  syncEqDetail(r);
  paintEqSummary();
}

/* Update the open parameter panel's own controls in place.

   "Reset all parameters to default" is rendered once, when the panel opens,
   and every edit after that goes through an input handler that repaints only
   the row. Without this the button kept whatever disabled state it was born
   with, which is why changing a parameter left it dead. */
function syncEqDetail(r) {
  const tr = $(`#eq-table tr[data-tag="${CSS.escape(r.tag)}"]`);
  const next = tr && tr.nextElementSibling;
  const detail = next && next.classList.contains('eq-detail-row') ? next : null;
  const btn = detail && detail.querySelector('.eq-reset-all');
  if (!btn) return;
  const edited = eqEdited(r);
  btn.disabled = !edited.length;
  btn.title = edited.length
    ? `Put ${paramNames(edited)} back to the catalogue values`
    : 'Nothing on this item differs from the catalogue';
}

/* ---------------------------------------------------------------------
   Process parameters and utility consumption.

   An equipment item is one object holding what it is, what drives its cost,
   what else is known about it, and what it consumes. The cost driver stays in
   `size` where the correlation reads it; these two blocks are everything
   around it. A flowsheet import later writes to exactly these fields.
   --------------------------------------------------------------------- */
const utilHelp = k => optHelp('equipment_utility', k);

/* The catalogue record behind a utility name — the same match teakit.project
   makes on the Python side, so what the row previews is what the run costs. */
function utilRec(name) {
  const wanted = String(name || '').trim().toLowerCase();
  if (!wanted) return null;
  return (state.meta.utilities || []).find(
    u => u.name.toLowerCase() === wanted) || null;
}
/* The one price this utility is charged at across the whole study.

   In order of authority, matching Project.utility_price_book on the Python
   side: a price set for the project, then the plant-level line of that name
   on the Operating cost panel, then the shipped catalogue. A price on the
   equipment line itself still wins if a loaded project carries one — old
   files must not silently change — but the interface no longer offers to set
   one, because electricity does not cost one thing at the compressor and
   another at the pump. */
function projectPrice(name) {
  if (!name) return null;
  const opx = state.project.opex || {};
  const explicit = (opx.utility_prices || {})[name];
  if (explicit !== undefined && explicit !== null) return Number(explicit);
  for (const key of ['utilities', 'waste', 'raw_materials', 'other_variable']) {
    const hit = (opx[key] || []).find(x => x.name === name);
    if (hit) return Number(hit.price);
  }
  const rec = utilRec(name);
  return rec ? Number(rec.price) : null;
}

/* Where that price came from, for the line under the control. */
function projectPriceSource(name) {
  const opx = state.project.opex || {};
  if (((opx.utility_prices || {})[name]) !== undefined) return 'set for this project';
  for (const key of ['utilities', 'waste', 'raw_materials', 'other_variable']) {
    const hit = (opx[key] || []).find(x => x.name === name);
    if (hit) return hit.source || `the ${name} line on this project`;
  }
  const rec = utilRec(name);
  return rec ? (rec.source || 'utility catalogue') : 'no price';
}

/* Set the price for a utility everywhere it is used, in one place. */
function setProjectPrice(name, price) {
  if (!name) return;
  const opx = state.project.opex || {};
  for (const key of ['utilities', 'waste', 'raw_materials', 'other_variable']) {
    const hit = (opx[key] || []).find(x => x.name === name);
    if (hit) { hit.price = price; return; }
  }
  (opx.utility_prices ||= {})[name] = price;
}

const utilPrice = u => (u.price !== null && u.price !== undefined && u.price !== '')
  ? Number(u.price) : projectPrice(u.name);
const utilUnit = u => u.unit || (utilRec(u.name) || {}).unit || '';

/* Duty units, spares excluded — EquipmentItem.running_quantity on the Python
   side. A spare is bought and is in the capital; it is not running and it is
   not drawing anything. */
const runningUnits = item => Math.max(parseInt(item.quantity, 10) || 0, 0);

/* Utility lines the user has chosen to name themselves. Keyed on the object,
   not on an index — a WeakSet keeps nothing alive, survives rows being added
   and removed above it, and cannot leak into the saved project the way an
   extra field on the line would. */
const utilCustom = new WeakSet();

/* Custom means: the user asked for a free-text name, or the name they have is
   one the catalogue has never heard of (an imported or hand-edited project). */
const isCustomUtil = u => utilCustom.has(u) ||
  Boolean(u.name && !utilRec(u.name));

/* Adopt a catalogued utility wholesale.

   The unit and the category come with the name — that is the point of picking
   from a catalogue — and any price typed against the *previous* utility is
   dropped, because a price entered for electricity is not a price for steam
   and silently carrying it over is worse than asking again. */
function applyUtilCatalogue(u, name) {
  const rec = utilRec(name);
  u.name = name;
  if (rec) {
    u.unit = rec.unit;
    u.category = rec.category || 'utility';
    u.price = null;                     // null = take the catalogue's price
    u.source = '';
  }
}

/* The name control: a dropdown like every other one, with a way out to a
   free-text name for anything the catalogue does not carry. */
function utilNameControl(item, u, onChanged) {
  if (isCustomUtil(u)) {
    const box = el('div', { class: 'util-name-custom' },
      el('input', {
        class: 'txt', type: 'text', value: u.name || '',
        placeholder: 'name this utility',
        title: 'A utility of your own. It has no catalogue price, so give it ' +
               'one in the Price column.',
        // No repaint on a keystroke: rebuilding the table here is what threw
        // the caret away and sent the page back to the top on every backspace.
        oninput: e => { u.name = e.target.value; touch(); onChanged(); }
      }),
      el('button', {
        class: 'x', type: 'button', title: 'Back to the utility catalogue',
        onclick: () => {
          utilCustom.delete(u);
          if (u.name && !utilRec(u.name)) u.name = '';
          touch(); onChanged(true);
        }
      }, '↩'));
    return box;
  }

  const sel = el('select', {
    class: 'txt', title: utilHelp('name'),
    onchange: e => {
      if (e.target.value === '__custom__') {
        utilCustom.add(u);
        u.name = ''; u.price = null;
      } else {
        applyUtilCatalogue(u, e.target.value);
      }
      touch(); onChanged(true);
    }
  });
  sel.appendChild(el('option', { value: '', selected: !u.name || null },
                     'Choose a utility…'));
  const groups = {};
  (state.meta.utilities || []).forEach(x => {
    (groups[x.category || 'utility'] = groups[x.category || 'utility'] || []).push(x);
  });
  Object.entries(groups).forEach(([cat, list]) => {
    const og = el('optgroup', { label: optLabel(cat.replace(/_/g, ' ')) });
    list.forEach(x => og.appendChild(el('option', {
      value: x.name, selected: x.name === u.name || null,
      title: `${fmt(x.price)} $/${x.unit} — ${x.source || ''}` },
      `${sentenceLabel(x.name)}  ·  ${fmt(x.price)} $/${x.unit}`)));
    sel.appendChild(og);
  });
  sel.appendChild(el('option', { value: '__custom__' },
                     'Something else… (name it yourself)'));
  return sel;
}

/* The rate-basis control. Each option carries its own sentence, so hovering
   either the control or an open option says what the choice actually does. */
/* The basis is a repaint, not a sync.

   It used to only move the cost cells, which was right when the unit column
   read the same either way. It no longer does: an hourly line is labelled in
   its rate unit (kW) and an annual one in its quantity unit (kWh), so
   changing the basis has to redraw the unit control beside it or the row
   ends up claiming a compressor consumes 5,200 kW per year. */
function utilBasisControl(u, onChanged) {
  const sel = el('select', {
    class: 'txt',
    title: utilHelp('basis') + '\n\n' +
           `Per operating hour: ${optHelp('stream_basis', 'hour')}\n\n` +
           `Per year: ${optHelp('stream_basis', 'year')}`,
    onchange: e => { u.basis = e.target.value; touch(); onChanged(); }
  });
  [['hour', STREAM_BASIS_LABEL.hour], ['year', STREAM_BASIS_LABEL.year]]
    .forEach(([v, label]) => sel.appendChild(el('option', {
      value: v, selected: (u.basis === 'year') === (v === 'year') || null,
      title: optHelp('stream_basis', v) }, label)));
  return sel;
}

/* Every cost cell for one line, wherever it is on the page.

   The same utility object is shown twice — in the equipment row and in the
   Operating cost roll-up — and both have to move when a rate changes. Updating
   the cells by key beats repainting either table: a repaint would take the
   caret out of the box being typed in. */
const utilKey = (item, i) => `${item.tag}${i}`;

function syncUtilLine(item, i) {
  const annual = utilAnnual(item, item.utilities[i]);
  $$(`[data-util="${CSS.escape(utilKey(item, i))}"]`).forEach(cell => {
    cell.textContent = annual === null ? 'no price' : moneyFull(annual);
    cell.classList.toggle('unpriced', annual === null);
    // A negative rate is generation: the line is a credit, not an expense.
    cell.classList.toggle('credit', annual !== null && annual < 0);
    cell.title = annual === null
      ? 'No price for this utility — give it one in the Price column'
      : moneyExact(annual);
  });
  syncUtilTotals();
}

/* Every annual-cost cell on the Operating cost panel, recomputed.

   Called when something global moves — the operating hours, the capacity
   factor, a utility price — rather than when one line is edited. */
function syncAllCostCells() {
  // Every box showing the price of a given utility is showing the *same*
  // number. Change one and the rest have to follow, or the panel displays two
  // prices for one utility while charging a third — exactly the confusion the
  // price book exists to remove. The box being typed in is skipped so the
  // caret survives.
  $$('[data-price]').forEach(inp => {
    if (inp === document.activeElement) return;
    const v = projectPrice(inp.dataset.price);
    const shown = v === null ? '' : String(v);
    if (inp.value !== shown) inp.value = shown;
  });
  (state.project.equipment || []).forEach(item =>
    (item.utilities || []).forEach((u, i) => syncUtilLine(item, i)));
  Object.entries(STREAM_TABLES).forEach(([key]) => {
    ((state.project.opex || {})[key] || []).forEach((st, i) =>
      syncStreamRow(key, i));
  });
  syncUtilTotals();
}

/* One plant-level stream's cost cell. */
function syncStreamRow(key, i) {
  const st = ((state.project.opex || {})[key] || [])[i];
  if (!st) return;
  const annual = streamAnnual(st);
  $$(`[data-stream="${CSS.escape(key + '|' + i)}"]`).forEach(cell => {
    cell.textContent = annual === null ? '—' : moneyFull(annual);
    cell.title = annual === null ? '' : moneyExact(annual);
  });
}

/* The per-item footer and the roll-up's group and grand totals. */
function syncUtilTotals() {
  (state.project.equipment || []).forEach(item => {
    const total = (item.utilities || [])
      .reduce((a, u) => a + (utilAnnual(item, u) || 0), 0);
    $$(`[data-util-total="${CSS.escape(item.tag)}"]`).forEach(n => {
      n.textContent = moneyFull(total) + '/yr';
      n.title = moneyExact(total);
    });
  });
  const groups = {};
  let grand = 0;
  (state.project.equipment || []).forEach(item =>
    (item.utilities || []).forEach(u => {
      if (!u.rate) return;
      const v = utilAnnual(item, u) || 0;
      groups[u.name || '(unnamed)'] = (groups[u.name || '(unnamed)'] || 0) + v;
      grand += v;
    }));
  $$('[data-util-group]').forEach(n => {
    const v = groups[n.dataset.utilGroup] || 0;
    n.textContent = moneyFull(v);
    n.title = moneyExact(v);
  });
  $$('[data-util-grand]').forEach(n => {
    n.textContent = moneyFull(grand);
    n.title = moneyExact(grand);
  });
}

/* teakit.opex.Stream.annual_cost, in the browser.

   One formula, used by the plant-level table, the equipment blocks and the
   roll-up, so every annual figure on the Operating cost panel is the figure
   the engine will produce — and, more to the point, so all of them move the
   moment the operating hours or the capacity factor move. They used to be
   read out of the last run, which meant editing the operating time changed
   nothing on screen until something unrelated forced a repaint. */
function streamAnnual({ rate, price, basis, scales_with_rate }) {
  if (price === null || price === undefined) return null;
  const op = state.project.opex || {};
  const hours = Number(op.operating_hours) || 0;
  const cf = Number(op.capacity_factor);
  const perYear = basis === 'year' ? 1 : hours;
  const scale = scales_with_rate === false ? 1 : (Number.isFinite(cf) ? cf : 1);
  return (Number(rate) || 0) * perYear * scale * Number(price);
}

/* Annual cost of one equipment utility line, with the item's running units
   applied. */
function utilAnnual(item, u) {
  const price = utilPrice(u);
  if (price === null) return null;
  const units = u.per_unit === false ? 1 : runningUnits(item);
  return streamAnnual({ rate: (Number(u.rate) || 0) * units, price,
                        basis: u.basis,
                        scales_with_rate: u.scales_with_rate });
}

/* The unit control.

   A utility is metered in a small, known set of units, and typing one is how
   a project ends up pricing kWh against a rate quoted in MW. The dropdown
   offers the set for whatever is being measured — electrical energy, fuel,
   mass, volume, normalised gas volume — with "Other…" for anything teakit
   does not know, and whatever the project already holds kept at the top so a
   loaded file never loses its unit.

   The units are quantity units, because that is what a price is per. What an
   engineer says aloud is the rate: 5,200 kWh per operating hour is 5,200 kW,
   and unitNote() prints that underneath. */
function unitOptionsFor(name, unit) {
  const sets = (state.meta && state.meta.unit_sets) || {};
  const measures = (state.meta && state.meta.utility_measures) || {};
  const key = String(name || '').trim().toLowerCase();
  let measure = '';
  for (const [k, v] of Object.entries(measures)) {
    if (k.toLowerCase() === key) { measure = v; break; }
  }
  if (!measure) {
    for (const [k, v] of Object.entries(sets)) {
      if ((v.units || []).includes(unit)) { measure = k; break; }
    }
  }
  const opts = [...(((sets[measure] || {}).units) || [])];
  if (unit && !opts.includes(unit)) opts.unshift(unit);
  return { measure, opts };
}

/* The unit a rate is *read* in, as against the unit it is priced in.

   A stream holds a quantity unit because that is what the price is per —
   electricity is metered and sold in kWh. On an hourly line the number beside
   it is not an amount of energy, it is a draw: 5,200 kWh per operating hour
   is 5,200 kW, and no engineer writes it the other way. The unit control
   therefore shows kW while the project stores kWh, and hours x kW = kWh keeps
   the arithmetic honest. */
function rateUnit(unit, basis, name) {
  if (!unit) return '';
  if (basis !== 'hour') return unit;
  const { measure } = unitOptionsFor(name, unit);
  const perHour = (((state.meta || {}).unit_sets || {})[measure] || {}).per_hour || {};
  return perHour[unit] || `${unit}/h`;
}

/* Why the label differs from the unit the price is quoted in — on the control
   itself, so nobody has to guess whether to type kW or kWh. */
function rateUnitNote(unit, basis, name) {
  if (!unit) return '';
  const shown = rateUnit(unit, basis, name);
  if (basis !== 'hour' || shown === unit) {
    return `Quantity is in ${unit}, and the price is per ${unit}.`;
  }
  return `Rate is in ${shown}; the price is per ${unit}, and the annual ` +
         `quantity comes out in ${unit} — operating hours x ${shown}.`;
}

/* What a price cell is actually per. The rate beside it may be shown in kW
   while the price is per kWh, so the box says which. */
function priceTitle(line) {
  const unit = line.unit || (utilRec(line.name) || {}).unit || '';
  return (unit ? `Price in USD per ${unit}. ` : '') + utilHelp('price') +
    (unit ? '\n\n' + rateUnitNote(unit, line.basis, line.name) : '');
}

/* "5,200 kWh per operating hour" is 5,200 kW. Say so. */
function naturalRate(rate, unit, basis, name) {
  const r = Number(rate) || 0;
  if (basis === 'year') return `${fmtRate(r)} ${unit || ''}/yr`.trim();
  return `${fmtRate(r)} ${rateUnit(unit, basis, name)}`.trim();
}

function unitControl(line, onChanged) {
  const { opts } = unitOptionsFor(line.name, line.unit);
  const hint = () => optHelp('equipment_utility', 'unit') + '\n\n' +
    rateUnitNote(line.unit, line.basis, line.name);
  if (!opts.length) {
    return el('input', {
      class: 'txt', type: 'text', value: line.unit || '', size: '6',
      placeholder: 'unit', title: hint(),
      oninput: e => { line.unit = e.target.value; touch(); onChanged(); } });
  }
  const sel = el('select', {
    class: 'txt', title: hint(),
    onchange: e => {
      if (e.target.value === '__other__') {
        unitFreeText.add(line);
      } else {
        line.unit = e.target.value;
      }
      touch(); onChanged(true);
    } });
  /* The option's *value* is the quantity unit the project stores; its *label*
     is what the number beside it actually is. On an hourly electricity line
     that reads kW, not kWh. */
  opts.forEach(u => sel.appendChild(el('option', {
    value: u, selected: u === line.unit || null,
    title: rateUnitNote(u, line.basis, line.name) },
    rateUnit(u, line.basis, line.name))));
  sel.appendChild(el('option', { value: '__other__' }, 'Other…'));
  if (unitFreeText.has(line)) {
    return el('div', { class: 'util-name-custom' },
      el('input', {
        class: 'txt', type: 'text', value: line.unit || '', size: '6',
        placeholder: 'unit', title: hint(),
        oninput: e => { line.unit = e.target.value; touch(); onChanged(); } }),
      el('button', { class: 'x', type: 'button', title: 'Back to the unit list',
        onclick: () => { unitFreeText.delete(line); touch(); onChanged(true); }
      }, '↩'));
  }
  return sel;
}

/* Lines whose unit the user is typing rather than picking. */
const unitFreeText = new WeakSet();

/* A block heading with an "add" button on the right. */
function eqBlockHead(title, hint, addLabel, onAdd) {
  return el('div', { class: 'eq-block-h' },
    el('div', {},
      el('h4', {}, title),
      hint ? el('span', { class: 'eq-block-hint' }, hint) : null),
    el('button', { class: 'btn xs', type: 'button', onclick: onAdd }, addLabel));
}

/* --- process parameters ------------------------------------------------ */
function eqParameterBlock(r) {
  const box = el('div', { class: 'eq-block' });
  (r.parameters ||= []);

  box.appendChild(eqBlockHead(
    'Process parameters',
    'Recorded and reported. The cost comes from the size above, not from these.',
    '+ Parameter',
    () => { r.parameters.push({ name: '', value: 0, unit: '', note: '' });
            touch(); paintEquipment(); }));

  const grid = el('div', { class: 'kv-grid params' });
  grid.appendChild(el('div', { class: 'kv-head' }, 'Parameter'));
  grid.appendChild(el('div', { class: 'kv-head n' }, 'Value'));
  grid.appendChild(el('div', { class: 'kv-head' }, 'Unit'));
  grid.appendChild(el('div', { class: 'kv-head' }, 'Note'));
  grid.appendChild(el('div', { class: 'kv-head' }, ''));

  /* The cost driver, shown in the same table but not editable here: it is the
     "size" control in the grid above, and two boxes holding one number is how
     they come to disagree. */
  const d = catRec(r.kind);
  grid.appendChild(el('div', { class: 'kv-locked' }, 'size',
    el('span', { class: 'pill xs' }, 'cost driver')));
  grid.appendChild(el('div', { class: 'kv-locked n' }, fmt(r.size, 4)));
  grid.appendChild(el('div', { class: 'kv-locked' },
    r.mode === 'direct' ? (r.size_unit || '—') : (d ? d.unit : (r.size_unit || '—'))));
  grid.appendChild(el('div', { class: 'kv-locked' }, 'Edited in the box above'));
  grid.appendChild(el('div', {}));

  r.parameters.forEach((prm, i) => {
    grid.appendChild(el('input', {
      class: 'txt', type: 'text', value: prm.name || '',
      placeholder: 'e.g. duty, inlet flow',
      list: 'param-names',
      oninput: e => { prm.name = e.target.value; touch(); } }));
    grid.appendChild(el('input', {
      type: 'number', class: 'n', step: 'any', value: prm.value ?? 0,
      oninput: e => { prm.value = parseFloat(e.target.value) || 0; touch(); } }));
    grid.appendChild(el('input', {
      class: 'txt', type: 'text', value: prm.unit || '', placeholder: 'kW',
      oninput: e => { prm.unit = e.target.value; touch(); } }));
    grid.appendChild(el('input', {
      class: 'txt', type: 'text', value: prm.note || '', placeholder: 'optional',
      oninput: e => { prm.note = e.target.value; touch(); } }));
    grid.appendChild(el('button', {
      class: 'x', type: 'button', title: 'Remove this parameter',
      onclick: () => { r.parameters.splice(i, 1); touch(); paintEquipment(); }
    }, '×'));
  });

  box.appendChild(grid);
  if (!r.parameters.length) {
    box.appendChild(el('div', { class: 'eq-block-empty' },
      'Nothing else recorded. Add duty, flow, temperature or pressure — they ' +
      'go into the equipment schedule and give the utility figures below ' +
      'something to be checked against.'));
  }
  return box;
}

/* --- replacement parts -------------------------------------------------
   Neither a utility nor capital: bought again and again on a schedule, so
   teakit spreads each over its interval and adds it to the operating cost.
   ----------------------------------------------------------------------- */
const partHelp = k => optHelp('equipment_consumable', k);

/* The intervals people actually use, plus a way to type any other. */
const INTERVAL_PRESETS = [
  [0.25, 'Every 3 months'], [0.5, 'Every 6 months'], [1, 'Every year'],
  [1.5, 'Every 18 months'], [2, 'Every 2 years'], [3, 'Every 3 years'],
  [4, 'Every 4 years'], [5, 'Every 5 years'], [10, 'Every 10 years'],
];

function intervalLabel(y) {
  const v = Number(y) || 0;
  if (v <= 0) return 'no interval';
  const hit = INTERVAL_PRESETS.find(([n]) => Math.abs(n - v) < 1e-9);
  if (hit) return hit[1].toLowerCase();
  const months = v * 12;
  if (Math.abs(months - Math.round(months)) < 1e-6 && months < 24) {
    return `every ${Math.round(months)} months`;
  }
  return `every ${(+v.toFixed(4))} years`;
}

/* Annual cost of one part, the way teakit.project computes it. */
function partAnnual(item, c) {
  const iv = Number(c.interval_years) || 0;
  if (iv <= 0) return null;
  const n = c.per_unit === false ? 1 : runningUnits(item);
  const qty = (Number(c.quantity) || 0) * n / iv;
  return streamAnnual({ rate: qty, price: Number(c.unit_cost) || 0,
                        basis: 'year', scales_with_rate: c.scales_with_rate });
}

const partKey = (item, i) => `${item.tag}#${i}`;

function syncPartLine(item, i) {
  const annual = partAnnual(item, item.consumables[i]);
  $$(`[data-part="${CSS.escape(partKey(item, i))}"]`).forEach(cell => {
    cell.textContent = annual === null ? 'no interval' : moneyFull(annual);
    cell.classList.toggle('unpriced', annual === null);
    cell.title = annual === null
      ? 'Set a replacement interval — without one there is nothing to spread'
      : moneyExact(annual);
  });
  const total = (item.consumables || [])
    .reduce((a, c) => a + (partAnnual(item, c) || 0), 0);
  $$(`[data-part-total="${CSS.escape(item.tag)}"]`).forEach(n => {
    n.textContent = moneyFull(total) + '/yr';
    n.title = moneyExact(total);
  });
}

function eqConsumableBlock(r) {
  const box = el('div', { class: 'eq-block' });
  (r.consumables ||= []);

  box.appendChild(eqBlockHead(
    'Replacement parts',
    'Electrodes, catalyst, membranes, liners — bought again on a schedule ' +
    'and spread over it.',
    '+ Part',
    () => { r.consumables.push({ name: '', quantity: 1, unit: '', unit_cost: 0,
                                 interval_years: 1, per_unit: true,
                                 scales_with_rate: true, category: 'catalyst',
                                 source: '', note: '' });
            touch(); paintEquipment(); }));

  const grid = el('div', { class: 'kv-grid parts' });
  [['Part', 'name'], ['Qty each', 'quantity'], ['Unit', 'unit'],
   ['Cost USD each', 'unit_cost'], ['Replaced', 'interval_years'],
   ['Per unit', 'per_unit'], ['Follows CF', 'scales_with_rate'],
   [`Annual (${curCode()})`, ''], ['', '']]
    .forEach(([h, k], idx) => grid.appendChild(el('div', {
      class: 'kv-head' + ([1, 3, 7].includes(idx) ? ' n' : '') +
             ([5, 6].includes(idx) ? ' c' : ''),
      title: k ? partHelp(k) : '' }, h)));

  const running = runningUnits(r);

  r.consumables.forEach((c, i) => {
    const annual = partAnnual(r, c);
    grid.appendChild(el('input', {
      class: 'txt', type: 'text', value: c.name || '',
      placeholder: 'electrodes', title: partHelp('name'),
      oninput: e => { c.name = e.target.value; touch(); } }));
    grid.appendChild(el('input', {
      type: 'number', class: 'n', step: 'any', min: '0', value: c.quantity ?? 1,
      title: partHelp('quantity'),
      oninput: e => { c.quantity = parseFloat(e.target.value) || 0;
                      touch(); syncPartLine(r, i); } }));
    grid.appendChild(el('input', {
      class: 'txt', type: 'text', value: c.unit || '', placeholder: 'set',
      title: partHelp('unit'),
      oninput: e => { c.unit = e.target.value; touch(); } }));
    grid.appendChild(el('input', {
      type: 'number', class: 'n', step: 'any', min: '0', value: c.unit_cost ?? 0,
      title: partHelp('unit_cost'),
      oninput: e => { c.unit_cost = parseFloat(e.target.value) || 0;
                      touch(); syncPartLine(r, i); } }));

    // Interval: the common schedules as a list, with any other typed in.
    const known = INTERVAL_PRESETS.some(([n]) =>
      Math.abs(n - (Number(c.interval_years) || 0)) < 1e-9);
    if (known && !partFreeInterval.has(c)) {
      const sel = el('select', { class: 'txt', title: partHelp('interval_years'),
        onchange: e => {
          if (e.target.value === '__other__') { partFreeInterval.add(c); }
          else { c.interval_years = parseFloat(e.target.value); }
          touch(); paintEquipment();
        } });
      INTERVAL_PRESETS.forEach(([v, label]) => sel.appendChild(el('option', {
        value: v, selected: Math.abs(v - c.interval_years) < 1e-9 || null }, label)));
      sel.appendChild(el('option', { value: '__other__' }, 'Other…'));
      grid.appendChild(sel);
    } else {
      grid.appendChild(el('div', { class: 'util-name-custom' },
        el('input', {
          type: 'number', step: 'any', min: '0', value: c.interval_years ?? 1,
          title: partHelp('interval_years') + '\nIn years: 0.25 is quarterly.',
          oninput: e => { c.interval_years = parseFloat(e.target.value) || 0;
                          touch(); syncPartLine(r, i); } }),
        el('button', { class: 'x', type: 'button', title: 'Back to the list',
          onclick: () => { partFreeInterval.delete(c);
                           c.interval_years = 1; touch(); paintEquipment(); }
        }, '↩')));
    }

    grid.appendChild(el('label', { class: 'kv-check',
      title: partHelp('per_unit') +
        `\nThis item has ${running} running unit${running === 1 ? '' : 's'}.` },
      el('input', { type: 'checkbox', checked: c.per_unit !== false || null,
        onchange: e => { c.per_unit = e.target.checked;
                         touch(); syncPartLine(r, i); } })));
    grid.appendChild(el('label', { class: 'kv-check',
      title: partHelp('scales_with_rate') },
      el('input', { type: 'checkbox', checked: c.scales_with_rate !== false || null,
        onchange: e => { c.scales_with_rate = e.target.checked;
                         touch(); syncPartLine(r, i); } })));
    grid.appendChild(el('div', {
      class: 'kv-cost n' + (annual === null ? ' unpriced' : ''),
      'data-part': partKey(r, i),
      title: annual === null ? 'Set a replacement interval' : moneyExact(annual) },
      annual === null ? 'no interval' : moneyFull(annual)));
    grid.appendChild(el('button', {
      class: 'x', type: 'button', title: 'Remove this part',
      onclick: () => { r.consumables.splice(i, 1); touch(); paintEquipment(); }
    }, '×'));
  });

  box.appendChild(grid);
  if (!r.consumables.length) {
    box.appendChild(el('div', { class: 'eq-block-empty' },
      'Nothing recorded. Add anything this item wears out and has replaced — ' +
      'a set of electrodes on an 18-month cycle costs two-thirds of a set a ' +
      'year, and that is what reaches the operating cost.'));
  } else {
    const total = r.consumables.reduce((a, c) => a + (partAnnual(r, c) || 0), 0);
    box.appendChild(el('div', { class: 'eq-block-foot' },
      el('span', {}, r.consumables.filter(c => c.name).map(c =>
        `${c.name} ${intervalLabel(c.interval_years)}`).join(' · ')),
      el('b', { 'data-part-total': r.tag, title: moneyExact(total) },
        moneyFull(total) + '/yr')));
  }
  return box;
}

const partFreeInterval = new WeakSet();

/* --- utility consumption ----------------------------------------------- */
function eqUtilityBlock(r) {
  const box = el('div', { class: 'eq-block' });
  (r.utilities ||= []);

  box.appendChild(eqBlockHead(
    'Utility consumption',
    'Priced and rolled into the operating cost, tagged with this item.',
    '+ Utility',
    () => { r.utilities.push({ name: '', rate: 0, unit: '', price: null,
                               basis: 'hour', scales_with_rate: true,
                               per_unit: true, category: 'utility',
                               source: '', note: '' });
            touch(); paintEquipment(); }));

  const grid = el('div', { class: 'kv-grid utils' });
  [['Utility', ''], ['Rate', 'n'], ['Unit', ''], ['Price USD/unit', 'n'],
   ['Rate basis', ''], ['Per unit', 'c'], ['Follows CF', 'c'],
   [`Annual (${curCode()})`, 'n'], ['', '']]
    .forEach(([h, cls]) => grid.appendChild(
      el('div', { class: 'kv-head ' + cls, title: h ? utilHelp(
        { 'Rate': 'rate', 'Unit': 'unit', 'Price USD/unit': 'price',
          'Rate basis': 'basis', 'Per unit': 'per_unit',
          'Follows CF': 'scales_with_rate', 'Utility': 'name' }[h] || '') : '' }, h)));

  const running = Math.max(parseInt(r.quantity, 10) || 0, 0);

  r.utilities.forEach((u, i) => {
    const rec = utilRec(u.name);
    const annual = utilAnnual(r, u);
    // A discrete choice repaints; a keystroke never does.
    const changed = full => full ? paintEquipment() : syncUtilLine(r, i);

    grid.appendChild(utilNameControl(r, u, changed));
    grid.appendChild(el('input', {
      type: 'number', class: 'n', step: 'any', value: u.rate ?? 0,
      title: utilHelp('rate'),
      oninput: e => { u.rate = parseFloat(e.target.value) || 0;
                      touch(); syncUtilLine(r, i); } }));
    grid.appendChild(unitControl(u, changed));
    grid.appendChild(el('input', {
      type: 'number', class: 'n', step: 'any', 'data-price': u.name || '',
      value: utilPrice(u) === null ? '' : utilPrice(u),
      placeholder: 'no price',
      title: priceTitle(u) + '\n\n' + projectPriceSource(u.name) +
             '\n\nThis is the price for the whole study. Editing it here ' +
             'moves every item drawing on this utility.',
      oninput: e => {
        const v = e.target.value === '' ? null : (parseFloat(e.target.value) || 0);
        // One utility, one price: this writes to the project's price book,
        // not to this line, so the compressor and the pump cannot end up
        // being charged differently for the same electricity.
        u.price = null;
        if (v !== null) setProjectPrice(u.name, v);
        touch(); syncAllCostCells();
      } }));
    grid.appendChild(utilBasisControl(u, () => changed(true)));
    grid.appendChild(el('label', { class: 'kv-check',
      title: utilHelp('per_unit') + (running > 1
        ? `\nThis item has ${running} running unit${running === 1 ? '' : 's'}.` : '') },
      el('input', { type: 'checkbox', checked: u.per_unit !== false || null,
        onchange: e => { u.per_unit = e.target.checked;
                         touch(); syncUtilLine(r, i); } })));
    grid.appendChild(el('label', { class: 'kv-check', title: utilHelp('scales_with_rate') },
      el('input', { type: 'checkbox', checked: u.scales_with_rate !== false || null,
        onchange: e => { u.scales_with_rate = e.target.checked;
                         touch(); syncUtilLine(r, i); } })));
    grid.appendChild(el('div', {
      class: 'kv-cost n' + (annual === null ? ' unpriced'
                            : (annual < 0 ? ' credit' : '')),
      'data-util': utilKey(r, i),
      title: annual === null
        ? 'No price for this utility — give it one in the Price column'
        : moneyExact(annual) },
      annual === null ? 'no price' : moneyFull(annual)));
    grid.appendChild(el('button', {
      class: 'x', type: 'button', title: 'Remove this utility line',
      onclick: () => { r.utilities.splice(i, 1); touch(); paintEquipment(); }
    }, '×'));
  });

  box.appendChild(grid);

  if (!r.utilities.length) {
    box.appendChild(el('div', { class: 'eq-block-empty' },
      'Nothing recorded. Add what this item draws when it runs — the lines ' +
      'appear on the Operating cost panel under this tag, and move when the ' +
      'item does.'));
  } else {
    const total = r.utilities.reduce((a, u) => a + (utilAnnual(r, u) || 0), 0);
    box.appendChild(el('div', { class: 'eq-block-foot' },
      el('span', {}, running > 1
        ? `${running} running unit${running === 1 ? '' : 's'} — spares excluded, ` +
          'they are in the capital but they are not drawing anything.'
        : 'Rates are at full production; the capacity factor is applied on top.'),
      el('b', { 'data-util-total': r.tag, title: moneyExact(total) },
        moneyFull(total) + '/yr')));
    const spoken = r.utilities.filter(u => u.rate).map(u =>
      `${sentenceLabel(u.name || 'unnamed')} ` +
      naturalRate((u.per_unit === false ? 1 : running) * (Number(u.rate) || 0),
                  utilUnit(u), u.basis, u.name));
    if (spoken.length) {
      box.appendChild(el('div', { class: 'eq-block-foot' },
        el('span', {}, 'As drawn: ' + spoken.join(' · '))));
    }
  }
  return box;
}

/* ---------------------------------------------------------------------
   The parameter panel for one item.
   --------------------------------------------------------------------- */
function eqDetail(r, idx) {
  const d = eqDefaults(r);
  const m = r.mode === 'catalogue' ? catRec(r.kind) : null;
  const box = el('div', { class: 'eq-detail' });

  /* --- what this correlation is, and how far it can be trusted --- */
  if (m) {
    const grid = el('dl', { class: 'kv' },
      el('dt', {}, 'scaled parameter'), el('dd', {}, m.unit),
      el('dt', {}, 'fitted range'),
      el('dd', {}, `${fmt(m.valid_min)} – ${fmt(m.valid_max)} ${m.unit}`),
      el('dt', {}, 'fit quality'),
      el('dd', {}, m.r_squared != null
        ? `R² ${m.r_squared.toFixed(3)}` +
          (m.rel_rmse != null ? `, rel. RMSE ${(m.rel_rmse * 100).toFixed(1)}%` : '') +
          (m.n_points ? `, ${m.n_points} points` : '')
        : '—'),
      el('dt', {}, 'cost basis'),
      el('dd', {}, `${state.meta.basis_year} Q${state.meta.basis_quarter || 1}, ` +
                   `${state.meta.basis_location || 'US Gulf Coast'}, ` +
                   `${state.meta.basis_material || 'carbon steel'}`));
    box.appendChild(el('div', { class: 'eq-about' },
      el('div', { class: 'eq-about-h' }, m.description),
      grid,
      el('div', { class: 'msg note' },
        el('b', {}, 'source: '), state.meta.source || 'DOE/NETL-2002/1169')));

    const outOfRange = r.size > 0 && (r.size < m.valid_min || r.size > m.valid_max);
    if (!m.reliable) {
      box.appendChild(el('div', { class: 'msg warn' },
        el('b', {}, 'weak fit — '), m.caution ||
        'this correlation is flagged unreliable; use the tabulated points instead.'));
    }
    if (outOfRange) {
      box.appendChild(el('div', { class: 'msg warn' },
        el('b', {}, 'outside the fitted range — '),
        r.size > m.valid_max
          ? `above ${fmt(m.valid_max)} ${m.unit} teakit splits the duty into ` +
            'parallel trains at roughly constant unit cost, rather than ' +
            'extrapolating the power law.'
          : `below ${fmt(m.valid_min)} ${m.unit} this is an extrapolation, and ` +
            'is refused unless you allow extrapolation above.'));
    }
  }

  /* --- the parameters --- */
  const params = el('div', { class: 'par-grid' });

  /* Which correlation prices this item. It used to be a column in the table,
     repeating one stock description down every row that shared a correlation;
     it is a parameter of the item, so it lives with the parameters. */
  if (r.mode === 'catalogue') {
    const sel = el('select', {
      class: 'txt', title: (catRec(r.kind) || {}).description || '',
      onchange: e => {
        r.kind = e.target.value;
        // A different correlation has a different scaled parameter, so any
        // override of the old one is meaningless against the new one.
        ['base_cost', 'base_size', 'exponent'].forEach(k => { r[k] = null; });
        r.size_unit = catUnit(r.kind) || '';
        touch(); paintEquipment();
      } },
      ...(state.meta.equipment || []).map(m =>
        el('option', { value: m.key, title: `${m.key} — ${m.description}`,
                       selected: m.key === r.kind || null },
           `${sentenceLabel(m.description)}  ·  ${m.key}`)));
    params.appendChild(el('div', { class: 'par wide' },
      el('label', {}, 'correlation'), sel,
      el('div', { class: 'par-foot' },
        el('span', { class: 'par-def' }, eqHelp('kind')))));
  }

  params.appendChild(paramField(r, 'name', {
    label: 'name', type: 'text', help: eqHelp('name'),
    placeholder: r.mode === 'catalogue'
      ? (catRec(r.kind) || {}).description || 'what this item is'
      : 'what this item is'
  }));

  params.appendChild(paramField(r, 'size', {
    label: 'size', unit: r.mode === 'direct' ? '' : (m ? m.unit : r.size_unit || ''),
    help: eqHelp('size'), step: 'any', dp: 4
  }));

  if (r.mode === 'direct') {
    params.appendChild(paramField(r, 'direct_cost', {
      label: 'quoted price', unit: 'USD', help: eqHelp('direct_cost'),
      step: 1000, required: true
    }));
    /* The quote's own year. `override: false` because it always holds a
       value and the sensible one is the project's dollar year: setting it to
       the year it already is has changed nothing, and used to be reported as
       an edit against a "default 2,025". */
    params.appendChild(paramField(r, 'base_year', {
      label: 'price basis year', help: eqHelp('base_year'), step: 1,
      def: state.project.dollar_year, override: false, fmtDef: fmtYear
    }));
    params.appendChild(paramField(r, 'size_unit', {
      label: 'size unit', type: 'text', help: eqHelp('size_unit'),
      placeholder: 'e.g. kW, m3, tonne/h'
    }));
  } else {
    params.appendChild(paramField(r, 'base_cost', {
      label: 'base cost', unit: 'USD', help: eqHelp('base_cost'),
      step: 1000, def: d && d.base_cost, required: !d,
      fmtDef: v => '$' + fmt(v)
    }));
    params.appendChild(paramField(r, 'base_size', {
      label: 'base size', unit: m ? m.unit : (r.size_unit || ''),
      help: eqHelp('base_size'), step: 'any', def: d && d.base_size,
      required: !d, dp: 4
    }));
    /* With no catalogue entry behind it the exponent used to be a bare
       required field, so a user correlation started at whatever the Add
       button happened to seed. It now defaults to the item's equipment type
       — fitted from the catalogue regressions where there are any, the
       literature value where there are not, and 0.6 only as a last resort —
       and the evidence for it is printed underneath. `override: false`
       because it always holds a value: mode='custom' cannot run without one,
       so reset restores the default rather than clearing the field. */
    const te = typeExponent(eqCategoryOf(r));
    params.appendChild(paramField(r, 'exponent', {
      label: 'exponent n', help: eqHelp('exponent'), step: 0.01,
      def: d ? d.exponent : te.exponent, required: false, dp: 4,
      override: !!d,
      foot: d ? null : `${te.basis} — ${exponentEvidence(eqCategoryOf(r))}`,
      footTitle: te.source
    }));
    params.appendChild(paramField(r, 'base_year', {
      label: 'cost basis year', help: eqHelp('base_year'), step: 1,
      def: d ? d.base_year : undefined, required: !d, fmtDef: fmtYear
    }));
    if (!m) {
      params.appendChild(paramField(r, 'size_unit', {
        label: 'size unit', type: 'text', help: eqHelp('size_unit'),
        placeholder: 'e.g. kW, m3, tonne/h'
      }));
    }
  }

  params.appendChild(paramField(r, 'quantity', {
    label: 'quantity', help: eqHelp('quantity'), step: 1, min: '1', def: 1,
    dp: 0, override: false
  }));
  params.appendChild(paramField(r, 'spare', {
    label: 'installed spares', help: eqHelp('spare'), step: 1, min: '0', def: 0,
    dp: 0, override: false
  }));
  params.appendChild(paramField(r, 'section', {
    label: 'plant section', type: 'text', help: eqHelp('section'),
    placeholder: 'Process'
  }));
  /* Equipment type: a list you can pick from, and a field you can write in.
     Choosing a type moves the exponent default and the installation factor
     with it, so it is worth setting on anything that is not a catalogue
     item. Blank means "take the catalogue family". */
  const typeWrap = el('div', { class: 'par' });
  const typeFoot = el('div', { class: 'par-foot' });
  const typeLabel = el('label', { title: eqHelp('category') }, 'equipment type');
  const paintTypeFoot = () => {
    const t = eqCategoryOf(r);
    const te = typeExponent(t);
    typeFoot.innerHTML = '';
    typeFoot.appendChild(el('span', { class: 'par-def', title: te.source },
      `n ${te.exponent.toFixed(3)} · ${te.basis}`));
    if (r.category) {
      typeFoot.appendChild(el('button', {
        class: 'btn xs', type: 'button',
        title: 'Clear the type and take the catalogue family again',
        onclick: () => { r.category = ''; touch(); paintEquipment(); }
      }, 'reset'));
    }
  };
  typeWrap.appendChild(typeLabel);
  typeWrap.appendChild(eqTypeControl(r, (before, after) => {
    /* Move the exponent with the type — but only when it was still sitting on
       the old type's default. A number the user typed is theirs, and is left
       alone with the "edited" badge to show it now differs. */
    if (r.mode === 'custom' && !d) {
      /* Compare against the type as it was, not against eqCategoryOf(r) —
         `oninput` has already written the new type, so falling back to the
         item would ask "what is it now" and never see a match. An empty type
         is an unknown one, which is 0.6, which is what a new user
         correlation is seeded at. */
      const was = typeExponent(before).exponent;
      const now = typeExponent(after).exponent;
      const held = Number(r.exponent);
      if (!(held > 0) || Math.abs(held - was) < 1e-9) r.exponent = now;
    }
    touch(); paintEquipment();
  }));
  typeWrap.appendChild(typeFoot);
  paintTypeFoot();
  params.appendChild(typeWrap);
  params.appendChild(paramField(r, 'note', {
    label: r.mode === 'catalogue' ? 'note' : 'description', type: 'text',
    help: eqHelp('note'), placeholder: r.mode === 'direct' ? 'vendor and quote date' : ''
  }));

  /* One machine's own installation factor, when it is genuinely unlike the
     rest of its type. Only shown for the per-item method, because the three
     plant-wide methods apply one factor to the whole list by construction and
     a field that silently does nothing is worse than no field. An item
     entered at an installed price never meets a factor at all. */
  if (state.project.capital.installation_method === 'type' && !r.cost_is_installed) {
    const tf = typeInstallation(eqCategoryOf(r));
    params.appendChild(paramField(r, 'installation_factor', {
      label: 'installation factor', unit: '× purchased',
      help: eqHelp('installation_factor'), step: 0.05, min: '1', dp: 3,
      def: tf.factor,
      foot: `from ${eqCategoryOf(r)}`,
      footTitle: optHelp('installation_by_type', 'factor')
    }));
  }
  box.appendChild(params);

  /* --- the installed-cost flag, which deserves its own line ---
     One row: the box, then the sentence across the rest of the width. The
     full explanation is a tooltip and a line in the parameter guide, not a
     paragraph wrapped into a column three words wide. */
  box.appendChild(el('label', { class: 'eq-flag', title: eqHelp('cost_is_installed') },
    el('input', {
      type: 'checkbox', class: 'eq-flag-box',
      checked: r.cost_is_installed || null,
      onchange: e => { r.cost_is_installed = e.target.checked; touch(); paintEquipment(); }
    }),
    el('span', { class: 'eq-flag-text' },
      el('b', {}, 'This price already includes installation'),
      el('span', { class: 'eq-flag-sub' },
        'Such items skip the installation factors and enter the capital ' +
        'cascade at BEC. Leaving it unticked on an installed price is the ' +
        'classic and expensive error.'))));

  /* --- what else is known about it, and what it consumes --- */
  box.appendChild(eqParameterBlock(r));
  box.appendChild(eqUtilityBlock(r));
  box.appendChild(eqConsumableBlock(r));

  /* --- how the number is actually reached, for this item --- */
  const c = (state.result?.equipment_rows || []).find(x => x.tag === r.tag);
  if (c) {
    box.appendChild(el('div', { class: 'eq-calc' },
      el('div', { class: 'eq-calc-h' }, 'how this cost was reached'),
      el('code', {}, r.mode === 'direct'
        ? `${moneyFull(c.base_cost)} quoted → escalated to ${state.project.dollar_year} ` +
          `→ ${moneyFull(c.unit_cost)} each × ${c.quantity} = ${moneyFull(c.cost)}`
        : `${moneyFull(c.base_cost)} × (${fmt(c.size, 4)} / ${fmt(c.base_size, 4)})` +
          `^${(c.exponent ?? 0).toFixed(4)} → escalated, material and location ` +
          `→ ${moneyFull(c.unit_cost)} each × ${c.quantity} = ${moneyFull(c.cost)}`),
      (c.notes || []).length
        ? el('div', { class: 'par-help' }, (c.notes || []).join(' · '))
        : null));
  }

  /* --- row actions --- */
  const acts = el('div', { class: 'eq-acts' });
  acts.appendChild(el('button', {
    class: 'btn sm ghost', type: 'button',
    title: 'What every one of these parameters means',
    onclick: () => openParamGuide()
  }, 'Parameter guide'));
  if (d) {
    const over = eqEdited(r);
    acts.appendChild(el('button', {
      class: 'btn sm eq-reset-all', disabled: over.length ? null : true,
      title: over.length
        ? `Put ${paramNames(over)} back to the catalogue values`
        : 'Nothing on this item differs from the catalogue',
      onclick: () => {
        eqResetAll(r);
        touch(); paintEquipment();
        toast(`${r.tag} reset to the catalogue defaults`);
      }
    }, 'Reset all parameters to default'));
  }
  acts.appendChild(el('button', {
    class: 'btn sm', title: 'Add a copy of this item to the list',
    onclick: () => {
      const copy = Object.assign({}, r, { tag: nextTag(r.tag.split('-')[0] || 'X') });
      state.project.equipment.splice(idx + 1, 0, copy);
      touch(); paintEquipment();
      toast(`Duplicated as ${copy.tag}`);
    }
  }, 'Duplicate'));
  acts.appendChild(el('span', { class: 'spacer' }));
  acts.appendChild(el('button', {
    class: 'btn sm danger', title: 'Remove this item from the estimate',
    onclick: () => {
      state.project.equipment.splice(idx, 1);
      eqOpen.delete(r.tag); touch(); paintEquipment();
    }
  }, 'Remove item'));
  box.appendChild(acts);
  return box;
}

/* ---------------------------------------------------------------------
   The parameter guide.

   Every explanation the equipment editor has, gathered in one dialog reachable
   from the toolbar and from inside any open row. teakit.methods owns the
   sentences, so the guide, the tooltips, the report and the workbook cannot
   drift apart.
   --------------------------------------------------------------------- */
const PARAM_GUIDE_ORDER = [
  'tag', 'kind', 'size', 'size_unit', 'base_cost', 'base_size', 'exponent',
  'base_year', 'direct_cost', 'quantity', 'spare', 'material', 'category',
  'section', 'installation_factor', 'cost_is_installed', 'note',
];

function openParamGuide(focus) {
  const dlg = $('#dlg-params');
  if (!dlg) return;
  const body = $('#params-body');
  const help = (state.meta && state.meta.option_help &&
                state.meta.option_help.equipment_param) || {};
  const modes = (state.meta && state.meta.option_help &&
                 state.meta.option_help.equipment_mode) || {};
  body.innerHTML = '';

  body.appendChild(el('p', { class: 'hint' },
    'What every field behind an equipment cost means. Each control in an open ' +
    'row carries the same sentence as its tooltip, so this page is the only ' +
    'place it has to be read in full.'));

  body.appendChild(el('div', { class: 'g-eq' },
    el('span', { class: 'g-eq-n' }, 'The correlation'),
    el('code', {}, 'cost = base cost × (size ÷ base size) ^ n, ' +
                   'then escalated by CEPCI and factored for material and location')));

  if (Object.keys(modes).length) {
    body.appendChild(el('h4', { class: 'guide-h' }, 'How an item can be priced'));
    const dl = el('dl', { class: 'guide-dl' });
    Object.entries(modes).forEach(([k, v]) => {
      dl.appendChild(el('dt', {}, MODE_LABEL[k] || optLabel(k)));
      dl.appendChild(el('dd', {}, sentenceLabel(v)));
    });
    body.appendChild(dl);
  }

  const utilHelpAll = (state.meta && state.meta.option_help &&
                       state.meta.option_help.equipment_utility) || {};

  body.appendChild(el('h4', { class: 'guide-h' }, 'The parameters'));
  const dl = el('dl', { class: 'guide-dl' });
  const keys = PARAM_GUIDE_ORDER.filter(k => help[k])
    .concat(Object.keys(help).filter(k => !PARAM_GUIDE_ORDER.includes(k)));
  keys.forEach(k => {
    const dt = el('dt', { 'data-param': k }, paramTitle(k));
    const dd = el('dd', {}, sentenceLabel(help[k]));
    if (k === focus) { dt.classList.add('hit'); dd.classList.add('hit'); }
    dl.appendChild(dt); dl.appendChild(dd);
  });
  body.appendChild(dl);

  if (Object.keys(utilHelpAll).length) {
    body.appendChild(el('h4', { class: 'guide-h' }, 'A utility line on an item'));
    body.appendChild(el('p', { class: 'hint' },
      'What an item draws when it runs. Each line is priced and rolled into ' +
      'the operating cost under this item\u2019s tag, so the utility bill can ' +
      'be traced back to the machines that cause it.'));
    const ul = el('dl', { class: 'guide-dl' });
    const order = ['name', 'rate', 'unit', 'price', 'basis', 'per_unit',
                   'scales_with_rate', 'category'];
    const utilTitle = {
      name: 'Utility', rate: 'Rate', unit: 'Unit', price: 'Price',
      basis: 'Rate basis', per_unit: 'Per unit',
      scales_with_rate: 'Follows CF', category: 'Category',
    };
    order.filter(k => utilHelpAll[k])
      .concat(Object.keys(utilHelpAll).filter(k => !order.includes(k)))
      .forEach(k => {
        ul.appendChild(el('dt', {}, utilTitle[k] || optLabel(k.replace(/_/g, ' '))));
        ul.appendChild(el('dd', {}, sentenceLabel(utilHelpAll[k])));
      });
    body.appendChild(ul);
  }

  body.appendChild(el('p', { class: 'hint' },
    `Catalogue correlations are on a ${state.meta.basis_year || 1998} ` +
    `${state.meta.basis_location || 'US Gulf Coast'}, ` +
    `${state.meta.basis_material || 'carbon steel'} basis. ` +
    `Source: ${state.meta.source || 'DOE/NETL-2002/1169'}.`));

  dlg.showModal();
  if (focus) {
    const hit = body.querySelector(`dt[data-param="${focus}"]`);
    if (hit) hit.scrollIntoView({ block: 'center' });
  }
}

/* ---------------------------------------------------------------------
   The list.
   --------------------------------------------------------------------- */
function paintEquipment() {
  const rows = state.project.equipment;
  const t = $('#eq-table');
  $('#eq-empty').style.display = rows.length ? 'none' : '';
  t.style.display = rows.length ? '' : 'none';
  t.innerHTML = '';
  const btn = $('#btn-eq-expand');
  if (btn) btn.textContent = eqOpen.size >= rows.length && rows.length
    ? 'Collapse all' : 'Expand all';
  if (!rows.length) { paintEqSummary(); return; }

  const costs = {};
  (state.result?.equipment_rows || []).forEach(r => { costs[r.tag] = r; });

  /* Two cost columns, not one. An item's purchased price and what it costs
     once it is in the ground are different numbers by a factor of two to
     four, and an equipment list that shows only the first invites the reader
     to add them up and call the total a plant. */
  const NUM_COLS = new Set(['Size', 'n', '+sp']);
  t.appendChild(el('thead', {}, el('tr', {},
    el('th', { class: 'exp' }, ''),
    ...[['Tag', ''],
        ['Basis', 'Where the number comes from: a catalogue correlation, your ' +
                  'own correlation, or a vendor price.'],
        ['Item', 'What this item is called. The tag identifies it; this is ' +
                 'what makes the schedule readable.'],
        ['Size', ''], ['Unit', ''], ['n', ''], ['+sp', ''], ['Material', ''],
        ['Section', ''],
        [`Purchased (${curCode()})`,
         'FOB purchased cost for every unit of this item. Blank when the ' +
         'price you entered already includes installation.'],
        [`Installed (${curCode()})`,
         'Purchased cost times the installation factor — this item’s ' +
         'share of the bare erected cost. An already-installed price is ' +
         'carried straight across.'],
        ['', '']].map(([h, tip]) =>
      el('th', { class: NUM_COLS.has(h) || /^(Purchased|Installed)/.test(h)
                          ? 'n' : '', title: tip || null }, h)))));

  const tb = el('tbody');
  rows.forEach((r, i) => {
    const c = costs[r.tag];
    const open = eqOpen.has(r.tag);
    const over = eqEdited(r);

    const toggle = el('button', {
      class: 'exp-btn' + (open ? ' on' : ''),
      title: open ? 'Close the parameters' : 'Open the parameters for this item',
      'aria-expanded': open ? 'true' : 'false',
      onclick: () => {
        if (open) eqOpen.delete(r.tag); else eqOpen.add(r.tag);
        paintEquipment();
      }
    }, '›');

    /* The Item column is this item's *name* — "Syngas compressor", not the
       correlation's stock description repeated down the page. The name is
       what tells two compressors apart; the description is the same sentence
       on every row that shares a correlation, and it is still one column to
       the right, on the control that chooses it, and in the open panel. */
    const nameCell = el('input', {
      class: 'txt', type: 'text', value: r.name || '',
      title: r.name || (catRec(r.kind) || {}).description || '',
      placeholder: r.note ||
        (r.mode === 'catalogue' ? (catRec(r.kind) || {}).description || 'what this item is'
                                : 'what this item is'),
      oninput: e => { r.name = e.target.value; e.target.title = e.target.value;
                      touch(); } });

    const sizeCell = r.mode === 'direct'
      ? el('input', { type: 'number', value: r.direct_cost ?? 0, step: '1000',
          title: eqHelp('direct_cost'),
          oninput: e => { r.direct_cost = parseFloat(e.target.value) || 0;
                          touch(); repaintEqRow(r); } })
      : el('input', { type: 'number', value: r.size, step: 'any',
          title: eqHelp('size'),
          oninput: e => { r.size = parseFloat(e.target.value) || 0;
                          touch(); repaintEqRow(r); } });

    const tr = el('tr', { 'data-tag': r.tag, class: open ? 'open' : '' },
      el('td', { class: 'exp' }, toggle),
      el('td', {}, el('input', { class: 'txt', type: 'text', value: r.tag,
        title: eqHelp('tag'),
        oninput: e => {
          if (eqOpen.delete(r.tag)) eqOpen.add(e.target.value);
          r.tag = e.target.value; touch(); paintEqSummary();
        } })),
      el('td', {}, el('span', { class: 'pill', title: optHelp('equipment_mode', r.mode) },
        MODE_LABEL[r.mode]),
        over.length ? el('span', { class: 'pill warn xs', title:
          `Changed from the catalogue: ${paramNames(over)}` }, 'edited') : null),
      el('td', {}, nameCell),
      el('td', { class: 'n' }, sizeCell),
      el('td', {}, r.mode === 'direct' ? el('span', { class: 'pill' }, '$')
        : el('span', { class: 'unit' },
             c?.size_unit || catUnit(r.kind) || r.size_unit || '')),
      el('td', { class: 'n' }, el('input', { type: 'number', value: r.quantity,
        min: '1', step: '1', title: eqHelp('quantity'),
        oninput: e => { r.quantity = parseInt(e.target.value, 10) || 1;
                        touch(); repaintEqRow(r); } })),
      el('td', { class: 'n' }, el('input', { type: 'number', value: r.spare,
        min: '0', step: '1', title: eqHelp('spare'),
        oninput: e => { r.spare = parseInt(e.target.value, 10) || 0;
                        touch(); repaintEqRow(r); } })),
      el('td', {}, el('select', { class: 'txt', title: eqHelp('material'),
          onchange: e => { r.material = e.target.value; touch(); repaintEqRow(r); } },
        ...(state.meta.materials || []).map(m =>
          el('option', { value: m, selected: m === r.material || null },
             materialLabel(m))))),
      el('td', {}, el('input', { class: 'txt', type: 'text', value: r.section,
        title: eqHelp('section'),
        oninput: e => { r.section = e.target.value; touch(); paintEqSummary(); } })),
      // An item entered at an installed price has no purchased cost to show —
      // that is the whole point of the flag — so the cell says so rather than
      // repeating the installed figure under a heading it does not belong to.
      el('td', { class: 'n cost',
                 title: c && !r.cost_is_installed ? moneyExact(c.cost)
                   : 'entered as an already-installed price' },
        c && !r.cost_is_installed ? moneyFull(c.cost) : '—'),
      el('td', { class: 'n cost',
                 title: c && c.installed_cost != null
                   ? `${moneyExact(c.installed_cost)}` +
                     (r.cost_is_installed ? ' (as entered)'
                       : ` — ×${(c.installation_factor || 1).toFixed(3)}` +
                         (state.project.capital.installation_method === 'type'
                           ? ` for ${eqCategoryOf(r)}` : ''))
                   : 'run the estimate' },
        c && c.installed_cost != null ? moneyFull(c.installed_cost) : '—'),
      el('td', { class: 'act' }, el('button', {
        class: 'x', title: 'Remove this item', onclick: () => {
          state.project.equipment.splice(i, 1);
          eqOpen.delete(r.tag); touch(); paintEquipment();
        } }, '×'))
    );
    tb.appendChild(tr);

    if (open) {
      tb.appendChild(el('tr', { class: 'eq-detail-row' },
        el('td', { colspan: '13' }, eqDetail(r, i))));
    }
  });
  t.appendChild(tb);

  if (state.result) {
    const res = state.result;
    t.appendChild(el('tfoot', {}, el('tr', { class: 'sum' },
      el('td', { colspan: '10' },
        'Purchased equipment cost, and bare erected cost' +
        (state.project.capital.installation_method === 'type'
          ? ` — installed item by item, ×${(res.installation_factor || 1).toFixed(3)} overall`
          : ` at ×${(res.installation_factor || 1).toFixed(3)}`)),
      el('td', { class: 'n', title: moneyExact(res.purchased_equipment_cost) },
        moneyFull(res.purchased_equipment_cost)),
      el('td', { class: 'n', title: moneyExact(res.bec) }, moneyFull(res.bec)),
      el('td', {}))));
    const notes = (state.result.equipment_rows || [])
      .flatMap(r => (r.notes || []).map(n => [r.tag, n]));
    $('#eq-notes-card').style.display = notes.length ? '' : 'none';
    $('#eq-notes').innerHTML = notes.map(([tag, n]) =>
      `<div class="msg ${/EXTRAPOL|UNRELIABLE/.test(n) ? 'warn' : 'note'}">
        <b>${esc(tag)}</b> — ${esc(n)}</div>`).join('');
  }
  paintEqSummary();
  // The Operating cost roll-up is a view of this list, and a utility is edited
  // through paintEquipment() rather than paintStreams(). Repaint it here or it
  // keeps showing whatever the project held when it loaded.
  paintEquipmentUtilities();
  // Two other panels are views of this list as well: which cost-index years
  // the study depends on, and which equipment types need an installation
  // factor. Both go stale the moment an item is added or retyped.
  paintCepci();
  paintInstallTypes();
}

/* ---------------------------------------------------------------------
   The summary under the list. Purchased and already-installed costs are
   kept apart: they enter the capital cascade at different rungs, and
   adding them together is the error the application exists to prevent.
   --------------------------------------------------------------------- */
function paintEqSummary() {
  const card = $('#eq-summary-card');
  const box = $('#eq-summary');
  if (!card || !box) return;
  const rows = state.project.equipment;
  if (!rows.length) { card.style.display = 'none'; return; }
  card.style.display = '';

  const costs = {};
  (state.result?.equipment_rows || []).forEach(r => { costs[r.tag] = r; });
  const cost = r => (costs[r.tag]?.cost ?? null);
  const priced = state.result && rows.some(r => cost(r) !== null);

  const agg = (keyFn) => {
    const out = new Map();
    rows.forEach(r => {
      const k = keyFn(r) || '—';
      const e = out.get(k) || { n: 0, units: 0, purchased: 0, installed: 0 };
      e.n += 1;
      e.units += (r.quantity || 1) + (r.spare || 0);
      const v = cost(r) || 0;
      if (r.cost_is_installed) e.installed += v; else e.purchased += v;
      out.set(k, e);
    });
    return out;
  };

  const grand = { n: rows.length, units: 0, purchased: 0, installed: 0 };
  rows.forEach(r => {
    grand.units += (r.quantity || 1) + (r.spare || 0);
    const v = cost(r) || 0;
    if (r.cost_is_installed) grand.installed += v; else grand.purchased += v;
  });
  const grandTotal = grand.purchased + grand.installed;

  /* "Installed" has to mean one thing on this page. In the list above it is
     what an item costs once it is in the ground; here it used to head the
     column of prices that were *entered* as installed, which is a different
     quantity entirely. That column is now named for what it is, and the
     installed cost — the rollup someone actually wants per section — is its
     own column, on the same factor the list uses. */
  const factor = state.result?.installation_factor || 1;
  const erected = e => e.purchased * factor + e.installed;

  const table = (title, map) => {
    const t = el('table', { class: 't' });
    t.appendChild(el('thead', {}, el('tr', {},
      el('th', {}, title),
      el('th', { class: 'n' }, 'Items'),
      el('th', { class: 'n' }, 'Units'),
      el('th', { class: 'n', title: 'FOB purchased cost of the items that go ' +
                 'through the installation factors.' },
         `Purchased (${curCode()})`),
      el('th', { class: 'n', title: 'Items whose price was entered as already ' +
                 'including installation. They bypass the factors and enter ' +
                 'the capital cascade at BEC.' },
         `Entered installed (${curCode()})`),
      el('th', { class: 'n' }, `Equipment total (${curCode()})`),
      el('th', { class: 'n', title: `Purchased × ${factor.toFixed(3)}, plus ` +
                 'anything already installed — this group\u2019s share of BEC.' },
         `Installed cost (${curCode()})`),
      el('th', { class: 'n' }, '% of total'))));
    const tb = el('tbody');
    [...map.entries()]
      .sort((a, b) => (b[1].purchased + b[1].installed) - (a[1].purchased + a[1].installed))
      .forEach(([k, e]) => {
        const tot = e.purchased + e.installed;
        tb.appendChild(el('tr', {},
          el('td', {}, k),
          el('td', { class: 'n' }, String(e.n)),
          el('td', { class: 'n' }, String(e.units)),
          el('td', { class: 'n' }, priced ? moneyFull(e.purchased) : '—'),
          el('td', { class: 'n' }, priced ? moneyFull(e.installed) : '—'),
          el('td', { class: 'n' }, priced ? moneyFull(tot) : '—'),
          el('td', { class: 'n' }, priced ? moneyFull(erected(e)) : '—'),
          el('td', { class: 'n' }, priced && grandTotal
            ? (tot / grandTotal * 100).toFixed(1) + '%' : '—')));
      });
    t.appendChild(tb);
    t.appendChild(el('tfoot', {}, el('tr', { class: 'sum' },
      el('td', {}, 'Total'),
      el('td', { class: 'n' }, String(grand.n)),
      el('td', { class: 'n' }, String(grand.units)),
      el('td', { class: 'n' }, priced ? moneyFull(grand.purchased) : '—'),
      el('td', { class: 'n' }, priced ? moneyFull(grand.installed) : '—'),
      el('td', { class: 'n' }, priced ? moneyFull(grandTotal) : '—'),
      el('td', { class: 'n' }, priced ? moneyFull(erected(grand)) : '—'),
      el('td', { class: 'n' }, priced ? '100.0%' : '—'))));
    return el('div', { class: 'tbl-wrap' }, t);
  };

  box.innerHTML = '';
  box.appendChild(table('Plant section', agg(r => r.section)));
  box.appendChild(el('div', { style: 'height:16px' }));
  box.appendChild(table('Cost basis', agg(r => MODE_LABEL[r.mode])));

  if (!priced) {
    box.appendChild(el('div', { class: 'msg note' },
      'Run the estimate to price these items. Counts and units are live.'));
  } else if (grand.installed > 0) {
    box.appendChild(el('div', { class: 'msg note' },
      el('b', {}, `${moneyFull(grand.installed)} `),
      'was entered as an already-installed price. It bypasses the installation ' +
      'factors and enters the capital cascade at BEC, which is why it is shown ' +
      'in its own column rather than added to purchased cost.'));
  }
  if (priced && state.result) {
    box.appendChild(el('div', { class: 'msg note' },
      'Installed cost is purchased cost × the installation factor of ',
      el('b', {}, `${factor.toFixed(3)}`),
      ', plus anything entered at an installed price. The column therefore ' +
      'adds up to the bare erected cost, ',
      el('b', {}, moneyFull(state.result.bec)), '.'));
  }
}

function nextTag(prefix) {
  const used = new Set(state.project.equipment.map(e => e.tag));
  for (let i = 101; i < 999; i++) { const t = `${prefix}-${i}`; if (!used.has(t)) return t; }
  return prefix + '-X';
}

/* ---------------------------- stream tables ---------------------------- */
const STREAM_TABLES = {
  raw_materials: '#rm-table', utilities: '#ut-table', waste: '#ws-table'
};

/* ---------------------------------------------------------------------
   What the equipment list consumes, on the Operating cost panel.

   Editable, and the same objects the Equipment panel edits — not a copy of
   them. A rate changed here is the rate changed there, because both views
   hold references into `state.project.equipment[i].utilities[j]`. The cost
   cells carry a key so an edit in either place updates the other without
   rebuilding a table someone is typing into.
   --------------------------------------------------------------------- */
function paintEquipmentUtilities() {
  const box = $('#eq-util-rollup');
  if (!box) return;
  box.innerHTML = '';

  const items = state.project.equipment || [];
  // Every line with a name or a rate — an empty row someone has just added is
  // shown too, so it can be filled in from this panel.
  const lines = items.flatMap(item => (item.utilities || []).map(
    (u, i) => ({ item, u, i })));
  if (!lines.length) {
    box.appendChild(el('div', { class: 'msg note' },
      el('b', {}, 'Nothing from the equipment yet — '),
      'open any item on the Equipment panel and give it a utility. Its ' +
      'consumption is priced and listed here against its tag, and can be ' +
      'edited from either place.'));
    return;
  }

  // Grouped by utility — that is the number a reader wants first — then by
  // the item that draws it.
  const groups = {};
  lines.forEach(l => {
    const k = l.u.name || '(unnamed)';
    (groups[k] = groups[k] || []).push(l);
  });
  const groupTotal = k => groups[k].reduce(
    (a, l) => a + (utilAnnual(l.item, l.u) || 0), 0);
  const grand = Object.keys(groups).reduce((a, k) => a + groupTotal(k), 0);

  const t = el('table', { class: 't rollup', id: 'eq-util-table' });
  t.appendChild(el('thead', {}, el('tr', {},
    el('th', {}, 'From the equipment list'),
    el('th', { class: 'n', title: utilHelp('rate') }, 'Rate'),
    el('th', { title: optHelp('stream_basis', 'hour') + '\n\n' +
                      optHelp('stream_basis', 'year') }, 'Rate basis'),
    el('th', { title: utilHelp('unit') }, 'Unit'),
    el('th', { class: 'n', title: utilHelp('price') }, 'Price USD/unit'),
    el('th', { class: 'c', title: utilHelp('per_unit') }, 'Per unit'),
    el('th', { class: 'c', title: utilHelp('scales_with_rate') }, 'Follows CF'),
    el('th', { class: 'n' }, `Annual cost (${curCode()})`),
    el('th', {}, ''))));
  const tb = el('tbody');

  Object.keys(groups)
    .sort((a, b) => Math.abs(groupTotal(b)) - Math.abs(groupTotal(a)))
    .forEach(name => {
      const list = groups[name];
      const rate = list.reduce((a, l) => a + (l.u.per_unit === false
        ? (Number(l.u.rate) || 0)
        : (Number(l.u.rate) || 0) * runningUnits(l.item)), 0);
      tb.appendChild(el('tr', { class: 'sub' },
        el('td', {}, sentenceLabel(name)),
        el('td', { class: 'n', title: naturalRate(rate, utilUnit(list[0].u),
                                                  list[0].u.basis, name) },
          fmtRate(rate)),
        el('td', {}, ''),
        el('td', { title: rateUnitNote(utilUnit(list[0].u), list[0].u.basis, name) },
          rateUnit(utilUnit(list[0].u), list[0].u.basis, name)),
        el('td', {}, ''), el('td', {}, ''), el('td', {}, ''),
        el('td', { class: 'n', 'data-util-group': name,
                   title: moneyExact(groupTotal(name)) },
          moneyFull(groupTotal(name))),
        el('td', {})));

      list.forEach(({ item, u, i }) => {
        const rec = utilRec(u.name);
        const annual = utilAnnual(item, u);
        tb.appendChild(el('tr', { class: 'rollup-item' },
          el('td', {},
            el('button', {
              class: 'linkish', type: 'button',
              title: 'Open this item on the Equipment panel',
              onclick: () => {
                eqOpen.add(item.tag);
                paintEquipment();
                showPanel('equipment');
                const tr = $(`#eq-table tr[data-tag="${CSS.escape(item.tag)}"]`);
                if (tr) tr.scrollIntoView({ block: 'center' });
              }
            }, item.tag),
            el('span', { class: 'rollup-name' },
               item.name || item.note || ''),
            (Number(u.rate) || 0) < 0
              ? el('span', { class: 'pill gen xs',
                  title: 'A negative rate: this item generates rather than ' +
                         'draws, and nets against everything else on this ' +
                         'utility.' }, 'generates')
              : null),
          el('td', { class: 'n' }, el('input', {
            type: 'number', step: 'any', value: u.rate ?? 0,
            title: utilHelp('rate'),
            oninput: e => { u.rate = parseFloat(e.target.value) || 0;
                            touch(); syncUtilLine(item, i); } })),
          el('td', {}, utilBasisControl(u, () => paintAllUtilityViews())),
          el('td', {}, unitControl(u, full => full
            ? paintAllUtilityViews() : syncUtilLine(item, i))),
          el('td', { class: 'n' }, el('input', {
            type: 'number', step: 'any', 'data-price': u.name || '',
            value: utilPrice(u) === null ? '' : utilPrice(u),
            placeholder: 'no price',
            title: priceTitle(u) + '\n\n' + projectPriceSource(u.name) +
                   '\n\nOne price per utility for the whole study — editing ' +
                   'it here moves every item drawing on it.',
            oninput: e => {
              const v = e.target.value === '' ? null
                : (parseFloat(e.target.value) || 0);
              u.price = null;
              if (v !== null) setProjectPrice(u.name, v);
              touch(); syncAllCostCells();
            } })),
          el('td', { class: 'c' }, el('input', {
            type: 'checkbox', style: 'width:auto',
            checked: u.per_unit !== false || null,
            title: utilHelp('per_unit') +
              `\nThis item has ${runningUnits(item)} running unit` +
              `${runningUnits(item) === 1 ? '' : 's'}.`,
            onchange: e => { u.per_unit = e.target.checked;
                             touch(); syncUtilLine(item, i); } })),
          el('td', { class: 'c' }, el('input', {
            type: 'checkbox', style: 'width:auto',
            checked: u.scales_with_rate !== false || null,
            title: utilHelp('scales_with_rate'),
            onchange: e => { u.scales_with_rate = e.target.checked;
                             touch(); syncUtilLine(item, i); } })),
          el('td', { class: 'n cost' + (annual === null ? ' unpriced'
                                         : (annual < 0 ? ' credit' : '')),
                     'data-util': utilKey(item, i),
                     title: annual === null
                       ? 'No price for this utility — give it one here'
                       : moneyExact(annual) },
            annual === null ? 'no price' : moneyFull(annual)),
          el('td', { class: 'act' }, el('button', {
            class: 'x', type: 'button',
            title: `Remove this line from ${item.tag}`,
            onclick: () => { item.utilities.splice(i, 1); touch();
                             paintAllUtilityViews(); }
          }, '×'))));
        // The utility's *name* is deliberately not editable inline here: it
        // decides the unit, the price and the category together, so it is
        // changed on the item, where those three sit side by side. The tag
        // link on the left is the way there.
      });
    });

  tb.appendChild(el('tr', { class: 'sum' },
    el('td', { colspan: '7' }, 'From equipment, total'),
    el('td', { class: 'n', 'data-util-grand': '1', title: moneyExact(grand) },
      moneyFull(grand)),
    el('td', {})));
  t.appendChild(tb);
  box.appendChild(el('div', { class: 'tbl-wrap' }, t));

  const unpriced = lines.filter(l => l.u.rate && utilAnnual(l.item, l.u) === null);
  if (unpriced.length) {
    box.appendChild(el('div', { class: 'msg warn' },
      el('b', {}, 'No price — '),
      `${unpriced.map(l => `${l.item.tag} ${l.u.name || '(unnamed)'}`).join(', ')}. ` +
      'These have a consumption but nothing to price it at, so they cost ' +
      'nothing in the estimate. Give the line a price here, or pick a ' +
      'catalogued utility on the item.'));
  }
}

/* A structural change — a line added, removed or renamed — repaints both
   views. A keystroke never does; syncUtilLine handles that. */
function paintAllUtilityViews() {
  paintEquipment();                    // which repaints the roll-up in turn
}

function paintStreams() {
  for (const [key, sel] of Object.entries(STREAM_TABLES)) {
    const list = state.project.opex[key] || (state.project.opex[key] = []);
    const t = $(sel);
    t.innerHTML = '';
    t.appendChild(el('thead', {}, el('tr', {},
      ...[['Line', ''],
          ['Rate', 'At full production. The capacity factor is applied on top.'],
          ['Rate basis', 'Whether the rate is per operating hour or per year.'],
          ['Unit', 'The physical unit the rate and the price share.'],
          ['Price USD/unit', 'Cost per unit, in project dollars.'],
          ['Follows CF', 'On, consumption follows the capacity factor. Off ' +
                         'pins it to a fixed annual amount — a take-or-pay ' +
                         'contract, or a charge on a calendar schedule.'],
          [`Annual cost (${curCode()})`, ''], ['', '']]
        .map(([h, tip], i) => el('th',
          { class: [1, 4, 6].includes(i) ? 'n' : '', title: tip }, h)))));
    const tb = el('tbody');
    if (!list.length) {
      tb.appendChild(el('tr', {}, el('td', { colspan: '8',
        style: 'color:var(--muted);padding:10px 8px' }, 'No lines yet.')));
    }
    list.forEach((s, i) => {
      tb.appendChild(el('tr', {},
        el('td', {}, el('input', { class: 'txt', type: 'text', value: s.name,
          oninput: e => { s.name = e.target.value; touch(); syncAllCostCells(); } })),
        el('td', { class: 'n' }, el('input', { type: 'number', value: s.rate, step: 'any',
          oninput: e => { s.rate = parseFloat(e.target.value) || 0;
                          touch(); syncStreamRow(key, i); } })),
        el('td', {}, el('select', { class: 'txt',
            title: optHelp('stream_basis', 'hour') + '\n\n' +
                   optHelp('stream_basis', 'year'),
            // A repaint, because the unit column is labelled from the basis.
            onchange: e => { s.basis = e.target.value; touch(); paintStreams(); } },
          el('option', { value: 'hour', selected: s.basis === 'hour' || null,
                         title: optHelp('stream_basis', 'hour') },
             STREAM_BASIS_LABEL.hour),
          el('option', { value: 'year', selected: s.basis === 'year' || null,
                         title: optHelp('stream_basis', 'year') },
             STREAM_BASIS_LABEL.year))),
        el('td', {}, unitControl(s, () => syncStreamRow(key, i))),
        el('td', { class: 'n' }, el('input', { type: 'number', value: s.price,
          step: 'any', 'data-price': s.name || '',
          title: priceTitle(s) + '\n\nThe price for this line across the ' +
                 'whole study — every equipment item drawing on it is ' +
                 'charged here.',
          oninput: e => { s.price = parseFloat(e.target.value) || 0;
                          // One utility, one price: an equipment line reads
                          // this, so the whole panel moves with it.
                          touch(); syncAllCostCells(); } })),
        el('td', {}, el('input', { type: 'checkbox', checked: s.scales_with_rate !== false || null,
          style: 'width:auto', title: optHelp('equipment_utility', 'scales_with_rate'),
          onchange: e => { s.scales_with_rate = e.target.checked;
                           touch(); syncStreamRow(key, i); } })),
        el('td', { class: 'n', 'data-stream': `${key}|${i}`,
                   title: moneyExact(streamAnnual(s) || 0) },
          streamAnnual(s) === null ? '—' : moneyFull(streamAnnual(s))),
        el('td', { class: 'act' }, el('button', { class: 'x', title: 'Remove',
          onclick: () => { list.splice(i, 1); touch(); paintStreams(); } }, '×'))
      ));
      if (s.source) tb.appendChild(el('tr', {}, el('td', { colspan: '8',
        style: 'padding:0 8px 6px;font-size:11px;color:var(--muted);border:0' },
        s.source)));
    });
    t.appendChild(tb);
  }
}

function paintStaff() {
  const lb = state.project.opex.labor || (state.project.opex.labor = {});
  const list = lb.staff || (lb.staff = []);
  const t = $('#staff-table');
  t.innerHTML = '';
  t.appendChild(el('thead', {}, el('tr', {},
    ...['Role', 'Count', 'Salary USD/yr', 'Shift position', ''].map((h, i) =>
      el('th', { class: [1, 2].includes(i) ? 'n' : '' }, h)))));
  const tb = el('tbody');
  if (!list.length) tb.appendChild(el('tr', {}, el('td', { colspan: '5',
    style: 'color:var(--muted);padding:10px 8px' },
    'No roles yet. Shift positions are multiplied by the coverage factor.')));
  list.forEach((s, i) => {
    tb.appendChild(el('tr', {},
      el('td', {}, el('input', { class: 'txt', type: 'text', value: s.role,
        oninput: e => { s.role = e.target.value; touch(); } })),
      el('td', { class: 'n' }, el('input', { type: 'number', value: s.count, step: '1',
        oninput: e => { s.count = parseFloat(e.target.value) || 0; touch(); } })),
      el('td', { class: 'n' }, el('input', { type: 'number', value: s.annual_salary, step: '1000',
        oninput: e => { s.annual_salary = parseFloat(e.target.value) || 0; touch(); } })),
      el('td', {}, el('input', { type: 'checkbox', checked: s.shift_position || null,
        style: 'width:auto',
        onchange: e => { s.shift_position = e.target.checked; touch(); } })),
      el('td', { class: 'act' }, el('button', { class: 'x',
        onclick: () => { list.splice(i, 1); touch(); paintStaff(); } }, '×'))));
  });
  t.appendChild(tb);
}

/* A product's output for the year, on whichever basis it was entered and with
   the capacity factor applied — the same arithmetic teakit.products does, so
   the cell and the estimate cannot disagree. */
function productAnnual(p) {
  const opx = state.project.opex || {};
  const hours = Number(opx.operating_hours) || 0;
  const cf = opx.capacity_factor === null || opx.capacity_factor === undefined
    ? 1 : Number(opx.capacity_factor);
  const base = (Number(p.annual_production) || 0) *
    (p.basis === 'hour' ? hours : 1);
  return base * (p.scales_with_rate === false ? 1 : cf);
}

/* Redraw one product's derived cell without rebuilding the table under the
   caret of whoever is typing into it. */
function syncProductRow(i) {
  const cell = $(`#pr-table td[data-product="${i}"]`);
  const p = state.project.products.products[i];
  if (!cell || !p) return;
  cell.textContent = fmt(productAnnual(p), 0);
  cell.title = `${fmt(productAnnual(p), 4)} ${p.unit || ''}/yr`;
}

function paintProducts() {
  const list = state.project.products.products;
  const t = $('#pr-table');
  t.innerHTML = '';
  /* Output is entered the way a feed is: a rate and a basis, not an annual
     lump that has to be worked out by hand every time the operating hours
     change. The derived column is what the estimate will actually use. */
  t.appendChild(el('thead', {}, el('tr', {},
    ...[['Product', ''], ['Role', ''],
        ['Output', 'At full production. The capacity factor is applied on top.'],
        ['Rate basis', optHelp('product_basis', 'hour') + '\n\n' +
                       optHelp('product_basis', 'year')],
        ['Unit', ''], ['Price USD/unit', ''],
        ['Follows CF', 'On, output follows the capacity factor. Off pins it to ' +
                       'a fixed annual amount.'],
        ['Annual at CF', 'What the estimate levelises against: the rate on its ' +
                         'basis, times the operating hours if it is hourly, ' +
                         'times the capacity factor.'],
        ['Energy/unit', ''], ['Mass t/unit', ''], ['', '']]
      .map(([h, tip], i) =>
        el('th', { class: [2, 5, 7, 8, 9].includes(i) ? 'n' : '',
                   title: tip || null }, h)))));
  const tb = el('tbody');
  if (!list.length) tb.appendChild(el('tr', {}, el('td', { colspan: '11',
    style: 'color:var(--muted);padding:10px 8px' },
    'Add at least one product — there is nothing to levelise against otherwise.')));
  list.forEach((p, i) => {
    const resync = () => { touch(); syncProductRow(i); };
    tb.appendChild(el('tr', {},
      el('td', {}, el('input', { class: 'txt', type: 'text', value: p.name,
        oninput: e => { p.name = e.target.value; touch(); } })),
      el('td', {}, el('select', { class: 'txt', onchange: e => {
          p.role = e.target.value;
          if (p.role === 'primary') list.forEach((q, j) => {
            if (j !== i && q.role === 'primary') q.role = 'coproduct';
          });
          touch(); paintProducts();
        } },
        ...['primary', 'coproduct', 'byproduct'].map(r =>
          el('option', { value: r, selected: r === p.role || null },
             ROLE_LABEL[r])))),
      el('td', { class: 'n' }, el('input', { type: 'number',
        value: p.annual_production, step: 'any',
        oninput: e => { p.annual_production = parseFloat(e.target.value) || 0;
                        resync(); } })),
      el('td', {}, el('select', { class: 'txt',
          title: optHelp('product_basis', 'hour') + '\n\n' +
                 optHelp('product_basis', 'year'),
          onchange: e => { p.basis = e.target.value; resync(); } },
        el('option', { value: 'hour', selected: p.basis === 'hour' || null,
                       title: optHelp('product_basis', 'hour') },
           STREAM_BASIS_LABEL.hour),
        el('option', { value: 'year', selected: p.basis !== 'hour' || null,
                       title: optHelp('product_basis', 'year') },
           STREAM_BASIS_LABEL.year))),
      el('td', {}, el('input', { class: 'txt', type: 'text', value: p.unit, size: '6',
        oninput: e => { p.unit = e.target.value; resync(); } })),
      el('td', { class: 'n' }, el('input', { type: 'number', value: p.price ?? '', step: 'any',
        placeholder: p.role === 'primary' ? 'solved' : '0',
        oninput: e => { p.price = e.target.value === '' ? null : parseFloat(e.target.value); touch(); } })),
      el('td', {}, el('input', { type: 'checkbox',
        checked: p.scales_with_rate !== false || null, style: 'width:auto',
        onchange: e => { p.scales_with_rate = e.target.checked; resync(); } })),
      el('td', { class: 'n', 'data-product': String(i),
                 title: `${fmt(productAnnual(p), 4)} ${p.unit || ''}/yr` },
        fmt(productAnnual(p), 0)),
      el('td', { class: 'n' }, el('input', { type: 'number', value: p.energy_content ?? 0, step: 'any',
        oninput: e => { p.energy_content = parseFloat(e.target.value) || 0; touch(); } })),
      el('td', { class: 'n' }, el('input', { type: 'number', value: p.mass_per_unit ?? 1, step: 'any',
        oninput: e => { p.mass_per_unit = parseFloat(e.target.value) || 0; touch(); } })),
      el('td', { class: 'act' }, el('button', { class: 'x',
        onclick: () => { list.splice(i, 1); touch(); paintProducts(); } }, '×'))));
  });
  t.appendChild(tb);
}

/* ======================================================================= */
/*                             title block                                 */
/* ======================================================================= */
function paintBlock() {
  const r = state.result, p = state.project;
  $('#tb-name').textContent = p.name || 'Untitled';
  $('#tb-basis').textContent = `${p.dollar_year} ${p.currency}`;
  $('#tb-basis').title = p.currency === 'USD' ? ''
    : `converted from ${p.dollar_year} USD at 1 USD = ${p.exchange_rate} ` +
      `${p.currency} (${p.exchange_rate_source || 'manual'})`;
  $('#tb-method').textContent = methodLabel(p.method);
  $('#tb-method').title = optHelp('method', p.method);
  $('#tb-loc').textContent = p.location;
  const v = $('#tb-value');
  if (r) {
    v.textContent = fmt(r.unit_cost, r.unit_cost < 100 ? 3 : 1);
    v.classList.toggle('stale', state.stale);
    v.title = `${moneyExact(r.unit_cost)} per ${r.unit}`;
    $('#tb-klabel').textContent = `Levelised cost of ${r.product}`;
    $('#tb-unit').textContent = `${curSym()}/${r.unit}` +
      ` · ${fmt(r.annual_production)} ${r.unit}/yr`;
    const toc = $('#tb-toc'), opx = $('#tb-opex');
    toc.textContent = money(r.capital.toc);
    toc.title = moneyExact(r.capital.toc);
    opx.textContent = money(r.opex.total);
    opx.title = moneyExact(r.opex.total);
    $('#tb-rev').textContent = String(state.rev).padStart(2, '0');
    const st = $('#tb-state');
    st.textContent = state.stale ? 'superseded' : 'current';
    st.classList.toggle('stale', state.stale);

    const stack = r.cost_stack;
    $('#tb-stack').style.display = '';
    const tt = $('#tb-stack-t'); tt.innerHTML = '';
    let tot = 0;
    for (const [k, val] of Object.entries(stack)) {
      tot += val;
      tt.appendChild(el('tr', {},
        el('td', { class: 'lbl' }, k),
        el('td', {}, fmt(val, val < 100 ? 3 : 1))));
    }
    tt.appendChild(el('tr', { class: 'tot' },
      el('td', { class: 'lbl' }, 'total'),
      el('td', {}, fmt(tot, tot < 100 ? 3 : 1))));
    const bar = $('#tb-bar'); bar.innerHTML = '';
    const P = pal();
    Object.values(stack).forEach((val, i) => {
      if (val <= 0) return;
      bar.appendChild(el('i', { style:
        `width:${(val / Math.max(tot, 1e-9) * 100).toFixed(2)}%;background:${P[i % P.length]}` }));
    });

    $('#tb-warn').innerHTML = (r.warnings || []).length
      ? '<h4>Warnings</h4>' + r.warnings.map(w =>
          `<div class="msg warn">${esc(w)}</div>`).join('')
      : '';
  } else {
    v.textContent = '—';
    $('#tb-unit').textContent = 'not yet run';
    $('#tb-rev').textContent = '—';
    $('#tb-state').textContent = 'not run';
  }
}

/* ======================================================================= */
/*                                results                                  */
/* ======================================================================= */
function kvTable(pairs, numeric = true) {
  const t = el('table', { class: 't' });
  const tb = el('tbody');
  for (const [k, v, cls, title] of pairs) {
    tb.appendChild(el('tr', { class: cls || '' },
      el('td', {}, k),
      el('td', { class: numeric ? 'n' : '', title: title || null }, v)));
  }
  t.appendChild(tb);
  return t;
}

function card(title, hint, ...kids) {
  return el('div', { class: 'card' },
    el('h3', {}, title),
    hint ? el('p', { class: 'hint' }, hint) : null,
    ...kids);
}

function methodPointer() {
  return el('div', { class: 'card m-pointer' },
    el('h3', {}, 'How this number was reached'),
    el('p', { class: 'hint' },
      'The equations actually used on this run, with these numbers substituted, ' +
      'are set out step by step — and go to the end of every report you export.'),
    el('div', { class: 'row' },
      el('button', {
        class: 'btn', onclick: () => { showPanel('info'); showInfoTab('method'); }
      }, 'Show the calculations'),
      el('button', { class: 'btn', onclick: () => doExport('xlsx') },
        'Excel workbook')));
}

/* ---------------------------------------------------------------------
   The operating-cost table, with its subtotals.

   Equipment consumption arrives as one line per machine — "electricity —
   K-101", "electricity — P-101" — which is the right level of detail to
   have and the wrong level to read a total off. The list is therefore
   grouped by the category each line belongs to, with a subtotal per category
   and, inside a category, a subtotal for every utility drawn by more than one
   item. So the electricity bill, the feed bill and the whole utility bill are
   all on the page beside the lines that make them up, instead of having to be
   added up by eye or read off a chart.
   --------------------------------------------------------------------- */
const OPEX_CATEGORY_LABEL = {
  raw_material: 'Raw materials', catalyst: 'Catalysts and chemicals',
  utility: 'Utilities', waste: 'Waste and effluent', royalty: 'Royalties',
  other: 'Other variable',
};
/* Biggest and most-argued-about first; anything unrecognised follows. */
const OPEX_CATEGORY_ORDER = ['raw_material', 'catalyst', 'utility', 'waste',
                             'royalty', 'other'];

/* "electricity — K-101" is the electricity line for K-101. The part before the
   dash is the tariff it is charged at, and is what a subtotal is about. */
const opexBaseName = k => String(k).split(' \u2014 ')[0].trim();

function opexRows(op) {
  const rows = [];
  const items = op.variable_items || {};
  const cats = op.variable_categories || {};
  const bySize = (a, b) => Math.abs(b[1]) - Math.abs(a[1]);

  const groups = {};
  Object.entries(items).forEach(([k, v]) => {
    const c = cats[k] || 'other';
    (groups[c] = groups[c] || []).push([k, v]);
  });
  const order = [...OPEX_CATEGORY_ORDER.filter(c => groups[c]),
                 ...Object.keys(groups).filter(c => !OPEX_CATEGORY_ORDER.includes(c))];

  order.forEach(cat => {
    const lines = groups[cat];
    const total = lines.reduce((a, [, v]) => a + v, 0);
    const label = OPEX_CATEGORY_LABEL[cat] || sentenceLabel(cat.replace(/_/g, ' '));
    rows.push([label, '', 'grp']);

    /* Lines that share a tariff are kept together, largest bill first, with
       the tariff's own total under them. Sorting the category flat by size
       instead scatters the five electricity lines through the list and leaves
       their subtotal sitting under whatever happened to come last. */
    const byName = new Map();
    lines.forEach(([k, v]) => {
      const n = opexBaseName(k);
      if (!byName.has(n)) byName.set(n, { sum: 0, lines: [] });
      const g = byName.get(n);
      g.sum += v;
      g.lines.push([k, v]);
    });
    [...byName.entries()]
      .sort((a, b) => Math.abs(b[1].sum) - Math.abs(a[1].sum))
      .forEach(([n, g]) => {
        g.lines.sort(bySize).forEach(([k, v]) =>
          rows.push([k, moneyFull(v), null, moneyExact(v)]));
        // A subtotal identical to the single line above it is noise.
        if (g.lines.length > 1) {
          rows.push([`${n} — all items`, moneyFull(g.sum), 'subline',
                     moneyExact(g.sum)]);
        }
      });
    rows.push([`Subtotal ${label.toLowerCase()}`, moneyFull(total), 'sub',
               moneyExact(total)]);
  });

  rows.push(['Subtotal variable', moneyFull(op.variable_total), 'sub',
             moneyExact(op.variable_total)]);
  rows.push(['Fixed', '', 'grp']);
  Object.entries(op.fixed_items || {}).sort(bySize)
    .forEach(([k, v]) => rows.push([k, moneyFull(v), null, moneyExact(v)]));
  rows.push(['Subtotal fixed', moneyFull(op.fixed_total), 'sub',
             moneyExact(op.fixed_total)]);
  rows.push(['Total annual operating cost', moneyFull(op.total), 'sum',
             moneyExact(op.total)]);
  return rows;
}

function paintResults(extra) {
  const r = state.result, body = $('#results-body');
  body.innerHTML = '';
  if (!r) { body.appendChild(el('div', { class: 'empty' },
    'Run the estimate to see results.')); return; }
  const cur = curSym();

  (r.warnings || []).forEach(w =>
    body.appendChild(el('div', { class: 'msg warn', html: `<b>Check</b> — ${esc(w)}` })));

  // basis
  const asm = (extra?.assumptions || []).map(a => [a.label, a.value]);
  body.appendChild(card('Basis of estimate',
    'This table belongs at the front of any report built on these numbers.',
    el('div', { class: 'tbl-wrap' }, kvTable(asm, false))));

  // method comparison
  if (extra?.comparison) {
    const base = extra.comparison.dcf;
    body.appendChild(card('The method changes the answer',
      'Same inputs, three conventions. The spread is the cost of capital and how ' +
      'each method charges for it. Quote which one you used.',
      el('div', { class: 'tbl-wrap' }, kvTable(
        Object.entries(extra.comparison).map(([m, v]) => [
          methodLabel(m) + (m === r.method ? '  ← selected' : ''),
          v === null ? 'Failed' : `${fmt(v, v < 100 ? 3 : 1)} ${cur}/${r.unit}` +
            (base && v ? `   (${((v / base - 1) * 100).toFixed(0)}% vs DCF)` : '')
        ]), false))));
  }

  // capital — full figures, exact value on hover
  const c = r.capital;
  body.appendChild(card('Capital cost', null, el('div', { class: 'tbl-wrap' }, kvTable([
    ['Bare erected cost (BEC)', moneyFull(c.bec), null, moneyExact(c.bec)],
    ['+ EPC contractor services', moneyFull(c.epc_fee), null, moneyExact(c.epc_fee)],
    ['= EPC cost (EPCC)', moneyFull(c.epcc), 'sub', moneyExact(c.epcc)],
    ['+ process contingency', moneyFull(c.process_contingency), null,
      moneyExact(c.process_contingency)],
    ['+ project contingency', moneyFull(c.project_contingency), null,
      moneyExact(c.project_contingency)],
    ['= Total plant cost (TPC)', moneyFull(c.tpc), 'sub', moneyExact(c.tpc)],
    ...Object.entries(c.owners_costs).map(([k, v]) =>
      ['+ ' + k, moneyFull(v), null, moneyExact(v)]),
    ['= Total overnight cost (TOC)', moneyFull(c.toc), 'sum', moneyExact(c.toc)],
    [`× TASC/TOC factor (${c.tasc_toc_factor.toFixed(4)})`, moneyFull(c.tasc),
      null, moneyExact(c.tasc)],
  ]))));

  // opex
  const op = r.opex;
  body.appendChild(card('Operating cost',
    `${fmt(op.operating_hours)} h/yr at ${(op.capacity_factor * 100).toFixed(0)}% ` +
    `capacity factor. Depreciation and financing are excluded by construction.`,
    el('div', { class: 'tbl-wrap' }, kvTable(opexRows(op)))));

  // levelised
  body.appendChild(card('Levelised cost build-up', null,
    el('div', { class: 'tbl-wrap' }, kvTable([
      ...Object.entries(r.cost_stack).map(([k, v]) =>
        [k, fmt(v, Math.abs(v) < 100 ? 4 : 1)]),
      [`${r.product} cost, ${cur}/${r.unit}`,
       fmt(r.unit_cost, r.unit_cost < 100 ? 4 : 1), 'sum'],
    ]))));

  // cash flow
  if (r.cash_flow) {
    const cf = r.cash_flow;
    const t = el('table', { class: 't' });
    t.appendChild(el('thead', {}, el('tr', {},
      ...['Year', 'Capex', 'Revenue', 'Opex', 'Deprec.', 'Tax', 'Net CF', 'Cum. DCF']
        .map((h, i) => el('th', { class: i ? 'n' : '' },
          i ? `${h} (${curCode()})` : h)))));
    const tb = el('tbody');
    const cell = v => el('td', { class: 'n', title: moneyExact(v) }, moneyFull(v));
    cf.years.forEach((y, i) => tb.appendChild(el('tr', {},
      el('td', {}, y),
      cell(-cf.capex[i]),
      cell(cf.revenue[i]),
      cell(-cf.opex[i]),
      cell(cf.depreciation[i]),
      cell(-cf.tax[i]),
      cell(cf.net_cash_flow[i]),
      cell(cf.cumulative_dcf[i]))));
    t.appendChild(tb);
    body.appendChild(card('Cash flow',
      `NPV ${money(cf.npv)} at ${pct(state.project.finance.discount_rate)}; ` +
      `IRR ${cf.irr ? pct(cf.irr) : 'n/a'}` +
      (cf.payback_year ? `; discounted payback in year ${cf.payback_year.toFixed(1)}` : ''),
      el('div', { class: 'tbl-wrap' }, t)));
  }

  if ((r.notes || []).length) {
    body.appendChild(card('Method notes', null,
      ...r.notes.map(n => el('div', { class: 'msg note' }, n))));
  }

  body.appendChild(methodPointer());
}

/* ======================================================================= */
/*                          utility distribution                           */
/* ======================================================================= */
/* Every other view here answers "what does it cost". A process engineer asks
   the other question first — which machines are drawing this, and how much —
   and every figure needed to answer it is already recorded against the items.

   The chart is built in the browser from the run's own distribution data
   rather than fetched: switching utility or grouping is a repaint, not a
   round trip, and the same data is already on screen in the table below. The
   report gets the identical figures from teakit.charts. */
const UD_GROUP_KEY = { item: 'items', section: 'by_section', type: 'by_type' };
const UD_GROUP_LABEL = { item: 'by equipment item', section: 'by plant section',
                         type: 'by equipment type' };

const utilityDistribution = () => (state.result || {}).utility_distribution || [];
const udEntry = name => utilityDistribution().find(e => e.utility === name) || null;

/* The rows of whichever grouping is selected, as {label, quantity, cost}. */
function udRows(entry, group) {
  const rows = entry[UD_GROUP_KEY[group]] || [];
  return group === 'item'
    ? rows.map(r => ({ label: r.tag || r.label, sub: r.label, n: r.units,
                       rate: r.rate, rate_unit: r.rate_unit,
                       section: r.section, type: r.equipment_type,
                       source: r.source,
                       quantity: r.annual_quantity, cost: r.annual_cost }))
    : rows.map(r => ({ label: r.name, sub: `${r.n} line${r.n === 1 ? '' : 's'}`,
                       quantity: r.annual_quantity, cost: r.annual_cost }));
}

function paintUtilityDistribution() {
  const sel = $('#f-ud-util'), out = $('#ud-out'), tbl = $('#ud-table'),
        note = $('#ud-note');
  if (!sel || !out || !tbl) return;
  const dist = utilityDistribution();

  // Keep the selection across re-runs; a repaint that resets the dropdown to
  // the first utility every time is unusable while iterating.
  const want = state.udUtility || sel.value;
  sel.innerHTML = '';
  dist.forEach(e => sel.appendChild(el('option', {
    value: e.utility,
    title: `${fmt(e.annual_quantity, 0)} ${e.unit}/yr · ${money(e.annual_cost)}/yr`
  }, `${sentenceLabel(e.utility)} — ${fmt(e.annual_quantity, 0)} ${e.unit}/yr`)));
  if (!dist.length) {
    out.innerHTML = '';
    tbl.innerHTML = '';
    note.className = 'msg note';
    note.textContent = state.result
      ? 'Nothing is consumed in this estimate yet. Give an equipment item a ' +
        'utility, or add a line on the Operating cost panel.'
      : 'Run the estimate to see where the utilities go.';
    return;
  }
  if (dist.some(e => e.utility === want)) sel.value = want;
  state.udUtility = sel.value;

  const entry = udEntry(sel.value);
  const group = $('#f-ud-group').value;
  const measure = $('#f-ud-measure').value;
  const kind = $('#f-ud-kind').value;
  const rows = udRows(entry, group).filter(r => r[measure === 'cost' ? 'cost' : 'quantity']);
  const key = measure === 'cost' ? 'cost' : 'quantity';
  const unit = measure === 'cost' ? `${curCode()}/yr` : `${entry.unit}/yr`;

  const spec = {
    kind, title: `${sentenceLabel(entry.utility)} ${UD_GROUP_LABEL[group]}`,
    labels: rows.map(r => r.label), values: rows.map(r => r[key]),
    y_label: unit, unit, currency: measure === 'cost' ? curSym() : '',
    note: measure === 'cost'
      ? `${money(entry.annual_cost)}/yr in total`
      : `${fmt(entry.annual_quantity, 0)} ${entry.unit}/yr in total` +
        (entry.generated ? `, of which ${fmt(entry.generated, 0)} generated` : '')
  };
  out.innerHTML = '';
  out.appendChild(figure(spec, 880, 380));

  // The table carries what the chart cannot: the rate each item draws at, in
  // the unit an engineer reads it in, and where it sits.
  const total = rows.reduce((a, r) => a + r[key], 0) || 1;
  tbl.innerHTML = '';
  const head = group === 'item'
    ? [['Item', ''], ['Section', ''], ['Type', ''],
       ['Rate', 'What it draws while running, for the running units — ' +
                'installed spares are excluded.'],
       ['Unit', ''], [`Per year (${entry.unit})`, ''], ['Share', ''],
       [`Cost (${curCode()}/yr)`, '']]
    : [[group === 'section' ? 'Plant section' : 'Equipment type', ''],
       ['Lines', ''], [`Per year (${entry.unit})`, ''], ['Share', ''],
       [`Cost (${curCode()}/yr)`, '']];
  tbl.appendChild(el('thead', {}, el('tr', {}, ...head.map(([h, tip], i) =>
    el('th', { class: i === 0 ? '' : 'n', title: tip || null }, h)))));

  const tb = el('tbody');
  rows.forEach(r => {
    tb.appendChild(group === 'item'
      ? el('tr', {},
          el('td', { title: r.sub || '' },
            r.label,
            r.source === 'plant'
              ? el('span', { class: 'pill xs',
                  title: 'Entered on the Operating cost panel rather than ' +
                         'against a machine, so it cannot be attributed further.'
                }, 'plant')
              : null),
          el('td', { class: 'n' }, r.section || '—'),
          el('td', { class: 'n' }, r.type || '—'),
          el('td', { class: 'n' }, fmtRate(r.rate)),
          el('td', { class: 'n' }, r.rate_unit || entry.unit),
          el('td', { class: 'n' }, fmt(r.quantity, 0)),
          el('td', { class: 'n' }, (r[key] / total * 100).toFixed(1) + '%'),
          el('td', { class: 'n', title: moneyExact(r.cost) }, moneyFull(r.cost)))
      : el('tr', {},
          el('td', {}, r.label),
          el('td', { class: 'n' }, r.sub),
          el('td', { class: 'n' }, fmt(r.quantity, 0)),
          el('td', { class: 'n' }, (r[key] / total * 100).toFixed(1) + '%'),
          el('td', { class: 'n', title: moneyExact(r.cost) }, moneyFull(r.cost))));
  });
  tbl.appendChild(tb);
  tbl.appendChild(el('tfoot', {}, el('tr', { class: 'sum' },
    el('td', {}, 'Total'),
    ...Array(group === 'item' ? 4 : 1).fill(0).map(() => el('td', { class: 'n' }, '')),
    el('td', { class: 'n' }, fmt(entry.annual_quantity, 0)),
    el('td', { class: 'n' }, '100.0%'),
    el('td', { class: 'n', title: moneyExact(entry.annual_cost) },
      moneyFull(entry.annual_cost)))));

  note.className = 'msg note';
  const attributed = (entry.items || []).filter(i => i.source === 'equipment');
  const plant = (entry.items || []).filter(i => i.source === 'plant');
  const attrQ = attributed.reduce((a, i) => a + Math.abs(i.annual_quantity), 0);
  const allQ = (entry.items || []).reduce((a, i) => a + Math.abs(i.annual_quantity), 0) || 1;
  note.innerHTML =
    `<b>${(attrQ / allQ * 100).toFixed(0)}%</b> of this utility is attributed to ` +
    `${attributed.length} equipment item${attributed.length === 1 ? '' : 's'}` +
    (plant.length
      ? `; the rest is ${plant.length} plant-level line` +
        `${plant.length === 1 ? '' : 's'}, which cannot be broken down further. ` +
        'Move it onto the item that incurs it and it appears here.'
      : '. Everything is traceable to a machine.') +
    (entry.priced ? '' : ' This utility has no price, so it costs nothing in ' +
                         'the estimate — the consumption is still real.');
}

function paintCharts() {
  paintUtilityDistribution();
  const body = $('#charts-body');
  body.innerHTML = '';
  const specs = { ...(state.charts || {}), ...(state.utilityCharts || {}) };
  if (!specs || !Object.keys(specs).length) {
    body.appendChild(el('div', { class: 'empty' }, 'Run the estimate to see charts.'));
    return;
  }
  /* Grouped, because a page of fourteen unlabelled figures is a page nobody
     finds anything on. Each group answers one question, and the order inside
     it goes from the whole to the parts. Anything unrecognised falls into
     "Other" rather than being dropped. */
  const GROUPS = [
    ['The answer', 'What the estimate comes to, and what it is made of.',
     ['cost_stack', 'capex_opex_split']],
    ['Capital', 'From purchased equipment to total capital.',
     ['capex_waterfall']],
    ['Equipment', 'The same equipment list, read three ways: which item cost ' +
     'the most, where on the site the money went, and what kind of machine ' +
     'it was spent on.',
     ['equipment_share', 'section_share', 'type_share']],
    ['Operating cost', 'What the plant spends every year.',
     ['opex_breakdown', 'opex_by_category', 'cash_flow']],
    ['Utilities', 'What the plant consumes, and which machines consume it. ' +
     'Quantities are in each utility\u2019s own units.',
     null],   // everything utility_*, in the order the library emits them
  ];
  const WIDE_BY_DEFAULT = new Set(['cash_flow', 'capex_waterfall',
                                   'opex_breakdown', 'utility_totals']);

  const placed = new Set();
  const section = (title, hint, keys) => {
    keys = keys.filter(k => specs[k] && !placed.has(k));
    if (!keys.length) return;
    keys.forEach(k => placed.add(k));
    body.appendChild(el('h3', { class: 'fig-group' }, title));
    if (hint) body.appendChild(el('p', { class: 'hint' }, hint));
    const grid = el('div', { class: 'figs' });
    keys.forEach(k => {
      // A default, not a lock: the reader's own choice, once made, wins.
      if (WIDE_BY_DEFAULT.has(k) && figWide[figKey(specs[k])] === undefined) {
        figWide[figKey(specs[k])] = true;
      }
      grid.appendChild(figure(specs[k], 460, 340));
    });
    body.appendChild(grid);
  };

  GROUPS.forEach(([title, hint, keys]) => section(title, hint,
    keys || Object.keys(specs).filter(k => k.startsWith('utility_'))));
  section('Other', null, Object.keys(specs));
}

/* ======================================================================= */
/*                                 actions                                 */
/* ======================================================================= */
async function run() {
  try {
    const j = await api('run', { project: state.project, compare_methods: true });
    state.result = j.result;
    state.charts = j.charts || {};
    state.utilityCharts = j.utility_charts || {};
    state.explanation = j.explanation || [];
    state.rev += 1;
    state.stale = false;
    paintBlock();
    paintResults(j);
    paintCharts();
    paintEquipment();
    paintStreams();
    paintEquipmentUtilities();
    // The installation note quotes what the step actually came to in money,
    // which only exists once there is a result to quote from.
    paintInstallNote();
    paintMethodExplain();
    toast(`Rev ${String(state.rev).padStart(2, '0')} — ` +
          `${fmt(j.result.unit_cost, j.result.unit_cost < 100 ? 3 : 1)} ` +
          `per ${j.result.unit}`);
    refreshParams();
  } catch (e) {
    toast(e.message, 5200);
    $('#results-body').innerHTML =
      `<div class="msg err"><b>The estimate did not run.</b> ${esc(e.message)}</div>`;
  }
}

/* Base64 to bytes. The Excel workbook is binary and the API is JSON, so it
   arrives base64-encoded; writing the string straight into a Blob would
   produce a file Excel refuses to open. */
function b64bytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/* =======================================================================
   Where the files go.

   Exports used to be handed to the browser and nowhere else, which made
   "where did my report go?" a fair question with no answer inside the
   application. They now go to a folder teakit owns and shows — reports/ beside
   the application by default, anywhere the user points it otherwise — and the
   browser download stays available as a deliberate choice rather than the only
   behaviour. The folder itself lives in teakit.app.workspace on the Python
   side; this is only its face.
   ======================================================================= */
const DEST_KEY = 'teakit.destination';

/* Null until the first successful call. Every painter treats that as "we do
   not know yet" rather than as an error, so a slow or failed lookup never
   blocks the interface. */
let workspaceInfo = null;

function destMode() {
  try {
    const v = localStorage.getItem(DEST_KEY);
    if (v === 'download' || v === 'folder') return v;
  } catch (e) { /* private window: fall through to the default */ }
  return 'folder';
}

function setDestMode(v) {
  try { localStorage.setItem(DEST_KEY, v); } catch (e) { /* not fatal */ }
  paintDest();
  if ($('#dlg-files') && $('#dlg-files').open) paintFiles();
}

async function refreshWorkspace(loud = false) {
  try {
    workspaceInfo = await api('workspace');
  } catch (e) {
    workspaceInfo = null;
    if (loud) toast(e.message, 4000);
  }
  paintDest();
  return workspaceInfo;
}

/* Shown from the right, and cut on a separator rather than mid-word:
   "…\teakit main\reports" says where a file landed, where "…0.0-source\teakit"
   only says that the path was long. */
function shortPath(p, n = 34) {
  const t = String(p || '');
  if (t.length <= n) return t;
  const sep = t.indexOf('\\') >= 0 ? '\\' : '/';
  const parts = t.split(/[\\/]/).filter(Boolean);
  let tail = '';
  for (let i = parts.length - 1; i >= 0; i--) {
    const next = sep + parts[i] + tail;
    if (next.length + 1 > n && tail) break;
    tail = next;
  }
  return '…' + (tail || sep + parts[parts.length - 1]);
}

const fileSize = b => b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB'
  : b >= 1024 ? Math.round(b / 1024) + ' KB' : b + ' B';

function paintDest() {
  const btn = $('#dest-path');
  if (!btn) return;
  const folder = workspaceInfo && workspaceInfo.dir;
  const unwritable = destMode() === 'folder' && workspaceInfo &&
                     !workspaceInfo.writable;
  if (destMode() === 'download') {
    btn.textContent = 'Browser downloads';
    btn.title = 'Exports are handed to the browser. ' +
                'Click to save them into a folder instead.';
  } else if (folder) {
    btn.textContent = shortPath(folder);
    btn.title = folder + (unwritable ? '\n\nThis folder cannot be written to.' : '') +
                '\n\nClick to change it, or to switch to browser downloads.';
  } else {
    btn.textContent = 'Choose a folder…';
    btn.title = 'Click to choose where teakit writes its files.';
  }
  btn.classList.toggle('warn', Boolean(unwritable));
  const open = $('#btn-dest-open');
  if (open) open.disabled = !(folder && destMode() === 'folder');
}

/* --------------------------- the files dialog -------------------------- */
function openFiles() {
  const dlg = $('#dlg-files');
  if (!dlg) return;
  paintFiles();
  dlg.showModal();
  refreshWorkspace().then(() => { if (dlg.open) paintFiles(); });
}

function paintFiles() {
  const body = $('#files-body');
  if (!body) return;
  const w = workspaceInfo;
  body.innerHTML = '';

  body.appendChild(el('p', { class: 'hint' },
    'Reports, workbooks, CSVs and saved projects are written here. Anything ' +
    'you drop into this folder yourself sits alongside them and is listed ' +
    'below — it is an ordinary folder, not a store teakit manages.'));

  /* --- where exports go --- */
  const choose = el('div', { class: 'dest-choice' });
  [['folder', 'Save into a folder',
    'Files are written straight to disk and listed below.'],
   ['download', 'Hand to the browser',
    'Files go wherever your browser puts downloads.']].forEach(([v, label, note]) => {
    const on = destMode() === v;
    choose.appendChild(el('label', { class: 'dest-opt' + (on ? ' on' : '') },
      el('input', { type: 'radio', name: 'teakit-dest', value: v,
        checked: on || null, onchange: () => setDestMode(v) }),
      el('span', {},
        el('b', {}, label),
        el('span', { class: 'dest-opt-n' }, note))));
  });
  body.appendChild(choose);

  /* --- the folder --- */
  body.appendChild(el('h4', { class: 'guide-h' }, 'The folder'));
  const input = el('input', {
    type: 'text', class: 'dest-input', spellcheck: 'false',
    value: (w && w.dir) || '',
    placeholder: 'Type or paste a folder path',
    onkeydown: e => { if (e.key === 'Enter') { e.preventDefault(); apply(); } },
  });
  const apply = async () => {
    try {
      workspaceInfo = await api('workspace_set', { dir: input.value });
      paintDest(); paintFiles();
      toast('Files will be saved to ' + workspaceInfo.dir, 4000);
    } catch (e) { toast(e.message, 5000); }
  };
  body.appendChild(el('div', { class: 'dest-row' }, input,
    el('button', { class: 'btn sm primary', type: 'button', onclick: apply,
      title: 'Use the folder in the box, creating it if it does not exist' },
      'Use this folder')));

  body.appendChild(el('div', { class: 'dest-row' },
    el('button', {
      class: 'btn sm', type: 'button',
      title: w && w.can_pick ? 'Pick a folder with the system dialog'
        : 'This Python build has no folder chooser — type the path instead',
      disabled: (w && w.can_pick) ? null : true,
      onclick: async e => {
        // The chooser is a native window from the Python side, and it can sit
        // open for as long as the user likes. Say so rather than looking hung.
        const b = e.target; const was = b.textContent;
        b.disabled = true; b.textContent = 'Choose in the dialog…';
        try {
          const j = await api('workspace_pick', { dir: (w && w.dir) || '' });
          workspaceInfo = j;
          paintDest(); paintFiles();
          if (!j.cancelled) toast('Files will be saved to ' + j.dir, 4000);
        } catch (err) { toast(err.message, 5000); }
        finally { b.disabled = null; b.textContent = was; }
      }
    }, 'Browse…'),
    el('button', {
      class: 'btn sm', type: 'button', title: 'Open this folder in the file manager',
      onclick: () => api('workspace_open', {})
        .catch(err => toast(err.message, 5000))
    }, 'Open folder'),
    el('button', {
      class: 'btn sm ghost', type: 'button',
      disabled: (w && !w.is_default) ? null : true,
      title: w ? `Go back to ${w.default_dir}` : '',
      onclick: async () => {
        try {
          workspaceInfo = await api('workspace_reset');
          paintDest(); paintFiles();
          toast('Back to the folder beside the application', 3500);
        } catch (e) { toast(e.message, 5000); }
      }
    }, 'Use the default')));

  if (w) {
    body.appendChild(el('div', { class: w.writable ? 'msg note' : 'msg warn' },
      w.writable
        ? el('span', {}, el('b', {}, 'Ready — '),
            `files are written to ${w.dir}.` +
            (w.is_default ? ' This is the default: the reports folder beside ' +
                            `the application in ${w.app_root}.` : ''))
        : el('span', {}, el('b', {}, 'Not writable — '),
            `${w.dir} cannot be written to. Choose another folder, or exports ` +
            'will be handed to the browser instead.')));
  }

  /* --- what is in it --- */
  const files = (w && w.files) || [];
  body.appendChild(el('h4', { class: 'guide-h' },
    files.length ? `In the folder — ${files.length} file${files.length === 1 ? '' : 's'}`
                 : 'In the folder'));
  if (!files.length) {
    body.appendChild(el('div', { class: 'empty' },
      'Nothing here yet. Export a report and it will appear.'));
  } else {
    const t = el('table', { class: 't' },
      el('thead', {}, el('tr', {},
        el('th', {}, 'File'), el('th', { class: 'n' }, 'Size'),
        el('th', {}, 'Saved'), el('th', {}, ''))),
      el('tbody', {}, ...files.map(f => el('tr', {},
        el('td', { title: f.path }, f.name),
        el('td', { class: 'n' }, fileSize(f.bytes)),
        el('td', {}, f.modified),
        el('td', { class: 'act' }, el('button', {
          class: 'btn xs', type: 'button',
          title: 'Show this file in the file manager',
          onclick: () => api('workspace_open', { path: f.path })
            .catch(err => toast(err.message, 5000))
        }, 'Show'))))));
    body.appendChild(el('div', { class: 'tbl-wrap' }, t));
  }
}

function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime || 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function doExport(format) {
  try {
    const payload = { project: state.project, format };
    if (format === 'html') {
      payload.extra_charts = {};
      $$('#sens-body .fig').forEach((f, i) => {
        if (f._spec) payload.extra_charts['sensitivity_' + i] = f._spec;
      });
    }
    const j = await api('export', payload);
    const toBrowser = () => download(j.filename,
      j.encoding === 'base64' ? b64bytes(j.content) : j.content, j.mime);

    if (destMode() === 'folder') {
      let res;
      try {
        res = await api('workspace_save', {
          filename: j.filename, content: j.content,
          encoding: j.encoding || 'text' });
      } catch (e) {
        // A folder that has been deleted, renamed or filled up must not cost
        // the user the file they just asked for. Hand it over and say why.
        toBrowser();
        toast(`Could not write to the report folder — ${e.message} ` +
              `${j.filename} was downloaded instead.`, 7000);
        return;
      }
      workspaceInfo = res;
      paintDest();
      if ($('#dlg-files') && $('#dlg-files').open) paintFiles();
      toast(`Saved ${res.saved.name} to ${res.saved.dir}`, 4500);
      return;
    }

    toBrowser();
    toast(j.bytes
      ? `Downloaded ${j.filename} — ${Math.round(j.bytes / 1024)} KB`
      : 'Downloaded ' + j.filename);
  } catch (e) { toast(e.message, 5000); }
}

/* --------------------------- catalogue picker -------------------------- */
function openCatalogue() {
  const dlg = $('#dlg-cat');
  const paint = () => {
    const q = $('#cat-q').value.trim().toLowerCase();
    const items = state.meta.equipment.filter(m =>
      !q || (m.key + ' ' + m.description).toLowerCase().includes(q));
    const box = $('#cat-list'); box.innerHTML = '';
    items.forEach(m => {
      box.appendChild(el('div', {
        class: 'cat-row', tabindex: '0',
        onclick: () => { addCatalogue(m); dlg.close(); },
        onkeydown: e => { if (e.key === 'Enter') { addCatalogue(m); dlg.close(); } }
      },
        el('div', {},
          el('div', { class: 'k' }, m.key,
            m.reliable ? null : el('span', { class: 'pill warn',
              style: 'margin-left:8px' }, 'weak fit')),
          el('div', { class: 'd' }, m.description)),
        el('div', { class: 'm' },
          `n = ${m.exponent.toFixed(3)}`, el('br'),
          `${fmt(m.valid_min)}–${fmt(m.valid_max)} ${m.unit}`)));
    });
    $('#cat-count').textContent = `${items.length} of ${state.meta.equipment.length}`;
  };
  $('#cat-q').oninput = paint;
  paint();
  dlg.showModal();
  $('#cat-q').focus();
}

function addCatalogue(m) {
  const prefix = m.key.startsWith('pump') ? 'P' : m.key.startsWith('hx') ? 'E'
    : m.key.startsWith('compressor') || m.key.startsWith('blower') ? 'K'
    : m.key.startsWith('tank') ? 'TK' : m.key.startsWith('vessel') ? 'V'
    : m.key.startsWith('turbine') ? 'GT' : m.key.startsWith('filter') ? 'F' : 'X';
  state.project.equipment.push({
    tag: nextTag(prefix), kind: m.key,
    size: +(Math.sqrt(m.valid_min * m.valid_max)).toPrecision(2),
    quantity: 1, spare: 0, material: 'carbon steel', mode: 'catalogue',
    base_cost: null, base_size: null, exponent: null, base_year: null,
    size_unit: m.unit, direct_cost: null, cost_is_installed: false,
    // Blank rather than the catalogue description: the Item column shows the
    // name and falls back to the description as its placeholder, so a name
    // typed later replaces a suggestion instead of editing a copy of one.
    section: 'Process', name: '', note: ''
  });
  touch(); paintEquipment();
  toast(`Added ${m.key} — set the size, it starts at the geometric mean of the fitted range`);
}

/* ----------------------------- sensitivity ----------------------------- */
let allParams = [];

async function refreshParams() {
  try {
    const j = await api('parameters', { project: state.project });
    allParams = j.parameters;
    const fill = (sel, ph) => {
      const cur = sel.value;
      sel.innerHTML = '';
      if (ph) sel.appendChild(el('option', { value: '' }, ph));
      const groups = {};
      allParams.forEach(p => (groups[p.group] = groups[p.group] || []).push(p));
      for (const [g, list] of Object.entries(groups)) {
        const og = el('optgroup', { label: optLabel(g) });
        list.forEach(p => og.appendChild(el('option', { value: p.path },
          `${sentenceLabel(p.label)}${p.unit ? ' (' + p.unit + ')' : ''}`)));
        sel.appendChild(og);
      }
      if (cur) sel.value = cur;
    };
    fill($('#f-spath'));
    fill($('#tp-add'), 'Add a parameter to the tornado…');
    if (!state.tornadoParams.length) {
      state.tornadoParams = j.suggested.map(s =>
        ({ ...s, mode: 'percent', low: null, high: null }));
    }
    // The Current and Range columns read from allParams, which has just
    // changed, so the table is stale whether or not the list itself is.
    paintTornadoParams();
  } catch (e) { /* parameters are a convenience; a failure is not fatal */ }
}

/* The current value of a tornado parameter, from the last parameter scan. */
const tpBase = p => (allParams.find(a => a.path === p.path) || {}).value;
const tpMeta = p => allParams.find(a => a.path === p.path) || {};

/* What a row's low and high actually come to, whatever mode it is in.

   "Low 0.7" used to be on screen with nothing saying whether that was seven
   tenths of the discount rate or a discount rate of 70%. This resolves the
   row exactly as teakit.sensitivity.SensitivityParam.resolve does, so the
   number in the Range column is the number the study will use. */
function tpResolve(p) {
  const base = tpBase(p);
  const m = tpMeta(p);
  if (typeof base !== 'number') return null;
  const pct = p.mode === 'percent';
  const lo = p.low === null || p.low === undefined || p.low === ''
    ? base * (m.low_mult ?? 0.75)
    : (pct ? base * (1 + Number(p.low) / 100) : Number(p.low));
  const hi = p.high === null || p.high === undefined || p.high === ''
    ? base * (m.high_mult ?? 1.25)
    : (pct ? base * (1 + Number(p.high) / 100) : Number(p.high));
  return { base, lo, hi,
           autoLo: p.low === null || p.low === undefined || p.low === '',
           autoHi: p.high === null || p.high === undefined || p.high === '' };
}

/* The multipliers a blank cell falls back to, written the way the row reads
   them, so "auto" has a visible value in either mode. */
function tpAutoPlaceholder(p, side) {
  const m = tpMeta(p);
  const mult = side === 'low' ? (m.low_mult ?? 0.75) : (m.high_mult ?? 1.25);
  const base = tpBase(p);
  if (p.mode === 'percent') {
    return `auto ${(mult - 1) * 100 > 0 ? '+' : ''}${((mult - 1) * 100).toFixed(0)}%`;
  }
  return typeof base === 'number' ? `auto ${fmt(base * mult, 4)}` : 'auto';
}

function paintTornadoParams() {
  const box = $('#tp-list'); box.innerHTML = '';
  if (!state.tornadoParams.length) {
    box.appendChild(el('div', { class: 'empty' },
      'Automatic selection: discount rate, contingency, plant life, capacity ' +
      'factor and your largest variable-cost lines.'));
    return;
  }
  const t = el('table', { class: 't', id: 'tp-table' });
  t.appendChild(el('thead', {}, el('tr', {},
    el('th', {}, 'Parameter'),
    el('th', { class: 'n', title: 'What this parameter is set to in the ' +
               'project right now. The tornado swings around it.' }, 'Current'),
    el('th', { class: 'n' }, 'Unit'),
    el('th', { title: 'Absolute: type the low and high values themselves. ' +
               'Percent: type them as a change from the current value, so ' +
               '-20 and +20 is a ±20% swing.' }, 'Low/high as'),
    el('th', { class: 'n' }, 'Low'),
    el('th', { class: 'n' }, 'High'),
    el('th', { class: 'n', title: 'What the low and high come to once the ' +
               'mode above is applied — the values the study will actually ' +
               'run.' }, 'Range'),
    el('th', {}, ''))));
  const tb = el('tbody');

  state.tornadoParams.forEach((p, i) => {
    const m = tpMeta(p);
    const rangeCell = el('td', { class: 'n' });

    /* Redraw the resolved range in place. A repaint on every keystroke would
       take the caret out of the box being typed in. */
    const paintRange = () => {
      const r = tpResolve(p);
      rangeCell.innerHTML = '';
      if (!r) {
        rangeCell.appendChild(el('span', { class: 'unit' }, 'no base value'));
        return;
      }
      rangeCell.appendChild(el('span', {
        title: `${r.lo} to ${r.hi}` }, `${fmt(r.lo, 4)} → ${fmt(r.hi, 4)}`));
      if (r.autoLo && r.autoHi) {
        rangeCell.appendChild(el('span', { class: 'pill xs',
          title: 'From the conventional range teakit uses for this class of ' +
                 'parameter. Type a value to override it.' }, 'auto'));
      }
    };

    const numCell = side => {
      const inp = el('input', {
        type: 'number', step: 'any', value: p[side] ?? '',
        placeholder: tpAutoPlaceholder(p, side),
        title: p.mode === 'percent'
          ? 'A change from the current value, in percent. -20 means 20% below.'
          : 'The value itself, in the parameter\u2019s own unit.',
        oninput: e => {
          p[side] = e.target.value === '' ? null : parseFloat(e.target.value);
          paintRange();
        } });
      return el('td', { class: 'n' }, inp);
    };

    const modeCell = el('td', {}, el('select', {
      class: 'txt',
      title: 'How the two boxes to the right are read.',
      onchange: e => {
        const was = tpResolve(p);
        p.mode = e.target.value;
        // Carry the numbers across rather than silently reinterpreting them:
        // a 0.7 typed as an absolute discount rate is not -0.7%.
        const base = tpBase(p);
        if (was && typeof base === 'number' && base !== 0) {
          if (p.mode === 'percent') {
            if (p.low !== null && p.low !== undefined && p.low !== '')
              p.low = +(((was.lo / base) - 1) * 100).toFixed(4);
            if (p.high !== null && p.high !== undefined && p.high !== '')
              p.high = +(((was.hi / base) - 1) * 100).toFixed(4);
          } else {
            if (p.low !== null && p.low !== undefined && p.low !== '')
              p.low = +was.lo.toPrecision(6);
            if (p.high !== null && p.high !== undefined && p.high !== '')
              p.high = +was.hi.toPrecision(6);
          }
        }
        paintTornadoParams();
      } },
      el('option', { value: 'absolute', selected: p.mode !== 'percent' || null },
         'Absolute value'),
      el('option', { value: 'percent', selected: p.mode === 'percent' || null },
         '% of current')));

    const base = tpBase(p);
    tb.appendChild(el('tr', {},
      el('td', { title: p.path }, p.label || p.path),
      el('td', { class: 'n' }, typeof base === 'number'
        ? el('span', { title: String(base) }, fmt(base, 4))
        : el('span', { class: 'unit' }, '—')),
      el('td', { class: 'n' }, el('span', { class: 'unit' },
        p.unit || m.unit || '')),
      modeCell,
      numCell('low'),
      numCell('high'),
      rangeCell,
      el('td', { class: 'act' }, el('button', { class: 'x',
        title: 'Remove this parameter from the tornado',
        onclick: () => { state.tornadoParams.splice(i, 1); paintTornadoParams(); }
      }, '×'))));
    paintRange();
  });
  t.appendChild(tb);
  box.appendChild(el('div', { class: 'tbl-wrap' }, t));
}

async function runSensitivity() {
  const kind = state.sensKind;
  const metric = $('#f-metric').value || 'msp';
  const body = $('#sens-body');
  const payload = { project: state.project, kind, metric };
  if (kind === 'tornado' && state.tornadoParams.length) {
    /* A percent row is sent as a multiplier, which is what
       SensitivityParam.resolve already understands — the library has always
       supported it, only the interface had no way to say so. */
    const blank = v => v === null || v === undefined || v === '';
    payload.params = state.tornadoParams.map(p => {
      const q = { path: p.path, label: p.label, unit: p.unit };
      if (p.mode === 'percent') {
        if (!blank(p.low)) q.low_mult = 1 + Number(p.low) / 100;
        if (!blank(p.high)) q.high_mult = 1 + Number(p.high) / 100;
      } else {
        if (!blank(p.low)) q.low = Number(p.low);
        if (!blank(p.high)) q.high = Number(p.high);
      }
      return q;
    });
  }
  if (kind === 'sweep') {
    payload.path = $('#f-spath').value;
    payload.n = parseInt($('#f-sn').value, 10) || 13;
    if (!payload.path) return toast('Pick a parameter to sweep');
  }
  if (kind === 'monte_carlo') {
    payload.n = parseInt($('#f-mcn').value, 10) || 400;
    const one = $('#f-spath').value;
    if (one) payload.distributions = { [one]: {} };
  }
  if (kind === 'breakeven') {
    payload.path = $('#f-spath').value;
    payload.target = parseFloat($('#f-target').value);
    if (!payload.path || Number.isNaN(payload.target))
      return toast('Breakeven needs a parameter and a target value');
  }

  body.innerHTML = '';
  try {
    const j = await api('sensitivity', payload);
    if (kind === 'breakeven') {
      body.appendChild(card('Breakeven', null, el('div', {
        class: j.value === null ? 'msg warn' : 'msg note',
        html: j.value === null ? esc(j.message)
          : `<b>${$('#f-spath').selectedOptions[0].textContent}</b> = ` +
            `<b>${fmt(j.value, 4)}</b> puts ${esc(metric)} at ` +
            `${fmt(payload.target, 4)}.` })));
      return;
    }
    if (figWide[figKey(j.chart)] === undefined) figWide[figKey(j.chart)] = true;
    body.appendChild(el('div', { class: 'figs' },
      figure(j.chart, 880, kind === 'tornado'
        ? Math.max(320, 60 + 30 * (j.chart.labels || []).length) : 420)));

    if (kind === 'tornado') {
      const t = el('table', { class: 't' });
      t.appendChild(el('thead', {}, el('tr', {},
        el('th', {}, 'Parameter'),
        ...['Low input', 'High input', 'Low', 'High', 'Swing', '% of base']
          .map(h => el('th', { class: 'n' }, h)))));
      const tb = el('tbody');
      j.data.rows.forEach(r => tb.appendChild(el('tr', {},
        el('td', {}, r.label),
        el('td', { class: 'n' }, fmt(r.low_param)),
        el('td', { class: 'n' }, fmt(r.high_param)),
        el('td', { class: 'n' }, fmt(r.low_value, 3)),
        el('td', { class: 'n' }, fmt(r.high_value, 3)),
        el('td', { class: 'n' }, fmt(r.swing, 3)),
        el('td', { class: 'n' }, r.swing_pct.toFixed(1) + '%'))));
      t.appendChild(tb);
      body.appendChild(card('Sensitivity table',
        `Base ${fmt(j.data.base_value, 4)}. ` + (j.data.notes || []).join(' '),
        el('div', { class: 'tbl-wrap' }, t)));
    }
    if (kind === 'monte_carlo') {
      const d = j.data;
      body.appendChild(card('Distribution',
        `${d.n} successful trials. ` + (d.notes || []).join(' '),
        el('div', { class: 'tbl-wrap' }, kvTable([
          ['Deterministic base', fmt(d.base_value, 4)],
          ['Mean', fmt(d.mean, 4)],
          ['Standard deviation', fmt(d.stdev, 4)],
          ...Object.entries(d.percentiles).map(([k, v]) => [k, fmt(v, 4)]),
        ]))));
    }
    if (kind === 'sweep' && (j.data.failures || []).length) {
      body.appendChild(el('div', { class: 'msg warn' },
        `${j.data.failures.length} point(s) failed to solve and were dropped.`));
    }
  } catch (e) {
    body.innerHTML = `<div class="msg err">${esc(e.message)}</div>`;
  }
}

/* ======================================================================= */
/*                                  boot                                   */
/* ======================================================================= */
/* ======================================================================= */
/*                          guide, options, method                         */
/* ======================================================================= */
/* All three tabs of the Info section render from data the Python side owns:
   teakit.methods.GUIDE for the manual, OPTION_HELP for the option reference,
   and teakit.methods.explain() for the calculations. Nothing here is a second
   copy of an explanation that also lives in the library. */

function guideBlock(b) {
  switch (b.kind) {
    case 'p':
      return el('p', { class: 'g-p', html: b.text });
    case 'ul':
      return el('ul', { class: 'g-ul' },
        ...b.items.map(i => el('li', { html: i })));
    case 'eq':
      return el('div', { class: 'g-eq' },
        el('code', {}, b.expr),
        b.note ? el('span', { class: 'g-eq-n' }, b.note) : null);
    case 'note':
      return el('div', { class: 'msg ' + (b.tone === 'warn' ? 'warn' : 'note'),
                         html: b.text });
    case 'table': {
      const t = el('table', { class: 't' });
      t.appendChild(el('thead', {}, el('tr', {},
        ...b.headers.map(h => el('th', {}, h)))));
      t.appendChild(el('tbody', {},
        ...b.rows.map(r => el('tr', {},
          ...r.map((c, i) => el('td', { class: i === 0 ? 'k' : '', html: c }))))));
      return el('div', { class: 'tbl-wrap' }, t);
    }
    default:
      return el('p', {}, String(b.text || ''));
  }
}

function paintGuide() {
  const box = $('#info-guide');
  if (!box) return;
  box.innerHTML = '';
  const guide = state.meta?.guide || [];
  if (!guide.length) {
    box.appendChild(el('div', { class: 'empty' }, 'The manual is unavailable.'));
    return;
  }

  // A contents strip, so a long manual stays navigable.
  box.appendChild(el('div', { class: 'card g-toc' },
    el('h3', {}, 'Contents'),
    el('div', { class: 'row' },
      ...guide.map(sec => el('button', {
        class: 'btn sm', onclick: () => {
          const t = $('#g-' + sec.id);
          if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, sec.title)))));

  guide.forEach(sec => {
    const card = el('div', { class: 'card g-sec', id: 'g-' + sec.id },
      el('h3', {}, sec.title),
      sec.blurb ? el('p', { class: 'hint' }, sec.blurb) : null);
    (sec.blocks || []).forEach(b => card.appendChild(guideBlock(b)));
    box.appendChild(card);
  });

  box.appendChild(el('div', { class: 'card' },
    el('h3', {}, 'Version'),
    el('dl', { class: 'kv' },
      el('dt', {}, 'teakit'), el('dd', {}, state.meta.version || '—'),
      el('dt', {}, 'correlations'),
      el('dd', {}, `${state.meta.equipment?.length || 0} fits, ` +
                   `${state.meta.basis_year} basis`),
      el('dt', {}, 'source'), el('dd', {}, state.meta.source || '—'),
      el('dt', {}, 'CEPCI years'),
      el('dd', {}, state.meta.cepci_years?.length
        ? `${state.meta.cepci_years[0]}–` +
          `${state.meta.cepci_years[state.meta.cepci_years.length - 1]}`
        : '—'))));

  /* Strings come from teakit.CITATION through api.meta; this only lays them
     out. target=_blank so the native window hands links to the system
     browser instead of navigating away from the application. */
  const cite = state.meta.citation || {};
  const link = (url, text) => el('a',
    { href: url, target: '_blank', rel: 'noopener' }, text || url);
  const ref = c => c && el('p', { class: 'g-p' },
    c.journal
      ? `${c.authors}. ${c.title}. ${c.journal}, ${c.year}. `
      : `${c.authors}. ${c.title}, version ${c.version}, ${c.year}. `,
    link(c.url, c.doi ? 'doi:' + c.doi : c.url));

  box.appendChild(el('div', { class: 'card' },
    el('h3', {}, 'Credits and citation'),
    el('dl', { class: 'kv' },
      el('dt', {}, 'author'), el('dd', {}, state.meta.author || '—'),
      el('dt', {}, 'licence'),
      el('dd', {}, `${state.meta.license || '—'}` +
                   (state.meta.license_note ? ' — ' + state.meta.license_note
                                            : '')),
      el('dt', {}, 'source'),
      el('dd', {}, state.meta.url ? link(state.meta.url) : '—')),
    el('p', { class: 'hint' },
      'If an estimate made here appears in published work, cite the study ' +
      'teakit was written for, the toolkit itself, and the DOE/NETL and NREL ' +
      'sources the method comes from, which are named in the sections above.'),
    ref(cite.paper),
    ref(cite.software)));
}

/* Every option in the interface, with the sentence the tooltip shows. This is
   the page to search when a dropdown is the thing you do not understand. */
const OPTION_FIELD_TITLES = {
  method: 'Costing method (01 Project)',
  basis: 'Finance basis (06 Finance)',
  capital_basis: 'Capital escalation basis (03 Capital)',
  installation_method: 'Installation method (03 Capital)',
  loh_service: 'Service, for the distributive factors (03 Capital)',
  loh_setting: 'Setting-labour class (03 Capital)',
  lang_type: 'Lang plant type (03 Capital)',
  convention: 'Factored fixed-cost convention (04 Operating cost)',
  labor_mode: 'Labour model (04 Operating cost)',
  allocation: 'Cost allocation (05 Products)',
  depreciation_years: 'MACRS recovery period (06 Finance)',
  equipment_mode: 'How an equipment item is priced (02 Equipment)',
  equipment_param: 'Equipment parameters (02 Equipment)',
  cost_index: 'Cost index (01 Project)',
  installation: 'Installation (03 Capital)',
  land: 'Land (03 Capital)',
  product_basis: 'How product output is entered (05 Products)',
  sensitivity_kind: 'Sensitivity study (09 Sensitivity)',
  chart_source: 'Chart series (08 Charts)',
  chart_kind: 'Chart type (08 Charts)',
  export: 'Exports',
};

function paintOptionsRef() {
  const box = $('#info-options');
  if (!box) return;
  box.innerHTML = '';
  const help = state.meta?.option_help || {};

  const filter = el('input', {
    type: 'search', class: 'txt', placeholder: 'Filter — contingency, TASC, MACRS…',
    style: 'max-width:340px;padding:7px 9px;border:1px solid var(--rule);' +
           'border-radius:3px;background:var(--sheet)',
    oninput: e => paint(e.target.value.trim().toLowerCase())
  });
  box.appendChild(el('div', { class: 'card' },
    el('h3', {}, 'Search the options'),
    el('p', { class: 'hint' },
      'Every choice the interface offers, and what choosing it means. The same ' +
      'sentence appears as a tooltip on the option itself and under the control ' +
      'once it is selected.'),
    filter));

  const out = el('div');
  box.appendChild(out);

  function paint(q) {
    out.innerHTML = '';
    let shown = 0;
    Object.keys(help).forEach(field => {
      const entries = Object.entries(help[field] || {}).filter(([k, v]) =>
        !q || (k + ' ' + v).toLowerCase().includes(q));
      if (!entries.length) return;
      shown += entries.length;
      const t = el('table', { class: 't' });
      t.appendChild(el('thead', {}, el('tr', {},
        el('th', { style: 'width:22%' }, 'Option'),
        el('th', {}, 'What it means'))));
      t.appendChild(el('tbody', {},
        ...entries.map(([k, v]) => el('tr', {},
          el('td', {}, el('code', {}, k)),
          el('td', {}, v)))));
      out.appendChild(el('div', { class: 'card' },
        el('h3', {}, OPTION_FIELD_TITLES[field] || field),
        el('div', { class: 'tbl-wrap' }, t)));
    });
    if (!shown) {
      out.appendChild(el('div', { class: 'empty' },
        'Nothing matches that. Try a shorter word.'));
    }
  }
  paint('');
}

/* The equations the last run actually used, with its own numbers in them. */
function paintMethodExplain() {
  const box = $('#info-method');
  if (!box) return;
  box.innerHTML = '';
  const secs = state.explanation || [];
  if (!secs.length) {
    box.appendChild(el('div', { class: 'empty' },
      'Run the estimate and the equations it used will appear here, with your ' +
      'numbers substituted.'));
    return;
  }

  box.appendChild(el('div', { class: 'card' },
    el('h3', {}, 'How this estimate was calculated'),
    el('p', { class: 'hint' },
      'Only the methods you selected are set out in full; the alternatives are ' +
      'named so it is clear a choice was made. The same appendix goes to the ' +
      'end of the HTML and Markdown reports, and onto the Method sheet of the ' +
      'Excel workbook.'),
    el('div', { class: 'row' },
      el('button', { class: 'btn sm', onclick: () => doExport('xlsx') },
        'Excel workbook'),
      el('button', { class: 'btn sm', onclick: () => doExport('html') },
        'HTML report'))));

  secs.forEach((sec, i) => {
    const card = el('div', { class: 'card m-sec' },
      el('h3', {}, `${i + 1}. ${sec.title}`),
      el('p', { class: 'hint' }, sec.summary));
    if (sec.source) {
      card.appendChild(el('div', { class: 'm-src' }, 'source: ' + sec.source));
    }
    (sec.equations || []).forEach(eq => {
      card.appendChild(el('div', { class: 'g-eq' },
        el('span', { class: 'g-eq-n' }, eq.label),
        el('code', {}, eq.expr)));
    });
    if ((sec.symbols || []).length) {
      const t = el('table', { class: 't' });
      t.appendChild(el('thead', {}, el('tr', {},
        el('th', { style: 'width:16%' }, 'Symbol'),
        el('th', {}, 'Meaning'),
        el('th', { style: 'width:26%' }, 'This run'))));
      t.appendChild(el('tbody', {}, ...sec.symbols.map(x => el('tr', {},
        el('td', {}, el('code', {}, x.sym)),
        el('td', {}, x.meaning),
        el('td', {}, el('b', {}, x.value))))));
      card.appendChild(el('div', { class: 'tbl-wrap' }, t));
    }
    if ((sec.steps || []).length) {
      const t = el('table', { class: 't' });
      t.appendChild(el('tbody', {}, ...sec.steps.map(x => {
        const strong = /^[=]/.test(x.label.trim()) || x.label === x.label.toUpperCase();
        return el('tr', { class: strong ? 'sub' : '' },
          el('td', {}, x.label),
          el('td', { class: 'n' }, x.detail));
      })));
      card.appendChild(el('div', { class: 'tbl-wrap m-steps' }, t));
    }
    (sec.notes || []).forEach(nt =>
      card.appendChild(el('div', { class: 'msg note' }, String(nt))));
    box.appendChild(card);
  });
}

function showInfoTab(kind) {
  state.infoTab = kind;
  $$('#info-tabs button').forEach(b =>
    b.setAttribute('aria-selected', b.dataset.info === kind ? 'true' : 'false'));
  ['guide', 'options', 'method'].forEach(k => {
    const n = $('#info-' + k);
    if (n) n.style.display = k === kind ? '' : 'none';
  });
  if (kind === 'guide' && !$('#info-guide').children.length) paintGuide();
  if (kind === 'options' && !$('#info-options').children.length) paintOptionsRef();
  if (kind === 'method') paintMethodExplain();
}

function showPanel(name) {
  $$('.panel').forEach(p => p.classList.toggle('on', p.id === 'p-' + name));
  $$('.step').forEach(b => b.setAttribute('aria-current',
    b.dataset.panel === name ? 'true' : 'false'));
  if (name === 'sensitivity' && !allParams.length) refreshParams();
  // The equipment panel and the Operating cost panel edit the same utility
  // objects. Neither repaints the other on a keystroke — that would take the
  // caret away — so the panel being opened is refreshed here instead, which
  // is the moment it becomes visible and the cheapest place to be sure it is
  // showing the current numbers.
  if (name === 'equipment') paintEquipment();
  if (name === 'operating') { paintStreams(); paintEquipmentUtilities(); }
  if (name === 'info') showInfoTab(state.infoTab);
  $('#main').scrollTo?.({ top: 0 });
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function fillSelect(sel, values, labelFn) {
  sel.innerHTML = '';
  values.forEach(v => sel.appendChild(el('option', { value: v },
    labelFn ? labelFn(v) : v)));
}

function buildStaticOptions() {
  const m = state.meta;
  /* The list runs to 2050, well past the published index, because a plant is
     costed years before it is built. A year with no index says so on the
     option rather than failing only when the estimate is run. */
  fillSelect($('#f-year'), m.cepci_years.slice().reverse(),
             y => (m.cepci || {})[String(y)] != null
               ? String(y) : `${y} — index needed`);
  fillSelect($('#f-cur'), Object.keys(m.currencies),
             c => `${c} — ${m.currencies[c]}`);
  // Changing the currency re-runs the estimate; it is a conversion, not a label.
  // Typing in either operating-time box has to move the derived line under
  // them. paintFields() would do it, but it also rewrites every input on the
  // page and would take the caret out of the one being typed in.
  FIELD_HOOKS.optime = () => {
    paintOperatingTime(); syncAllCostCells(); paintProducts();
  };
  FIELD_HOOKS.currency = () => applyCurrency(state.project.currency);
  // The dollar year decides which index rows matter and what a direct price's
  // basis year defaults to, so both views follow it.
  FIELD_HOOKS.year = () => { paintCepci(); paintYearNote(); paintEquipment(); };
  FIELD_HOOKS.install = () => { paintConditionalFields(); paintInstallNote(); };
  /* Land is one amount reached two ways. Whichever control was typed in wins,
     and the other is cleared rather than left on screen contradicting it. */
  FIELD_HOOKS.landcalc = () => {
    const c = state.project.capital;
    const acres = Number(c.land_area_acres) || 0;
    if (acres > 0) {
      c.land_cost = acres * (Number(c.land_cost_per_acre) || 0);
      $('#f-land').value = c.land_cost;
    }
    paintLandNote();
  };
  FIELD_HOOKS.land = () => {
    const c = state.project.capital;
    if (Number(c.land_area_acres) > 0) {
      c.land_area_acres = 0;
      $('#f-land-acres').value = '';
    }
    paintLandNote();
  };
  // A hand-typed rate is a project decision — record it as such, and let the
  // stale "superseded" marker prompt the re-run rather than firing one per
  // keystroke.
  FIELD_HOOKS.rate = () => {
    const p = state.project;
    if (p.currency === 'USD') return;
    const r = p.exchange_rate;
    if (r === null || r === undefined || !(r > 0)) {
      // Refuse silently-wrong output: a blank or zero rate would otherwise
      // produce USD figures wearing a foreign label.
      $('#rate-note').textContent =
        'A positive rate is required to report in ' + p.currency +
        '. Type one, or press Update.';
      $('#rate-note').classList.add('warn');
      return;
    }
    p.exchange_rate_source = 'manual, set for this project';
    paintRateNote();
  };
  fillSelect($('#f-loc'), m.locations.map(l => l.name));
  /* The distributive-factor keys are identifiers, not labels:
     "gas_gt400F_gt150psig" is precise and unreadable. serviceLabel spells the
     comparisons and the units out so the dropdown reads as engineering
     English rather than as a database column. */
  fillSelect($('#f-service'), m.loh_services, serviceLabel);
  fillSelect($('#f-setting'), m.loh_settings, sentenceLabel);
  fillSelect($('#f-lang'), m.lang_types, sentenceLabel);
  fillSelect($('#f-conv'), Object.keys(m.fixed_conventions));
  fillSelect($('#f-metric'), m.metrics, metricLabel);

  const band = $('#f-proc-band');
  band.innerHTML =
    '<option value="">Set from an AACE 16R-90 maturity band…</option>';
  Object.entries(m.process_contingency_bands).forEach(([k, [lo, hi]]) =>
    band.appendChild(el('option', { value: (lo + hi) / 2 },
      `${k} — ${(lo * 100).toFixed(0)}–${(hi * 100).toFixed(0)}%`)));
  band.onchange = e => {
    if (!e.target.value) return;
    state.project.capital.process_contingency_frac = parseFloat(e.target.value);
    touch(); paintFields(); e.target.value = '';
  };

  const tp = $('#f-tax-preset');
  tp.innerHTML = '<option value="">Set from a published tax rate…</option>';
  Object.entries(m.tax_presets).forEach(([k, v]) =>
    tp.appendChild(el('option', { value: v.rate }, `${k} — ${(v.rate * 100).toFixed(2)}%`)));
  tp.onchange = e => {
    if (!e.target.value) return;
    state.project.finance.tax_rate = parseFloat(e.target.value);
    touch(); paintFields(); e.target.value = '';
  };

  const fp = $('#f-preset');
  fp.innerHTML = '<option value="">Choose a published basis…</option>';
  Object.keys(m.finance_presets).forEach(k =>
    fp.appendChild(el('option', { value: k }, k)));
  fp.onchange = e => {
    const k = e.target.value;
    if (!k) return;
    const preset = m.finance_presets[k];
    Object.entries(preset).forEach(([kk, vv]) => {
      if (kk === 'source') return;
      if (kk === 'basis') { state.project.capital.basis = vv; state.project.finance.basis = vv; }
      else if (kk in state.project.finance) state.project.finance[kk] = vv;
    });
    state.project.finance.preset = k;
    $('#preset-note').textContent = preset.source || '';
    touch(); paintFields();
    toast('Loaded ' + k);
  };

  const op = $('#f-preset-op');
  op.innerHTML = '<option value="">Choose an operating-time preset…</option>';
  Object.entries(m.operating_presets).forEach(([k, v]) =>
    op.appendChild(el('option', {
      value: k,
      // The percentage in a preset's name is the stream factor — the hours as
      // a share of the calendar year — and saying so on the option is the
      // cheapest place to stop it being read as a capacity factor.
      title: `${fmt(v.operating_hours, 0)} h/yr — ` +
             `${(v.operating_hours / 8760 * 100).toFixed(1)}% of the calendar ` +
             `year.\n${v.source || ''}\n\nSets the hours only. Your capacity ` +
             `factor is left as it is.`
    }, k)));
  op.onchange = e => {
    const k = e.target.value;
    e.target.value = '';
    const v = m.operating_presets[k];
    if (!v) return;
    const opx = state.project.opex;
    // A preset is about operating *time*. It used to assign its own
    // capacity_factor as well — every one of them carries 1.00 — which
    // silently threw away a derate the user had set and changed the estimate
    // without saying so. The hours are what it is for; the capacity factor is
    // the user's and is left alone.
    opx.operating_hours = v.operating_hours;
    state.opPreset = { name: k, source: v.source || '' };
    touch(); paintFields();
    toast(`${k} — operating hours set to ${fmt(v.operating_hours, 0)}. ` +
          `Capacity factor left at ${pct(opx.capacity_factor ?? 1)}.`, 4600);
  };

  const uq = $('#ut-quick');
  m.utilities.forEach(u => uq.appendChild(el('option', { value: u.name },
    `${sentenceLabel(u.name)} — ${fmt(u.price)} $/${u.unit}`)));
  uq.onchange = e => {
    const u = m.utilities.find(x => x.name === e.target.value);
    if (!u) return;
    state.project.opex.utilities.push({
      name: u.name, rate: 0, unit: u.unit, price: u.price, category: u.category,
      basis: 'hour', scales_with_rate: true, source: u.source, note: ''
    });
    touch(); paintStreams(); e.target.value = '';
  };

  const sq = $('#staff-quick');
  m.labor_roles.forEach(r => sq.appendChild(el('option', { value: r.role },
    `${sentenceLabel(r.role)} — ${fmt(r.salary)} $/yr`)));
  sq.onchange = e => {
    const r = m.labor_roles.find(x => x.role === e.target.value);
    if (!r) return;
    (state.project.opex.labor.staff ||= []).push({
      role: r.role, count: 1, annual_salary: r.salary,
      shift_position: r.shift, note: '' });
    touch(); paintStaff(); e.target.value = '';
  };

  /* Every dropdown gets its explanations from the library: a native tooltip on
     each <option>, and the selected option's sentence printed underneath. The
     mapping is control id -> OPTION_HELP field. */
  Object.entries({
    '#f-method': 'method',
    '#f-basis': 'basis',
    '#f-cbasis': 'capital_basis',
    '#f-inst': 'installation_method',
    '#f-service': 'loh_service',
    '#f-setting': 'loh_setting',
    '#f-lang': 'lang_type',
    '#f-conv': 'convention',
    '#f-alloc': 'allocation',
    '#f-dep': 'depreciation_years',
    '#f-cc-src': 'chart_source',
    '#f-cc-kind': 'chart_kind',
  }).forEach(([sel, field]) => describeSelect($(sel), field));

  const tdl = $('#equipment-types');
  if (tdl) {
    tdl.innerHTML = '';
    (m.equipment_types || []).forEach(t => tdl.appendChild(
      el('option', { value: t.type },
         `n ${t.exponent.toFixed(3)} — ${t.basis}`)));
  }

  const tReset = $('#inst-type-reset');
  if (tReset) tReset.onclick = () => {
    state.project.capital.type_installation_factors = {};
    touch(); paintInstallTypes(); paintInstallNote();
    toast('Installation factors back to the published values');
  };

  const cadd = $('#cepci-add');
  if (cadd) cadd.onchange = e => {
    const y = e.target.value;
    e.target.value = '';
    if (!y) return;
    // Seed with the published value where there is one, so the row appears
    // showing what it would use rather than empty and apparently broken.
    const pub = cepciPublished(y);
    cepciOverrides()[cepciKey(y)] = pub != null ? pub : '';
    touch(); paintCepci();
  };
  const creset = $('#cepci-reset');
  if (creset) creset.onclick = () => {
    state.project.cepci_overrides = {};
    touch(); paintCepci(); paintYearNote();
    toast('Cost index back to the published series');
  };

  const dr = $('#demo-row');
  Object.entries(m.demos).forEach(([k, desc]) =>
    dr.appendChild(el('button', { class: 'btn', title: desc,
      onclick: () => loadDemo(k) }, desc)));
}

async function loadDemo(kind) {
  const j = await api('demo', { kind });
  state.project = j.project;
  state.result = null; state.charts = {}; state.rev = 0; state.stale = true;
  state.tornadoParams = []; state.explanation = []; state.opPreset = null;
  eqOpen.clear();
  paintAll();
  await run();
  showPanel('results');
}

function paintAll() {
  paintFields();
  paintEquipment();
  paintStreams();
  paintEquipmentUtilities();
  paintStaff();
  paintProducts();
  paintBlock();
  paintResults();
  paintCharts();
  paintMethodExplain();
}

function wire() {
  $$('.step').forEach(b => b.onclick = () => showPanel(b.dataset.panel));

  $$('#info-tabs button').forEach(b =>
    b.onclick = () => showInfoTab(b.dataset.info));

  const guide = $('#btn-param-guide');
  if (guide) guide.onclick = () => openParamGuide();

  const expand = $('#btn-eq-expand');
  if (expand) expand.onclick = () => {
    const rows = state.project.equipment;
    if (eqOpen.size >= rows.length && rows.length) eqOpen.clear();
    else rows.forEach(r => eqOpen.add(r.tag));
    paintEquipment();
  };

  // The export buttons say what each file is for, from the same source the
  // Info section reads.
  $$('[data-export]').forEach(b => {
    const h = optHelp('export', b.dataset.export);
    if (h) b.title = h.charAt(0).toUpperCase() + h.slice(1);
  });
  $$('[data-run]').forEach(b => b.onclick = run);
  $$('[data-export]').forEach(b => b.onclick = () => doExport(b.dataset.export));
  $$('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());

  /* The step rail, collapsed to its numbers.

     On a laptop the rail is 15% of the window and the equipment table wants
     every pixel of the rest. Collapsed it keeps the numbers and the current
     step, which is enough to navigate by, and the names come back as
     tooltips. The choice is remembered, like the theme, because a reader who
     wants the room wants it every session. */
  const setRail = (collapsed, announce) => {
    document.body.classList.toggle('rail-min', collapsed);
    const b = $('#btn-rail');
    b.textContent = collapsed ? '\u00bb' : '\u00ab';
    b.title = collapsed ? 'Show the step names again'
                        : 'Collapse the step list to its numbers';
    b.setAttribute('aria-label', b.title);
    // Collapsed, the name is gone from the screen, so it has to be on the
    // control — otherwise "04" is all a reader has to go on.
    $$('.step').forEach(st => {
      st.title = collapsed ? (st.querySelector('.t')?.textContent || '') : '';
    });
    try { localStorage.setItem('teakit-rail', collapsed ? 'min' : 'full'); }
    catch (e) {}
    if (announce) paintCharts();   // the figure grid reflows into the space
  };
  $('#btn-rail').onclick = () =>
    setRail(!document.body.classList.contains('rail-min'), true);
  try { if (localStorage.getItem('teakit-rail') === 'min') setRail(true); }
  catch (e) {}

  $('#theme').onclick = () => {
    const dark = document.documentElement.dataset.theme === 'dark';
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    $('#theme').textContent = dark ? 'Dark' : 'Light';
    try { localStorage.setItem('teakit-theme', dark ? 'light' : 'dark'); } catch (e) {}
    paintCharts();
    if (state.result) paintBlock();
    // _redraw keeps the tools and the reader's width choice; innerHTML alone
    // used to throw both away.
    $$('.fig').forEach(f => { if (f._redraw) f._redraw(); });
  };

  $('#btn-new').onclick = async () => {
    const j = await api('blank');
    state.project = j.project; state.result = null; state.charts = {};
    state.rev = 0; state.stale = true; state.tornadoParams = [];
    state.opPreset = null;
    paintAll(); showPanel('project');
    toast('New project');
  };

  $('#btn-rate').onclick = async () => {
    const code = state.project.currency;
    if (code === 'USD') return toast('USD is the base currency — nothing to fetch.');
    await applyCurrency(code, { live: true });
  };

  $('#btn-add-cat').onclick = openCatalogue;
  $('#btn-add-custom').onclick = () => {
    state.project.equipment.push({
      tag: nextTag('X'), kind: '', size: 1, quantity: 1, spare: 0,
      material: 'carbon steel', mode: 'custom', base_cost: 100000, base_size: 1,
      exponent: 0.6, base_year: state.project.dollar_year, size_unit: '',
      direct_cost: null, cost_is_installed: false, section: 'Process',
      name: '', note: 'user correlation' });
    touch(); paintEquipment();
  };
  $('#btn-add-direct').onclick = () => {
    state.project.equipment.push({
      tag: nextTag('Q'), kind: '', size: 0, quantity: 1, spare: 0,
      material: 'carbon steel', mode: 'direct', base_cost: null, base_size: null,
      exponent: null, base_year: state.project.dollar_year, size_unit: '',
      direct_cost: 1000000, cost_is_installed: true, section: 'Process',
      name: '', note: 'vendor quote' });
    touch(); paintEquipment();
  };

  $$('[data-add-stream]').forEach(b => b.onclick = () => {
    const key = b.dataset.addStream;
    const cat = { raw_materials: 'raw_material', utilities: 'utility', waste: 'waste' }[key];
    (state.project.opex[key] ||= []).push({
      name: 'new line', rate: 0, unit: 'tonne', price: 0, category: cat,
      basis: 'hour', scales_with_rate: true, source: '', note: '' });
    touch(); paintStreams();
  });

  $('#btn-add-product').onclick = () => {
    const list = state.project.products.products;
    list.push({
      name: list.length ? 'byproduct' : 'product', annual_production: 0,
      unit: 'tonne', price: list.length ? 0 : null,
      role: list.length ? 'byproduct' : 'primary',
      energy_content: 0, mass_per_unit: 1, scales_with_rate: true,
      basis: 'year', note: '' });
    touch(); paintProducts();
  };

  $$('#labor-tabs button').forEach(b => b.onclick = () => {
    state.laborMode = b.dataset.mode;
    $$('#labor-tabs button').forEach(x =>
      x.setAttribute('aria-selected', String(x === b)));
    $('#labor-rule').style.display = b.dataset.mode === 'rule' ? '' : 'none';
    $('#labor-plan').style.display = b.dataset.mode === 'plan' ? '' : 'none';
    if (b.dataset.mode === 'rule') { state.project.opex.labor.staff = []; }
    else { state.project.opex.labor.operators_per_shift = 0; }
    touch(); paintStaff(); paintFields();
  });

  $('#btn-nrel-staff').onclick = () => {
    const roles = state.meta.labor_roles;
    state.project.opex.labor.staff = Object.entries(state.meta.nrel_staffing)
      .map(([role, n]) => {
        const r = roles.find(x => x.role === role) || { salary: 70000, shift: false };
        return { role, count: n, annual_salary: r.salary,
                 shift_position: false, note: 'NREL/TP-5100-47764 Table 22' };
      });
    state.project.opex.labor.operators_per_shift = 0;
    touch(); paintStaff();
    toast('Loaded the NREL staffing template — counts are already fully manned, ' +
          'so shift coverage is not applied again');
  };

  ['#f-ud-util', '#f-ud-group', '#f-ud-measure', '#f-ud-kind'].forEach(id => {
    const n = $(id);
    if (n) n.onchange = () => {
      if (id === '#f-ud-util') state.udUtility = n.value;
      paintUtilityDistribution();
    };
  });

  $('#btn-cc').onclick = async () => {
    try {
      const j = await api('custom_chart', {
        project: state.project, source: $('#f-cc-src').value,
        kind: $('#f-cc-kind').value,
        title: $('#f-cc-src').selectedOptions[0].textContent });
      const out = $('#cc-out'); out.innerHTML = '';
      out.appendChild(figure(j.chart, 880, 400));
    } catch (e) { toast(e.message, 4500); }
  };

  $$('#sens-tabs button').forEach(b => b.onclick = () => {
    state.sensKind = b.dataset.kind;
    $$('#sens-tabs button').forEach(x =>
      x.setAttribute('aria-selected', String(x === b)));
    $$('[data-sens]').forEach(n =>
      n.style.display = n.dataset.sens.split(' ').includes(state.sensKind) ? '' : 'none');
    $('#sens-hint').textContent = {
      tornado: 'One parameter at a time between a low and a high case, sorted by swing. Bars assume the inputs are independent.',
      sweep: 'One parameter across a range. Shows the curvature a two-point tornado hides.',
      monte_carlo: 'Every listed input sampled at once. Report P10/P50/P90 and say where the ranges came from.',
      breakeven: 'Solves for the parameter value that puts the metric on a target. Needs the metric to be monotone in that parameter.'
    }[state.sensKind];
  });
  $('#btn-sens').onclick = runSensitivity;
  $('#tp-clear').onclick = () => { state.tornadoParams = []; paintTornadoParams(); };
  $('#tp-add').onchange = e => {
    const p = allParams.find(x => x.path === e.target.value);
    if (p) {
      state.tornadoParams.push({ path: p.path, label: p.label,
                                 unit: p.unit || '', mode: 'percent',
                                 low: null, high: null });
      paintTornadoParams();
    }
    e.target.value = '';
  };

  const destBtn = $('#dest-path');
  if (destBtn) destBtn.onclick = openFiles;
  const destOpen = $('#btn-dest-open');
  if (destOpen) destOpen.onclick = () => api('workspace_open', {})
    .catch(e => toast(e.message, 5000));
  const filesBtn = $('#btn-files');
  if (filesBtn) filesBtn.onclick = openFiles;

  $('#btn-load').onclick = () => $('#file-in').click();
  $('#file-in').onchange = async e => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const obj = JSON.parse(await f.text());
      state.project = obj.project || obj;
      state.result = null; state.charts = {}; state.rev = 0; state.stale = true;
      state.tornadoParams = []; state.opPreset = null;
      paintAll(); showPanel('project');
      toast('Opened ' + f.name);
    } catch (err) { toast('That file is not a teakit project: ' + err.message, 5000); }
    e.target.value = '';
  };

  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
  });
  window.addEventListener('beforeunload', e => {
    if (state.project && state.project.equipment.length) {
      e.preventDefault(); e.returnValue = '';
    }
  });
}

(async function boot() {
  try {
    const saved = localStorage.getItem('teakit-theme');
    if (saved) { document.documentElement.dataset.theme = saved;
      $('#theme').textContent = saved === 'dark' ? 'Light' : 'Dark'; }
  } catch (e) {}

  try {
    const m = await api('meta');
    state.meta = m;
    const b = await api('blank');
    state.project = b.project;
  } catch (e) {
    document.body.innerHTML =
      `<div style="padding:40px;font-family:system-ui">
        <h1>teakit could not start</h1>
        <p>${esc(e.message)}</p>
        <p>Restart with <code>teakit app</code>.</p></div>`;
    return;
  }
  buildStaticOptions();
  bindFields();
  wire();
  paintAll();

  // Seed the rate table from what shipped with the build so the interface has
  // something immediately, then refresh in the background. Startup must never
  // block on a network that may not be there.
  rateTable = { rates: state.meta.exchange_rates || {},
                as_of: state.meta.exchange_rates_as_of, source: 'bundled table',
                live: false };
  paintRateNote();
  loadRates().then(() => paintRateNote()).catch(() => {});
  // Same reasoning as the rate table: the interface must come up whether or
  // not the folder resolves, so this is fired and not awaited.
  refreshWorkspace();
  $$('[data-sens]').forEach(n =>
    n.style.display = n.dataset.sens.split(' ').includes('tornado') ? '' : 'none');
  $('#sens-hint').textContent =
    'One parameter at a time between a low and a high case, sorted by swing. ' +
    'Bars assume the inputs are independent.';
  refreshParams();
})();
