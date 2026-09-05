/* Tape Pulse — market theme tracker frontend */
'use strict';

const DATA = 'data/';
const cache = {};
let currentView = 'themes';
let themeTab = 'industry';
let sortKey = 'd1';
// hide 1-2 stock sub-industries by default: a single name's move is not a theme
let minNames = (() => { try { return localStorage.getItem('tp_minNames') !== '0'; } catch (e) { return true; } })();
let sortDir = -1;
let scannerDir = 'all';
let earnWeekOffset = 0;
let modalChart = null;
let cotChart = null;

const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const main = $('#main');

const TF_COLS = [
  ['d1', 'Today'], ['w1', '1W'], ['m1', '1M'], ['m3', '3M'], ['m6', '6M'], ['ytd', 'YTD'],
];

async function getJSON(name) {
  if (cache[name]) return cache[name];
  const r = await fetch(DATA + name + '?v=' + Date.now().toString().slice(0, -5));
  if (!r.ok) throw new Error(name + ' ' + r.status);
  cache[name] = await r.json();
  return cache[name];
}

function fmtPct(v, signed = true) {
  if (v === null || v === undefined || Number.isNaN(v)) return '<span class="dim">—</span>';
  const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : 'dim';
  const sign = signed && v > 0 ? '+' : '';
  return `<span class="${cls}">${sign}${v.toFixed(2)}%</span>`;
}
function fmtNum(v) {
  if (v === null || v === undefined) return '—';
  return v.toLocaleString('en-US');
}
function fmtCap(v) {
  if (!v) return '—';
  if (v >= 1e12) return (v / 1e12).toFixed(2) + 'T';
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(0) + 'M';
  return String(v);
}
function fmtVol(v) {
  if (!v) return '—';
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
  return String(v);
}
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------------- boot ---------------- */
(async function boot() {
  initTheme();
  initNav();
  initSearch();
  try {
    const [meta, tape] = await Promise.all([getJSON('meta.json'), getJSON('tape.json')]);
    // Convert "YYYY-MM-DD HH:MM UTC" -> Hong Kong local time (UTC+8, no DST).
    const hkUpdated = (() => {
      const m = /^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) UTC$/.exec(meta.updated || '');
      if (!m) return meta.updated;
      const d = new Date(`${m[1]}T${m[2]}:${m[3]}:00Z`);
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Hong_Kong',
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
      }).formatToParts(d).reduce((o, p) => (o[p.type] = p.value, o), {});
      return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} HKT`;
    })();
    $('#updated').textContent = `updated ${hkUpdated} · bar ${meta.last_bar}`;
    if (meta.stale) {
      $('#updated').innerHTML += ` <span class="stale-warn" title="Latest session (${meta.expected_bar}) not yet in the data — an update should land shortly.">⚠ data behind</span>`;
    }
    renderTape(tape);
  } catch (e) { /* first run before data exists */ }
  render();
})();

function initTheme() {
  const saved = window.__theme || 'dark';
  document.documentElement.dataset.theme = saved;
  $('#theme-toggle').onclick = () => {
    const cur = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = cur;
    window.__theme = cur;
  };
}

function initNav() {
  $$('#main-nav .nav-btn').forEach((b) => {
    b.onclick = () => {
      $$('#main-nav .nav-btn').forEach((x) => x.classList.remove('active'));
      b.classList.add('active');
      currentView = b.dataset.view;
      render();
    };
  });
}

function renderTape(tape) {
  const items = tape.rows.map((r) =>
    `<span class="tape-item"><b>${esc(r.t)}</b>${fmtPct(r.chg)}</span>`).join('');
  $('#tape').innerHTML = items + items;
}

async function render() {
  main.innerHTML = '<div class="loading">loading…</div>';
  try {
    if (currentView === 'themes') await renderThemes();
    else if (currentView === 'spotlight') await renderSpotlight();
    else if (currentView === 'breadth') await renderBreadth();
    else if (currentView === 'scanner') await renderScanner();
    else if (currentView === 'earnings') await renderEarnings();
    else if (currentView === 'cot') await renderCOT();
  } catch (e) {
    main.innerHTML = `<div class="empty">Data not available yet — the GitHub Action may still be running its first update.<br><span class="dim">${esc(e.message)}</span></div>`;
  }
}

/* ---------------- themes view ---------------- */
const THEME_TABS = [
  ['industry', 'Themes'], ['sector', 'Sectors'], ['sp', 'S&P ETFs'],
  ['eqwt', 'Equal Weight'], ['country', 'Country'], ['snapshot', 'Snapshots'],
];

async function renderThemes() {
  const [themes, spotlight] = await Promise.all([getJSON('themes.json'), getJSON('spotlight.json').catch(() => null)]);
  const etfs = await getJSON('etfs.json').catch(() => null);

  const pills = THEME_TABS.map(([k, label]) =>
    `<button class="pill ${themeTab === k ? 'active' : ''}" data-tab="${k}">${label}</button>`).join('');

  let gainers = '';
  if (spotlight && spotlight.gainers) {
    gainers = `<div class="strip"><span class="label">TOP GAINERS</span>` +
      spotlight.gainers.slice(0, 12).map((r) =>
        `<a data-ticker="${esc(r.t)}"><b>${esc(r.t)}</b> ${fmtPct(r.chg)}</a>`).join('') + '</div>';
  }

  main.innerHTML = `
    <div class="pills" id="theme-pills">${pills}</div>
    ${gainers}
    <div class="card">
      <div class="card-head"><h2 id="tbl-title"></h2>
        <span class="card-tools"><label class="toggle" id="min-names-wrap" title="Hide sub-industries with fewer than 3 constituents"><input type="checkbox" id="min-names"> 3+ names</label><span class="meta" id="tbl-meta"></span></span></div>
      <div class="tbl-wrap"><table id="main-tbl"></table></div>
    </div>
    <p class="note">Group returns are equal-weight averages of constituents (S&P 1500 universe, Yahoo Finance industry classification). Click a group to see its stocks; click a ticker for a full workup.</p>`;

  $$('#theme-pills .pill').forEach((p) => {
    p.onclick = () => { themeTab = p.dataset.tab; sortKey = 'd1'; sortDir = -1; renderThemes(); };
  });
  bindTickerLinks(main);
  drawThemesTable(themes, etfs);
}

function drawThemesTable(themes, etfs) {
  const isGroup = themeTab === 'industry' || themeTab === 'sector';
  let rows, title;
  const wrap = $('#min-names-wrap');
  if (wrap) {
    wrap.style.display = themeTab === 'industry' ? '' : 'none';
    const cb = $('#min-names');
    cb.checked = minNames;
    cb.onchange = () => {
      minNames = cb.checked;
      try { localStorage.setItem('tp_minNames', minNames ? '1' : '0'); } catch (e) { /* sandboxed */ }
      drawThemesTable(themes, etfs);
    };
  }
  if (isGroup) {
    rows = themes[themeTab].slice();
    if (themeTab === 'industry' && minNames) rows = rows.filter((r) => (r.n || 0) >= 3);
    title = themeTab === 'industry' ? `Sub-Industry Themes` : 'Yahoo Finance Sectors';
  } else {
    rows = (etfs ? etfs[themeTab] : []).slice();
    title = { sp: 'S&P Sector & Industry ETFs', eqwt: 'Equal-Weight ETFs', country: 'Country ETFs', snapshot: 'Macro Snapshot ETFs' }[themeTab];
  }
  rows.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
  });

  $('#tbl-title').textContent = title;
  const hidden = (themeTab === 'industry' && minNames) ? themes.industry.length - rows.length : 0;
  $('#tbl-meta').textContent = `${rows.length} ${isGroup ? 'groups' : 'funds'}${hidden ? ` · ${hidden} thin groups hidden` : ''}`;

  const head = `<thead><tr><th data-k="g">${isGroup ? 'Group' : 'Fund'}</th>` +
    TF_COLS.map(([k, label]) =>
      `<th data-k="${k}" class="${sortKey === k ? 'sorted' : ''}">${label}${sortKey === k ? (sortDir < 0 ? ' ↓' : ' ↑') : ''}</th>`).join('') +
    '</tr></thead>';

  const body = rows.map((r, i) => {
    const label = isGroup
      ? `${esc(r.g)}<span class="count">${r.n}</span>`
      : `<span class="tick-link" data-ticker="${esc(r.t)}">${esc(r.t)}</span><span class="secname">${esc(r.g)}</span>`;
    return `<tr data-idx="${i}" data-group="${isGroup ? esc(r.g) : ''}">` +
      `<td>${label}</td>` + TF_COLS.map(([k]) => `<td>${fmtPct(r[k])}</td>`).join('') + '</tr>';
  }).join('');

  const tbl = $('#main-tbl');
  tbl.innerHTML = head + `<tbody>${body}</tbody>`;

  $$('thead th', tbl).forEach((th) => {
    th.onclick = () => {
      const k = th.dataset.k;
      if (k === 'g') return;
      if (sortKey === k) sortDir *= -1; else { sortKey = k; sortDir = -1; }
      drawThemesTable(themes, etfs);
    };
  });

  if (isGroup) {
    $$('tbody tr', tbl).forEach((tr) => {
      tr.onclick = (ev) => {
        if (ev.target.dataset.ticker) return;
        toggleDrill(tr, themes);
      };
    });
  }
  bindTickerLinks(tbl);
}

function toggleDrill(tr, themes) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('drill-row')) { next.remove(); return; }
  $$('.drill-row').forEach((x) => x.remove());
  const group = tr.dataset.group;
  const members = (themeTab === 'industry' ? themes.cons : themes.sec_cons)[group] || [];
  const stocks = themes.stocks;
  const inner = members.slice(0, 60).map((t) => {
    const s = stocks[t];
    if (!s) return '';
    return `<tr><td><span class="tick-link" data-ticker="${esc(t)}">${esc(t)}</span><span class="secname">${esc(s.name)}</span></td>` +
      `<td>${s.px ?? '—'}</td><td>${fmtCap(s.mcap)}</td>` +
      TF_COLS.map(([k]) => `<td>${fmtPct(s[k])}</td>`).join('') + '</tr>';
  }).join('');
  const row = document.createElement('tr');
  row.className = 'drill-row';
  row.innerHTML = `<td colspan="7"><div class="drill-inner"><div class="tbl-wrap" style="max-height:340px"><table class="drill">
    <thead><tr><th>Ticker</th><th>Price</th><th>MCap</th>${TF_COLS.map(([, l]) => `<th>${l}</th>`).join('')}</tr></thead>
    <tbody>${inner}</tbody></table></div></div></td>`;
  tr.after(row);
  bindTickerLinks(row);
}

/* ---------------- spotlight ---------------- */
let _spotSide = 'highs'; // 'highs' | 'lows'
async function renderSpotlight() {
  const s = await getJSON('spotlight.json');
  const sum = s.summary || {
    universe: (s.highs.length + s.lows.length) || 1,
    highs_count: s.highs.length, lows_count: s.lows.length,
    highs_pct: 0, lows_pct: 0, lookback_days: 63,
  };
  const totalHL = sum.highs_count + sum.lows_count;
  // Share of the H/L pool that each side represents (matches Market Pulse's
  // green/red bar which fills based on the H vs L balance today).
  const hShare = totalHL ? (100 * sum.highs_count / totalHL) : 50;
  const lShare = totalHL ? 100 - hShare : 50;

  const chip = (r) => {
    const n = r.n ?? '';
    const chgStr = (r.chg == null || Number.isNaN(r.chg))
      ? '' : `${r.chg > 0 ? '+' : ''}${r.chg.toFixed(2)}%`;
    const tip = esc(`${r.name} · ${chgStr}`);
    return `<span class="hl-chip" data-ticker="${esc(r.t)}" title="${tip}">` +
      `<span class="hl-t">${esc(r.t)}</span>` +
      (n !== '' ? `<span class="hl-n">${n}</span>` : '') +
      `</span>`;
  };

  const groupCard = (g) => `
    <div class="hl-group">
      <div class="hl-group-head">
        <span class="hl-group-name">${esc(g.industry)}</span>
        <span class="hl-group-hits">${g.hits} hits · ${g.count} names</span>
      </div>
      <div class="hl-chips">${g.items.map(chip).join('')}</div>
    </div>`;

  const side = _spotSide;
  const groups = (side === 'highs' ? s.highs_grouped : s.lows_grouped) || [];
  const groupsHTML = groups.length
    ? groups.map(groupCard).join('')
    : '<div class="empty">none today</div>';

  const moverList = (rows) => rows.map((r) =>
    `<tr><td><span class="tick-link" data-ticker="${esc(r.t)}">${esc(r.t)}</span><span class="secname">${esc(r.name)}</span></td>` +
    `<td>${r.px ?? '—'}</td><td>${fmtPct(r.chg)}</td><td style="text-align:left" class="dim">${esc(r.ind)}</td></tr>`).join('');
  const moverBlock = (title, rows) => `
    <div class="card"><div class="card-head"><h2>${title}</h2></div>
    <div class="tbl-wrap" style="max-height:48vh"><table>
    <thead><tr><th>Ticker</th><th>Price</th><th>Chg</th><th style="text-align:left">Industry</th></tr></thead>
    <tbody>${rows.length ? rows : ''}</tbody></table>${rows.length ? '' : '<div class="empty">none today</div>'}</div></div>`;

  main.innerHTML = `
    <div class="card hl-summary-card">
      <div class="hl-summary">
        <div class="hl-summary-nums">
          <span class="pos">New Highs ${sum.highs_pct}%</span>
          <span class="dim">(${sum.highs_count})</span>
          <span class="neg" style="margin-left:18px">New Lows ${sum.lows_pct}%</span>
          <span class="dim">(${sum.lows_count})</span>
          <span class="dim" style="margin-left:18px;font-size:12px">of ${sum.universe} · past ${sum.lookback_days}d</span>
        </div>
        <div class="hl-bar">
          <div class="hl-bar-h" style="width:${hShare}%"></div>
          <div class="hl-bar-l" style="width:${lShare}%"></div>
        </div>
        <div class="hl-tabs">
          <button class="hl-tab ${side === 'highs' ? 'active' : ''}" data-side="highs">Highs (${sum.highs_count})</button>
          <button class="hl-tab ${side === 'lows' ? 'active' : ''}" data-side="lows">Lows (${sum.lows_count})</button>
        </div>
      </div>
    </div>
    <div class="card"><div class="card-head">
      <h2>${side === 'highs' ? 'New 52-Week Highs by Industry' : 'New 52-Week Lows by Industry'}</h2>
      <span class="meta">${groups.length} groups · number after ticker = days on list in past ${sum.lookback_days} sessions</span>
    </div>${groupsHTML}</div>
    <div class="grid-2" style="margin-top:16px">
      ${moverBlock('Top Gainers (>$10B)', moverList(s.gainers))}
      ${moverBlock('Top Losers (>$10B)', moverList(s.losers))}
    </div>`;

  main.querySelectorAll('.hl-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      _spotSide = btn.dataset.side;
      renderSpotlight();
    });
  });
  main.querySelectorAll('.hl-chip').forEach((el) => {
    el.addEventListener('click', () => openTicker(el.dataset.ticker));
    el.style.cursor = 'pointer';
  });
  bindTickerLinks(main);
}

/* ---------------- breadth ---------------- */
async function renderBreadth() {
  const b = await getJSON('breadth.json');
  const rows = b.rows.map((r) => {
    const heat = (v, hi, lo) => v >= hi ? 'heat h-strong' : v <= lo ? 'heat h-weak' : '';
    const ratioHeat = (v) => v >= 2 ? 'heat h-strong' : v <= 0.5 ? 'heat h-weak' : v < 1 ? 'heat h-warn' : '';
    return `<tr>
      <td>${r.date}</td>
      <td class="${r.adv > r.dec ? 'pos' : 'neg'}">${r.adv}/${r.dec}</td>
      <td class="${heat(r.up4, 300, 0)}">${r.up4}</td>
      <td class="${r.dn4 >= 300 ? 'heat h-weak' : ''}">${r.dn4}</td>
      <td class="${ratioHeat(r.r5)}">${r.r5 ?? '—'}</td>
      <td class="${ratioHeat(r.r10)}">${r.r10 ?? '—'}</td>
      <td>${r.up25q}</td><td>${r.dn25q}</td>
      <td>${r.up25m}</td><td>${r.dn25m}</td>
      <td>${r.up13}</td><td>${r.dn13}</td>
      <td class="${heat(r.nh, 100, 0)}">${r.nh}</td>
      <td class="${r.nl >= 100 ? 'heat h-weak' : ''}">${r.nl}</td>
      <td class="${heat(r.a20, 70, 30)}">${r.a20}</td>
      <td class="${heat(r.a50, 70, 30)}">${r.a50}</td>
      <td class="${heat(r.a200, 70, 30)}">${r.a200}</td>
    </tr>`;
  }).join('');
  main.innerHTML = `<div class="card">
    <div class="card-head"><h2>Market Breadth — S&P 1500 universe</h2><span class="meta">${b.universe_size} stocks · ${b.rows.length} sessions</span></div>
    <div class="tbl-wrap"><table>
      <thead><tr>
        <th style="text-align:left">Date</th><th>Adv/Dec</th>
        <th>+4% Day</th><th>-4% Day</th><th>5D Ratio</th><th>10D Ratio</th>
        <th>+25% Qtr</th><th>-25% Qtr</th><th>+25% Mo</th><th>-25% Mo</th>
        <th>+13%/34D</th><th>-13%/34D</th>
        <th>52W NH</th><th>52W NL</th>
        <th>%&gt;20MA</th><th>%&gt;50MA</th><th>%&gt;200MA</th>
      </tr></thead><tbody>${rows}</tbody></table></div></div>
    <p class="note">Computed from daily closes of the S&P 1500 universe. Ratio cells: green ≥ 2, amber &lt; 1, red ≤ 0.5. Percent-above-MA cells: green ≥ 70, red ≤ 30.</p>`;
}

/* ---------------- scanner ---------------- */
async function renderScanner() {
  const s = await getJSON('scanner.json');
  let rows = s.rows;
  if (scannerDir === 'up') rows = rows.filter((r) => r.gap > 0);
  if (scannerDir === 'down') rows = rows.filter((r) => r.gap < 0);
  const body = rows.map((r) =>
    `<tr><td><span class="tick-link" data-ticker="${esc(r.t)}">${esc(r.t)}</span><span class="secname">${esc(r.name)}</span></td>` +
    `<td>${r.px}</td><td>${fmtPct(r.gap)}</td><td>${fmtPct(r.chg)}</td>` +
    `<td>${fmtVol(r.vol)}</td><td>${r.rvol ?? '—'}x</td><td style="text-align:left" class="dim">${esc(r.ind)}</td></tr>`).join('');
  main.innerHTML = `
    <div class="pills">
      <button class="pill ${scannerDir === 'all' ? 'active' : ''}" data-d="all">All</button>
      <button class="pill ${scannerDir === 'up' ? 'active' : ''}" data-d="up">Gap Up</button>
      <button class="pill ${scannerDir === 'down' ? 'active' : ''}" data-d="down">Gap Down</button>
    </div>
    <div class="card"><div class="card-head"><h2>Gap Scanner</h2><span class="meta">${rows.length} names · price &gt; $5 · avg vol &gt; 300K</span></div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Ticker</th><th>Price</th><th>Gap %</th><th>Chg %</th><th>Volume</th><th>RVOL</th><th style="text-align:left">Industry</th></tr></thead>
      <tbody>${body}</tbody></table>${rows.length ? '' : '<div class="empty">no qualifying gaps</div>'}</div></div>
    <p class="note">Gap = last session open vs prior close. Data refreshes on the GitHub Actions schedule (delayed, not tick-level). RVOL = last volume ÷ 20-day average.</p>`;
  $$('.pills .pill', main).forEach((p) => { p.onclick = () => { scannerDir = p.dataset.d; renderScanner(); }; });
  bindTickerLinks(main);
}

/* ---------------- earnings ---------------- */
async function renderEarnings() {
  const e = await getJSON('earnings.json');
  const dates = Object.keys(e.days).sort();
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7) + earnWeekOffset * 7);
  const week = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    week.push(d.toISOString().slice(0, 10));
  }
  const fmtEps = (v) => v === null || v === undefined ? '—' : v.toFixed(2);
  const blocks = week.filter((d) => e.days[d]).map((d) => {
    const rows = e.days[d].map((r) =>
      `<tr><td><span class="tick-link" data-ticker="${esc(r.t)}">${esc(r.t)}</span><span class="secname">${esc(r.name)}</span></td>` +
      `<td>${fmtCap(r.mcap)}</td><td>${fmtEps(r.est)}</td><td>${fmtEps(r.act)}</td><td>${fmtPct(r.surp)}</td>` +
      `<td style="text-align:left" class="dim">${esc(r.ind)}</td></tr>`).join('');
    const dayName = new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
    return `<div class="day-block"><h3>${dayName}</h3>
      <div class="tbl-wrap" style="max-height:none"><table>
      <thead><tr><th>Ticker</th><th>MCap</th><th>EPS Est</th><th>EPS Act</th><th>Surprise</th><th style="text-align:left">Industry</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`;
  }).join('');
  const wkLabel = `${week[0]} → ${week[6]}`;
  main.innerHTML = `
    <div class="week-nav">
      <button class="pill" id="wk-prev">← Prev week</button>
      <span class="cur">${wkLabel}</span>
      <button class="pill" id="wk-next">Next week →</button>
      <button class="pill" id="wk-now">This week</button>
    </div>
    <div class="card">${blocks || '<div class="empty">no reports found this week</div>'}</div>
    <p class="note">Earnings dates &amp; EPS from Yahoo Finance. Dates can shift; ${dates.length} days cached (−3 weeks … +4 weeks).</p>`;
  $('#wk-prev').onclick = () => { earnWeekOffset--; renderEarnings(); };
  $('#wk-next').onclick = () => { earnWeekOffset++; renderEarnings(); };
  $('#wk-now').onclick = () => { earnWeekOffset = 0; renderEarnings(); };
  bindTickerLinks(main);
}

/* ---------------- COT ---------------- */
async function renderCOT() {
  const c = await getJSON('cot.json');
  const codes = Object.keys(c.markets);
  if (!codes.length) { main.innerHTML = '<div class="empty">no COT data yet</div>'; return; }
  const options = codes.map((k) => `<option value="${k}">${esc(c.markets[k].name)}</option>`).join('');
  main.innerHTML = `
    <div class="cot-controls">
      <label class="dim" style="font-size:12px">Market</label>
      <select id="cot-select">${options}</select>
    </div>
    <div class="card">
      <div class="card-head"><h2 id="cot-title"></h2><span class="meta">CFTC legacy futures-only · weekly</span></div>
      <div class="cot-chart-box"><canvas id="cot-canvas"></canvas></div>
      <div class="legend">
        <span><i style="background:#2ecc71"></i>Large speculators (net)</span>
        <span><i style="background:#ff5c5c"></i>Commercials (net)</span>
        <span><i style="background:#f0a832"></i>Small traders (net)</span>
        <span><i style="background:#5b8def"></i>Open interest</span>
      </div>
    </div>`;
  const draw = (code) => {
    const m = c.markets[code];
    $('#cot-title').textContent = m.name;
    const labels = m.rows.map((r) => r.date);
    if (cotChart) cotChart.destroy();
    cotChart = new Chart($('#cot-canvas'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Large spec net', data: m.rows.map((r) => r.spec), backgroundColor: '#2ecc71', stack: 'x' },
          { label: 'Commercial net', data: m.rows.map((r) => r.comm), backgroundColor: '#ff5c5c', stack: 'y' },
          { label: 'Small net', data: m.rows.map((r) => r.small), backgroundColor: '#f0a832', stack: 'z' },
          { label: 'Open interest', data: m.rows.map((r) => r.oi), type: 'line', yAxisID: 'y2', borderColor: '#5b8def', pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#626a7d', maxTicksLimit: 12, font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { color: '#626a7d', font: { size: 10 } }, grid: { color: 'rgba(120,130,150,0.08)' } },
          y2: { position: 'right', ticks: { color: '#5b8def', font: { size: 10 } }, grid: { display: false } },
        },
      },
    });
  };
  $('#cot-select').onchange = (e) => draw(e.target.value);
  draw(codes[0]);
}

/* ---------------- deep-dive modal ---------------- */
function bindTickerLinks(root) {
  $$('[data-ticker]', root).forEach((el) => {
    el.addEventListener('click', (ev) => { ev.stopPropagation(); openDeepDive(el.dataset.ticker); });
  });
}

async function openDeepDive(ticker) {
  const backdrop = $('#modal-backdrop');
  const modal = $('#modal');
  backdrop.classList.add('open');
  modal.innerHTML = '<div class="loading">loading…</div>';
  let d;
  try {
    d = await getJSON('tickers/' + ticker + '.json');
  } catch (e) {
    modal.innerHTML = `<div class="empty">${esc(ticker)} — not in the tracked universe.<br>
      <a class="tick-link" href="https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}" target="_blank" rel="noopener">Open on Yahoo Finance →</a></div>
      <button class="icon-btn modal-close" onclick="closeModal()">✕</button>`;
    return;
  }
  const f = d.f || {};
  const pct = (v) => v === undefined || v === null ? '—' : (v * 100).toFixed(1) + '%';
  const num = (v, nd = 2) => v === undefined || v === null ? '—' : Number(v).toFixed(nd);
  const stats = [
    ['Mkt Cap', fmtCap(d.mcap)], ['P/E', num(f.pe, 1)], ['Fwd P/E', num(f.fpe, 1)],
    ['P/S', num(f.ps, 1)], ['EPS (ttm)', num(f.eps)], ['Margin', pct(f.margin)],
    ['Rev Growth', pct(f.revg)], ['EPS Growth', pct(f.epsg)], ['Beta', num(f.beta, 2)],
    ['Div Yield', f.divy ? Number(f.divy).toFixed(2) + '%' : '—'], ['Short % Float', pct(f.short)], ['Inst Own', pct(f.inst)],
    ['52W High', d.hi52], ['52W Low', d.lo52], ['Avg Vol', fmtVol(d.avgvol)],
  ];
  const news = (d.news || []).map((n) =>
    `<a href="${esc(n.url)}" target="_blank" rel="noopener"><span class="src">${esc(n.src)} ${esc(n.pub)}</span>${esc(n.title)}</a>`).join('');
  modal.innerHTML = `
    <button class="icon-btn modal-close" onclick="closeModal()">✕</button>
    <div class="modal-head">
      <span class="tk">${esc(d.t)}</span><span class="nm">${esc(d.name)}</span>
      <span class="px">$${d.px}</span><span class="chg">${fmtPct(d.chg)}</span>
    </div>
    <div class="tags"><span>${esc(d.sector)}</span><span>${esc(d.industry)}</span>${f.web ? `<a class="tick-link" href="${esc(f.web)}" target="_blank" rel="noopener">site ↗</a>` : ''}
      <a class="tick-link" href="https://finance.yahoo.com/quote/${encodeURIComponent(d.t)}" target="_blank" rel="noopener">yahoo ↗</a></div>
    <div class="chart-box"><canvas id="dd-canvas"></canvas></div>
    <div class="stat-grid">${stats.map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('')}</div>
    ${f.desc ? `<p class="desc">${esc(f.desc)}…</p>` : ''}
    ${news ? `<div class="news-list">${news}</div>` : ''}`;

  if (modalChart) modalChart.destroy();
  const up = d.closes[d.closes.length - 1] >= d.closes[0];
  modalChart = new Chart($('#dd-canvas'), {
    type: 'line',
    data: {
      labels: d.dates,
      datasets: [{
        data: d.closes, borderColor: up ? '#2ecc71' : '#ff5c5c', borderWidth: 1.6,
        pointRadius: 0, fill: true, tension: 0.1,
        backgroundColor: (ctx) => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 260);
          g.addColorStop(0, up ? 'rgba(46,204,113,0.18)' : 'rgba(255,92,92,0.18)');
          g.addColorStop(1, 'rgba(0,0,0,0)');
          return g;
        },
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { color: '#626a7d', maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { color: '#626a7d', font: { size: 10 } }, grid: { color: 'rgba(120,130,150,0.08)' } },
      },
    },
  });
}

window.closeModal = () => {
  $('#modal-backdrop').classList.remove('open');
  if (modalChart) { modalChart.destroy(); modalChart = null; }
};
$('#modal-backdrop').addEventListener('click', (e) => { if (e.target === e.currentTarget) window.closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') window.closeModal(); });

/* ---------------- search ---------------- */
async function initSearch() {
  const input = $('#search');
  const results = $('#search-results');
  let stocks = null;
  input.addEventListener('input', async () => {
    if (!stocks) {
      try { stocks = (await getJSON('themes.json')).stocks; } catch (e) { return; }
    }
    const q = input.value.trim().toUpperCase();
    if (q.length < 1) { results.classList.remove('open'); return; }
    const hits = [];
    for (const [t, s] of Object.entries(stocks)) {
      if (t.startsWith(q)) hits.push([0, t, s]);
      else if (s.name.toUpperCase().includes(q)) hits.push([1, t, s]);
      if (hits.length > 60) break;
    }
    hits.sort((a, b) => a[0] - b[0] || b[2].mcap - a[2].mcap);
    results.innerHTML = hits.slice(0, 12).map(([, t, s]) =>
      `<div class="sr-item" data-t="${esc(t)}"><span class="tick">${esc(t)}</span><span class="nm">${esc(s.name)}</span>${fmtPct(s.d1)}</div>`).join('') || '<div class="sr-item dim">no matches</div>';
    results.classList.add('open');
    $$('.sr-item', results).forEach((el) => {
      el.onclick = () => { results.classList.remove('open'); input.value = ''; if (el.dataset.t) openDeepDive(el.dataset.t); };
    });
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-wrap')) results.classList.remove('open');
  });
}
