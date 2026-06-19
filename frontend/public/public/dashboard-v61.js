/**
 * Trading Platform Dashboard — Command Center
 * Calls Node RPC endpoints directly (no Python proxy).
 */
const REFRESH_INTERVAL = 1500;
let refreshTimer = null;
let _lastState = null;
let _lastTrades = null;
let _lastStats = null;
let _lastOptimizerAudit = null;
const _cryptoPrices = {}; // unused — equity-only platform
// Trade view filter — 'live' = LIVE only, 'sim' = SIM only, 'all' = both
let _tradeView = (typeof window !== 'undefined' && window.localStorage)
                 ? (window.localStorage.getItem('tradeView') || 'live')
                 : 'live';

function setTradeView(view) {
  _tradeView = view;
  try { window.localStorage.setItem('tradeView', view); } catch(e) {}
  if (_lastTrades) renderActiveTrades(_lastTrades);
  if (_lastState)  renderMarkets((_lastState || {}).markets, (_lastState || {}).lifecycle);
}
if (typeof window !== 'undefined') {
  window.dashboard = window.dashboard || {};
  window.dashboard.setTradeView = setTradeView;
}

function _filterTradesForView(trades) {
  if (!Array.isArray(trades)) return [];
  if (_tradeView === 'live') return trades.filter(t => !t.is_sim);
  if (_tradeView === 'sim')  return trades.filter(t => !!t.is_sim);
  return trades;
}
// ── Market definitions ────────────────────────────────────────────────────────
const EQUITY_MARKETS = [
  { key: 'nasdaq100',   label: 'NASDAQ 100',     flag: '🇺🇸', region: 'Americas' },
  { key: 'sp500',       label: 'S&P 500',         flag: '🇺🇸', region: 'Americas' },
  { key: 'dowjones',    label: 'Dow Jones',        flag: '🇺🇸', region: 'Americas' },
  { key: 'tsx',         label: 'TSX',              flag: '🇨🇦', region: 'Americas' },
  { key: 'bovespa',     label: 'Bovespa',          flag: '🇧🇷', region: 'Americas' },
  { key: 'ftse100',     label: 'FTSE 100',         flag: '🇬🇧', region: 'Europe' },
  { key: 'dax40',       label: 'DAX 40',           flag: '🇩🇪', region: 'Europe' },
  { key: 'cac40',       label: 'CAC 40',           flag: '🇫🇷', region: 'Europe' },
  { key: 'eurostoxx50', label: 'Euro STOXX 50',    flag: '🇪🇺', region: 'Europe' },
  { key: 'aex',         label: 'AEX',              flag: '🇳🇱', region: 'Europe' },
  { key: 'ibex35',      label: 'IBEX 35',          flag: '🇪🇸', region: 'Europe' },
  { key: 'mib',         label: 'FTSE MIB',         flag: '🇮🇹', region: 'Europe' },
  { key: 'omxs30',      label: 'OMX Stockholm',    flag: '🇸🇪', region: 'Europe' },
  { key: 'smi',         label: 'SMI',              flag: '🇨🇭', region: 'Europe' },
  { key: 'nikkei225',   label: 'Nikkei 225',       flag: '🇯🇵', region: 'Asia-Pacific' },
  { key: 'hangseng',    label: 'Hang Seng',        flag: '🇭🇰', region: 'Asia-Pacific' },
  { key: 'csi300',      label: 'CSI 300',          flag: '🇨🇳', region: 'Asia-Pacific' },
  { key: 'kospi',       label: 'KOSPI',            flag: '🇰🇷', region: 'Asia-Pacific' },
  { key: 'sensex',      label: 'SENSEX',           flag: '🇮🇳', region: 'Asia-Pacific' },
  { key: 'twse',        label: 'TWSE',             flag: '🇹🇼', region: 'Asia-Pacific' },
  { key: 'set',         label: 'SET',              flag: '🇹🇭', region: 'Asia-Pacific' },
  { key: 'asx200',      label: 'ASX 200',          flag: '🇦🇺', region: 'Asia-Pacific' },
  { key: 'nzx50',       label: 'NZX 50',           flag: '🇳🇿', region: 'Asia-Pacific' },
  { key: 'tadawul',     label: 'Tadawul',          flag: '🇸🇦', region: 'Middle East & Africa' },
  { key: 'jse',         label: 'JSE',              flag: '🇿🇦', region: 'Middle East & Africa' },
];
// Markets whose native exchange is NOT carried by the current EODHD data plan.
// These never receive a live feed — they are "NOT CONNECTED" (vs. merely CLOSED).
// Everything else is covered: it shows LIVE and goes live again when its session opens.
const UNCOVERED_MARKETS = new Set(['nzx50', 'mib', 'nikkei225', 'sensex', 'set', 'tadawul', 'jse']);
function isMarketConnected(key) { return !UNCOVERED_MARKETS.has(key); }
// ── RPC helper ────────────────────────────────────────────────────────────────
let _rpcIdCounter = 1;
async function rpcCall(method, params) {
  const id = _rpcIdCounter++;
  // The SDK middleware feeds the raw body through superjson.deserialize, then
  // passes the result to typed-rpc's handleRpc which expects JSON-RPC 2.0.
  // So we must wrap the JSON-RPC request in a superjson envelope: { json: <request> }.
  const rpcRequest = {
    jsonrpc: '2.0',
    id,
    method,
    params: params !== undefined ? [params] : [],
  };
  const body = JSON.stringify({ json: rpcRequest });
  const resp = await fetch(`/api/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  if (!resp.ok) throw new Error(`RPC ${method} → HTTP ${resp.status}`);
  const envelope = await resp.json();
  // The response is also superjson-wrapped: { json: { jsonrpc, id, result|error } }
  const data = envelope && 'json' in envelope ? envelope.json : envelope;
  if (data && 'error' in data) throw new Error(`RPC ${method} error: ${data.error?.message}`);
  if (data && 'result' in data) {
    const r = data.result;
    // result may itself be a superjson envelope: { json: <actual value>, meta: ... }
    if (r && typeof r === 'object' && !Array.isArray(r) && 'json' in r) {
      return r.json;
    }
    return r;
  }
  return data;
}
// ── DOM helpers ───────────────────────────────────────────────────────────────
function el(id) { return document.getElementById(id); }
function timeSince(ts) {
  if (!ts) return '—';
  const secs = Math.round((Date.now() / 1000) - ts);
  if (secs < 60)   return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}
function formatTime(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return isNaN(d) ? isoStr : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function formatDate(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return isNaN(d) ? isoStr : d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function formatPrice(v) {
  if (v == null) return '—';
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  return n.toFixed(2);
}
function formatPnl(v) {
  if (v == null || v === '') return '<span class="pnl-zero">—</span>';
  const n = parseFloat(v);
  if (isNaN(n) || n === 0) return '<span class="pnl-zero">—</span>';
  if (n > 0) return `<span class="pnl-up">▲ +${n.toFixed(2)}%</span>`;
  return `<span class="pnl-down">▼ ${n.toFixed(2)}%</span>`;
}
function formatAud(n) {
  if (n == null || isNaN(n)) return '—';
  const abs = Math.abs(n).toFixed(2);
  if (n > 0) return `<span class="pnl-up">+A$${abs}</span>`;
  if (n < 0) return `<span class="pnl-down">-A$${abs}</span>`;
  return `<span class="pnl-zero">A$0.00</span>`;
}
function signalPill(signal) {
  if (!signal) return '<span class="pill pill-none">–</span>';
  if (signal === 'BUY')  return '<span class="pill pill-buy">BUY</span>';
  if (signal === 'SELL') return '<span class="pill pill-sell">SELL</span>';
  return `<span class="pill pill-none">${signal}</span>`;
}
function statusPill(status) {
  if (status === 'OPEN')   return '<span class="pill pill-open">OPEN</span>';
  if (status === 'CLOSED') return '<span class="pill pill-closed">CLOSED</span>';
  return `<span class="pill pill-none">${status || '—'}</span>`;
}
function lifecyclePill(lc) {
  const map = {
    SIM:      '<span class="lc-pill lc-sim">SIM</span>',
    LIVE:     '<span class="lc-pill lc-live">LIVE</span>',
    DEGRADED: '<span class="lc-pill lc-degraded">DEGRADED</span>',
    RESET:    '<span class="lc-pill lc-reset">RESET</span>',
  };
  return map[lc] || `<span class="lc-pill lc-sim">${lc || 'SIM'}</span>`;
}
function engineDot(status) {
  if (!status) return 'dot dot-grey';
  const s = status.toUpperCase();
  if (['RUNNING', 'READY', 'BUILDING'].includes(s)) return 'dot dot-green';
  if (s === 'QUIET') return 'dot dot-yellow';
  if (['DEGRADED', 'BLOCKED'].includes(s)) return 'dot dot-red';
  return 'dot dot-grey';
}
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '<').replace(/>/g, '>');
}
function showError(msg) {
  const bar = el('error-bar');
  bar.style.display = 'block';
  bar.textContent = `⚠ ${msg}`;
}
function clearError() {
  const bar = el('error-bar');
  bar.style.display = 'none';
  bar.textContent = '';
}
// ── Render: Header ────────────────────────────────────────────────────────────
function renderHeader(state) {
  const dot  = el('status-dot');
  const text = el('status-text');
  const status = state.status || 'UNKNOWN';
  dot.className = 'dot ' + (
    status === 'RUNNING'  ? 'dot-green' :
    status === 'DEGRADED' ? 'dot-red'   : 'dot-grey'
  );
  text.textContent = status;
}
// ── Render: Stats bar ─────────────────────────────────────────────────────────
function renderStats(stats) {
  if (!stats) return;
  _lastStats = stats;
  const s   = el('stat-wins');       if (s)  s.textContent = stats.wins ?? '—';
  const l   = el('stat-losses');     if (l)  l.textContent = stats.losses ?? '—';
  const wr  = el('stat-winrate');    if (wr) wr.textContent = stats.winRate != null ? `${stats.winRate}%` : '—';
  const pfTop = el('profit-factor-big');
  if (pfTop) {
    const trades = (_lastTrades || []).filter(t => t.status === 'CLOSED' && !t.is_sim);
    const grossWin = trades.filter(t => _tradePnlAud(t) > 0).reduce((s,t)=>s+_tradePnlAud(t),0);
    const grossLoss = Math.abs(trades.filter(t => _tradePnlAud(t) < 0).reduce((s,t)=>s+_tradePnlAud(t),0));
    const pf = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? 999 : 0);
    pfTop.textContent = pf >= 999 ? '∞' : pf.toFixed(2);
    pfTop.className = pf >= 2 ? 'perf-value up' : pf > 0 && pf < 1 ? 'perf-value down' : 'perf-value';
  }
  const net = el('stat-net');        if (net) net.innerHTML = formatAud(stats.totalPnl);
  const tw  = el('stat-today-wins'); if (tw)  tw.textContent = stats.todayWins ?? '—';
  const tl  = el('stat-today-losses'); if (tl) tl.textContent = stats.todayLosses ?? '—';
  const tp  = el('stat-today-pnl');  if (tp) tp.innerHTML = formatAud(stats.todayPnl);
  // Avg P&L per trade — LIVE trades only (sacred: real money only)
  const avg = el('stat-avg-trade');
  if (avg) {
    const liveCount = stats.liveClosed ?? 0;
    if (liveCount > 0 && stats.liveAvgPnlPerTrade != null) {
      avg.innerHTML = formatAud(stats.liveAvgPnlPerTrade);
    } else {
      avg.innerHTML = '<span style="color:#555;font-size:20px;">—</span>';
    }
  }
  const avgSub = el('stat-avg-trade-sub');
  if (avgSub) {
    const n = stats.liveClosed ?? 0;
    avgSub.textContent = n > 0 ? `LIVE · ${n} trade${n === 1 ? '' : 's'}` : 'LIVE · no trades yet';
  }
  if (wr) {
    const rate = stats.winRate ?? 0;
    wr.className = rate >= 70 ? 'stat-big pnl-up' : rate < 50 ? 'stat-big pnl-down' : 'stat-big';
  }
  const netTile = document.getElementById('tile-net-pnl');
  if (netTile) {
    netTile.classList.remove('stat-tile-up', 'stat-tile-down');
    if ((stats.totalPnl ?? 0) > 0) netTile.classList.add('stat-tile-up');
    else if ((stats.totalPnl ?? 0) < 0) netTile.classList.add('stat-tile-down');
  }
  const todayTile = document.getElementById('tile-today-pnl');
  if (todayTile) {
    todayTile.classList.remove('stat-tile-up', 'stat-tile-down');
    if ((stats.todayPnl ?? 0) > 0) todayTile.classList.add('stat-tile-up');
    else if ((stats.todayPnl ?? 0) < 0) todayTile.classList.add('stat-tile-down');
  }
  // Command bar updates
  const cmdTrades = el('cmd-trade-count');
  if (cmdTrades) cmdTrades.textContent = stats.total ?? (stats.wins ?? 0) + (stats.losses ?? 0);
  const cmdToday = el('cmd-today-pnl');
  if (cmdToday) {
    const v = stats.todayPnl ?? 0;
    cmdToday.innerHTML = formatAud(v);
  }
  const cmdAll = el('cmd-alltime-pnl');
  if (cmdAll) {
    const v = stats.totalPnl ?? 0;
    cmdAll.innerHTML = formatAud(v);
  }
}
// ── Render: Engine tab badges ─────────────────────────────────────────────────
function renderEngines(engines) {
  const defs = [
    { key: 'equity', label: 'Equity Engine' },
  ];
  const summaryIds = { equity: 'summary-equity' };
  defs.forEach(({ key }) => {
    const e = (engines || {})[key] || {};
    const status = e.status || 'UNKNOWN';
    let statusText, color;
    // For equity, count only open markets
    const openMarketKeys = EQUITY_MARKETS.filter(m => isMarketOpen(m.key)).map(m => m.key);
    const openCount = openMarketKeys.length;
    if (openCount === 0) {
      statusText = 'CLOSED';
      color = '#555';
    } else {
      const markets = e.markets || {};
      const signalCount = openMarketKeys.filter(k => markets[k] && markets[k].signal).length;
      if (signalCount > 0) {
        statusText = signalCount + ' signals';
        color = '#22c55e';
      } else {
        statusText = openCount + ' open';
        color = '#eab308';
      }
    }
    const badge = el(`etab-status-${key}`);
    if (badge) {
      badge.textContent = (color === '#22c55e' ? '● ' : '○ ') + statusText;
      badge.style.color = color;
    }
    const summary = el(summaryIds[key]);
    if (summary) {
      summary.textContent = statusText;
      summary.style.color = color;
    }
  });
  // Command bar counts — equity only
  const enginesObj = engines || {};
  let runningCount = 0, quietCount = 0, closedCount = 0;
  ['equity'].forEach(k => {
    const s = ((enginesObj[k] || {}).status || '').toUpperCase();
    if (s === 'RUNNING') runningCount++;
    else if (s === 'QUIET' || s === 'BUILDING') quietCount++;
    else closedCount++;
  });
  // Also count equity open vs closed markets
  const openMarketCount = EQUITY_MARKETS.filter(m => isMarketOpen(m.key)).length;
  const cmdRunning = el('cmd-engines-running');
  if (cmdRunning) cmdRunning.textContent = openMarketCount;
  const cmdQuiet = el('cmd-engines-quiet');
  if (cmdQuiet) cmdQuiet.textContent = 25 - openMarketCount;
  // guard: old engine-cards div may still exist in some cached HTML
  const old = el('engine-cards');
  if (old) old.innerHTML = '';
}
// ── Render: Kitty panel (dashboard overview) ───────────────────────────────────
function renderKitty(kitty) {
  const container = el('kitty-panel');
  if (!container) return;
  if (!kitty) {
    container.innerHTML = '<div style="color:#aaaaaa;font-size:12px">Kitty unavailable</div>';
    return;
  }
  const bal      = parseFloat(kitty.balance != null ? kitty.balance : 400);
  const reserved = parseFloat(kitty.reserved || 0);
  const avail    = parseFloat(kitty.available != null ? kitty.available : bal - reserved);
  const color    = bal >= 400 ? '#22c55e' : '#ef4444';
  const hasLive  = reserved > 0;
  const mirror   = kitty.broker_mirror || null;
  const liveMirror = mirror && mirror.connected;
  const mirrorStr = liveMirror
    ? `<span style="background:#14532d;border:1px solid #22c55e;color:#22c55e;padding:2px 7px;border-radius:3px;font-size:9px;font-weight:900;letter-spacing:0.08em;">● BROKER LIVE</span>`
    : `<span style="background:#1a0a0a;border:1px solid #ef444466;color:#ef4444;padding:2px 7px;border-radius:3px;font-size:9px;font-weight:900;letter-spacing:0.08em;">BROKER OFFLINE</span>`;
  const srcLabel = liveMirror
    ? `<span style="font-size:8px;color:#22c55e;font-weight:800;letter-spacing:0.1em;margin-left:4px;">PEPPERSTONE · ${mirror.currency || ''}</span>`
    : `<span style="font-size:8px;color:#666;font-weight:800;letter-spacing:0.1em;margin-left:4px;">LOCAL</span>`;
  const unrealized = mirror && typeof mirror.unrealized_pnl === 'number' ? mirror.unrealized_pnl : null;
  const openPos    = mirror && typeof mirror.open_positions === 'number' ? mirror.open_positions : null;
  const unrColor   = unrealized == null ? '#888' : (unrealized >= 0 ? '#22c55e' : '#ef4444');
  const unrSign    = unrealized == null ? '' : (unrealized >= 0 ? '+' : '');
  const usedMargin = mirror && typeof mirror.used_margin === 'number' ? mirror.used_margin : null;
  container.innerHTML = `
    <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">
      <div>
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
          <span style="font-size:10px;color:#ccc;font-weight:800;letter-spacing:0.1em;text-transform:uppercase;">KITTY</span>
          ${mirrorStr}
        </div>
        <div style="font-size:28px;font-weight:900;color:${color};line-height:1;text-shadow:0 0 16px ${color}30;">A$${bal.toFixed(2)}${srcLabel}</div>
      </div>
      ${hasLive ? `
      <div style="display:flex;gap:20px;">
        <div>
          <div style="font-size:9px;color:#ccc;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:2px;">AVAILABLE</div>
          <div style="font-size:16px;font-weight:900;color:#fff;">A$${avail.toFixed(2)}</div>
        </div>
        <div>
          <div style="font-size:9px;color:#ccc;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:2px;">LIVE RESERVED</div>
          <div style="font-size:16px;font-weight:900;color:#ef4444;">A$${reserved.toFixed(2)}</div>
        </div>
      </div>` : ''}
      ${liveMirror && (openPos > 0 || unrealized != null) ? `
      <div style="display:flex;gap:20px;border-left:1px solid #333;padding-left:20px;margin-left:4px;">
        <div>
          <div style="font-size:9px;color:#ccc;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:2px;">OPEN POS</div>
          <div style="font-size:16px;font-weight:900;color:#fff;" data-testid="broker-open-pos">${openPos ?? 0}</div>
        </div>
        <div>
          <div style="font-size:9px;color:#ccc;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:2px;">UNREALISED P&L</div>
          <div style="font-size:16px;font-weight:900;color:${unrColor};" data-testid="broker-unrealized">${unrealized == null ? '—' : `${unrSign}$${unrealized.toFixed(2)}`}</div>
        </div>
        <div>
          <div style="font-size:9px;color:#ccc;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:2px;">USED MARGIN</div>
          <div style="font-size:16px;font-weight:900;color:#fbbf24;" data-testid="broker-used-margin">${usedMargin == null ? '—' : `A$${usedMargin.toFixed(2)}`}</div>
        </div>
      </div>` : ''}
    </div>
  `;
}
// ── Render: Swarm panel (dashboard overview) ──────────────────────────────────
function renderSwarm(swarm) {
  const container = el('swarm-panel');
  if (!container) return;
  if (!swarm) {
    container.innerHTML = '<div style="color:#555;font-size:12px">Swarm unavailable</div>';
    return;
  }
  const patterns = swarm.patterns || [];
  const gated = patterns.filter(p => p.gated);
  if (patterns.length === 0) {
    container.innerHTML = '<div style="color:#555;font-size:12px">No patterns learned yet</div>';
    return;
  }
  const rows = patterns.slice(0, 8).map(p => `
    <div class="swarm-row ${p.gated ? 'swarm-gated' : ''}">
      <span class="swarm-gate-icon">${p.gated ? '🔴' : '🟢'}</span>
      <span class="swarm-pattern">${escHtml(p.pattern)}</span>
      <span class="swarm-votes">${p.votes}v</span>
      <span class="swarm-markets">${(p.markets || []).length} markets</span>
    </div>`).join('');
  container.innerHTML = `
    <div class="swarm-summary">${gated.length} gates active / ${patterns.length} patterns</div>
    ${rows}
  `;
}
// ── Market hours ──────────────────────────────────────────────────────────────
const MARKET_HOURS = {
  nasdaq100:   { tz: 'America/New_York',       open: [9,30],  close: [16,0],  days: [1,2,3,4,5] },
  sp500:       { tz: 'America/New_York',       open: [9,30],  close: [16,0],  days: [1,2,3,4,5] },
  dowjones:    { tz: 'America/New_York',       open: [9,30],  close: [16,0],  days: [1,2,3,4,5] },
  tsx:         { tz: 'America/Toronto',        open: [9,30],  close: [16,0],  days: [1,2,3,4,5] },
  bovespa:     { tz: 'America/Sao_Paulo',      open: [10,0],  close: [17,0],  days: [1,2,3,4,5] },
  ftse100:     { tz: 'Europe/London',          open: [8,0],   close: [16,30], days: [1,2,3,4,5] },
  dax40:       { tz: 'Europe/Berlin',          open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  cac40:       { tz: 'Europe/Paris',           open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  eurostoxx50: { tz: 'Europe/Paris',           open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  aex:         { tz: 'Europe/Amsterdam',       open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  ibex35:      { tz: 'Europe/Madrid',          open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  mib:         { tz: 'Europe/Rome',            open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  omxs30:      { tz: 'Europe/Stockholm',       open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  smi:         { tz: 'Europe/Zurich',          open: [9,0],   close: [17,30], days: [1,2,3,4,5] },
  nikkei225:   { tz: 'Asia/Tokyo',             open: [9,0],   close: [15,30], days: [1,2,3,4,5], lunch: [[11,30],[12,30]] },
  hangseng:    { tz: 'Asia/Hong_Kong',         open: [9,30],  close: [16,0],  days: [1,2,3,4,5], lunch: [[12,0],[13,0]] },
  csi300:      { tz: 'Asia/Shanghai',          open: [9,30],  close: [15,0],  days: [1,2,3,4,5], lunch: [[11,30],[13,0]] },
  kospi:       { tz: 'Asia/Seoul',             open: [9,0],   close: [15,30], days: [1,2,3,4,5] },
  sensex:      { tz: 'Asia/Kolkata',           open: [9,15],  close: [15,30], days: [1,2,3,4,5] },
  twse:        { tz: 'Asia/Taipei',            open: [9,0],   close: [13,30], days: [1,2,3,4,5] },
  set:         { tz: 'Asia/Bangkok',           open: [10,0],  close: [16,30], days: [1,2,3,4,5] },
  asx200:      { tz: 'Australia/Sydney',       open: [10,0],  close: [16,0],  days: [1,2,3,4,5] },
  nzx50:       { tz: 'Pacific/Auckland',       open: [10,0],  close: [17,0],  days: [1,2,3,4,5] },
  tadawul:     { tz: 'Asia/Riyadh',            open: [10,0],  close: [15,0],  days: [0,1,2,3,4] }, // Sun–Thu
  jse:         { tz: 'Africa/Johannesburg',    open: [9,0],   close: [17,0],  days: [1,2,3,4,5] },
};
function isMarketOpen(key) {
  const h = MARKET_HOURS[key];
  if (!h) return false;
  try {
    const now = new Date();
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: h.tz,
      hour: 'numeric', minute: 'numeric', weekday: 'short',
      hour12: false
    }).formatToParts(now);
    const get = (type) => parts.find(p => p.type === type)?.value;
    const weekdayStr = get('weekday'); // Mon, Tue, ...
    const dayMap = { Sun:0, Mon:1, Tue:2, Wed:3, Thu:4, Fri:5, Sat:6 };
    const day = dayMap[weekdayStr];
    if (!h.days.includes(day)) return false;
    const hour = parseInt(get('hour'), 10);
    const min  = parseInt(get('minute'), 10);
    const cur  = hour * 60 + min;
    const open  = h.open[0]  * 60 + h.open[1];
    const close = h.close[0] * 60 + h.close[1];
    if (cur < open || cur >= close) return false;
    if (h.lunch) {
      const lunchStart = h.lunch[0][0] * 60 + h.lunch[0][1];
      const lunchEnd   = h.lunch[1][0] * 60 + h.lunch[1][1];
      if (cur >= lunchStart && cur < lunchEnd) return false;
    }
    return true;
  } catch(e) {
    return false;
  }
}
// ── Render: Market grid ────────────────────────────────────────────────────────
// Store P&L history per market for sparklines
let _marketPnlHistory = {};
let _expandedCrypto = null;
let _expandedMarket = null;
let _expandedActiveTrade = null;

function _buildSparklineSvg(values, width, height, color) {
  if (!values || values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / range) * height * 0.8 - height * 0.1).toFixed(1)}`).join(' ');
  const zeroY = (height - ((0 - min) / range) * height * 0.8 - height * 0.1).toFixed(1);
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block;">
    <line x1="0" y1="${zeroY}" x2="${width}" y2="${zeroY}" stroke="#444" stroke-width="0.5" stroke-dasharray="2,2"/>
    <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

function _getMarketPnlValues(key) {
  // Build a synthetic sparkline that matches the current WPS/signal direction
  // Uses closed trade P&L if available, otherwise generates from WPS
  const closed = _filterTradesForView(_lastTrades || []).filter(t => t.symbol === key && t.status === 'CLOSED').slice(0, 15).reverse();
  if (closed.length >= 3) {
    let cum = 0;
    return closed.map(t => { cum += (parseFloat(t.pnl) || 0); return cum; });
  }
  // Not enough history — generate from current market data
  const m = (_lastState && _lastState.markets) ? (_lastState.markets[key] || null) : null;
  if (!m) return [];
  const wps = parseFloat(m.wps) || 0;
  // Generate 8 points trending in the WPS direction
  const dir = wps >= 0 ? 1 : -1;
  const magnitude = Math.min(Math.abs(wps) / 100, 1);
  const points = [];
  let val = 0;
  for (let i = 0; i < 8; i++) {
    val += dir * magnitude * (0.5 + Math.random() * 0.5);
    // Add some noise
    val += (Math.random() - 0.5) * magnitude * 0.3;
    points.push(val);
  }
  return points;
}

function _getSparklineColor(key, markets) {
  const m = (markets || {})[key];
  if (!m) return '#555';
  const wps = parseFloat(m.wps) || 0;
  const signal = m.signal;
  if (signal === 'BUY' || wps > 0) return '#22c55e';
  if (signal === 'SELL' || wps < 0) return '#ef4444';
  return '#555';
}


function _auditVerdictClass(v) {
  v = String(v || '').toUpperCase();
  if (v === 'HELPING') return 'op-pass';
  if (v === 'HURTING') return 'op-fail';
  if (v === 'MIXED') return 'op-warn';
  return 'op-neutral';
}
function _shortAuditMessage(msg) {
  msg = String(msg || '');
  return msg.replace(/\s+/g, ' ').replace('gates tightened', 'gates↑').replace('gates loosened', 'gates↓').replace('WPS tightened', 'WPS↑').replace('WPS loosened', 'WPS↓');
}
function renderOptimizerAudit(audit) {
  const box = document.getElementById('optimizer-audit-box');
  if (!box) return;
  const items = (audit && audit.last5) || [];
  if (!items.length) {
    box.innerHTML = '<div class="op-empty">NO OPTIMIZER CHANGES YET</div>';
    return;
  }
  const count24 = audit.count24h || 0;
  const helping = audit.helping24h || 0;
  const hurting = audit.hurting24h || 0;
  box.innerHTML = `
    <div class="optimizer-audit-summary">
      <span>24H ${count24}</span>
      <span class="op-pass">HELP ${helping}</span>
      <span class="op-fail">HURT ${hurting}</span>
    </div>
    ${items.map(it => {
      const imp = it.impact || {};
      const verdict = imp.verdict || 'PENDING';
      const cls = _auditVerdictClass(verdict);
      const net = Number.isFinite(parseFloat(imp.netPnl)) ? parseFloat(imp.netPnl) : 0;
      const pf = imp.profitFactor === 999 ? '∞' : (Number.isFinite(parseFloat(imp.profitFactor)) ? parseFloat(imp.profitFactor).toFixed(2) : '—');
      return `<div class="optimizer-audit-row" title="${escHtml(it.message || '')}">
        <span class="optimizer-audit-time">${formatTime(it.created_at)}</span>
        <span class="optimizer-audit-msg">${escHtml(_shortAuditMessage(it.message))}</span>
        <span class="optimizer-audit-impact ${cls}">${escHtml(verdict)} ${imp.trades || 0}T ${net >= 0 ? '+' : ''}${net.toFixed(0)} PF ${pf}</span>
      </div>`;
    }).join('')}
  `;
}

function renderMarkets(markets, lifecycle) {
  const hasPosition = (key) => (_lastTrades || []).some(t => t.symbol === key && t.status === 'OPEN');
  const getOpenTrade = (key) => (_lastTrades || []).find(t => t.symbol === key && t.status === 'OPEN');
  const isLiveLc = (key) => ((lifecycle || {})[key] || {}).lifecycle === 'LIVE';
  // Collect all visible markets
  const allVisible = EQUITY_MARKETS.filter(m => isMarketOpen(m.key) || hasPosition(m.key));
  // 3 groups: LIVE-graduated markets at top, then active SIM trades, then watching
  const liveGroup = allVisible.filter(m => isLiveLc(m.key));
  const active = allVisible.filter(m => !isLiveLc(m.key) && hasPosition(m.key)).sort((a, b) => {
    const aT = getOpenTrade(a.key);
    const bT = getOpenTrade(b.key);
    const aPnl = Math.abs(parseFloat((aT||{}).pnl) || 0);
    const bPnl = Math.abs(parseFloat((bT||{}).pnl) || 0);
    return bPnl - aPnl;
  });
  const watching = allVisible.filter(m => !isLiveLc(m.key) && !hasPosition(m.key));
  let html = '';
  if (liveGroup.length > 0) {
    html += `<div class="region-label" style="border-left-color:#22c55e;color:#22c55e;">LIVE MARKETS — ${liveGroup.length}</div><div class="market-grid">`;
    for (const { key, label, flag } of liveGroup) {
      const m = (markets || {})[key];
      const trade = getOpenTrade(key);
      html += _buildMarketCard(key, label, flag, m, lifecycle, trade, true, markets);
    }
    html += '</div>';
  }
  if (active.length > 0) {
    html += `<div class="region-label">ACTIVE TRADES — ${active.length}</div><div class="market-grid">`;
    for (const { key, label, flag } of active) {
      const m = (markets || {})[key];
      const trade = getOpenTrade(key);
      html += _buildMarketCard(key, label, flag, m, lifecycle, trade, true, markets);
    }
    html += '</div>';
  }
  if (watching.length > 0) {
    html += `<div class="region-label">WATCHING — ${watching.length}</div><div class="market-grid">`;
    for (const { key, label, flag } of watching) {
      const m = (markets || {})[key];
      html += _buildMarketCard(key, label, flag, m, lifecycle, null, true, markets);
    }
    html += '</div>';
  }
  const container = el('market-cards');
  if (container) container.innerHTML = html;
}

// ── Render: static geographic market grid in index.html ──────────────────────
// index.html ships a fixed AMERICAS/EUROPE/… grid whose value spans use ids like
// wps-val-<key>, conf-<key>, align-<key>, sig-<key>, regime-<key>, mom-<key>.
// A few static keys differ from the backend's getMarketState keys, so map them.
const STATIC_GRID_MAP = {
  nasdaq100: 'nasdaq100', sp500: 'sp500', dowjones: 'dowjones', tsx: 'tsx',
  bovespa: 'bovespa', ftse100: 'ftse100', dax: 'dax40', cac40: 'cac40',
  eurostoxx50: 'eurostoxx50', smi: 'smi', aex: 'aex', ibex35: 'ibex35',
  nikkei: 'nikkei225', asx200: 'asx200', hangseng: 'hangseng',
  shanghai: 'csi300', sensex: 'sensex', kospi: 'kospi', tadawul: 'tadawul',
  jse: 'jse',
};
function renderStaticMarketGrid(markets) {
  if (!markets) return;
  const setText = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
  for (const [gridKey, beKey] of Object.entries(STATIC_GRID_MAP)) {
    // Connection badge in the card header — coverage-based, shown regardless of data.
    const _card = document.getElementById('market-' + gridKey);
    if (_card) {
      const _hdr = _card.querySelector('.mc-header');
      if (_hdr) {
        let _cb = _hdr.querySelector('.mc-conn');
        if (!_cb) { _cb = document.createElement('span'); _cb.className = 'mc-conn'; _hdr.appendChild(_cb); }
        const _conn = isMarketConnected(beKey);
        _cb.textContent = _conn ? 'LIVE' : 'NO FEED';
        _cb.title = _conn ? 'Live data feed connected' : "This market's exchange isn't on the current data plan — no live feed";
        _cb.style.cssText = 'flex-shrink:0;font-size:8px;font-weight:900;padding:1px 5px;border-radius:3px;letter-spacing:0.05em;' +
          (_conn ? 'background:#0e2a1a;color:#22c55e;border:1px solid #22c55e66;' : 'background:#2a2018;color:#f59e0b;border:1px solid #f59e0b66;');
      }
    }
    const m = markets[beKey];
    if (!m) continue;
    const wps  = m.wps != null ? parseFloat(m.wps) : null;
    const cRaw = m.confidence != null ? parseFloat(m.confidence) : null;
    const conf = cRaw != null ? Math.round(cRaw <= 1 ? cRaw * 100 : cRaw) : null;
    const aln  = m.alignment != null ? m.alignment : null;
    const sig  = m.signal || null;

    setText(`wps-val-${gridKey}`, wps  != null ? `WPS ${wps.toFixed(1)}` : 'WPS —');
    setText(`conf-${gridKey}`,    conf != null ? `CONF ${conf}`         : 'CONF —');
    setText(`align-${gridKey}`,   aln  != null ? `ALN ${aln}`           : 'ALN —');

    const regEl = document.getElementById(`regime-${gridKey}`);
    if (regEl) {
      regEl.textContent = (m.regime || '—')
        .replace('CHOPPY_HIGH', 'CHOPPY').replace('CHOPPY_MEDIUM', 'CHOPPY').replace('CHOPPY_LOW', 'CHOPPY');
    }

    const sigEl = document.getElementById(`sig-${gridKey}`);
    if (sigEl) {
      const label = sig || '—';
      sigEl.textContent = label;
      sigEl.className = 'sig-pill ' + (label === 'BUY' ? 'sig-buy' : label === 'SELL' ? 'sig-sell' : 'sig-none');
    }

    const momEl = document.getElementById(`mom-${gridKey}`);
    if (momEl) {
      const up = wps != null && wps > 0, down = wps != null && wps < 0;
      momEl.textContent = up ? '↑' : down ? '↓' : '→';
      momEl.style.color = up ? '#22c55e' : down ? '#ef4444' : '#888';
    }

    const mag = wps != null ? Math.min(Math.abs(wps), 100) : 0;
    const posBar = document.getElementById(`wps-bar-${gridKey}`);
    const negBar = document.getElementById(`wps-bar-neg-${gridKey}`);
    if (posBar) posBar.style.width = (wps != null && wps >= 0) ? mag + '%' : '0';
    if (negBar) negBar.style.width = (wps != null && wps < 0)  ? mag + '%' : '0';
  }
}

function _buildMarketCard(key, label, flag, m, lifecycle, trade, open, markets) {
      const hasPos = !!trade;
      const getOpenTrade = () => trade;
      const lcData    = (lifecycle || {})[key] || {};
      const lcWins    = lcData.win_count || 0;
      const lcLosses  = lcData.loss_count || 0;
      const lcPf      = lcData.profit_factor ? parseFloat(lcData.profit_factor).toFixed(2) : '—';
      const lcWr      = lcData.win_rate ? (parseFloat(lcData.win_rate) * 100).toFixed(0) : '0';
      const lcPnl     = lcData.total_pnl ? parseFloat(lcData.total_pnl) : 0;
      const lcStatus  = lcData.lifecycle || 'SIM';
      const lcSimTrades = lcData.sim_trades || 0;
      const lcRegAcc  = lcData.regime_accuracy ? (parseFloat(lcData.regime_accuracy) * 100).toFixed(0) : '0';
      const lcBwc     = lcData.brain_wash_count || 0;
      const pnlColor  = lcPnl > 0 ? '#22c55e' : lcPnl < 0 ? '#ef4444' : '#555';
      const pnlStr    = lcPnl >= 0 ? `+A$${lcPnl.toFixed(2)}` : `-A$${Math.abs(lcPnl).toFixed(2)}`;
      const wrNum     = parseInt(lcWr) || 0;
      const wrColor   = wrNum >= 60 ? '#22c55e' : wrNum >= 45 ? '#eab308' : wrNum > 0 ? '#ef4444' : '#555';
      const regime    = m ? (m.regime || '') : '';
      const wps       = m && m.wps != null ? parseFloat(m.wps).toFixed(1) : '—';
      const conf      = m && m.confidence != null ? parseFloat(m.confidence).toFixed(0) : '—';
      const sig       = m ? (m.signal || null) : null;
      const wpsColor  = parseFloat(wps) > 0 ? '#22c55e' : parseFloat(wps) < 0 ? '#ef4444' : '#ccc';
      const isExpanded = _expandedMarket === key;
      // Lifecycle badge — clickable toggle
      const lcBadge = lcStatus === 'LIVE'
        ? `<span onclick="event.stopPropagation();window.dashboard.toggleMarketLifecycle('${key}','LIVE')" style="background:#14532d;color:#22c55e;border:1px solid #22c55e66;font-size:9px;font-weight:900;padding:1px 6px;border-radius:3px;cursor:pointer;" title="Click to switch to SIM">LIVE</span>`
        : lcStatus === 'DEGRADED'
        ? `<span onclick="event.stopPropagation();window.dashboard.toggleMarketLifecycle('${key}','DEGRADED')" style="background:#450a0a;color:#ef4444;border:1px solid #ef444466;font-size:9px;font-weight:900;padding:1px 6px;border-radius:3px;cursor:pointer;" title="Click to switch to LIVE">DEG</span>`
        : `<span onclick="event.stopPropagation();window.dashboard.toggleMarketLifecycle('${key}','SIM')" style="background:#1a1a1a;color:#777;border:1px solid #333;font-size:9px;font-weight:800;padding:1px 6px;border-radius:3px;cursor:pointer;" title="Click to switch to LIVE">SIM</span>`;
      // BUY / SELL buttons
      const sigBtnB = sig === 'BUY'
        ? '<span style="background:#14532d;color:#22c55e;font-size:10px;font-weight:900;padding:2px 6px;border-radius:3px;">B</span>'
        : '<span style="background:#1a1a1a;color:#444;font-size:10px;font-weight:800;padding:2px 6px;border-radius:3px;">B</span>';
      const sigBtnS = sig === 'SELL'
        ? '<span style="background:#450a0a;color:#ef4444;font-size:10px;font-weight:900;padding:2px 6px;border-radius:3px;">S</span>'
        : '<span style="background:#1a1a1a;color:#444;font-size:10px;font-weight:800;padding:2px 6px;border-radius:3px;">S</span>';
      // Trade P&L
      let tradePnlPct = '';
      if (trade) {
        const tPnl = parseFloat(trade.pnl) || 0;
        const tColor = tPnl > 0 ? '#22c55e' : tPnl < 0 ? '#ef4444' : '#555';
        tradePnlPct = `<span style="color:${tColor};font-size:14px;font-weight:900;">${tPnl >= 0 ? '+' : ''}${tPnl.toFixed(2)}%</span>`;
      }
      // Sparkline
      const pnlValues = _getMarketPnlValues(key);
      const sparkColor = _getSparklineColor(key, markets);
      const sparkline = _buildSparklineSvg(pnlValues, 100, 28, sparkColor);
      const borderColor = hasPos ? (trade && trade.side === 'BUY' ? '#22c55e' : '#ef4444') : '#3a3a3a';
      // Connection indicator — coverage-based, independent of OPEN/CLOSED.
      // Covered markets read LIVE even while closed (they go live when the session opens);
      // the uncovered 7 read NOT CONNECTED (their exchange isn't on the EODHD data plan).
      const connected = isMarketConnected(key);
      const connBadge = connected
        ? `<span title="Live data feed connected" style="background:#0e2a1a;color:#22c55e;border:1px solid #22c55e66;font-size:9px;font-weight:900;padding:1px 6px;border-radius:3px;display:inline-flex;align-items:center;gap:4px;"><span style="width:6px;height:6px;border-radius:50%;background:#22c55e;box-shadow:0 0 5px #22c55e;display:inline-block;"></span>LIVE</span>`
        : `<span title="This market's exchange isn't carried by the current data plan — no live feed" style="background:#2a2018;color:#f59e0b;border:1px solid #f59e0b66;font-size:9px;font-weight:900;padding:1px 6px;border-radius:3px;display:inline-flex;align-items:center;gap:4px;"><span style="width:6px;height:6px;border-radius:50%;background:#f59e0b;display:inline-block;"></span>NOT CONNECTED</span>`;
      // Regime label — override with CLOSED when data is stale (but NOT for uncovered markets:
      // they aren't "closed", they simply have no feed).
      const isStale = !!(m && m.stale);
      const regimeLabel = !connected ? '— NO FEED'
        : isStale ? '✕ MARKET CLOSED'
        : regime.includes('TRENDING') ? (parseFloat(wps) >= 0 ? '▲ TREND UP' : '▼ TREND DN')
        : regime.includes('CHOPPY') ? '◆ CHOPPY' : regime.includes('REVERSAL') ? '↻ REVERSAL' : '—';
      const regimeColor = !connected ? '#f59e0b'
        : isStale ? '#555'
        : regime.includes('TRENDING') ? (parseFloat(wps) >= 0 ? '#22c55e' : '#ef4444')
        : regime.includes('CHOPPY') ? '#eab308' : regime.includes('REVERSAL') ? '#f97316' : '#555';
      // Trade info inline
      let tradeHtml = '';
      if (trade) {
        const tPnl = parseFloat(trade.pnl) || 0;
        const tStake = parseFloat(trade.size) || 50;
        const tDollarPnl = tStake * tPnl / 100;
        const tPnlColor = tDollarPnl > 0 ? '#22c55e' : tDollarPnl < 0 ? '#ef4444' : '#555';
        const tSideColor = trade.side === 'BUY' ? '#22c55e' : '#ef4444';
        const tArrow = trade.side === 'BUY' ? '▲' : '▼';
        let dur = '';
        if (trade.created_at) {
          const created = new Date(trade.created_at);
          const diffSec = Math.max(0, Math.floor((new Date() - created) / 1000));
          if (diffSec < 60) dur = diffSec + 's';
          else if (diffSec < 3600) dur = Math.floor(diffSec / 60) + 'm';
          else dur = Math.floor(diffSec / 3600) + 'h ' + Math.floor((diffSec % 3600) / 60) + 'm';
        }
        tradeHtml = `
          <span style="color:${tSideColor};font-size:13px;font-weight:900;">${tArrow}${trade.side}</span>
          <span style="color:#fff;font-size:12px;font-weight:800;">A$${tStake.toFixed(0)}</span>
          <span style="color:#ccc;font-size:11px;">${formatPrice(trade.entry_price)}→${formatPrice(trade.current_price)}</span>
          <span style="color:#888;font-size:11px;">${dur}</span>
          <span style="color:${tPnlColor};font-size:14px;font-weight:900;">${tDollarPnl >= 0 ? '+' : ''}A$${tDollarPnl.toFixed(2)}</span>
          <span style="color:${tPnlColor};font-size:12px;font-weight:800;">${tPnl >= 0 ? '+' : ''}${tPnl.toFixed(2)}%</span>
          <button onclick="event.stopPropagation();window.dashboard.closeTrade(${trade.id})" style="padding:3px 10px;background:#2a0a0a;border:1px solid #ef444466;color:#ef4444;font-size:10px;font-weight:900;border-radius:4px;cursor:pointer;font-family:inherit;">CLOSE</button>`;
      }
      return `
        <div onclick="window.dashboard.expandMarket('${key}')" data-market="${key}"
             onmouseover="this.style.background='#333';" onmouseout="this.style.background='#2a2a2a';"
             style="background:#2a2a2a;border:1px solid ${borderColor};${hasPos ? 'border-left:3px solid '+borderColor+';' : ''}border-radius:6px;cursor:pointer;overflow:hidden;transition:background 0.15s;">
          <div style="display:flex;align-items:center;gap:10px;padding:7px 12px;flex-wrap:wrap;">
            ${connBadge}
            ${lcBadge}
            <span style="font-size:16px;">${flag}</span>
            <span style="font-size:13px;font-weight:900;color:#fff;">${label}</span>
            <span style="font-size:12px;font-weight:900;color:${regimeColor};">${regimeLabel}</span>
            <span style="color:#ccc;font-size:11px;font-weight:700;">WPS<span style="color:${wpsColor};font-weight:900;margin-left:3px;">${wps}</span></span>
            <span style="color:${wrColor};font-size:12px;font-weight:900;">${wrNum > 0 ? wrNum+'%' : '—'}</span>
            <span style="color:#ccc;font-size:11px;font-weight:800;">${lcWins}W/${lcLosses}L</span>
            <span style="color:${pnlColor};font-size:13px;font-weight:900;">${pnlStr}</span>
            ${(() => {
              const pfLive = (m && m.pf_live != null) ? parseFloat(m.pf_live).toFixed(2) : '—';
              const wrLive = (m && m.wr_live != null) ? Math.round(parseFloat(m.wr_live) * 100) : null;
              const pfSim  = (m && m.pf_sim  != null) ? parseFloat(m.pf_sim ).toFixed(2) : '—';
              const wrSim  = (m && m.wr_sim  != null) ? Math.round(parseFloat(m.wr_sim ) * 100) : null;
              const cPfL = pfLive !== '—' && parseFloat(pfLive) >= 1.5 ? '#22c55e' : pfLive !== '—' && parseFloat(pfLive) >= 1.0 ? '#eab308' : pfLive !== '—' ? '#ef4444' : '#555';
              const cPfS = pfSim  !== '—' && parseFloat(pfSim ) >= 1.5 ? '#22c55e' : pfSim  !== '—' && parseFloat(pfSim ) >= 1.0 ? '#eab308' : pfSim  !== '—' ? '#ef4444' : '#555';
              const cWrL = wrLive == null ? '#555' : wrLive >= 60 ? '#22c55e' : wrLive >= 45 ? '#eab308' : '#ef4444';
              const cWrS = wrSim  == null ? '#555' : wrSim  >= 60 ? '#22c55e' : wrSim  >= 45 ? '#eab308' : '#ef4444';
              const nL = (m && m.trades_live) || 0;
              const nS = (m && m.trades_sim)  || 0;
              return `
                <span data-testid="card-pf-live-${key}" title="LIVE Profit Factor (${nL} trades)" style="color:#ccc;font-size:10px;font-weight:700;">PF<span style="color:#22c55e;font-size:8px;">L</span><span style="color:${cPfL};font-weight:900;margin-left:2px;">${pfLive}</span></span>
                <span data-testid="card-wr-live-${key}" title="LIVE Win Rate" style="color:#ccc;font-size:10px;font-weight:700;">WR<span style="color:#22c55e;font-size:8px;">L</span><span style="color:${cWrL};font-weight:900;margin-left:2px;">${wrLive == null ? '—' : wrLive+'%'}</span></span>
                <span data-testid="card-pf-sim-${key}"  title="SIM Profit Factor (${nS} trades)" style="color:#888;font-size:10px;font-weight:700;">PF<span style="color:#888;font-size:8px;">S</span><span style="color:${cPfS};font-weight:900;margin-left:2px;">${pfSim}</span></span>
                <span data-testid="card-wr-sim-${key}"  title="SIM Win Rate" style="color:#888;font-size:10px;font-weight:700;">WR<span style="color:#888;font-size:8px;">S</span><span style="color:${cWrS};font-weight:900;margin-left:2px;">${wrSim == null ? '—' : wrSim+'%'}</span></span>
              `;
            })()}
            <div style="flex-shrink:0;">${sparkline || ''}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-left:auto;flex-shrink:0;">
              ${tradeHtml}
            </div>
            <span style="color:${isExpanded ? '#22c55e' : '#555'};font-size:14px;font-weight:900;flex-shrink:0;width:18px;text-align:center;" title="Click row to ${isExpanded ? 'collapse' : 'view details'}">${isExpanded ? '▲' : '▼'}</span>
          </div>
          ${isExpanded ? _renderMarketDetail(key, m, lcData, trade) : ''}
        </div>`;
}

function _renderMarketDetail(key, m, lcData, trade) {
  const wps    = m && m.wps != null ? parseFloat(m.wps).toFixed(1) : '—';
  const conf   = m && m.confidence != null ? parseFloat(m.confidence).toFixed(0) : '—';
  const regime = m ? (m.regime || '—') : '—';
  const align  = m && m.alignment != null ? m.alignment + '/4' : '—';
  const lcWins    = lcData.win_count || 0;
  const lcLosses  = lcData.loss_count || 0;
  const lcPf      = lcData.profit_factor ? parseFloat(lcData.profit_factor).toFixed(2) : '—';
  const lcWr      = lcData.win_rate ? (parseFloat(lcData.win_rate) * 100).toFixed(0) : '0';
  const lcRegAcc  = lcData.regime_accuracy ? (parseFloat(lcData.regime_accuracy) * 100).toFixed(0) : '0';
  const lcBwc     = lcData.brain_wash_count || 0;
  const lcSimTrades = lcData.sim_trades || 0;
  const lcStatus  = lcData.lifecycle || 'SIM';
  // Progress toward LIVE
  let gateProgress = '';
  if (lcStatus === 'SIM') {
    const pfOk  = parseFloat(lcData.profit_factor || 0) >= 1.5;
    const wrOk  = parseFloat(lcData.win_rate || 0) >= 0.60;
    const raOk  = parseFloat(lcData.regime_accuracy || 0) >= 0.70;
    const trOk  = lcSimTrades >= 10;
    gateProgress = `
      <div style="margin-top:6px;padding-top:6px;border-top:1px solid #1a1a1a;">
        <div style="font-size:10px;color:#aaa;font-weight:800;margin-bottom:4px;">GATES TO LIVE</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <span style="font-size:10px;padding:2px 6px;border-radius:3px;${pfOk ? 'background:#14532d;color:#22c55e;' : 'background:#1a1a1a;color:#555;'}">PF ${lcPf}</span>
          <span style="font-size:10px;padding:2px 6px;border-radius:3px;${wrOk ? 'background:#14532d;color:#22c55e;' : 'background:#1a1a1a;color:#555;'}">WR ${lcWr}%</span>
          <span style="font-size:10px;padding:2px 6px;border-radius:3px;${raOk ? 'background:#14532d;color:#22c55e;' : 'background:#1a1a1a;color:#555;'}">Acc ${lcRegAcc}%</span>
          <span style="font-size:10px;padding:2px 6px;border-radius:3px;${trOk ? 'background:#14532d;color:#22c55e;' : 'background:#1a1a1a;color:#555;'}">Trades ${lcSimTrades}/10</span>
        </div>
      </div>`;
  }
  // Trade details if open
  let tradeHtml = '';
  if (trade) {
    const tPnl = parseFloat(trade.pnl) || 0;
    const tStake = parseFloat(trade.size) || 2;
    const tDollarPnl = tStake * tPnl / 100;
    const tPnlColor = tDollarPnl > 0 ? '#22c55e' : tDollarPnl < 0 ? '#ef4444' : '#555';
    tradeHtml = `
      <div style="margin-top:6px;padding-top:6px;border-top:1px solid #1a1a1a;">
        <div style="font-size:10px;color:#aaa;font-weight:800;margin-bottom:4px;">OPEN POSITION</div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="color:#ccc;font-size:11px;">${formatPrice(trade.entry_price)} → ${formatPrice(trade.current_price)}</span>
          <span style="color:${tPnlColor};font-size:13px;font-weight:900;">${tDollarPnl >= 0 ? '+' : ''}A$${tDollarPnl.toFixed(2)}</span>
        </div>
        <div style="margin-top:4px;">
          <button onclick="event.stopPropagation();window.dashboard.closeTrade(${trade.id})" style="width:100%;padding:5px 0;background:#1a0a0a;border:1px solid #ef444466;color:#ef4444;font-size:11px;font-weight:800;border-radius:4px;cursor:pointer;font-family:inherit;">CLOSE POSITION</button>
        </div>
      </div>`;
  }
  return `
    <div style="padding:0 10px 8px;border-top:1px solid #1a1a1a;" onclick="event.stopPropagation()">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:4px;margin-top:6px;">
        <div style="text-align:center;">
          <div style="font-size:9px;color:#fff;font-weight:800;">WPS</div>
          <div style="font-size:14px;font-weight:900;color:#fff;">${wps}</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:9px;color:#fff;font-weight:800;">CONF</div>
          <div style="font-size:14px;font-weight:900;color:#fff;">${conf}%</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:9px;color:#fff;font-weight:800;">ALIGN</div>
          <div style="font-size:14px;font-weight:900;color:#fff;">${align}</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:9px;color:#fff;font-weight:800;">REGIME</div>
          <div style="font-size:12px;font-weight:900;color:#fff;">${regime.replace('_',' ')}</div>
        </div>
      </div>
      ${_renderLiveAvgRow(key)}
      ${_renderTimeframeBreakdown(m)}
      ${lcBwc > 0 ? `<div style="margin-top:4px;font-size:10px;color:#f97316;font-weight:700;">BRAIN WASH x${lcBwc}</div>` : ''}
      ${gateProgress}
      ${tradeHtml}
      <div style="margin-top:6px;">
        <button onclick="event.stopPropagation();window.dashboard.resetMarketNow('${key}')" style="width:100%;padding:4px 0;background:#111;border:1px solid #33333366;color:#555;font-size:10px;font-weight:700;border-radius:4px;cursor:pointer;font-family:inherit;">RESET TO SIM</button>
      </div>
    </div>`;
}

// ── Timeframe alignment breakdown (5m / 15m / 30m / 60m) ──────────────────────
function _renderTimeframeBreakdown(m) {
  if (!m || !Array.isArray(m.timeframes) || m.timeframes.length === 0) return '';
  const winning = m.direction || m.signal || null;  // BUY / SELL / null
  const rows = m.timeframes.map(t => {
    const isAligned = winning && t.dir === winning;
    const isOpposite = winning && t.dir !== 'NEUTRAL' && t.dir !== winning;
    const pct = parseFloat(t.avg_pct) || 0;
    const absPct = Math.abs(pct);
    // Aligned → dark green; Opposite → red intensity scales with |%|; Neutral → grey
    let bg, fg, bd;
    if (isAligned) {
      bg = '#14532d'; fg = '#22c55e'; bd = '#22c55e';
    } else if (isOpposite) {
      // Stronger disagreement = brighter red
      const intensity = Math.min(1, absPct / 1.0);  // 1% diff = max red
      const r = Math.round(80 + intensity * 175);    // 80..255
      bg = `rgba(${r},30,30,0.25)`; fg = '#ef4444'; bd = '#ef444488';
    } else {
      bg = '#1a1a1a'; fg = '#666'; bd = '#333';
    }
    const pctStr = pct >= 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`;
    const arrow = t.dir === 'BUY' ? '▲' : (t.dir === 'SELL' ? '▼' : '■');
    return `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 8px;background:${bg};border:1px solid ${bd};border-radius:4px;">
        <span style="font-size:11px;font-weight:900;color:${fg};min-width:28px;">${t.tf}</span>
        <span style="font-size:11px;font-weight:900;color:${fg};min-width:55px;text-align:center;">${arrow} ${t.dir}</span>
        <span style="font-size:11px;font-weight:900;color:${fg};min-width:60px;text-align:right;">${pctStr}</span>
      </div>`;
  }).join('');
  return `
    <div style="margin-top:8px;padding-top:6px;border-top:1px solid #1a1a1a;">
      <div style="font-size:10px;color:#fff;font-weight:900;margin-bottom:4px;letter-spacing:0.1em;">TIMEFRAME ALIGNMENT ${winning ? '(vs ' + winning + ')' : ''}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px;">
        ${rows}
      </div>
    </div>`;
}

// ── Per-market LIVE avg $/trade row (used in drill-in detail) ─────────────────
function _renderLiveAvgRow(symbol) {
  const pm = (_lastStats && _lastStats.perMarketLive) ? (_lastStats.perMarketLive[symbol] || null) : null;
  if (!pm || !pm.count) {
    return `<div style="margin-top:8px;padding:8px 10px;background:#1a1a1a;border:1px solid #22c55e22;border-radius:5px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:10px;color:#22c55e;font-weight:900;letter-spacing:0.1em;text-transform:uppercase;">LIVE $/Trade</span>
        <span style="font-size:14px;color:#555;font-weight:900;">— no live trades yet</span>
      </div>
    </div>`;
  }
  const avgColor = pm.avgPnl > 0 ? '#22c55e' : pm.avgPnl < 0 ? '#ef4444' : '#ccc';
  const avgStr   = pm.avgPnl >= 0 ? `+A$${pm.avgPnl.toFixed(2)}` : `-A$${Math.abs(pm.avgPnl).toFixed(2)}`;
  const totColor = pm.totalPnl > 0 ? '#22c55e' : pm.totalPnl < 0 ? '#ef4444' : '#ccc';
  const totStr   = pm.totalPnl >= 0 ? `+A$${pm.totalPnl.toFixed(2)}` : `-A$${Math.abs(pm.totalPnl).toFixed(2)}`;
  return `<div style="margin-top:8px;padding:8px 10px;background:#0e1f14;border:1px solid #22c55e55;border-radius:5px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span style="font-size:10px;color:#22c55e;font-weight:900;letter-spacing:0.1em;text-transform:uppercase;">LIVE $/Trade</span>
        <span style="font-size:16px;color:${avgColor};font-weight:900;">${avgStr}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#e8e8e8;font-weight:800;">
        <span>${pm.count} trade${pm.count === 1 ? '' : 's'} · ${pm.wins}W / ${pm.losses}L</span>
        <span>TOTAL <span style="color:${totColor};font-weight:900;">${totStr}</span></span>
      </div>
    </div>`;
}
// Crypto removed — equity-only platform
const CRYPTO_COINS = [
  { sym: 'BTC-USD',  label: 'Bitcoin',   cgId: 'bitcoin',            icon: '₿' },
  { sym: 'ETH-USD',  label: 'Ethereum',  cgId: 'ethereum',           icon: 'Ξ' },
  { sym: 'SOL-USD',  label: 'Solana',    cgId: 'solana',             icon: 'S' },
  { sym: 'BNB-USD',  label: 'BNB',       cgId: 'binancecoin',        icon: 'B' },
  { sym: 'XRP-USD',  label: 'XRP',       cgId: 'ripple',             icon: 'X' },
  { sym: 'ADA-USD',  label: 'Cardano',   cgId: 'cardano',            icon: 'A' },
  { sym: 'AVAX-USD', label: 'Avalanche', cgId: 'avalanche-2',        icon: 'AV' },
  { sym: 'DOGE-USD', label: 'Dogecoin',  cgId: 'dogecoin',           icon: 'D' },
  { sym: 'TRX-USD',  label: 'TRON',      cgId: 'tron',               icon: 'T' },
  { sym: 'LINK-USD', label: 'Chainlink', cgId: 'chainlink',          icon: 'LN' },
  { sym: 'MATIC-USD',label: 'Polygon',   cgId: 'matic-network',      icon: 'M' },
  { sym: 'DOT-USD',  label: 'Polkadot',  cgId: 'polkadot',           icon: 'DO' },
  { sym: 'UNI-USD',  label: 'Uniswap',   cgId: 'uniswap',            icon: 'U' },
  { sym: 'LTC-USD',  label: 'Litecoin',  cgId: 'litecoin',           icon: 'L' },
  { sym: 'ATOM-USD', label: 'Cosmos',    cgId: 'cosmos',             icon: 'AT' },
  { sym: 'ICP-USD',  label: 'ICP',       cgId: 'internet-computer',  icon: 'IC' },
  { sym: 'APT-USD',  label: 'Aptos',     cgId: 'aptos',              icon: 'AP' },
  { sym: 'FIL-USD',  label: 'Filecoin',  cgId: 'filecoin',           icon: 'FI' },
  { sym: 'NEAR-USD', label: 'NEAR',      cgId: 'near',               icon: 'N' },
  { sym: 'ARB-USD',  label: 'Arbitrum',  cgId: 'arbitrum',           icon: 'AR' },
  { sym: 'OP-USD',   label: 'Optimism',  cgId: 'optimism',           icon: 'OP' },
  { sym: 'INJ-USD',  label: 'Injective', cgId: 'injective-protocol', icon: 'INJ' },
  { sym: 'SUI-USD',  label: 'Sui',       cgId: 'sui',                icon: 'SU' },
  { sym: 'FET-USD',  label: 'Fetch.ai',  cgId: 'fetch-ai',           icon: 'FE' },
  { sym: 'WLD-USD',  label: 'Worldcoin', cgId: 'worldcoin-wld',      icon: 'WL' },
];
function cryptoCoinCard(coin, coinData) {
  const d        = coinData || null;
  const ticker   = coin.sym.replace('-USD', '');
  const hasPos   = d && d.status === 'OPEN';
  const signal   = d ? (d.signal || null) : null;
  const regime   = d ? (d.regime || '') : '';
  const liveData  = _cryptoPrices[coin.cgId] || null;
  const rawPrice  = d ? (parseFloat(d.price) || null) : null;
  const livePrice = liveData ? liveData.price : null;
  const displayPrice = rawPrice || livePrice;
  const price = displayPrice ? formatPrice(displayPrice) : null;
  const change24h   = liveData ? liveData.change24h : null;
  const changeStr   = change24h != null ? ((change24h >= 0 ? '+' : '') + change24h.toFixed(2) + '%') : null;
  const changeColor = change24h != null ? (change24h >= 0 ? '#22c55e' : '#ef4444') : '#555';
  const pnlPct     = d ? (parseFloat(d.pnl) || 0) : 0;
  const stake      = d ? (parseFloat(d.size) || 2.0) : 2.0;
  const pnlDollars = stake * pnlPct / 100;
  const pnlColor   = pnlDollars > 0 ? '#22c55e' : pnlDollars < 0 ? '#ef4444' : '#555';
  const pnlStr     = pnlDollars >= 0 ? `+A$${pnlDollars.toFixed(2)}` : `-A$${Math.abs(pnlDollars).toFixed(2)}`;
  const side = d ? (d.side || null) : null;
  const sideColor = side === 'BUY' ? '#22c55e' : side === 'SELL' ? '#ef4444' : '#333';
  const tokenIcon = coin.icon || ticker[0];
  // Lifecycle from market_state (if available)
  const lcData = (_lastState && _lastState.lifecycle) ? (_lastState.lifecycle[coin.sym] || {}) : {};
  const lcWins = lcData.win_count || 0;
  const lcLosses = lcData.loss_count || 0;
  const lcPf = lcData.profit_factor ? parseFloat(lcData.profit_factor).toFixed(2) : '—';
  const lcWr = lcData.win_rate ? (parseFloat(lcData.win_rate) * 100).toFixed(0) : '0';
  const lcPnl = lcData.total_pnl ? parseFloat(lcData.total_pnl) : 0;
  const lcStatus = lcData.lifecycle || 'SIM';
  const wrNum = parseInt(lcWr) || 0;
  const wrColor = wrNum >= 60 ? '#22c55e' : wrNum >= 45 ? '#eab308' : wrNum > 0 ? '#ef4444' : '#555';
  const totalPnlColor = lcPnl > 0 ? '#22c55e' : lcPnl < 0 ? '#ef4444' : '#555';
  const totalPnlStr = lcPnl >= 0 ? `+A$${lcPnl.toFixed(2)}` : `-A$${Math.abs(lcPnl).toFixed(2)}`;
  // Lifecycle badge
  const lcBadge = lcStatus === 'LIVE'
    ? '<span style="background:#14532d;color:#22c55e;border:1px solid #22c55e66;font-size:9px;font-weight:900;padding:1px 6px;border-radius:3px;">LIVE</span>'
    : '<span style="background:#1a1a1a;color:#777;border:1px solid #333;font-size:9px;font-weight:800;padding:1px 6px;border-radius:3px;">SIM</span>';
  // B/S buttons
  const sigBtnB = signal === 'BUY'
    ? '<span style="background:#14532d;color:#22c55e;font-size:10px;font-weight:900;padding:2px 6px;border-radius:3px;">B</span>'
    : '<span style="background:#1a1a1a;color:#444;font-size:10px;font-weight:800;padding:2px 6px;border-radius:3px;">B</span>';
  const sigBtnS = signal === 'SELL'
    ? '<span style="background:#450a0a;color:#ef4444;font-size:10px;font-weight:900;padding:2px 6px;border-radius:3px;">S</span>'
    : '<span style="background:#1a1a1a;color:#444;font-size:10px;font-weight:800;padding:2px 6px;border-radius:3px;">S</span>';
  // Sparkline
  const pnlValues = _getMarketPnlValues(coin.sym);
  const sparkColor = signal === 'BUY' ? '#22c55e' : signal === 'SELL' ? '#ef4444' : (change24h != null ? (change24h >= 0 ? '#22c55e' : '#ef4444') : '#555');
  const sparkline = _buildSparklineSvg(pnlValues, 168, 44, sparkColor);
  // Border
  const borderColor = hasPos ? sideColor : '#1d1d1d';
  // Icon background
  const iconBg = hasPos ? sideColor + '30' : '#1a1a1a';
  const iconClr = hasPos ? sideColor : '#ccc';
  const isExpanded = _expandedCrypto === coin.sym;
  const openTrade = (_lastTrades || []).find(t => t.symbol === coin.sym && t.status === 'OPEN');
  // Inline trade detail on the card itself
  let inlineTradeHtml = '';
  if (openTrade) {
    const tPnl = parseFloat(openTrade.pnl) || 0;
    const tStake = parseFloat(openTrade.size) || 2;
    const tDollarPnl = tStake * tPnl / 100;
    const tPnlColor = tDollarPnl > 0 ? '#22c55e' : tDollarPnl < 0 ? '#ef4444' : '#555';
    const tSide = openTrade.side;
    const tSideColor = tSide === 'BUY' ? '#22c55e' : '#ef4444';
    const tArrow = tSide === 'BUY' ? '▲' : '▼';
    let dur = '';
    if (openTrade.created_at) {
      const created = new Date(openTrade.created_at);
      const diffSec = Math.max(0, Math.floor((new Date() - created) / 1000));
      if (diffSec < 60) dur = diffSec + 's';
      else if (diffSec < 3600) dur = Math.floor(diffSec / 60) + 'm';
      else dur = Math.floor(diffSec / 3600) + 'h ' + Math.floor((diffSec % 3600) / 60) + 'm';
    }
    inlineTradeHtml = `
      <div style="padding:6px 8px;border-top:1px solid #333;background:#1a1a1a;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="color:${tSideColor};font-size:14px;font-weight:900;">${tArrow} ${tSide}</span>
            <span style="color:#fff;font-size:12px;font-weight:800;">A$${tStake.toFixed(0)}</span>
            <span style="color:#888;font-size:11px;">${dur}</span>
          </div>
          <span style="color:${tPnlColor};font-size:16px;font-weight:900;">${tDollarPnl >= 0 ? '+' : ''}A$${tDollarPnl.toFixed(2)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span style="color:#ccc;font-size:11px;">${formatPrice(openTrade.entry_price)} → ${formatPrice(openTrade.current_price)}</span>
          <span style="color:${tPnlColor};font-size:12px;font-weight:800;">${tPnl >= 0 ? '+' : ''}${tPnl.toFixed(2)}%</span>
        </div>
        <button onclick="event.stopPropagation();window.dashboard.closeTrade(${openTrade.id})" style="width:100%;padding:5px 0;background:#2a0a0a;border:1px solid #ef444466;color:#ef4444;font-size:11px;font-weight:900;border-radius:4px;cursor:pointer;font-family:inherit;">CLOSE</button>
      </div>`;
  }
  // Expanded detail (gates, reset)
  let detailHtml = '';
  if (isExpanded) {
    let gateHtml = '';
    if (lcStatus === 'SIM') {
      const pfOk = parseFloat(lcData.profit_factor || 0) >= 1.5;
      const wrOk = parseFloat(lcData.win_rate || 0) >= 0.60;
      gateHtml = `
        <div style="margin-top:6px;padding-top:6px;border-top:1px solid #333;">
          <div style="font-size:10px;color:#ccc;font-weight:800;margin-bottom:4px;">GATES TO LIVE</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <span style="font-size:10px;padding:2px 6px;border-radius:3px;${pfOk ? 'background:#14532d;color:#22c55e;' : 'background:#1a1a1a;color:#555;'}">PF ${lcPf}</span>
            <span style="font-size:10px;padding:2px 6px;border-radius:3px;${wrOk ? 'background:#14532d;color:#22c55e;' : 'background:#1a1a1a;color:#555;'}">WR ${lcWr}%</span>
          </div>
        </div>`;
    }
    detailHtml = `
      <div style="padding:4px 8px 8px;border-top:1px solid #333;" onclick="event.stopPropagation()">
        ${changeStr ? `<div style="margin-top:4px;"><span style="color:#ccc;font-size:11px;">24h</span> <span style="color:${changeColor};font-size:12px;font-weight:800;">${changeStr}</span></div>` : ''}
        ${_renderLiveAvgRow(coin.sym)}
        ${gateHtml}
        <div style="margin-top:6px;">
          <button onclick="event.stopPropagation();window.dashboard.resetMarketNow('${coin.sym}')" style="width:100%;padding:4px 0;background:#1a1a1a;border:1px solid #333;color:#555;font-size:10px;font-weight:700;border-radius:4px;cursor:pointer;font-family:inherit;">RESET TO SIM</button>
        </div>
      </div>`;
  }
  const borderColorFinal = hasPos ? sideColor : '#3a3a3a';
  return `
    <div onclick="window.dashboard.expandCrypto('${coin.sym}')" style="min-width:190px;flex:1 1 190px;max-width:240px;background:#2a2a2a;border:1px solid ${borderColorFinal};border-radius:8px;overflow:hidden;cursor:pointer;transition:border-color 0.15s;">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;background:#222;border-bottom:1px solid #333;">
        <div style="display:flex;align-items:center;gap:4px;">
          ${lcBadge}
          <span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;background:${iconBg};color:${iconClr};font-size:10px;font-weight:900;border-radius:50%;">${tokenIcon}</span>
          <span style="font-size:12px;font-weight:900;color:#fff;">${ticker}</span>
        </div>
        <div style="display:flex;gap:3px;">
          ${sigBtnB} ${sigBtnS}
        </div>
      </div>
      <div style="padding:6px 8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;">
          <span style="font-size:16px;font-weight:900;color:#fff;">${price || '—'}</span>
          ${changeStr ? `<span style="color:${changeColor};font-size:13px;font-weight:900;">${changeStr}</span>` : `<span style="color:${totalPnlColor};font-size:13px;font-weight:900;">${totalPnlStr}</span>`}
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span style="font-size:12px;font-weight:900;text-transform:uppercase;${
            (() => {
              // Derive regime from 24h change if no regime from engine
              const ch = change24h || 0;
              const absC = Math.abs(ch);
              if (absC > 3) return ch > 0 ? 'color:#22c55e;">▲ TRENDING UP' : 'color:#ef4444;">▼ TRENDING DOWN';
              if (absC > 1) return ch > 0 ? 'color:#f97316;">↻ REVERSAL' : 'color:#f97316;">↻ REVERSAL';
              return 'color:#eab308;">◆ CHOPPY';
            })()
          }</span>
          <span style="color:${wrColor};font-size:11px;font-weight:900;">${wrNum > 0 ? wrNum + '% WR' : '—'}</span>
        </div>
        <div style="margin:2px 0 4px;background:#222;border-radius:4px;overflow:hidden;">
          ${sparkline || '<div style="height:44px;background:#222;"></div>'}
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="color:#ccc;font-size:11px;font-weight:800;">${lcWins}W / ${lcLosses}L</span>
          <span style="color:#ccc;font-size:10px;font-weight:700;">PF ${lcPf}</span>
        </div>
      </div>
      ${inlineTradeHtml}
      ${detailHtml}
    </div>`;
}
function renderCrypto(engines, cryptoCoins) {
  const scalp = (engines || {}).crypto_scalp || {};
  const longE = (engines || {}).crypto_long  || {};
  const coins = cryptoCoins || {};
  // Build combined coin map — merge scalp and long data per symbol
  const scalpMap = {};
  const longMap  = {};
  const combinedMap = {};
  for (const [key, data] of Object.entries(coins)) {
    const d = data;
    if (!d) continue;
    const sym = d.symbol || key.split('::')[1];
    if (d.engine === 'crypto_scalp') scalpMap[sym] = d;
    if (d.engine === 'crypto_long')  longMap[sym]  = d;
  }
  // Merge: prefer open position data, fall back to whichever has data
  for (const c of CRYPTO_COINS) {
    const s = scalpMap[c.sym];
    const l = longMap[c.sym];
    if (s && s.status === 'OPEN') combinedMap[c.sym] = s;
    else if (l && l.status === 'OPEN') combinedMap[c.sym] = l;
    else if (s) combinedMap[c.sym] = s;
    else if (l) combinedMap[c.sym] = l;
    else combinedMap[c.sym] = null;
  }
  // Render single unified crypto panel into whichever container exists
  const panel = el('crypto-scalp-cards') || el('crypto-long-cards');
  if (panel) {
    // Sort: open positions first
    const sorted = [...CRYPTO_COINS].sort((a, b) => {
      const aD = combinedMap[a.sym] || {};
      const bD = combinedMap[b.sym] || {};
      const aPos = aD.status === 'OPEN' ? 0 : 1;
      const bPos = bD.status === 'OPEN' ? 0 : 1;
      return (aPos - bPos);
    });
    const cards = sorted.map(c => cryptoCoinCard(c, combinedMap[c.sym])).join('');
    panel.innerHTML = `<div class="market-grid">${cards}</div>`;
  }
  // Clear the other panel if it exists
  const otherPanel = el('crypto-long-cards');
  if (otherPanel && otherPanel !== panel) otherPanel.innerHTML = '';
  const oldScalpPanel = el('crypto-scalp-cards');
  if (oldScalpPanel && oldScalpPanel !== panel) oldScalpPanel.innerHTML = '';
  // Legacy
  const old = el('crypto-cards');
  if (old) old.innerHTML = '';
}
// ── Render: Active Trades (prominent cards) ────────────────────────────────────
function _activeTradeCard(t) {
  const isBuy           = t.side === 'BUY';
  const pnlPctGross     = parseFloat(t.pnl) || 0;
  const stake           = parseFloat(t.size) || 2.0;
  const BROKER_FEE_PCT  = 0.1;
  const pnlPct          = pnlPctGross - BROKER_FEE_PCT;
  const pnlDollars      = stake * pnlPct / 100;
  const pnlCls          = pnlDollars > 0 ? 'pnl-up' : pnlDollars < 0 ? 'pnl-down' : 'pnl-zero';
  const pnlStr          = pnlDollars >= 0 ? `+A$${pnlDollars.toFixed(2)}` : `-A$${Math.abs(pnlDollars).toFixed(2)}`;
  const pnlPctStr       = (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%';
  const trendArrow      = pnlPct > 0 ? '↑' : pnlPct < 0 ? '↓' : '→';
  const simTag     = t.is_sim ? '<span style="background:#1a1a1a;color:#888;font-size:10px;font-weight:800;padding:2px 6px;border-radius:3px;">SIM</span>' : '<span style="background:#14532d;color:#22c55e;font-size:10px;font-weight:900;padding:2px 6px;border-radius:3px;">LIVE</span>';
  const engine     = (t.engine || '').replace(/_/g, ' ').toUpperCase();
  const arrow      = isBuy ? '▲' : '▼';
  const arrowClr   = isBuy ? '#22c55e' : '#ef4444';
  const sideClr    = isBuy ? '#22c55e' : '#ef4444';
  // Get flag or token icon
  let symbolIcon = '';
  if (t.engine === 'equity') {
    const mkt = EQUITY_MARKETS.find(m => m.key === t.symbol);
    symbolIcon = mkt ? `<span style="font-size:18px;margin-right:4px;">${mkt.flag}</span>` : '';
  } else {
    const coin = CRYPTO_COINS.find(c => c.sym === t.symbol);
    const icon = coin ? coin.icon : t.symbol.replace('-USD','')[0];
    symbolIcon = `<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;background:${arrowClr}30;color:${arrowClr};font-size:11px;font-weight:900;border-radius:50%;margin-right:4px;">${icon}</span>`;
  }
  // Duration since trade opened
  let durationStr = '';
  if (t.created_at) {
    const created = new Date(t.created_at);
    const now = new Date();
    const diffSec = Math.max(0, Math.floor((now - created) / 1000));
    if (diffSec < 60) durationStr = diffSec + 's';
    else if (diffSec < 3600) durationStr = Math.floor(diffSec / 60) + 'm ' + (diffSec % 60) + 's';
    else durationStr = Math.floor(diffSec / 3600) + 'h ' + Math.floor((diffSec % 3600) / 60) + 'm';
  }
  const isExpandedRow = (_expandedActiveTrade === t.symbol);
  const mkState = (_lastState && _lastState.markets) ? _lastState.markets[t.symbol] : null;
  const lcState = (_lastState && _lastState.lifecycle) ? (_lastState.lifecycle[t.symbol] || {}) : {};
  return `
    <div class="active-trade-card" data-trade-sym="${t.symbol}" onclick="window.dashboard.expandActiveTrade('${t.symbol}')" style="border-left:4px solid ${arrowClr};width:100%;box-sizing:border-box;padding:10px 16px;cursor:pointer;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:8px;">
          ${symbolIcon}
          <span style="font-size:18px;font-weight:900;color:${sideClr}">${arrow} ${t.side}</span>
          <span style="font-size:18px;font-weight:900;color:#ffffff">${escHtml(t.symbol)}</span>
          <span style="font-size:11px;color:#aaa;background:#1a1a1a;padding:2px 6px;border-radius:4px;font-weight:700;">${engine}</span>
          ${simTag}
          <span style="color:#555;font-size:12px;font-weight:700;">Entry ${formatPrice(t.entry_price)} → ${formatPrice(t.current_price)}</span>
          ${durationStr ? `<span style="color:#666;font-size:11px;font-weight:700;">${durationStr}</span>` : ''}
          <span style="color:#555;font-size:12px;font-weight:900;margin-left:4px;">${isExpandedRow ? '▲' : '▼'}</span>
        </div>
        <div style="display:flex;align-items:center;gap:14px;">
          <span class="${pnlCls}" style="font-size:16px;font-weight:900">${pnlPctStr} ${trendArrow}</span>
          <span class="${pnlCls}" style="font-size:20px;font-weight:900">${pnlStr}</span>
          <button onclick="event.stopPropagation();window.dashboard.closeTrade(${t.id})" style="padding:6px 14px;background:#1a0a0a;border:1px solid #ef444466;color:#ef4444;font-size:12px;font-weight:900;letter-spacing:0.06em;text-transform:uppercase;border-radius:4px;cursor:pointer;font-family:inherit;white-space:nowrap;" onmouseover="this.style.background='#2d0a0a';this.style.borderColor='#ef4444'" onmouseout="this.style.background='#1a0a0a';this.style.borderColor='#ef444466'">CLOSE</button>
        </div>
      </div>
      ${isExpandedRow ? _renderMarketDetail(t.symbol, mkState, lcState, t) : ''}
    </div>`;
}
// ── Engine stats calculator ────────────────────────────────────────────────────
function calcEngineStats(trades, engineKey) {
  const closed = (trades || []).filter(t => t.engine === engineKey && t.status === 'CLOSED');
  if (closed.length === 0) return null;
  let wins = 0, losses = 0, profitSum = 0, lossSum = 0, totalPnl = 0;
  for (const t of closed) {
    const stake = parseFloat(t.size) || 2.0;
    const pnlPct = parseFloat(t.pnl) || 0;
    const pnlDollars = stake * pnlPct / 100;
    totalPnl += pnlDollars;
    if (pnlPct > 0) { wins++; profitSum += pnlDollars; }
    else { losses++; lossSum += Math.abs(pnlDollars); }
  }
  const total = wins + losses;
  const winRate = total > 0 ? Math.round(wins / total * 100) : 0;
  const profitFactor = lossSum > 0 ? (profitSum / lossSum).toFixed(2) : profitSum > 0 ? '∞' : '—';
  return { wins, losses, winRate, profitFactor, totalPnl };
}
function renderEngineTabStats(trades) {
  const engines = ['equity', 'crypto_scalp', 'crypto_long'];
  for (const eng of engines) {
    const statsEl = el(`etab-stats-${eng}`);
    if (!statsEl) continue;
    const s = calcEngineStats(trades, eng);
    if (!s) {
      statsEl.textContent = '';
      continue;
    }
    const pnlStr = s.totalPnl >= 0
      ? `+A$${s.totalPnl.toFixed(2)}`
      : `-A$${Math.abs(s.totalPnl).toFixed(2)}`;
    const pnlColor = s.totalPnl > 0 ? '#22c55e' : s.totalPnl < 0 ? '#ef4444' : '#aaa';
    statsEl.innerHTML = `<span style="color:#aaa">${s.winRate}% WR · PF ${s.profitFactor} · ${s.wins}W/${s.losses}L · </span><span style="color:${pnlColor};font-weight:800">${pnlStr}</span>`;
  }
}
function renderEngineSummaryBoxes(engines, trades) {
  const cfg = [
    { key: 'equity', dotId: 'summary-equity-dot', statusId: 'summary-equity-status', statsId: 'summary-equity-stats' },
  ];
  for (const c of cfg) {
    const eng     = (engines || {})[c.key] || {};
    const dotEl   = el(c.dotId);
    const stEl    = el(c.statusId);
    const statsEl = el(c.statsId);
    const status      = (eng.status || '').toUpperCase();
    const statusColor = status === 'RUNNING' ? '#22c55e' : status === 'QUIET' ? '#eab308' : '#555';
    const statusBg    = status === 'RUNNING' ? '#22c55e18' : status === 'QUIET' ? '#eab30818' : '#ffffff08';
    // Coloured left border by status
    const boxEl = document.querySelector('.engine-summary-box[data-engine="' + c.key + '"]');
    if (boxEl) {
      boxEl.style.borderLeft = status === 'RUNNING' ? '3px solid #22c55e'
                             : status === 'QUIET'   ? '3px solid #eab308'
                             : '3px solid #333';
    }
    // Status dot
    if (dotEl) dotEl.className = 'dot ' + (status === 'RUNNING' ? 'dot-green' : status === 'QUIET' ? 'dot-yellow' : 'dot-grey');
    // Status badge pill
    if (stEl) stEl.innerHTML = `<span style="background:${statusBg};color:${statusColor};border:1px solid ${statusColor}40;font-size:10px;font-weight:700;padding:1px 7px;border-radius:10px;letter-spacing:0.06em;">${status || '—'}</span>`;
    if (!statsEl) continue;
    // Open positions + live P&L
    const openTrades = (trades || []).filter(t => t.status === 'OPEN' && t.engine === c.key);
    const open = openTrades.length;
    const livePnl = openTrades.reduce((sum, t) => {
      const stake = parseFloat(t.size) || 2.0;
      const pnl   = parseFloat(t.pnl)  || 0;
      return sum + (stake * pnl / 100);
    }, 0);
    const livePnlColor = livePnl > 0 ? '#22c55e' : livePnl < 0 ? '#ef4444' : '#555';
    const livePnlStr   = livePnl >= 0 ? `+A$${livePnl.toFixed(2)}` : `-A$${Math.abs(livePnl).toFixed(2)}`;
    // Closed trade stats
    const s        = calcEngineStats(trades, c.key);
    const pnlColor = s && s.totalPnl > 0 ? '#22c55e' : s && s.totalPnl < 0 ? '#ef4444' : '#aaa';
    const pnlStr   = s ? (s.totalPnl >= 0 ? `+A$${s.totalPnl.toFixed(2)}` : `-A$${Math.abs(s.totalPnl).toFixed(2)}`) : '';
    // Top 5 biggest losers for this engine
    const closedByMarket = {};
    for (const t of (trades || [])) {
      if (t.engine !== c.key || t.status !== 'CLOSED') continue;
      const sym = t.symbol;
      if (!closedByMarket[sym]) closedByMarket[sym] = { pnl: 0, count: 0 };
      const stake = parseFloat(t.size) || 2.0;
      const pnlPct = parseFloat(t.pnl) || 0;
      closedByMarket[sym].pnl += stake * pnlPct / 100;
      closedByMarket[sym].count++;
    }
    const sorted = Object.entries(closedByMarket)
      .map(([sym, d]) => ({ sym, pnl: d.pnl, count: d.count }))
      .sort((a, b) => a.pnl - b.pnl)
      .slice(0, 5);
    let losersHtml = '';
    if (sorted.length > 0 && sorted[0].pnl < 0) {
      const items = sorted.filter(s => s.pnl < 0).map(s => {
        const clr = '#ef4444';
        const amt = `-A$${Math.abs(s.pnl).toFixed(2)}`;
        // Find flag or icon
        const mkt = EQUITY_MARKETS.find(m => m.key === s.sym);
        const coin = CRYPTO_COINS.find(cc => cc.sym === s.sym);
        const icon = mkt ? mkt.flag : coin ? coin.icon : s.sym.slice(0,2);
        const name = mkt ? mkt.label : (coin ? s.sym.replace('-USD','') : s.sym);
        return `<span style="display:inline-flex;align-items:center;gap:3px;padding:2px 6px;background:#1a0a0a;border:1px solid #ef444420;border-radius:4px;font-size:10px;"><span>${icon}</span><span style="color:#fff;font-weight:700;">${name}</span><span style="color:${clr};font-weight:900;">${amt}</span></span>`;
      }).join('');
      losersHtml = `<div style="display:flex;align-items:center;gap:4px;margin-top:4px;padding:4px 8px;overflow-x:auto;"><span style="font-size:9px;color:#ef4444;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;flex-shrink:0;">COSTLY</span>${items}</div>`;
    }
    statsEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:0;justify-content:space-between;">
        <div style="text-align:center;flex:1;padding:4px 0;">
          <div style="font-size:10px;color:#ccc;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">OPEN</div>
          <div style="font-size:22px;font-weight:900;color:#fff;">${open}</div>
        </div>
        <div style="width:1px;height:32px;background:#1a1a1a;"></div>
        <div style="text-align:center;flex:1;padding:4px 0;">
          <div style="font-size:10px;color:#ccc;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">LIVE P&amp;L</div>
          <div style="font-size:18px;font-weight:900;color:${livePnlColor};">${livePnlStr}</div>
        </div>
        <div style="width:1px;height:32px;background:#1a1a1a;"></div>
        <div style="text-align:center;flex:1;padding:4px 0;">
          <div style="font-size:10px;color:#ccc;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">WIN RATE</div>
          <div style="font-size:18px;font-weight:900;color:${s && s.winRate >= 60 ? '#22c55e' : s && s.winRate < 50 ? '#ef4444' : '#eab308'};">${s ? s.winRate + '%' : '0%'}</div>
        </div>
        <div style="width:1px;height:32px;background:#1a1a1a;"></div>
        <div style="text-align:center;flex:1;padding:4px 0;">
          <div style="font-size:10px;color:#ccc;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">W / L</div>
          <div style="font-size:16px;font-weight:900;color:#ccc;">${s ? s.wins : 0}<span style="color:#333;"> / </span>${s ? s.losses : 0}</div>
        </div>
        <div style="width:1px;height:32px;background:#1a1a1a;"></div>
        <div style="text-align:center;flex:1;padding:4px 0;">
          <div style="font-size:10px;color:#ccc;font-weight:800;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">NET P&amp;L</div>
          <div style="font-size:18px;font-weight:900;color:${pnlColor};">${pnlStr || 'A$0.00'}</div>
        </div>
      </div>
      ${losersHtml}`;
  }
}
function renderActiveTrades(trades) {
  // Render ALL open trades in the global active trades section
  const globalContainer = el('all-active-trades');
  const countEl = el('active-trades-count');
  const open = (trades || []).filter(t => t.status === 'OPEN');
  if (countEl) countEl.textContent = open.length > 0 ? open.length + ' OPEN' : '';
  if (globalContainer) {
    if (open.length === 0) {
      globalContainer.innerHTML = '<div style="color:#555;font-size:14px;padding:12px 0;text-align:center;">No open positions</div>';
    } else {
      globalContainer.innerHTML = open.map(_activeTradeCard).join('');
    }
  }
  // Also render per-engine (for the engine panels that still have containers)
  const engines = ['equity', 'crypto_scalp', 'crypto_long'];
  for (const eng of engines) {
    const container = el(`active-trades-${eng}`);
    if (!container) continue;
    container.innerHTML = '';
  }
}
// ── Render: Trade table ────────────────────────────────────────────────────────
function _tradeRow(t) {
  const side       = t.side === 'BUY' ? '<span class="side-buy">BUY</span>' : '<span class="side-sell">SELL</span>';
  const simTag     = t.is_sim ? '<span class="sim-tag">SIM</span>' : '<span class="live-tag">LIVE</span>';
  const stakeStr   = t.size != null ? `A$${parseFloat(t.size).toFixed(2)}` : '—';
  const levelStr   = t.kitty_level != null ? `L${t.kitty_level}` : '—';
  const slStr      = t.stop_loss_price != null ? formatPrice(t.stop_loss_price) : '—';
  // Dollar P&L: stake × (pnl% - broker_fee%) / 100
  const pnlPctGrossRow  = parseFloat(t.pnl) || 0;
  const stake           = parseFloat(t.size) || 2.0;
  const BROKER_FEE_PCT  = 0.1;                         // 0.1% round-trip Pepperstone CFD fee
  const pnlPctRow       = pnlPctGrossRow - BROKER_FEE_PCT;
  const pnlDollars      = stake * pnlPctRow / 100;
  const pnlDollarStr    = pnlDollars > 0
    ? `<span class="pnl-up">+A$${pnlDollars.toFixed(2)}</span>`
    : pnlDollars < 0
    ? `<span class="pnl-down">-A$${Math.abs(pnlDollars).toFixed(2)}</span>`
    : '<span class="pnl-zero">A$0.00</span>';
  return `
    <tr>
      <td><strong>${escHtml(t.symbol)}</strong></td>
      <td>${side}</td>
      <td>${formatPrice(t.entry_price)}</td>
      <td>${formatPrice(t.current_price)}</td>
      <td>${pnlDollarStr}</td>
      <td>${stakeStr} <span style="color:#aaaaaa;font-size:10px">${levelStr}</span></td>
      <td style="color:#aaaaaa">${slStr}</td>
      <td>${statusPill(t.status)}</td>
      <td class="time-cell">${formatTime(t.created_at)}</td>
    </tr>`;
}
function renderTrades(trades) {
  // Normalise
  if (trades && !Array.isArray(trades)) {
    trades = trades.trades || trades.result || trades.data || [];
  }
  if (!trades || !Array.isArray(trades)) trades = [];
  const engines = ['equity', 'crypto_scalp', 'crypto_long'];
  for (const eng of engines) {
    const tbody = el(`trades-tbody-${eng}`);
    if (!tbody) continue;
    const subset = trades.filter(t => t.engine === eng);
    if (subset.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="no-trades">No trades yet.</td></tr>';
    } else {
      tbody.innerHTML = subset.map(_tradeRow).join('');
    }
  }
}
// ── Render: Lifecycle table (Controls tab) ────────────────────────────────────
// ── Render: Kitty detail (Systems tab) ───────────────────────────────────────
function renderKittyDetail(kitty) {
  const container = el('kitty-detail');
  if (!container || !kitty) return;
  const bal      = (kitty.balance != null ? kitty.balance : 500).toFixed(2);
  const avail    = (kitty.available != null ? kitty.available : kitty.balance - (kitty.reserved || 0)).toFixed(2);
  const reserved = (kitty.reserved || 0).toFixed(2);
  const balNum   = parseFloat(bal);
  const availNum = parseFloat(avail);
  container.innerHTML = `
    <div class="card" style="padding:12px;">
      <div style="display:flex;gap:20px;margin-bottom:10px;flex-wrap:wrap;">
        <div class="kitty-stat">
          <div class="kitty-label">Balance</div>
          <div class="kitty-value ${balNum >= 1000 ? 'pnl-up' : balNum < 500 ? 'pnl-down' : ''}">A$${bal}</div>
        </div>
        <div class="kitty-stat">
          <div class="kitty-label">Available</div>
          <div class="kitty-value">A$${avail}</div>
        </div>
        <div class="kitty-stat">
          <div class="kitty-label">Reserved</div>
          <div class="kitty-value ${parseFloat(reserved) > 0 ? 'pnl-down' : ''}">A$${reserved}</div>
        </div>
        <div class="kitty-stat">
          <div class="kitty-label">Max Exposure</div>
          <div class="kitty-value">A$62.00</div>
        </div>
      </div>
    </div>
  `;
}
// ── Render: Open trades (Systems tab) ─────────────────────────────────────────
function renderOpenTrades(trades) {
  const tbody = el('open-trades-tbody');
  if (!tbody) return;
  const open = (trades || []).filter(t => t.status === 'OPEN');
  if (open.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="no-trades">No open trades</td></tr>';
    return;
  }
  tbody.innerHTML = open.map(t => {
    const side = t.side === 'BUY' ? '<span class="side-buy">BUY</span>' : '<span class="side-sell">SELL</span>';
    const pnl  = t.pnl > 0
      ? `<span class="pnl-up">+A$${parseFloat(t.pnl).toFixed(2)}</span>`
      : t.pnl < 0
        ? `<span class="pnl-down">-A$${Math.abs(parseFloat(t.pnl)).toFixed(2)}</span>`
        : '<span class="pnl-zero">—</span>';
    return `<tr>
      <td><strong>${escHtml(t.symbol)}</strong></td>
      <td>${side}</td>
      <td>${formatPrice(t.entry_price)}</td>
      <td>${formatPrice(t.current_price)}</td>
      <td>${pnl}</td>
      <td style="color:#444">${t.stop_loss_price ? formatPrice(t.stop_loss_price) : '—'}</td>
    </tr>`;
  }).join('');
}
// ── Render: Kitty history (Systems tab) ───────────────────────────────────────
function renderKittyHistory(kitty) {
  const container = el('kitty-history');
  if (!container) return;
  const history = kitty?.history || [];
  if (history.length === 0) {
    container.innerHTML = '<div style="color:#444;font-size:11px;padding:8px">No kitty history yet</div>';
    return;
  }
  container.innerHTML = `
    <div class="table-wrap" style="border-radius:6px">
      <table>
        <thead><tr>
          <th>Event</th><th>Amount</th><th>Balance After</th><th>Market</th><th>Time</th>
        </tr></thead>
        <tbody>
          ${history.map(h => {
            const evClass = h.event === 'WIN' ? 'pnl-up' : h.event === 'LOSS' ? 'pnl-down' : '';
            const amtSign = h.event === 'WIN' ? '+' : h.event === 'LOSS' ? '-' : '';
            return `<tr>
              <td class="${evClass}" style="font-weight:700">${escHtml(h.event)}</td>
              <td>${amtSign ? `<span class="${evClass}">${amtSign}A$${Math.abs(h.amount).toFixed(2)}</span>` : `A$${h.amount.toFixed(2)}`}</td>
              <td>A$${parseFloat(h.balance_after).toFixed(2)}</td>
              <td style="color:#666">${escHtml(h.market || '—')}</td>
              <td class="time-cell">${formatTime(h.created_at)}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}
// ── Render: Swarm detail (Intelligence tab) ───────────────────────────────────
function renderSwarmDetail(swarm) {
  const container = el('swarm-detail');
  if (!container) return;
  const patterns = swarm?.patterns || [];
  if (patterns.length === 0) {
    container.innerHTML = '<div style="color:#444;font-size:11px;padding:8px">No swarm patterns yet</div>';
    return;
  }
  container.innerHTML = `
    <div class="table-wrap" style="border-radius:6px">
      <table>
        <thead><tr>
          <th>Pattern</th><th>Votes</th><th>Gated</th><th>Markets</th>
        </tr></thead>
        <tbody>
          ${patterns.map(p => `<tr>
            <td style="font-weight:700;color:#bbb">${escHtml(p.pattern)}</td>
            <td style="color:#666">${p.votes}</td>
            <td>${p.gated ? '<span style="color:#ef4444;font-weight:700">YES</span>' : '<span style="color:#444">no</span>'}</td>
            <td style="color:#555;font-size:10px">${escHtml((p.markets || []).join(', '))}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div style="color:#555;font-size:10px;margin-top:6px">${swarm.active_gates || 0} active gates</div>
  `;
}
// renderRanges removed — crypto/legacy feature
// ── Render: System events (Sys Audit tab) ─────────────────────────────────────
function renderSystemEvents(events) {
  const container = el('events-panel');
  if (!container) return;
  if (!events || events.length === 0) {
    container.innerHTML = '<div style="color:#444;font-size:11px;padding:8px">No system events yet</div>';
    return;
  }
  container.innerHTML = events.map(ev => {
    const lvl = (ev.level || 'INFO').toUpperCase();
    const lvlClass = lvl === 'WARN' || lvl === 'WARNING' ? 'ev-warn'
                   : lvl === 'ERROR' ? 'ev-error'
                   : lvl === 'DEBUG' ? 'ev-debug'
                   : 'ev-info';
    return `
    <div class="event-row">
      <span class="event-level ${lvlClass}">${escHtml(lvl)}</span>
      <span class="event-source">${escHtml(ev.source)}</span>
      <span class="event-msg">${escHtml(ev.message)}</span>
      <span class="event-time">${formatTime(ev.created_at)}</span>
    </div>`;
  }).join('');
}
// ── Render: Engine status detail (Sys Audit tab) ──────────────────────────────
function renderEngineStatusDetail(engines) {
  const container = el('engine-status-detail');
  if (!container) return;
  const defs = [
    { key: 'equity',       label: 'Equity Engine' },
    { key: 'crypto_scalp', label: 'Crypto Scalp' },
    { key: 'crypto_long',  label: 'Crypto Long' },
  ];
  container.innerHTML = `
    <div class="card" style="padding:12px;">
      ${defs.map(({ key, label }) => {
        const e = (engines || {})[key] || {};
        const status = e.status || 'UNKNOWN';
        return `
          <div class="cron-row">
            <span class="cron-name">${label}</span>
            <span class="cron-status">
              <span class="${engineDot(status)}"></span>
              <span style="margin-left:6px">${escHtml(status)}</span>
              ${e.count != null ? `<span style="color:#444;margin-left:8px;font-size:10px">${e.count} signals</span>` : ''}
            </span>
          </div>`;
      }).join('')}
    </div>
  `;
}
// ── Tab switching ─────────────────────────────────────────────────────────────
function initTabs() {
  // Command Center tabs
  document.querySelectorAll('.cmd-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.cmd-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.cmd-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = el(`tab-${target}`);
      if (panel) panel.classList.add('active');
      // Lazy-load tab data on first open
      if (target === 'systems') loadSystemsTab();
      if (target === 'intelligence') loadIntelligenceTab();
      if (target === 'sysaudit') loadSysAuditTab();
    });
  });
  // Engine panels are always visible — no tab switching needed
}
async function loadSystemsTab() {
  try {
    const [kitty, trades] = await Promise.all([
      rpcCall('getKittySummary'),
      rpcCall('getTrades'),
    ]);
    renderKittyDetail(kitty);
    renderOpenTrades(trades);
    renderKittyHistory(kitty);
  } catch (err) {
    console.error('loadSystemsTab error:', err);
  }
}
async function loadIntelligenceTab() {
  try {
    const swarm = await rpcCall('getSwarmSummary');
    renderSwarmDetail(swarm);
    renderRanges([]);
  } catch (err) {
    console.error('loadIntelligenceTab error:', err);
  }
}
async function loadSysAuditTab() {
  try {
    const [events, state] = await Promise.all([
      rpcCall('getSystemEvents'),
      rpcCall('getMarketState'),
    ]);
    renderSystemEvents(events);
    renderEngineStatusDetail(state?.engines || {});
  } catch (err) {
    console.error('loadSysAuditTab error:', err);
  }
}
// ── Render: Right column market cards based on active engine ──────────────────
function renderAllMarketCards() {
  const container = el('all-market-cards');
  if (!container) return;
  const active = _activeEnginePanel;
  if (!active) {
    // Equity-only platform — only equity market grid
    container.innerHTML = `<div id="market-cards"></div>`;
    if (_lastState) {
      renderMarkets((_lastState || {}).markets, (_lastState || {}).lifecycle);
    }
  } else if (active === 'equity') {
    container.innerHTML = '<div id="market-cards"></div>';
    if (_lastState) renderMarkets((_lastState || {}).markets, (_lastState || {}).lifecycle);
  } else {
    container.innerHTML = '<div id="market-cards"></div>';
    if (_lastState) renderMarkets((_lastState || {}).markets, (_lastState || {}).lifecycle);
  }
}
// ── Render: Closed trades (last 10) ───────────────────────────────────────────
function renderClosedTrades(trades) {
  const container = el('closed-trades-panel');
  if (!container) return;
  const closed = (trades || []).filter(t => t.status === 'CLOSED')
    .sort((a, b) => (b.id || 0) - (a.id || 0)).slice(0, 10);
  if (closed.length === 0) {
    container.innerHTML = '<div style="color:#444;font-size:12px;text-align:center;padding:12px 0;">No closed trades yet</div>';
    return;
  }
  container.innerHTML = closed.map(t => {
    const pnl = parseFloat(t.pnl) || 0;
    const stake = parseFloat(t.size) || 50;
    const dollars = stake * pnl / 100;
    const c = pnl > 0 ? '#22c55e' : pnl < 0 ? '#ef4444' : '#888';
    const arrow = t.side === 'BUY' ? '▲' : '▼';
    const sideC = t.side === 'BUY' ? '#22c55e' : '#ef4444';
    const tag = t.is_sim
      ? '<span style="background:#1d1d1d;color:#888;font-size:8px;font-weight:800;padding:1px 5px;border-radius:3px;">SIM</span>'
      : '<span style="background:#14532d;color:#22c55e;font-size:8px;font-weight:800;padding:1px 5px;border-radius:3px;">LIVE</span>';
    const reason = (t.reason || '').toUpperCase();
    const exitTag = reason.includes('SL_HIT')
      ? '<span style="background:#450a0a;color:#ef4444;font-size:8px;font-weight:900;padding:1px 5px;border-radius:3px;">SL</span>'
      : reason.includes('TS_HIT')
        ? '<span style="background:#1e3a5f;color:#60a5fa;font-size:8px;font-weight:900;padding:1px 5px;border-radius:3px;">TS</span>'
        : '';
    const slVal = t.stop_loss_price ? `SL ${parseFloat(t.stop_loss_price).toFixed(2)}` : '';
    const tsVal = t.trailing_stop_price ? `TS ${parseFloat(t.trailing_stop_price).toFixed(2)}` : '';
    const stakeStr = `A$${stake.toFixed(2)}`;
    return `<div data-testid="closed-trade-${t.id}" style="display:flex;flex-direction:column;gap:3px;padding:6px 10px;background:#0f0f0f;border:1px solid #1a1a1a;border-left:2px solid ${c};border-radius:4px;font-size:11px;">
      <div style="display:flex;align-items:center;gap:6px;">
        ${tag}${exitTag}
        <span style="color:${sideC};font-weight:900;">${arrow}</span>
        <span style="color:#fff;font-weight:900;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escHtml(t.symbol)}</span>
        <span style="color:#666;font-size:9px;">${stakeStr}</span>
        <span style="color:${c};font-weight:900;min-width:60px;text-align:right;">${dollars >= 0 ? '+' : ''}A$${dollars.toFixed(2)}</span>
      </div>
      <div style="display:flex;gap:12px;padding-left:2px;">
        <span style="color:#333;font-size:9px;">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</span>
        ${slVal ? `<span style="color:#555;font-size:9px;">${slVal}</span>` : ''}
        ${tsVal ? `<span style="color:#555;font-size:9px;">${tsVal}</span>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ── Render: "Other Stats" right column ───────────────────────────────────────
function renderOtherStats() {
  const container = el('other-stats-panel');
  if (!container) return;
  const markets = (_lastState && _lastState.markets) || {};
  const arr = Object.entries(markets).map(([k, m]) => ({ key: k, ...m }));
  // Regime distribution
  const regimes = {};
  for (const m of arr) {
    const r = (m.regime || '—').replace('CHOPPY_HIGH', 'CHOPPY').replace('CHOPPY_MEDIUM', 'CHOPPY').replace('CHOPPY_LOW', 'CHOPPY');
    regimes[r] = (regimes[r] || 0) + 1;
  }
  const regimeRows = Object.entries(regimes)
    .sort((a, b) => b[1] - a[1])
    .map(([r, c]) => {
      const color = r === 'TRENDING' ? '#22c55e' : r === 'REVERSAL' ? '#a855f7' : r === 'CHOPPY' ? '#eab308' : '#666';
      return `<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:11px;">
        <span style="color:${color};font-weight:800;">${r}</span>
        <span style="color:#ccc;font-weight:900;">${c}</span>
      </div>`;
    }).join('');
  // Top movers by |WPS|
  const sortedByWps = [...arr]
    .filter(m => m.wps != null)
    .sort((a, b) => Math.abs(parseFloat(b.wps) || 0) - Math.abs(parseFloat(a.wps) || 0))
    .slice(0, 5);
  const moversRows = sortedByWps.map(m => {
    const w = parseFloat(m.wps) || 0;
    const c = w > 0 ? '#22c55e' : w < 0 ? '#ef4444' : '#888';
    const def = EQUITY_MARKETS.find(e => e.key === m.key);
    const lbl = def ? def.label : m.key;
    return `<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:11px;">
      <span style="color:#ccc;">${lbl}</span>
      <span style="color:${c};font-weight:900;">${w >= 0 ? '+' : ''}${w.toFixed(1)}</span>
    </div>`;
  }).join('');
  // Signal counts
  const buys = arr.filter(m => m.signal === 'BUY').length;
  const sells = arr.filter(m => m.signal === 'SELL').length;
  const neutral = arr.filter(m => !m.signal).length;

  container.innerHTML = `
    <div class="card" style="padding:10px 12px;margin-bottom:8px;">
      <div style="font-size:9px;color:#888;font-weight:800;letter-spacing:0.12em;margin-bottom:6px;">SIGNAL DISTRIBUTION</div>
      <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:900;">
        <span style="color:#22c55e;" data-testid="sig-buys">BUY ${buys}</span>
        <span style="color:#ef4444;" data-testid="sig-sells">SELL ${sells}</span>
        <span style="color:#666;" data-testid="sig-neutral">— ${neutral}</span>
      </div>
    </div>
    <div class="card" style="padding:10px 12px;margin-bottom:8px;">
      <div style="font-size:9px;color:#888;font-weight:800;letter-spacing:0.12em;margin-bottom:6px;">REGIME MIX</div>
      ${regimeRows || '<div style="color:#444;font-size:11px;">No data</div>'}
    </div>
    <div class="card" style="padding:10px 12px;">
      <div style="font-size:9px;color:#888;font-weight:800;letter-spacing:0.12em;margin-bottom:6px;">TOP MOVERS (|WPS|)</div>
      ${moversRows || '<div style="color:#444;font-size:11px;">No data</div>'}
    </div>`;
}

// renderExpectancyLeaderboard and renderGateFlow removed — legacy PIP v2.1 panels
function renderExpectancyLeaderboard() {}
function renderGateFlow() {}

// ── 3-COL TERMINAL DASHBOARD RENDERERS ────────────────────────────────────────

// Stake chip values
const _STAKE_CHIPS = [2, 5, 10, 25, 50, 100, 250, 500];

function renderStakeChips() {
  const wrap = el('stake-chips');
  if (!wrap) return;
  wrap.innerHTML = _STAKE_CHIPS.map(v => {
    const active = (v === _taValue);
    return `<button data-testid="stake-chip-${v}" onclick="window.dashboard.setStake(${v})"
      style="padding:6px 10px;font-size:11px;font-weight:900;border-radius:4px;cursor:pointer;font-family:inherit;letter-spacing:0.04em;
      ${active ? 'background:#14532d;border:1px solid #22c55e;color:#22c55e;' : 'background:#1a1a1a;border:1px solid #2a2a2a;color:#888;'}">+${v}</button>`;
  }).join('');
  const cur = el('stake-current');
  if (cur) cur.textContent = '$' + _taValue;
}

async function setStake(amount) {
  _taValue = parseInt(amount) || 2;
  renderStakeChips();
  try { await rpcCall('setRiskParams', { base_trade_amount: _taValue }); } catch (e) {}
}

function _isToday(t) {
  if (!t || !t.closed_at) return false;
  const d = new Date(t.closed_at.replace(' ', 'T') + 'Z');
  const today = new Date();
  return d.getUTCFullYear() === today.getUTCFullYear() &&
         d.getUTCMonth() === today.getUTCMonth() &&
         d.getUTCDate() === today.getUTCDate();
}

function _classifyTrade(t) {
  const pnl = parseFloat(t.pnl) || 0;
  return pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'flat';
}

function _isLegitimateClose(t) {
  const r = (t.reason || '').toUpperCase();
  return r.includes('SL_HIT') || r.includes('TS_HIT');
}

function _aggregateTrades(trades) {
  let wins = 0, losses = 0, pnlSum = 0;
  for (const t of trades) {
    if (!_isLegitimateClose(t)) continue;  // skip cleanups/reseeds
    const c = _classifyTrade(t);
    if (c === 'win') wins++;
    else if (c === 'loss') losses++;
    const stake = parseFloat(t.size) || 0;
    const pnlPct = parseFloat(t.pnl) || 0;
    pnlSum += stake * pnlPct / 100;
  }
  return { wins, losses, flat: 0, total: wins + losses, settled: wins + losses, pnlSum };
}

function renderTodayWR() {
  const el2 = el('today-wr-line');
  if (!el2) return;
  // Only count legitimate settled closes (SL_HIT or TS_HIT) — must match the
  // filter used by every other counter on the page, otherwise RESEED admin
  // cleanups inflate the numbers.
  const trades = (_lastTrades || []).filter(t =>
    t.status === 'CLOSED' && _isLegitimateClose(t) && _isToday(t)
  );
  const wins = trades.filter(t => _classifyTrade(t) === 'win').length;
  const losses = trades.filter(t => _classifyTrade(t) === 'loss').length;
  const total = wins + losses;
  if (total === 0) {
    el2.textContent = 'No trades today';
    el2.style.color = '#666';
    return;
  }
  const wr = ((wins / total) * 100).toFixed(1);
  el2.textContent = `${wr}% (${wins}W/${losses}L)`;
  el2.style.color = (wins / total) >= 0.5 ? '#22c55e' : '#ef4444';
}

function _computePfWrFromTrades(symbol) {
  // Only count legitimate settled closes — RESEED/FLAT admin rows must never
  // pollute PF/WR (they were the source of the bogus "PF 999.0 WR 50%" cards).
  const closed = (_lastTrades || []).filter(t =>
    t.symbol === symbol && t.status === 'CLOSED' && _isLegitimateClose(t)
  );
  if (closed.length === 0) return { pf: 0, wr: 0, n: 0 };
  let wins = 0, losses = 0, profit = 0, loss = 0;
  for (const t of closed) {
    const stake = parseFloat(t.size) || 0;
    const pnlPct = parseFloat(t.pnl) || 0;
    const dollars = stake * pnlPct / 100;
    if (dollars > 0) { wins++; profit += dollars; }
    else if (dollars < 0) { losses++; loss += -dollars; }
  }
  const settled = wins + losses;
  const wr = settled > 0 ? wins / settled : 0;
  const pf = loss > 0 ? profit / loss : (profit > 0 ? 999.0 : 0);
  return { pf, wr, n: closed.length };
}


// Canonical anchor + tick per market (user-provided dataset).
// pip_value_aud = (tick / anchor_price) × stake_aud
const _MARKET_TICK = {
  nikkei225:   { anchor: "9984.T",      tick: 1.00 },
  eurostoxx50: { anchor: "ASML.AS",     tick: 0.01 },
  ftse100:     { anchor: "HSBA.L",      tick: 0.01 },
  bovespa:     { anchor: "PETR4.SA",    tick: 0.01 },
  twse:        { anchor: "2330.TW",     tick: 0.05 },
  hangseng:    { anchor: "0700.HK",     tick: 0.10 },
  csi300:      { anchor: "600519.SS",   tick: 0.01 },
  tsx:         { anchor: "RY.TO",       tick: 0.01 },
  sp500:       { anchor: "AAPL",        tick: 0.01 },
  nasdaq100:   { anchor: "MSFT",        tick: 0.01 },
  dax40:       { anchor: "SAP.DE",      tick: 0.01 },
  cac40:       { anchor: "MC.PA",       tick: 0.01 },
  asx200:      { anchor: "BHP.AX",      tick: 0.01 },
  kospi:       { anchor: "005930.KS",   tick: 0.01 },
  sensex:      { anchor: "RELIANCE.NS", tick: 0.05 },
  omxs30:      { anchor: "VOLV-B.ST",   tick: 0.01 },
  ibex35:      { anchor: "SAN.MC",      tick: 0.01 },
  smi:         { anchor: "NESN.SW",     tick: 0.01 },
  aex:         { anchor: "ASML.AS",     tick: 0.01 },
  // Markets in our 25 not on the user's canonical list — sensible defaults
  dowjones:    { anchor: "JPM",         tick: 0.01 },
  mib:         { anchor: "UCG.MI",      tick: 0.005 },
  jse:         { anchor: "BHG.JO",      tick: 1.00 },
  set:         { anchor: "PTT.BK",      tick: 0.25 },
  nzx50:       { anchor: "FPH.NZ",      tick: 0.01 },
  tadawul:     { anchor: "2222.SR",     tick: 0.05 },
};

function _pipValueAud(marketKey, stakeAud) {
  const cfg = _MARKET_TICK[marketKey];
  if (!cfg) return null;
  const openTrade = (_lastTrades || []).find(t => t.symbol === marketKey && t.status === 'OPEN');
  let anchorPrice = openTrade && parseFloat(openTrade.entry_price) > 0
    ? parseFloat(openTrade.entry_price) : 0;
  if (!anchorPrice) {
    // Fallback: last closed trade's anchor price
    const closed = (_lastTrades || []).filter(t => t.symbol === marketKey && t.status === 'CLOSED');
    if (closed.length) anchorPrice = parseFloat(closed[closed.length-1].entry_price) || 0;
  }
  if (!anchorPrice || anchorPrice <= 0) return null;
  return (cfg.tick / anchorPrice) * (stakeAud || 250);
}

function renderMarketPerf() {
  const container = el('market-perf-grid');
  if (!container) return;
  const markets = (_lastState && _lastState.markets) || {};
  const lifecycle = (_lastState && _lastState.lifecycle) || {};
  const hasPos = (key) => (_lastTrades || []).some(t => t.symbol === key && t.status === 'OPEN');
  // Sort EQUITY_MARKETS so open ones come first
  const sorted = EQUITY_MARKETS.slice().sort((a, b) => {
    const aOpen = (typeof isMarketOpen === 'function') ? isMarketOpen(a.key) : true;
    const bOpen = (typeof isMarketOpen === 'function') ? isMarketOpen(b.key) : true;
    if (aOpen && !bOpen) return -1;
    if (!aOpen && bOpen) return 1;
    return 0;
  });
  container.innerHTML = sorted.map(def => {
    const m = markets[def.key] || {};
    const lc = lifecycle[def.key] || {};
    const open = (typeof isMarketOpen === 'function') ? isMarketOpen(def.key) : true;
    const lcStatus = (lc.lifecycle || 'SIM').toUpperCase();
    const isActive = open && (hasPos(def.key) || (m.signal && m.signal !== ''));
    const nLive = parseFloat(m.trades_live) || 0;
    const nSim  = parseFloat(m.trades_sim)  || 0;
    let pf = parseFloat(lc.profit_factor) || 0;
    let wr = parseFloat(lc.win_rate) || 0;
    if (pf === 0 && wr === 0) {
      if (nLive > 0) { pf = parseFloat(m.pf_live) || 0; wr = parseFloat(m.wr_live) || 0; }
      else if (nSim > 0) { pf = parseFloat(m.pf_sim) || 0; wr = parseFloat(m.wr_sim) || 0; }
    }
    // Final fallback: derive PF/WR from the live trades feed (instant after each close)
    if (pf === 0 && wr === 0) {
      const fresh = _computePfWrFromTrades(def.key);
      if (fresh.n > 0) { pf = fresh.pf; wr = fresh.wr; }
    }
    // Display baseline when no closed trades yet (75 WR / 1.5 PF)
    if (pf === 0 && wr === 0) { pf = 1.5; wr = 0.76; }
    const wrPct = Math.round(wr * 100);
    const wps = parseFloat(m.wps) || 0;
    const conf = parseFloat(m.confidence) || 0;
    const align = parseInt(m.alignment) || 0;
    const regime = (m.regime || '—');
    const regShort = regime.replace('CHOPPY_HIGH','CH-H').replace('CHOPPY_MEDIUM','CH-M').replace('CHOPPY_LOW','CH-L').replace('TRENDING','TREND').replace('REVERSAL','REV');
    const regColor = regime.startsWith('TRENDING') ? '#22c55e' : regime.startsWith('REVERSAL') ? '#a855f7' : regime.startsWith('CHOPPY') ? '#eab308' : '#555';
    const sig = (m.signal || '').toUpperCase();
    const sigColor = sig === 'BUY' ? '#22c55e' : sig === 'SELL' ? '#ef4444' : '#444';
    const wpsColor = wps > 0 ? '#22c55e' : wps < 0 ? '#ef4444' : '#666';
    const statusLbl = lcStatus === 'LIVE' ? 'LIVE' : (isActive ? 'ACTIVE' : (open ? 'QUIET' : 'CLOSED'));
    const statusColor = lcStatus === 'LIVE' ? '#22c55e' : isActive ? '#60a5fa' : open ? '#666' : '#333';
    const borderColor = lcStatus === 'LIVE' ? '#22c55e60' : isActive ? '#3b82f650' : '#1a1a1a';
    return `<div data-testid="mp-${def.key}" style="position:relative;background:#0a0a0a;border:1px solid ${borderColor};border-radius:5px;padding:12px 14px;">
      ${open ? `<span data-testid="open-dot-${def.key}" title="Market open" style="position:absolute;top:8px;right:8px;display:inline-flex;align-items:center;gap:4px;">
          <span style="width:8px;height:8px;background:#22c55e;border-radius:50%;box-shadow:0 0 6px #22c55e88;animation:pulse-open 1.6s ease-in-out infinite;"></span>
          <span style="font-size:10px;font-weight:900;color:#22c55e;letter-spacing:0.12em;">OPEN</span>
        </span>` : ''}
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;${open ? 'padding-right:56px;' : ''}">
        <span style="font-size:22px;">${def.flag}</span>
        <span style="font-size:20px;font-weight:900;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">${def.label}</span>
        ${sig ? `<span style="font-size:16px;font-weight:900;color:${sigColor};letter-spacing:0.06em;">${sig}</span>` : ''}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:16px;margin-bottom:6px;">
        <span style="color:${statusColor};font-weight:900;letter-spacing:0.08em;">${statusLbl}</span>
        <span style="color:${regColor};font-weight:900;letter-spacing:0.06em;">${regShort}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:18px;margin-bottom:4px;">
        <span style="color:#666;">WPS <span style="color:${wpsColor};font-weight:900;">${wps >= 0 ? '+' : ''}${wps.toFixed(1)}</span></span>
        <span style="color:#666;">A <span style="color:#ccc;font-weight:800;">${align}/4</span></span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:18px;margin-bottom:4px;">
        <span style="color:#666;">CONF <span style="color:#ccc;font-weight:800;">${conf.toFixed(0)}</span></span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:18px;border-top:1px solid #141414;padding-top:6px;margin-top:6px;">
        <span style="color:#666;">PF <span style="color:#ccc;font-weight:800;">${pf >= 999 ? '∞' : pf.toFixed(1)}</span></span>
        <span style="color:#666;">WR <span style="color:#ccc;font-weight:800;">${wrPct}%</span></span>
      </div>
      ${(() => {
        const pip = _pipValueAud(def.key, _taValue || 250);
        if (!pip) return '';
        return `<div style="font-size:13px;color:#555;margin-top:4px;letter-spacing:0.04em;">
          1 tick ≈ <span style="color:#888;font-weight:800;">A$${pip < 0.01 ? pip.toFixed(5) : pip.toFixed(4)}</span>
          <span style="color:#333;">@ A$${_taValue || 250}</span>
        </div>`;
      })()}
    </div>`;
  }).join('');
}

function renderOpenPositions() {
  const list = el('open-list');
  const cnt = el('open-count');
  if (!list) return;
  const open = (_lastTrades || []).filter(t => t.status === 'OPEN')
    .sort((a, b) => (b.id || 0) - (a.id || 0));
  if (cnt) cnt.textContent = `(${open.length})`;
  if (open.length === 0) {
    list.innerHTML = `<div style="padding:24px;text-align:center;color:#444;font-size:12px;letter-spacing:0.06em;">No open positions — waiting for next signal</div>`;
    return;
  }
  list.innerHTML = open.map(t => {
    const pnl = parseFloat(t.pnl) || 0;
    const stake = parseFloat(t.size) || 0;
    const dollars = stake * pnl / 100;
    const c = pnl > 0 ? '#22c55e' : pnl < 0 ? '#ef4444' : '#888';
    const sideC = t.side === 'BUY' ? '#22c55e' : '#ef4444';
    const tag = t.is_sim
      ? '<span style="background:#1d1d1d;color:#888;font-size:8px;font-weight:900;padding:2px 5px;border-radius:3px;">SIM</span>'
      : '<span style="background:#14532d;color:#22c55e;font-size:8px;font-weight:900;padding:2px 5px;border-radius:3px;">LIVE</span>';
    return `<div data-testid="open-row-${t.id}" style="display:grid;grid-template-columns:36px 26px minmax(0,1fr) 60px 60px 70px;gap:6px;align-items:center;padding:7px 8px;background:#0f0f0f;border:1px solid #1a1a1a;border-left:2px solid ${c};border-radius:4px;font-size:11px;min-width:0;overflow:hidden;">
      ${tag}
      <span style="color:${sideC};font-weight:900;font-size:11px;">${t.side}</span>
      <span style="color:#fff;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">${escHtml(t.symbol)}</span>
      <span style="color:#666;font-weight:700;font-size:10px;">$${stake.toFixed(0)}</span>
      <span style="color:${c};font-weight:900;text-align:right;">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</span>
      <span style="color:${c};font-weight:900;text-align:right;">${dollars >= 0 ? '+' : ''}A$${dollars.toFixed(2)}</span>
    </div>`;
  }).join('');
}

function renderClosedToday() {
  const list = el('closed-list');
  const cnt = el('closed-count');
  if (!list) return;
  const allClosed = (_lastTrades || []).filter(t => t.status === 'CLOSED' && _isToday(t) && _isLegitimateClose(t))
    .sort((a, b) => (b.id || 0) - (a.id || 0));
  if (cnt) cnt.textContent = `(${allClosed.length})`;
  const closed = allClosed.slice(0, 30);
  if (closed.length === 0) {
    list.innerHTML = `<div style="padding:18px;text-align:center;color:#444;font-size:12px;">No trades closed yet today</div>`;
    return;
  }
  const lifecycle = (_lastState && _lastState.lifecycle) || {};
  list.innerHTML = closed.map(t => {
    const pnl = parseFloat(t.pnl) || 0;
    const stake = parseFloat(t.size) || 0;
    const dollars = stake * pnl / 100;
    const cls = _classifyTrade(t);
    const cls_color = cls === 'win' ? '#22c55e' : '#ef4444';
    const cls_bg = cls === 'win' ? '#14532d' : '#7f1d1d';
    const sideC = t.side === 'BUY' ? '#22c55e' : '#ef4444';
    const entry = parseFloat(t.entry_price) || 0;
    const exit = parseFloat(t.current_price) || parseFloat(t.exit_price) || entry;
    // Read the REAL exit reason from the DB reason field
    const rawReason = (t.reason || '').toUpperCase();
    const reason = rawReason.includes('SL_HIT') ? 'SL_HIT'
                 : rawReason.includes('TS_HIT') ? 'TS_HIT'
                 : '—';
    return `<div data-testid="closed-row-${t.id}" style="display:grid;grid-template-columns:46px 26px minmax(0,1fr) 50px 80px 70px 80px;gap:6px;align-items:center;padding:7px 8px;background:#0f0f0f;border:1px solid #1a1a1a;border-left:2px solid ${cls_color};border-radius:4px;font-size:11px;min-width:0;overflow:hidden;">
      <span style="background:${cls_bg};color:${cls_color};font-size:9px;font-weight:900;padding:2px 4px;border-radius:3px;text-align:center;">${cls.toUpperCase()}</span>
      <span style="color:${sideC};font-weight:900;">${t.side}</span>
      <span style="color:#fff;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">${escHtml(t.symbol)}</span>
      <span style="color:#888;font-weight:700;">$${stake.toFixed(0)}</span>
      <span style="color:#666;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${entry.toFixed(2)}→${exit.toFixed(2)}</span>
      <span style="color:#a16207;font-size:9px;font-weight:900;letter-spacing:0.04em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${reason}</span>
      <span style="color:${cls_color};font-weight:900;text-align:right;">${dollars >= 0 ? '+' : ''}A$${dollars.toFixed(2)}</span>
    </div>`;
  }).join('');
}

function renderRightCol(stats) {
  // Win rate big
  const allClosed = (_lastTrades || []).filter(t => t.status === 'CLOSED');
  const open = (_lastTrades || []).filter(t => t.status === 'OPEN');
  const todayClosed = allClosed.filter(_isToday);
  const allAgg = _aggregateTrades(allClosed);
  const todayAgg = _aggregateTrades(todayClosed);

  const wr = allAgg.settled > 0 ? ((allAgg.wins / allAgg.settled) * 100) : 0;
  const wrBig = el('wr-big');
  const wrSub = el('wr-sub');
  const wrCaution = el('wr-caution');
  if (wrBig) {
    wrBig.textContent = wr.toFixed(1) + '%';
    wrBig.style.color = wr >= 60 ? '#22c55e' : wr >= 50 ? '#eab308' : '#ef4444';
  }
  if (wrSub) wrSub.textContent = `${allAgg.wins}W / ${allAgg.losses}L · ${allAgg.settled} settled · ${open.length} open`;
  if (wrCaution) wrCaution.style.display = (wr < 60 && allAgg.settled > 0) ? 'inline-block' : 'none';

  // Kitty — single source of truth: backend kitty.balance.
  // Backend deducts stake on OPEN, credits (stake + pnl) on CLOSE, auto-resets to $10k on depletion.
  const kitty = (_lastState && _lastState.kitty) || {};
  const kittyBalance = parseFloat(kitty.balance);
  const availableBalance = isFinite(kittyBalance) ? kittyBalance : 10000;
  const realizedPnl = allAgg.pnlSum;  // for the P&L tiles only — NOT used for kitty math
  const totalPnl = realizedPnl;
  const setText = (id, txt, color) => { const e = el(id); if (e) { e.textContent = txt; if (color) e.style.color = color; } };
  setText('kitty-balance', 'A$' + availableBalance.toFixed(2),
          availableBalance < 5000 ? '#ef4444'
          : availableBalance < 8000 ? '#eab308' : '#fff');
  setText('kit-trades', String(allAgg.settled));
  setText('kit-wins', String(allAgg.wins));
  setText('kit-wr', wr.toFixed(1) + '%');

  // Settlement flash — fires when the settled-count tick increments.
  // (vanilla port of: useEffect(() => { setFlash(true); … }, [lastSettlement]))
  if (typeof window._prevSettledCount === 'number' && allAgg.settled > window._prevSettledCount) {
    _flashSettlement();
  }
  window._prevSettledCount = allAgg.settled;
  const pnlColor = totalPnl > 0 ? '#22c55e' : totalPnl < 0 ? '#ef4444' : '#888';
  setText('kit-pnl', (totalPnl >= 0 ? '+' : '') + 'A$' + totalPnl.toFixed(2), pnlColor);

  // Today P&L
  const todayPnlColor = todayAgg.pnlSum > 0 ? '#22c55e' : todayAgg.pnlSum < 0 ? '#ef4444' : '#888';
  setText('today-pnl-big', (todayAgg.pnlSum >= 0 ? '+' : '') + 'A$' + todayAgg.pnlSum.toFixed(2), todayPnlColor);
  setText('today-wins', String(todayAgg.wins));
  setText('today-losses', String(todayAgg.losses));
  setText('today-flat', String(todayAgg.flat));

  // All-time
  const allPnlColor = allAgg.pnlSum > 0 ? '#22c55e' : allAgg.pnlSum < 0 ? '#ef4444' : '#888';
  setText('alltime-pnl-big', (allAgg.pnlSum >= 0 ? '+' : '') + 'A$' + allAgg.pnlSum.toFixed(2), allPnlColor);
  setText('alltime-wins', String(allAgg.wins));
  setText('alltime-losses', String(allAgg.losses));
  setText('alltime-flat', String(allAgg.flat));
  setText('alltime-wr', wr.toFixed(1) + '%', wr >= 60 ? '#22c55e' : wr >= 50 ? '#eab308' : '#ef4444');

  // All-Time P&L banner — same numbers as the right column, in a top strip
  setText('bn-alltime-pnl', (allAgg.pnlSum >= 0 ? '+' : '') + 'A$' + allAgg.pnlSum.toFixed(2),
          allAgg.pnlSum > 0 ? '#22c55e' : allAgg.pnlSum < 0 ? '#ef4444' : '#888');
  setText('bn-wins', String(allAgg.wins));
  setText('bn-losses', String(allAgg.losses));
  setText('bn-flat', String(allAgg.flat));
  setText('bn-wr', wr.toFixed(1) + '%', wr >= 60 ? '#22c55e' : wr >= 50 ? '#eab308' : '#ef4444');

  // System status
  const broker = (_lastState && _lastState.broker) || {};
  const brokerConnected = !!broker.connected;
  setText('sys-broker', brokerConnected ? 'CONNECTED' : 'DISCONNECTED', brokerConnected ? '#22c55e' : '#ef4444');
  setText('sys-kitty', 'A$' + availableBalance.toFixed(2), availableBalance < 8000 ? '#eab308' : '#fff');
  const paused = !!((_lastState && _lastState.paused) || (stats && stats.paused));
  setText('sys-bot', paused ? 'PAUSED' : 'RUNNING', paused ? '#eab308' : '#22c55e');
}

let _lastCycleAt = 0;
const CYCLE_PERIOD_MS = 60_000;

function renderTerminalDashboard(stats) {
  renderStakeChips();
  renderTodayWR();
  renderMarketPerf();
  renderOpenPositions();
  renderClosedToday();
  renderRightCol(stats);
  // Cycle countdown — backend exposes last_cycle as unix epoch; cycle period is 60s
  if (stats && stats.last_cycle) {
    _lastCycleAt = parseFloat(stats.last_cycle) * 1000;
  }
}

setInterval(() => {
  const el2 = document.getElementById('cycle-countdown');
  if (!el2) return;
  if (!_lastCycleAt) { el2.textContent = '— s'; return; }
  const remaining = Math.max(0, Math.round((_lastCycleAt + CYCLE_PERIOD_MS - Date.now()) / 1000));
  el2.textContent = remaining + ' s';
  el2.style.color = remaining <= 5 ? '#f97316' : remaining <= 15 ? '#eab308' : '#22c55e';
}, 1000);

// ── Main refresh ───────────────────────────────────────────────────────────────
async function refresh() {
  const indicator = el('refresh-indicator');
  if (indicator) indicator.classList.add('refreshing');
  try {
    const [state, trades, stats, optimizerAudit] = await Promise.all([
      rpcCall('getMarketState'),
      rpcCall('getTrades'),
      rpcCall('getStats'),
      rpcCall('getOptimizerAudit'),
    ]);
    // Normalise trades — always an array
    const tradesArr = Array.isArray(trades) ? trades
      : (trades && Array.isArray(trades.trades)) ? trades.trades
      : [];
    _lastState  = state || {};
    _lastTrades = tradesArr;
    _lastOptimizerAudit = optimizerAudit || null;
    clearError();
    renderHeader(state);
    renderStats(stats || {});
    renderEngines((state || {}).engines);
    renderMarkets((state || {}).markets, (state || {}).lifecycle);
    renderStaticMarketGrid((state || {}).markets);
    renderKitty((state || {}).kitty);
    renderSwarm((state || {}).swarm || null);
    renderActiveTrades(tradesArr);
    renderClosedTrades(tradesArr);
    renderOtherStats();
    renderEngineTabStats(tradesArr);
    renderEngineSummaryBoxes((state || {}).engines, tradesArr);
    renderAllMarketCards();
    renderAllButtonStates();
    renderCategoryPills();
    syncPauseButton();
    syncBrokerButton();
    renderTerminalDashboard(stats || {});
    renderOptimizerAudit(optimizerAudit || null);
    // Refresh active tab's data too
    const activeTab = document.querySelector('.cmd-tab.active')?.dataset?.tab;
    if (activeTab === 'systems') loadSystemsTab();
    if (activeTab === 'intelligence') loadIntelligenceTab();
    if (activeTab === 'sysaudit') loadSysAuditTab();
  } catch (err) {
    showError(`Could not reach backend: ${err.message}`);
  } finally {
    if (indicator) indicator.classList.remove('refreshing');
  }
}
// ── Actions ───────────────────────────────────────────────────────────────────
async function resetMarket(market) {
  const ok = confirm(`Reset ${market} to SIM state? This counts as a manual brain wash.`);
  if (!ok) return;
  try {
    const result = await rpcCall('resetMarket', market);
    if (result?.ok) {
      alert(`✓ ${result.message}`);
      await refresh();
    } else {
      alert(`✗ Reset failed: ${result?.message || 'Unknown error'}`);
    }
  } catch (err) {
    showError(`Reset failed: ${err.message}`);
  }
}
async function triggerCycle() {
  const btn = el('btn-trigger');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Running…'; }
  try {
    const result = await rpcCall('runTradingCycle');
    await refresh();
    console.log('Cycle result:', result?.status);
  } catch (err) {
    showError(`Cycle trigger failed: ${err.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⚡ Trigger Cycle Now'; }
  }
}
// ── Bootstrap ──────────────────────────────────────────────────────────────────
function toggleCommandCenter() {
  const cc = document.getElementById('command-center');
  const btn = document.getElementById('cmd-toggle');
  if (!cc) return;
  const isHidden = cc.style.display === 'none';
  cc.style.display = isHidden ? 'block' : 'none';
  if (btn) {
    btn.style.color = isHidden ? '#fff' : '#444';
    btn.style.borderColor = isHidden ? '#333' : '#222';
  }
}
// ── Risk controls ─────────────────────────────────────────────────────────────
let _slValue = 2.0;
let _tsValue = 2.0;
let _taValue = 50;
async function adjustTradeAmount(delta) {
  _taValue = Math.min(500, Math.max(2, Math.round(_taValue + delta * 5)));
  const el2 = document.getElementById('ta-display');
  if (el2) el2.textContent = '$' + _taValue;
  renderStakeChips();
  try { await rpcCall('setRiskParams', { base_trade_amount: _taValue }); } catch(e) {}
}
async function adjustSL(delta) {
  _slValue = Math.min(40, Math.max(0, Math.round((_slValue + delta) * 10) / 10));
  const el2 = document.getElementById('sl-display');
  if (el2) el2.textContent = _slValue.toFixed(1) + '%';
  try { await rpcCall('setRiskParams', { stop_loss_pct: _slValue }); } catch(e) {}
}
async function adjustTrail(delta) {
  _tsValue = Math.min(40, Math.max(0, Math.round((_tsValue + delta) * 10) / 10));
  const el2 = document.getElementById('ts-display');
  if (el2) el2.textContent = _tsValue.toFixed(1) + '%';
  try { await rpcCall('setRiskParams', { trailing_stop_pct: _tsValue }); } catch(e) {}
}
async function resetRisk() {
  _slValue = 5.0; _tsValue = 5.0; _taValue = 50;
  const sl = document.getElementById('sl-display');
  const ts = document.getElementById('ts-display');
  const ta = document.getElementById('ta-display');
  if (sl) sl.textContent = '5.0%';
  if (ts) ts.textContent = '5.0%';
  if (ta) ta.textContent = '$' + _taValue;
  try { await rpcCall('setRiskParams', { stop_loss_pct: 5.0, trailing_stop_pct: 5.0, base_trade_amount: 50 }); } catch(e) {}
}
async function initRiskParams() {
  try {
    const p = await rpcCall('getRiskParams');
    if (p) {
      _slValue = parseFloat(p.stop_loss_pct) || 5.0;
      _tsValue = parseFloat(p.trailing_stop_pct) || 5.0;
      _taValue = parseFloat(p.base_trade_amount) || 50;
      const sl = document.getElementById('sl-display');
      const ts = document.getElementById('ts-display');
      const ta = document.getElementById('ta-display');
      if (sl) sl.textContent = _slValue.toFixed(1) + '%';
      if (ts) ts.textContent = _tsValue.toFixed(1) + '%';
      if (ta) ta.textContent = '$' + _taValue;
    }
  } catch(e) {}
}

// ── Gate control panel ───────────────────────────────────────────────────────
// _gateTightness mirrors the global gate tightness values; it is still consumed
// by _marketThresholds() to render per-tile WPS/CONF/ALN context.
const _gateTightness = { WPS: 0, CONF: 0, TIME4: 0 };

// Panel state
let _gateGlobal = {};        // global gate settings { GATE: {tightness, range} }
let _gateMarketCfg = {};     // market key -> config object from market_state
let _gateSel = null;         // currently selected market key
let _gateAln = 3;            // alignment required (2/3/4)
let _gateWps = 10;           // working WPS threshold for selected market (base=10, tightness 0=10, 1=90)
let _gateConf = 20;          // working CONF % for selected market (base=20%, tightness 0=20%, 1=55%)

// Alignment number (2/3/4) <-> TIME4 tightness (0/0.5/1.0)
function _alnToTight(aln) { return (Math.max(2, Math.min(4, aln)) - 2) / 2; }
function _tightToAln(t) { return Math.max(2, Math.min(4, Math.round(2 + _num(t, 0) * 2))); }
// CONF % (20..55) <-> CONF tightness (0..1)
function _tightToConfPct(t) { return Math.round((0.20 + _num(t, 0) * 0.35) * 100); }
function _confPctToTight(pct) { return Math.max(0, Math.min(1, ((pct / 100) - 0.20) / 0.35)); }

function _gateMarketLabel(key) {
  const def = EQUITY_MARKETS.find(m => m.key === key);
  return def ? def.label : String(key || '').toUpperCase();
}
function _setGateStatus(msg) {
  const el = document.getElementById('gate-status');
  if (el) el.textContent = msg || '';
}
function _populateGateMarketSelect() {
  const sel = document.getElementById('gate-market-select');
  if (!sel) return;
  sel.innerHTML = EQUITY_MARKETS.map(m => `<option value="${m.key}">${m.flag} ${m.label}</option>`).join('');
  if (_gateSel) sel.value = _gateSel;
}
function _renderGateControls() {
  const aEl = document.getElementById('gate-aln-display');
  if (aEl) aEl.textContent = _gateAln + (_gateAln === 1 ? ' gate' : ' gates');
  const wEl = document.getElementById('gate-wps-display');
  if (wEl) wEl.textContent = _gateWps.toFixed(1);
  const cEl = document.getElementById('gate-conf-display');
  if (cEl) cEl.textContent = _gateConf + '%';
}
function _loadGateMarket(key) {
  _gateSel = key;
  const cfg = _gateMarketCfg[key] || {};
  _gateWps = cfg.wps_threshold != null ? _num(cfg.wps_threshold, 10) : 10;
  const cfgGates = cfg.gates || {};
  const confTight = (cfgGates.CONF && cfgGates.CONF.tightness != null)
    ? _num(cfgGates.CONF.tightness, 0)
    : _num((_gateGlobal.CONF || {}).tightness, 0);
  _gateConf = _tightToConfPct(confTight);
  const alnTight = (cfgGates.TIME4 && cfgGates.TIME4.tightness != null)
    ? _num(cfgGates.TIME4.tightness, 0)
    : _num((_gateGlobal.TIME4 || {}).tightness, 0);
  _gateAln = _tightToAln(alnTight);
  _renderGateControls();
}
async function initGateSettings() {
  // Render defaults immediately so controls are never blank on load
  _renderGateControls();
  try {
    const r = await rpcCall('getGateSettings');
    _gateGlobal = (r && r.settings && r.settings.gates) || {};
    ['WPS','CONF','TIME4'].forEach(g => {
      _gateTightness[g] = parseFloat((_gateGlobal[g] || {}).tightness || 0);
    });
    _gateMarketCfg = {};
    ((r && r.markets) || []).forEach(m => { _gateMarketCfg[m.market] = m.config || {}; });
    _gateAln = _tightToAln((_gateGlobal.TIME4 || {}).tightness);
    if (!_gateSel) _gateSel = EQUITY_MARKETS[0] && EQUITY_MARKETS[0].key;
    _populateGateMarketSelect();
    _loadGateMarket(_gateSel);
    _renderGateControls();
  } catch(e) {
    _setGateStatus('GATE LOAD FAILED — showing defaults');
    _renderGateControls(); // still show defaults even on error
  }
}
// 1. Alignment Required (per selected market, TIME4 gate)
async function adjustAlignment(delta) {
  const market = _gateSel;
  if (!market) { _setGateStatus('SELECT A MARKET'); return; }
  _gateAln = Math.max(2, Math.min(4, _gateAln + delta));
  _renderGateControls();
  const tight = _alnToTight(_gateAln);
  _setGateStatus('SAVING ALIGNMENT…');
  try {
    await rpcCall('setGateSetting', { gate: 'TIME4', tightness: tight, market });
    _gateMarketCfg[market] = _gateMarketCfg[market] || {};
    _gateMarketCfg[market].gates = _gateMarketCfg[market].gates || {};
    _gateMarketCfg[market].gates.TIME4 = { ...(_gateMarketCfg[market].gates.TIME4 || {}), tightness: tight };
    _setGateStatus(_gateMarketLabel(market) + ' ALIGNMENT: ' + _gateAln + ' GATES');
    refresh();
  } catch(e) { _setGateStatus('SAVE FAILED: ' + e.message); }
}
// 2. Market selector
function selectGateMarket(key) {
  _loadGateMarket(key);
  _setGateStatus('');
}
// 3. WPS Threshold (per selected market)
function adjustGateWps(delta) {
  _gateWps = Math.max(0, Math.min(100, Math.round((_gateWps + delta) * 10) / 10));
  _renderGateControls();
}
async function saveGateWps() {
  const market = _gateSel;
  if (!market) { _setGateStatus('SELECT A MARKET'); return; }
  _setGateStatus('SAVING WPS…');
  try {
    await rpcCall('setMarketWpsThreshold', { market, threshold: _gateWps });
    _gateMarketCfg[market] = _gateMarketCfg[market] || {};
    _gateMarketCfg[market].wps_threshold = _gateWps;
    _setGateStatus(_gateMarketLabel(market) + ' WPS SAVED: ' + _gateWps.toFixed(1));
    refresh();
  } catch(e) { _setGateStatus('WPS SAVE FAILED: ' + e.message); }
}
// 4. CONF Threshold (per selected market)
function adjustGateConf(delta) {
  _gateConf = Math.max(20, Math.min(55, _gateConf + delta));
  _renderGateControls();
}
async function saveGateConf() {
  const market = _gateSel;
  if (!market) { _setGateStatus('SELECT A MARKET'); return; }
  const tight = _confPctToTight(_gateConf);
  _setGateStatus('SAVING CONF…');
  try {
    await rpcCall('setGateSetting', { gate: 'CONF', tightness: tight, market });
    _gateMarketCfg[market] = _gateMarketCfg[market] || {};
    _gateMarketCfg[market].gates = _gateMarketCfg[market].gates || {};
    _gateMarketCfg[market].gates.CONF = { ...(_gateMarketCfg[market].gates.CONF || {}), tightness: tight };
    _setGateStatus(_gateMarketLabel(market) + ' CONF SAVED: ' + _gateConf + '%');
    refresh();
  } catch(e) { _setGateStatus('CONF SAVE FAILED: ' + e.message); }
}

// ── Engine panel toggle ───────────────────────────────────────────────────────
let _activeEnginePanel = null;
function toggleEnginePanel(engine) {
  const panelIds = ['equity', 'crypto_scalp', 'crypto_long'];
  const boxMap   = { equity: 'equity', crypto_scalp: 'scalp', crypto_long: 'long' };
  if (_activeEnginePanel === engine) {
    // clicking the active panel — collapse it
    const panel = document.getElementById('epanel-' + engine);
    if (panel) panel.style.display = 'none';
    const box = document.querySelector('[data-engine="' + engine + '"]');
    if (box) {
      box.style.borderColor = '';
      const chev = box.querySelector('.engine-chevron');
      if (chev) chev.textContent = '▼';
    }
    _activeEnginePanel = null;
    renderAllMarketCards();
    return;
  }
  // hide all panels and reset all boxes first
  panelIds.forEach(id => {
    const p = document.getElementById('epanel-' + id);
    if (p) p.style.display = 'none';
    const b = document.querySelector('[data-engine="' + id + '"]');
    if (b) {
      b.style.borderColor = '';
      const chev = b.querySelector('.engine-chevron');
      if (chev) chev.textContent = '▼';
    }
  });
  // show the clicked panel
  const panel = document.getElementById('epanel-' + engine);
  if (panel) {
    panel.style.display = 'block';
    setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  }
  const box = document.querySelector('[data-engine="' + engine + '"]');
  if (box) {
    box.style.borderColor = '#00c278';
    const chev = box.querySelector('.engine-chevron');
    if (chev) chev.textContent = '▲';
  }
  _activeEnginePanel = engine;
  renderAllMarketCards();
}
async function closeTrade(id) {
  try {
    const res = await rpcCall('closeTradeNow', id);
    if (res && res.ok) {
      window.dashboard.refresh();
    }
  } catch(e) {}
}
function expandMarket(key) {
  _expandedMarket = _expandedMarket === key ? null : key;
  if (_lastState) {
    renderMarkets((_lastState || {}).markets, (_lastState || {}).lifecycle);
  }
}
function expandCrypto(sym) {
  _expandedCrypto = _expandedCrypto === sym ? null : sym;
  if (_lastState) {
  }
}
function expandActiveTrade(sym) {
  _expandedActiveTrade = _expandedActiveTrade === sym ? null : sym;
  if (_lastTrades) renderActiveTrades(_lastTrades);
}
async function togglePause() {
  const btn = document.getElementById('pause-btn');
  try {
    const state = await rpcCall('getPauseState');
    if (state && state.paused) {
      await rpcCall('resumeTrading');
      if (btn) { btn.textContent = 'PAUSE'; btn.style.borderColor = '#ef4444'; btn.style.color = '#ef4444'; }
    } else {
      await rpcCall('pauseTrading');
      if (btn) { btn.textContent = 'RESUME'; btn.style.borderColor = '#22c55e'; btn.style.color = '#22c55e'; }
    }
  } catch(e) {}
}
// ── Toast notification ────────────────────────────────────────────────────────
function toast(msg, kind = 'ok') {
  let host = document.getElementById('toast-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'toast-host';
    host.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none;';
    document.body.appendChild(host);
  }
  const bg = kind === 'ok' ? '#14532d' : kind === 'err' ? '#7f1d1d' : '#1e40af';
  const fg = kind === 'ok' ? '#22c55e' : kind === 'err' ? '#ef4444' : '#3b82f6';
  const t = document.createElement('div');
  t.style.cssText = `background:${bg};border:2px solid ${fg};color:${fg};padding:14px 22px;font-size:15px;font-weight:900;letter-spacing:0.08em;text-transform:uppercase;border-radius:6px;box-shadow:0 6px 24px rgba(0,0,0,0.6);min-width:260px;pointer-events:auto;transition:opacity 0.3s, transform 0.3s;transform:translateX(20px);opacity:0;font-family:inherit;`;
  t.textContent = msg;
  host.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity = '1'; t.style.transform = 'translateX(0)'; });
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateX(20px)';
    setTimeout(() => t.remove(), 350);
  }, 3000);
}

// ── Visible-feedback RPC helper for action buttons ────────────────────────────
async function _buttonAction(btn, labels, rpcMethod, params = null) {
  if (!btn) return;
  const origText = btn.textContent;
  const origBg   = btn.style.background;
  const origBd   = btn.style.borderColor;
  const origCol  = btn.style.color;
  btn.disabled = true;
  btn.style.opacity = '0.6';
  btn.textContent = '⏳ ' + labels.working;
  try {
    const result = await rpcCall(rpcMethod, params);
    if (result && result.ok === false) throw new Error(result.error || 'failed');
    btn.textContent = '✓ ' + labels.done;
    btn.style.background = '#14532d';
    btn.style.borderColor = '#22c55e';
    btn.style.color = '#22c55e';
    toast(labels.toast_ok + (result && result.count ? ` · ${result.count} MARKETS` : ''), 'ok');
    setTimeout(() => {
      btn.textContent = origText;
      btn.style.background = origBg;
      btn.style.borderColor = origBd;
      btn.style.color = origCol;
      btn.style.opacity = '1';
      btn.disabled = false;
      refresh();
    }, 1500);
  } catch (err) {
    btn.textContent = '✗ ' + labels.fail;
    btn.style.background = '#7f1d1d';
    btn.style.borderColor = '#ef4444';
    btn.style.color = '#ef4444';
    toast(`${labels.toast_fail}: ${err.message || 'error'}`, 'err');
    setTimeout(() => {
      btn.textContent = origText;
      btn.style.background = origBg;
      btn.style.borderColor = origBd;
      btn.style.color = origCol;
      btn.style.opacity = '1';
      btn.disabled = false;
    }, 2000);
  }
}

// ── Category lifecycle toggle (EQUITY / CRYPTO SCALP / CRYPTO LONG pills) ─────
async function toggleCategoryLifecycle(category, ev) {
  const btnId = `cat-toggle-${category}`;
  const btn = (ev && ev.target && ev.target.closest('button')) || document.getElementById(btnId);
  if (!btn) return;

  // Determine current state of this category's markets
  const lc = (_lastState && _lastState.lifecycle) || {};
  let symbols = [];
  if (category === 'equity') {
    // Only OPEN equity markets (respect market hours)
    symbols = EQUITY_MARKETS.filter(m => isMarketOpen(m.key)).map(m => m.key);
  } else {
    // Crypto categories — all 25 coins (24/7)
    symbols = CRYPTO_COINS.map(c => c.sym);
  }
  if (symbols.length === 0) {
    toast(`NO ${category.toUpperCase()} MARKETS OPEN`, 'err');
    return;
  }
  // Count current states
  let liveN = 0, simN = 0;
  for (const s of symbols) {
    const st = (lc[s] && lc[s].lifecycle) || 'SIM';
    if (st === 'LIVE') liveN++;
    else simN++;
  }
  // If majority already LIVE → flip to SIM; else flip to LIVE
  const target = liveN >= simN ? 'SIM' : 'LIVE';
  const labels = target === 'LIVE'
    ? { working: 'ARMING…', done: `${category.toUpperCase()} LIVE`, fail: 'FAILED – RETRY',
        toast_ok: `${category.toUpperCase()} → LIVE`, toast_fail: `${category.toUpperCase()} LIVE FAILED` }
    : { working: 'RESETTING…', done: `${category.toUpperCase()} SIM`, fail: 'FAILED – RETRY',
        toast_ok: `${category.toUpperCase()} → SIM`, toast_fail: `${category.toUpperCase()} SIM FAILED` };
  return _buttonAction(btn, labels, 'setMarketsLifecycle', { symbols, lifecycle: target });
}

// Update the pill label/colour on every refresh
function renderCategoryPills() {
  const lc = (_lastState && _lastState.lifecycle) || {};
  const cats = [
    { key: 'equity',       btn: document.getElementById('cat-toggle-equity') },
    { key: 'crypto_scalp', btn: document.getElementById('cat-toggle-crypto_scalp') },
    { key: 'crypto_long',  btn: document.getElementById('cat-toggle-crypto_long') },
  ];
  for (const { key, btn } of cats) {
    if (!btn || btn.disabled) continue;
    let symbols = [];
    if (key === 'equity') {
      symbols = EQUITY_MARKETS.filter(m => isMarketOpen(m.key)).map(m => m.key);
    } else {
      symbols = CRYPTO_COINS.map(c => c.sym);
    }
    if (symbols.length === 0) {
      btn.textContent = 'CLOSED';
      btn.style.background = '#0a0a0a';
      btn.style.borderColor = '#333';
      btn.style.color = '#555';
      btn.style.boxShadow = 'none';
      continue;
    }
    let liveN = 0, simN = 0;
    for (const s of symbols) {
      const st = (lc[s] && lc[s].lifecycle) || 'SIM';
      if (st === 'LIVE') liveN++;
      else simN++;
    }
    if (liveN === symbols.length) {
      btn.textContent = `● LIVE (${liveN})`;
      btn.style.background = '#14532d';
      btn.style.borderColor = '#22c55e';
      btn.style.color = '#fff';
      btn.style.boxShadow = '0 0 10px #22c55e80';
    } else if (simN === symbols.length) {
      btn.textContent = `SIM (${simN})`;
      btn.style.background = '#1a1a1a';
      btn.style.borderColor = '#666';
      btn.style.color = '#999';
      btn.style.boxShadow = 'none';
    } else {
      btn.textContent = `L ${liveN} / S ${simN}`;
      btn.style.background = '#1f1510';
      btn.style.borderColor = '#f97316';
      btn.style.color = '#f97316';
      btn.style.boxShadow = 'none';
    }
  }
}

async function setAllLive(ev) {
  const btn = (ev && ev.target && ev.target.closest('button')) || document.getElementById('btn-all-live');
  return _buttonAction(btn,
    {working: 'ARMING…', done: 'ALL LIVE', fail: 'FAILED – RETRY', toast_ok: 'ALL MARKETS → LIVE', toast_fail: 'ALL LIVE FAILED'},
    'setAllLive');
}
async function setAllSim(ev) {
  const btn = (ev && ev.target && ev.target.closest('button')) || document.getElementById('btn-all-sim');
  return _buttonAction(btn,
    {working: 'RESETTING…', done: 'ALL SIM', fail: 'FAILED – RETRY', toast_ok: 'ALL MARKETS → SIM', toast_fail: 'ALL SIM FAILED'},
    'setAllSim');
}

// Reflect current state on the ALL LIVE / ALL SIM buttons (bright = active mode).
function renderAllButtonStates() {
  const liveBtn = document.getElementById('btn-all-live');
  const simBtn  = document.getElementById('btn-all-sim');
  if (!liveBtn || !simBtn) return;
  // Skip if a button is mid-action (disabled/transient state)
  if (liveBtn.disabled || simBtn.disabled) return;

  const lc = (_lastState && _lastState.lifecycle) || {};
  const keys = Object.keys(lc);
  if (keys.length === 0) return;

  let liveCount = 0, simCount = 0;
  for (const k of keys) {
    const state = (lc[k] && lc[k].lifecycle) || 'SIM';
    if (state === 'LIVE') liveCount++;
    else simCount++;
  }
  const allLive = simCount === 0 && liveCount > 0;
  const allSim  = liveCount === 0 && simCount > 0;

  // Reset baseline
  liveBtn.style.background = '#0a2016';
  liveBtn.style.borderColor = '#22c55e55';
  liveBtn.style.color = '#22c55e88';
  liveBtn.style.boxShadow = 'none';
  simBtn.style.background = '#1a1a1a';
  simBtn.style.borderColor = '#555';
  simBtn.style.color = '#999';
  simBtn.style.boxShadow = 'none';

  // Active state highlight
  if (allLive) {
    liveBtn.style.background = '#14532d';
    liveBtn.style.borderColor = '#22c55e';
    liveBtn.style.color = '#fff';
    liveBtn.style.boxShadow = '0 0 12px #22c55e80';
    liveBtn.textContent = '● ALL LIVE';
    simBtn.textContent = 'ALL SIM';
  } else if (allSim) {
    simBtn.style.background = '#14532d';
    simBtn.style.borderColor = '#22c55e';
    simBtn.style.color = '#fff';
    simBtn.style.boxShadow = '0 0 12px #22c55e80';
    simBtn.textContent = '● ALL SIM';
    liveBtn.textContent = 'ALL LIVE';
  } else {
    // Mixed state
    liveBtn.textContent = `ALL LIVE (${liveCount})`;
    simBtn.textContent  = `ALL SIM (${simCount})`;
  }
}
async function toggleMarketLifecycle(market, currentLC) {
  try {
    if (currentLC === 'LIVE') {
      await rpcCall('setMarketSim', market);
    } else {
      await rpcCall('setMarketLive', market);
    }
    refresh();
  } catch(e) {}
}
async function connectBroker() {
  try {
    const r = await fetch('/api/ig/connect', { method: 'POST' });
    const d = await r.json();
    if (d.connected) {
      alert(`IG connected. Account ${d.account_id} · ${d.currency} ${d.balance}`);
    } else {
      alert('IG connect failed: ' + (d.error || 'unknown'));
    }
    setTimeout(syncBrokerButton, 200);
  } catch (e) {
    alert('IG connect error: ' + e.message);
  }
}
async function syncBrokerButton() {
  try {
    const r = await fetch('/api/ig/status');
    const d = await r.json();
    const btn = document.getElementById('broker-btn');
    const sys = document.getElementById('sys-broker');
    if (d.connected) {
      if (btn) { btn.textContent = `IG CONNECTED · ${d.account_id || ''}`; btn.style.borderColor = '#22c55e'; btn.style.color = '#22c55e'; }
      if (sys) { sys.textContent = 'CONNECTED'; sys.style.color = '#22c55e'; }
    } else {
      if (btn) { btn.textContent = 'BROKER OFF — TAP TO CONNECT'; btn.style.borderColor = '#eab308'; btn.style.color = '#eab308'; }
      if (sys) { sys.textContent = 'DISCONNECTED'; sys.style.color = '#ef4444'; }
    }
  } catch (e) {}
}
async function syncPauseButton() {
  try {
    const state = await rpcCall('getPauseState');
    const btn = document.getElementById('pause-btn');
    if (state && state.paused) {
      if (btn) { btn.textContent = 'RESUME'; btn.style.borderColor = '#22c55e'; btn.style.color = '#22c55e'; }
    } else {
      if (btn) { btn.textContent = 'PAUSE'; btn.style.borderColor = '#ef4444'; btn.style.color = '#ef4444'; }
    }
  } catch(e) {}
}
async function resetMarketNow(market) {
  try {
    await rpcCall('resetMarket', market);
    refresh();
  } catch(e) {}
}
window.dashboard = { refresh, reset: () => {}, resetMarket, resetMarketNow, triggerCycle, toggleCommandCenter, adjustSL, adjustTrail, adjustTradeAmount, setStake, resetRisk, adjustAlignment, selectGateMarket, adjustGateWps, saveGateWps, adjustGateConf, saveGateConf, toggleEnginePanel, closeTrade, expandMarket, expandCrypto, expandActiveTrade, togglePause, setAllLive, setAllSim, toggleMarketLifecycle, toggleCategoryLifecycle, connectBroker };
initTabs();
initRiskParams();
initGateSettings();
refresh();
refreshTimer = setInterval(refresh, REFRESH_INTERVAL);

// ── Mode-A retired ───────────────────────────────────────────────────────────
// Mode-A used to poll every 1.5s and adjust WPS separately from the optimiser.
// It has been retired so there is one owner for thresholds: Auto-Optimizer.
// Market Tuner now owns trade management only: stop loss, trailing stop, cooldown.
function refreshModeATicker() {
  const container = document.getElementById('mode-a-ticker-chips');
  if (container) {
    container.innerHTML = '<span class="ma-chip ma-chip-idle">Mode-A retired · Auto-Optimizer controls gates</span>';
  }
}
function openModeAModal() {}
function closeModeAModal() {}
window.dashboard.openModeAModal = openModeAModal;
window.dashboard.closeModeAModal = closeModeAModal;
refreshModeATicker();


// ─────────────────────────────────────────────────────────────────────────────
// REPAIR PATCH: compact operations dashboard rows
// Locked spec: horizontal rows, open markets only, hard-white text, no grey fog.
// This deliberately overrides the older chunky card renderers below without
// touching data feed wiring. Replit agents: do not "redesign" this back into cards.
// ─────────────────────────────────────────────────────────────────────────────
let _lastGateTrend = window._lastGateTrend || {};
window._lastGateTrend = _lastGateTrend;
// Direction of the market over the last 60 minutes, from the engine's 60m
// timeframe (avg_pct = weighted average % move; dir = BUY/SELL/NEUTRAL).
// Falls back to the overall market direction. 1 = up, -1 = down, 0 = flat.
function _trend60Dir(m) {
  const tfs = (m && m.timeframes) || [];
  for (const t of tfs) {
    if (t && t.tf === '60m') {
      const ap = parseFloat(t.avg_pct);
      if (Number.isFinite(ap) && ap !== 0) return ap > 0 ? 1 : -1;
      if (t.dir === 'BUY') return 1;
      if (t.dir === 'SELL') return -1;
    }
  }
  if (m && m.direction === 'BUY') return 1;
  if (m && m.direction === 'SELL') return -1;
  return 0;
}

function _num(v, fallback = 0) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : fallback;
}
function _fmt1(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n.toFixed(1) : '—';
}
function _fmt0(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? String(Math.round(n)) : '—';
}
function _confPct(v) {
  const n = parseFloat(v);
  if (!Number.isFinite(n)) return null;
  return n <= 1 ? n * 100 : n;
}
function _tradeAge(t) {
  const raw = t && (t.created_at || t.opened_at || t.entry_time);
  if (!raw) return '—';
  const d = new Date(raw);
  if (isNaN(d)) return '—';
  const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
  if (mins < 60) return mins + 'm';
  return Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm';
}
function _tradePnlAud(t) {
  const pnl = _num(t && t.pnl, 0);
  const stake = _num(t && t.size, 0);
  return stake * pnl / 100;
}
function _metricArrow(key, metric, value, pass, signal) {
  const v = Math.abs(_num(value, 0));
  const id = key + ':' + metric;
  const prev = _lastGateTrend[id];
  _lastGateTrend[id] = v;
  if (prev == null || Math.abs(v - prev) < 0.05) return '<span class="op-arrow op-flat">→</span>';
  const toward = v > prev;
  return `<span class="op-arrow ${toward ? 'op-up' : 'op-down'}">${toward ? '↑' : '↓'}</span>`;
}
function _metricCell(label, current, threshold, pass, arrowHtml) {
  const cls = pass ? 'op-pass' : 'op-fail';
  return `<span class="op-metric ${cls}"><b>${label}</b> ${current}/${threshold} ${arrowHtml || ''}</span>`;
}
function _marketThresholds(key, m, lcData) {
  let cfg = {};
  if (lcData && lcData.config) {
    try { cfg = typeof lcData.config === 'string' ? JSON.parse(lcData.config) : (lcData.config || {}); } catch(e) { cfg = {}; }
  }
  const gates = cfg.gates || {};
  const wps = m && m.wps_threshold != null ? _num(m.wps_threshold, 10)
            : cfg.wps_threshold != null ? _num(cfg.wps_threshold, 10)
            : 10;
  const confTight = gates.CONF && gates.CONF.tightness != null ? _num(gates.CONF.tightness, 0)
                  : (_gateTightness && _gateTightness.CONF != null ? _num(_gateTightness.CONF, 0) : 0);
  const conf = Math.round((0.20 + confTight * 0.35) * 100);
  const timeTight = gates.TIME4 && gates.TIME4.tightness != null ? _num(gates.TIME4.tightness, 0)
                  : (_gateTightness && _gateTightness.TIME4 != null ? _num(_gateTightness.TIME4, 0) : 0);
  const aln = Math.max(2, Math.min(4, Math.round(2 + timeTight * 2)));
  return { wps, conf, aln };
}
function _marketPerf(key, lcData, stats) {
  const lc = lcData || {};
  const pm = (stats && stats.perMarketLive && stats.perMarketLive[key]) || null;
  const wins = pm ? _num(pm.wins, 0) : _num(lc.wins_live ?? lc.win_count, 0);
  const losses = pm ? _num(pm.losses, 0) : _num(lc.losses_live ?? lc.loss_count, 0);
  const total = wins + losses;
  const wr = total > 0 ? Math.round((wins / total) * 100) : Math.round(_num((lc.wr_live != null ? lc.wr_live * 100 : lc.win_rate * 100), 0));
  const pf = pm ? (() => {
    const closed = (_lastTrades || []).filter(t => t.status === 'CLOSED' && t.symbol === key && !t.is_sim);
    const grossWin = closed.filter(t => _tradePnlAud(t) > 0).reduce((s,t)=>s+_tradePnlAud(t),0);
    const grossLoss = Math.abs(closed.filter(t => _tradePnlAud(t) < 0).reduce((s,t)=>s+_tradePnlAud(t),0));
    return grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? 999 : 0);
  })() : _num(lc.pf_live ?? lc.profit_factor, 0);
  const closed = (_lastTrades || []).filter(t => t.status === 'CLOSED' && t.symbol === key && !t.is_sim);
  const winVals = closed.map(_tradePnlAud).filter(v => v > 0);
  const lossVals = closed.map(_tradePnlAud).filter(v => v < 0);
  const avgW = winVals.length ? winVals.reduce((a,b)=>a+b,0)/winVals.length : 0;
  const avgL = lossVals.length ? lossVals.reduce((a,b)=>a+b,0)/lossVals.length : 0;
  return { wins, losses, wr, pf, avgW, avgL };
}
function _marketPrice(key, m, trade) {
  const v = (m && (m.price ?? m.current_price ?? m.last_price)) ?? (trade && trade.current_price) ?? null;
  const n = parseFloat(v);
  return Number.isFinite(n) && n > 0 ? n.toFixed(2) : '—';
}


function _auditVerdictClass(v) {
  v = String(v || '').toUpperCase();
  if (v === 'HELPING') return 'op-pass';
  if (v === 'HURTING') return 'op-fail';
  if (v === 'MIXED') return 'op-warn';
  return 'op-neutral';
}
function _shortAuditMessage(msg) {
  msg = String(msg || '');
  return msg.replace(/\s+/g, ' ').replace('gates tightened', 'gates↑').replace('gates loosened', 'gates↓').replace('WPS tightened', 'WPS↑').replace('WPS loosened', 'WPS↓');
}
function renderOptimizerAudit(audit) {
  const box = document.getElementById('optimizer-audit-box');
  if (!box) return;
  const items = (audit && audit.last5) || [];
  if (!items.length) {
    box.innerHTML = '<div class="op-empty">NO OPTIMIZER CHANGES YET</div>';
    return;
  }
  const count24 = audit.count24h || 0;
  const helping = audit.helping24h || 0;
  const hurting = audit.hurting24h || 0;
  box.innerHTML = `
    <div class="optimizer-audit-summary">
      <span>24H ${count24}</span>
      <span class="op-pass">HELP ${helping}</span>
      <span class="op-fail">HURT ${hurting}</span>
    </div>
    ${items.map(it => {
      const imp = it.impact || {};
      const verdict = imp.verdict || 'PENDING';
      const cls = _auditVerdictClass(verdict);
      const net = Number.isFinite(parseFloat(imp.netPnl)) ? parseFloat(imp.netPnl) : 0;
      const pf = imp.profitFactor === 999 ? '∞' : (Number.isFinite(parseFloat(imp.profitFactor)) ? parseFloat(imp.profitFactor).toFixed(2) : '—');
      return `<div class="optimizer-audit-row" title="${escHtml(it.message || '')}">
        <span class="optimizer-audit-time">${formatTime(it.created_at)}</span>
        <span class="optimizer-audit-msg">${escHtml(_shortAuditMessage(it.message))}</span>
        <span class="optimizer-audit-impact ${cls}">${escHtml(verdict)} ${imp.trades || 0}T ${net >= 0 ? '+' : ''}${net.toFixed(0)} PF ${pf}</span>
      </div>`;
    }).join('')}
  `;
}

function renderMarkets(markets, lifecycle) {
  const container = document.getElementById('markets-section') || document.getElementById('market-cards');
  if (!container) return;
  const hasOpenTrade = (key) => (_lastTrades || []).some(t => t.symbol === key && t.status === 'OPEN');
  const getOpenTrade = (key) => (_lastTrades || []).find(t => t.symbol === key && t.status === 'OPEN');
  const visible = EQUITY_MARKETS.filter(def => isMarketOpen(def.key) || hasOpenTrade(def.key));
  const stats = _lastStats || {};
  const rows = visible.map(def => {
    const key = def.key;
    const m = (markets || {})[key] || {};
    const lc = (lifecycle || {})[key] || {};
    const trade = getOpenTrade(key);
    const th = _marketThresholds(key, m, lc);
    const rawSignal = m.signal || m.direction || (trade ? trade.side : null);
    const signal = rawSignal === 'BUY' ? 'BUY' : rawSignal === 'SELL' ? 'SELL' : 'NO SIGNAL';
    const sigCls = signal === 'BUY' ? 'op-pass' : signal === 'SELL' ? 'op-fail' : 'op-warn';
    const wpsVal = _num(m.wps, 0);
    const confVal = _confPct(m.confidence);
    const alnVal = _num(m.alignment, 0);
    const wpsPass = Math.abs(wpsVal) >= th.wps;
    const confPass = confVal != null && confVal >= th.conf;
    const alnPass = alnVal >= th.aln;
    const perf = _marketPerf(key, lc, stats);
    const wpsArrow = _metricArrow(key, 'wps', wpsVal, wpsPass, signal);
    const confArrow = _metricArrow(key, 'conf', confVal, confPass, signal);
    const alnArrow = alnPass ? '<span class="op-arrow op-up">✓</span>' : '<span class="op-arrow op-down">↓</span>';
    const priceTxt = _marketPrice(key, m, trade);
    const trend60 = priceTxt === '—' ? 0 : _trend60Dir(m);
    const priceColor = trend60 > 0 ? 'op-pass' : trend60 < 0 ? 'op-fail' : 'op-flat';
    const priceArrow = priceTxt === '—' ? ''
      : trend60 > 0 ? '<span class="op-arrow op-up">↑</span>'
      : trend60 < 0 ? '<span class="op-arrow op-down">↓</span>'
      : '<span class="op-arrow op-flat">→</span>';
    return `<div class="mkt-tile" data-market="${key}" onclick="window.dashboard && window.dashboard.expandMarket && window.dashboard.expandMarket('${key}')">
      <div class="mkt-tile-head">
        <span class="mkt-name">${def.flag} ${escHtml(def.label)}</span>
        <span class="mkt-signal ${sigCls}">${signal}</span>
      </div>
      <div class="mkt-tile-metrics">
        ${_metricCell('WPS', _fmt1(Math.abs(wpsVal)), _fmt1(th.wps), wpsPass, wpsArrow)}
        ${_metricCell('CONF', _fmt0(confVal), _fmt0(th.conf), confPass, confArrow)}
        ${_metricCell('ALN', _fmt0(alnVal), _fmt0(th.aln), alnPass, alnArrow)}
      </div>
      <div class="mkt-tile-perf">
        <span class="mkt-stat ${perf.wr >= 60 ? 'op-pass' : 'op-fail'}">WR ${perf.wr}%</span>
        <span class="mkt-stat mkt-price-stat ${priceColor}">${priceTxt} ${priceArrow}</span>
        <span class="mkt-stat ${perf.pf >= 2 ? 'op-pass' : perf.pf >= 1 ? 'op-warn' : 'op-fail'}">PF ${perf.pf >= 999 ? '∞' : perf.pf.toFixed(2)}</span>
      </div>
    </div>`;
  }).join('');
  container.innerHTML = `<div class="op-section-title">OPEN MARKETS ONLY — ${visible.length}</div><div class="mkt-grid">${rows || '<div class="op-empty">NO OPEN MARKETS</div>'}</div>`;
}

function renderOpenPositions() {
  const list = document.getElementById('open-list');
  const cnt = document.getElementById('open-count');
  if (!list) return;
  const open = (_lastTrades || []).filter(t => t.status === 'OPEN').sort((a,b)=>(b.id||0)-(a.id||0));
  if (cnt) cnt.textContent = `(${open.length})`;
  if (!open.length) { list.innerHTML = '<div class="op-empty">NO OPEN TRADES</div>'; return; }
  list.innerHTML = open.map(t => {
    const dollars = _tradePnlAud(t);
    const c = dollars >= 0 ? 'op-pass' : 'op-fail';
    return `<div class="trade-row">
      <span class="op-market">${escHtml(t.symbol)}</span>
      <span class="op-signal ${t.side === 'BUY' ? 'op-pass' : 'op-fail'}">${escHtml(t.side)}</span>
      <span>OPEN ${_tradeAge(t)}</span>
      <span>ENTRY ${formatPrice(t.entry_price)}</span>
      <span>CURRENT ${formatPrice(t.current_price)}</span>
      <span class="${c}">P&L ${dollars >= 0 ? '+' : ''}A$${dollars.toFixed(2)}</span>
      <span>STOP ${t.stop_loss_price ? formatPrice(t.stop_loss_price) : '—'}</span>
    </div>`;
  }).join('');
}

function renderClosedToday() {
  const list = document.getElementById('closed-list');
  const cnt = document.getElementById('closed-count');
  if (!list) return;
  const closed = (_lastTrades || []).filter(t => t.status === 'CLOSED' && _isToday(t) && _isLegitimateClose(t)).sort((a,b)=>(b.id||0)-(a.id||0)).slice(0,50);
  if (cnt) cnt.textContent = `(${closed.length})`;
  if (!closed.length) { list.innerHTML = '<div class="op-empty">NO CLOSED TRADES TODAY</div>'; return; }
  list.innerHTML = closed.map(t => {
    const dollars = _tradePnlAud(t);
    const cls = dollars >= 0 ? 'op-pass' : 'op-fail';
    const held = t.closed_at && t.created_at ? (() => { const mins = Math.max(0, Math.round((new Date(t.closed_at)-new Date(t.created_at))/60000)); return mins < 60 ? mins+'m' : Math.floor(mins/60)+'h '+(mins%60)+'m'; })() : '—';
    const reason = (t.reason || '').toUpperCase().includes('TS') ? 'TRAIL' : (t.reason || '').toUpperCase().includes('SL') ? 'STOP' : 'CLOSE';
    return `<div class="trade-row">
      <span class="op-market">${escHtml(t.symbol)}</span>
      <span class="op-signal ${t.side === 'BUY' ? 'op-pass' : 'op-fail'}">${escHtml(t.side)}</span>
      <span>HELD ${held}</span>
      <span>${formatPrice(t.entry_price)}→${formatPrice(t.current_price)}</span>
      <span>${reason}</span>
      <span class="${cls}">${dollars >= 0 ? '+' : ''}A$${dollars.toFixed(2)}</span>
    </div>`;
  }).join('');
}



