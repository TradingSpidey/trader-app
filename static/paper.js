"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = (v, d = 2) => (v == null || v === "" || Number.isNaN(Number(v)) ? null : Number(v).toLocaleString("en-US", {maximumFractionDigits: d}));
const usd = (v, d) => { const n = num(v, d == null ? (Math.abs(Number(v)) >= 100 ? 2 : Math.abs(Number(v)) >= 1 ? 4 : 8) : d); return n == null ? "—" : (Number(v) < 0 ? "-$" : "$") + n.replace("-", ""); };
const sol = (v) => { const n = num(v, 4); return n == null ? "—" : n + " SOL"; };
const pctPoints = (v) => (v == null || v === "" || Number.isNaN(Number(v)) ? "—" : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(2) + "%");
const pctFrac = (v) => (v == null || v === "" || Number.isNaN(Number(v)) ? "—" : (Number(v) > 0 ? "+" : "") + (Number(v) * 100).toFixed(2) + "%");
const cls = (v) => (v > 0 ? "up" : v < 0 ? "dn" : "");
const dash = (v) => (v == null || v === "" ? "—" : String(v));

function parseTime(s) {
  if (!s) return null;
  const text = String(s).trim();
  if (/HKT/.test(text)) {
    const m = text.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (!m) return null;
    return Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] || "00"}+08:00`);
  }
  const t = Date.parse(text);
  return Number.isNaN(t) ? null : t;
}
function fmtHKT(s) {
  if (!s) return "—";
  if (/HKT/.test(String(s))) return String(s).replace(" HKT", "");
  const t = parseTime(s);
  if (t == null) return "—";
  const parts = new Intl.DateTimeFormat("zh-HK", {timeZone: "Asia/Hong_Kong", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"}).formatToParts(new Date(t));
  const g = (type) => parts.find((p) => p.type === type).value;
  return `${g("year")}-${g("month")}-${g("day")} ${g("hour")}:${g("minute")}:${g("second")}`;
}
function ago(ms) {
  if (ms == null) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (sec < 60) return sec + " 秒前";
  if (sec < 3600) return Math.floor(sec / 60) + " 分鐘前";
  return Math.floor(sec / 3600) + " 個鐘前";
}
function shortMint(m) {
  if (!m) return "—";
  const s = String(m);
  return s.length < 12 ? s : s.slice(0, 4) + "…" + s.slice(-4);
}
function sideName(s) {
  const k = String(s || "").toLowerCase();
  if (k === "buy") return "買入";
  if (k === "sell") return "賣出";
  return s ? String(s) : "—";
}

function equityPoints(book, data) {
  const rows = Array.isArray(data.equity) ? data.equity : [];
  const pts = [];
  rows.forEach((row) => {
    if (!row) return;
    const y = book === "crypto" ? row.equity_usd : row.equity;
    const x = book === "crypto" ? row.time_hkt : row.ts;
    const t = parseTime(x);
    const v = y == null || y === "" ? null : Number(y);
    if (t == null || v == null || Number.isNaN(v)) return;
    pts.push({t, v, label: fmtHKT(x)});
  });
  pts.sort((a, b) => a.t - b.t);
  return pts;
}
function chart(pts) {
  if (pts.length < 2) return `<p class="muted">權益曲線暫無數據</p>`;
  const w = 640, h = 160, pad = 8;
  const lo = Math.min(...pts.map((p) => p.v)), hi = Math.max(...pts.map((p) => p.v));
  const span = hi - lo || 1;
  const x = (i) => pad + (w - pad * 2) * i / (pts.length - 1);
  const y = (v) => pad + (h - pad * 2) * (hi - v) / span;
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const up = pts[pts.length - 1].v >= pts[0].v;
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="權益曲線"><path d="${line}" fill="none" stroke="${up ? "#3dffb0" : "#ff5d7a"}" stroke-width="2"/>
    <text x="8" y="14" fill="#8ea3b8" font-size="12">${esc(usd(lo, 2))} → ${esc(usd(hi, 2))}</text></svg>
    <p class="note">${esc(pts[0].label)} → ${esc(pts[pts.length - 1].label)} · ${pts.length} 點</p>`;
}

function winLine(data) {
  const n = data.closed_n == null || data.closed_n === "" ? null : Number(data.closed_n);
  const wins = data.wins == null || data.wins === "" ? null : Number(data.wins);
  const losses = data.losses == null || data.losses === "" ? (n != null && wins != null ? n - wins : null) : Number(data.losses);
  const wl = (wins == null && losses == null) ? "暫無數據" : `${wins == null ? "—" : wins} 贏 / ${losses == null ? "—" : losses} 輸`;
  if (n != null && n < 5) return `樣本太少（已平倉 ${n} 單）<br>${wl}`;
  if (n == null || wins == null || !n) return `暫無數據<br>${wl}`;
  return `${((wins / n) * 100).toFixed(1)}%<br>${wl}`;
}

function bookCard(name, book, item) {
  if (!item || !item.data) {
    return `<article class="card"><h2>${esc(name)}</h2><p>等緊數據傳上嚟</p></article>`;
  }
  const d = item.data;
  const cfg = d.config || {};
  const received = parseTime(item.received_at);
  const saved = parseTime(d.state_saved_hkt);
  const stale = received != null && Date.now() - received > 10 * 60 * 1000;
  const positions = Array.isArray(d.positions) ? d.positions : [];
  const trades = (Array.isArray(d.trades) ? d.trades.slice() : []).sort((a, b) => (parseTime(b.time_hkt || b.ts) || 0) - (parseTime(a.time_hkt || a.ts) || 0));
  const crypto = book === "crypto";
  const cost = crypto
    ? `每邊滑價 ${cfg.slippage_per_side == null ? "—" : (Number(cfg.slippage_per_side) * 100).toFixed(1) + "%"}，每單手續費 ${cfg.fee_sol_per_trade == null ? "—" : cfg.fee_sol_per_trade + " SOL"}。`
    : dash(cfg.costs);
  const posRows = positions.map((p) => `<tr>
    <td><b>${esc(p.symbol)}</b>${crypto ? `<div class="muted">${esc(shortMint(p.mint))}</div>` : ""}</td>
    <td class="num">${usd(p.entry_usd)}</td>
    <td class="num">${usd(p.last_usd)}</td>
    <td class="num ${cls(p.ret)}">${pctFrac(p.ret)}</td>
    <td class="num">${crypto ? sol(p.value_sol) : usd(p.value_usd)}</td>
    <td class="num ${cls(crypto ? p.upnl_sol : p.upnl_usd)}">${crypto ? sol(p.upnl_sol) : usd(p.upnl_usd)}</td>
    <td class="num">${esc(fmtHKT(p.opened_at))}</td>
    <td>${esc(p.why || p.reason || "暫無數據")}</td>
  </tr>`).join("");
  const tradeRows = trades.map((t) => {
    const pnl = crypto ? t.pnl_sol : (t.pnl != null && t.pnl !== "" ? t.pnl : t.pnl_usd);
    const price = crypto ? t.price_usd : t.price;
    const size = crypto ? (t.qty || t.sol) : t.qty;
    return `<tr>
      <td class="num">${esc(fmtHKT(t.time_hkt || t.ts))}</td>
      <td>${esc(sideName(t.side || t.action))}</td>
      <td>${esc(t.symbol)}</td>
      <td class="num">${usd(price)}</td>
      <td class="num">${esc(dash(size))}</td>
      <td>${esc(dash(t.reason))}</td>
      <td class="num ${cls(Number(pnl))}">${pnl == null || pnl === "" ? "—" : esc(String(pnl))}</td>
    </tr>`;
  }).join("");
  return `<article class="card">
    <h2>${esc(name)}</h2>
    <p class="note">起始 <b class="num">$50</b> · ${esc(fmtHKT(cfg.start_time_hkt))} 開始${crypto && cfg.start_sol != null ? `（${esc(num(cfg.start_sol, 4))} SOL）` : ""}</p>
    ${stale ? `<div class="stale">數據可能過時（我部電腦暫停中）</div>` : ""}
    <p class="note">最後更新 ${esc(dash(d.state_saved_hkt))} · ${esc(ago(saved))}</p>
    <div class="kpis">
      <div class="kpi"><span>而家權益（美元）</span><b class="num">${usd(d.equity_usd, 2)}</b></div>
      ${crypto ? `<div class="kpi"><span>而家權益（SOL）</span><b class="num">${sol(d.equity_sol)}</b></div>` : `<div class="kpi"><span>現金</span><b class="num">${usd(d.cash_usd, 2)}</b></div>`}
      <div class="kpi"><span>回報（美元）</span><b class="num ${cls(crypto ? d.ret_usd_pct : d.ret_pct)}">${pctPoints(crypto ? d.ret_usd_pct : d.ret_pct)}</b></div>
      ${crypto ? `<div class="kpi"><span>回報（SOL）</span><b class="num ${cls(d.ret_sol_pct)}">${pctPoints(d.ret_sol_pct)}</b></div>` : ""}
      <div class="kpi"><span>已實現</span><b class="num">${crypto ? sol(d.realized_sol) : usd(d.realized_usd, 2)}</b></div>
      <div class="kpi"><span>未實現</span><b class="num">${crypto ? sol(d.unrealized_sol) : usd(d.unrealized_usd, 2)}</b></div>
      <div class="kpi"><span>買入 / 賣出</span><b class="num">${dash(d.buys)} / ${dash(d.sells)}</b></div>
      <div class="kpi"><span>勝率</span><b>${winLine(d)}</b></div>
    </div>
    <h2 style="margin-top:12px">權益曲線</h2>
    ${chart(equityPoints(book, d))}
    <h2>持倉</h2>
    ${positions.length ? `<div class="scroll"><table><thead><tr><th>代號</th><th>入場</th><th>而家</th><th>回報</th><th>市值</th><th>浮動</th><th>開倉（香港）</th><th>原因</th></tr></thead><tbody>${posRows}</tbody></table></div>` : `<p class="muted">未有持倉</p>`}
    <h2 style="margin-top:12px">成交</h2>
    ${trades.length ? `<div class="scroll"><table><thead><tr><th>時間（香港）</th><th>方向</th><th>代號</th><th>價格</th><th>數量</th><th>原因</th><th>盈虧</th></tr></thead><tbody>${tradeRows}</tbody></table></div>` : `<p class="muted">未有成交</p>`}
    <p class="note">成本假設：${esc(cost)}</p>
    ${cfg.trading_hours ? `<p class="note">${esc(cfg.trading_hours)}</p>` : ""}
  </article>`;
}

async function load() {
  const r = await fetch("/api/paper");
  const j = await r.json();
  $("#books").innerHTML = `<div class="books">${bookCard("加密貨幣", "crypto", j.crypto)}${bookCard("美股", "stocks", j.stocks)}</div>`;
}
$("#books").id = "books";
load().catch((e) => { $("#books").textContent = e.message; });
setInterval(() => load().catch(() => {}), 30000);
