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
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="權益曲線"><path d="${line}" fill="none" stroke="${up ? "#2fce85" : "#ff5d6c"}" stroke-width="2"/>
    <text x="8" y="14" fill="#9aa6b5" font-size="12">${esc(usd(lo, 2))} → ${esc(usd(hi, 2))}</text></svg>
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

function cryptoCost(cfg) {
  const slip = cfg.slippage_per_side == null ? "—" : (Number(cfg.slippage_per_side) * 100).toFixed(1) + "%";
  const fee = cfg.fee_sol_per_trade == null ? "—" : cfg.fee_sol_per_trade + " SOL";
  return `每邊滑價 ${slip}，每單手續費 ${fee}。`;
}
function stockCost(cfg) {
  const slipRaw = cfg.slippage_per_side == null ? 0.001 : Number(cfg.slippage_per_side);
  const feeRaw = cfg.commission_min_usd != null ? Number(cfg.commission_min_usd)
    : (cfg.commission_usd != null ? Number(cfg.commission_usd) : 0.01);
  const prose = cfg.costs == null ? "" : String(cfg.costs).trim();
  const stale = /冇計滑價|冇計手續費|忽略滑價|忽略手續費|無滑價|無手續費|no slippage|ignores slippage|ignores fees/i.test(prose);
  if (prose && !stale && cfg.slippage_per_side == null && cfg.commission_min_usd == null && cfg.commission_usd == null) {
    return prose;
  }
  const slip = Number.isNaN(slipRaw) ? "—" : (slipRaw * 100).toFixed(1) + "%";
  const fee = Number.isNaN(feeRaw) ? "—" : feeRaw.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return `每邊滑價 ${slip}（買入高過報價、賣出低過報價），每邊手續費最少 $${fee}。`;
}
function rankNum(b) {
  if (!b || b.rank == null || b.rank === "") return null;
  const n = Number(b.rank);
  return Number.isFinite(n) ? n : null;
}
function pctOfFrac(v) {
  if (v == null || v === "" || !Number.isFinite(Number(v))) return "—";
  const n = Number(v) * 100;
  const text = Math.abs(n - Math.round(n)) < 0.05 ? String(Math.round(n)) : n.toFixed(1);
  return text + "%";
}
function statusLabel(s) {
  const k = String(s || "").toLowerCase();
  if (!k) return "—";
  if (k === "running") return "運行中";
  if (k === "not_started") return "未開始";
  if (k === "missing_config") return "缺設定";
  return String(s);
}
function firstParam(q, keys) {
  for (let i = 0; i < keys.length; i++) {
    const v = q[keys[i]];
    if (v != null && v !== "") return v;
  }
  return null;
}
function fmtGate(v) {
  if (v == null || v === "" || !Number.isFinite(Number(v))) return null;
  const n = Number(v);
  if (Math.abs(n) <= 1) return pctOfFrac(n);
  const text = Math.abs(n - Math.round(n)) < 0.05 ? String(Math.round(n)) : n.toFixed(1);
  return text + "%";
}
function fmtLiq(v) {
  if (v == null || v === "" || !Number.isFinite(Number(v))) return null;
  const n = Number(v);
  if (Math.abs(n) < 10) return pctOfFrac(n);
  return "$" + n.toLocaleString("en-US", {maximumFractionDigits: 0});
}
function bookCombo(b) {
  if (!b || typeof b !== "object") return "";
  const fromBook = b.combo;
  const fromParams = b.params && typeof b.params === "object" ? b.params.combo : "";
  const raw = fromBook != null && fromBook !== "" ? fromBook : fromParams;
  if (raw == null || raw === "") return "";
  return String(raw);
}
function comboBadge(combo) {
  if (!combo) return "";
  return `<span class="combo">${esc(combo)}</span>`;
}
function bookFamily(b) {
  if (!b || typeof b !== "object") return "";
  const fromBook = b.family;
  const fromParams = b.params && typeof b.params === "object" ? b.params.family : "";
  const raw = fromBook != null && fromBook !== "" ? fromBook : fromParams;
  if (raw == null || raw === "") return "";
  return String(raw);
}
function familyBadge(family) {
  if (!family) return "";
  return `<span class="combo family">${esc(family)}</span>`;
}
let boardMarket = "crypto";
function kpi(label, value) {
  return `<div class="kpi"><span>${esc(label)}</span><b class="num">${value}</b></div>`;
}
function matrixWait(bookCount, market) {
  const n = Number(bookCount);
  if (market === "stocks") {
    const count = Number.isFinite(n) && n > 0 ? String(Math.trunc(n)) : "36";
    return count + " 本美股交叉組合（CTRL + SX/QX/AX/ZX）";
  }
  const count = Number.isFinite(n) && n > 0 ? String(Math.trunc(n)) : "78";
  return count + " 本交叉組合（CTRL + CX/QX/AX/ZX）";
}
function shortParams(p, combo) {
  const q = p && typeof p === "object" ? p : {};
  const maxPos = q.max_positions == null || q.max_positions === "" ? "—" : String(q.max_positions);
  const bits = [`TP ${pctOfFrac(q.tp)} / SL ${pctOfFrac(q.sl)} · 日虧 ${pctOfFrac(q.daily_loss_of_start)} · 最多 ${maxPos} 倉 · 單倉 ${pctOfFrac(q.max_position_pct)}`];
  const mom = fmtGate(firstParam(q, ["mom", "momentum", "mom_h1", "min_mom"]));
  const liq = fmtLiq(firstParam(q, ["liq", "min_liq", "liq_usd", "min_liq_usd"]));
  const top10 = fmtGate(firstParam(q, ["top10", "top10_pct", "max_top10"]));
  if (mom) bits.push(`MOM ${mom}`);
  if (liq) bits.push(`LIQ ${liq}`);
  if (top10) bits.push(`TOP10 ${top10}`);
  const code = combo || (q.combo == null || q.combo === "" ? "" : String(q.combo));
  if (code) bits.unshift(String(code));
  return bits.join(" · ");
}

function demoBookDetail(b) {
  const combo = bookCombo(b);
  const family = bookFamily(b);
  const stocks = boardMarket === "stocks";
  const positions = Array.isArray(b.positions) ? b.positions : [];
  const trades = (Array.isArray(b.trades) ? b.trades.slice() : []).sort((a, c) => (parseTime(c.time_hkt || c.ts) || 0) - (parseTime(a.time_hkt || a.ts) || 0));
  const posRows = positions.map((p) => `<tr>
    <td><b>${esc(p.symbol)}</b>${p.mint ? `<div class="muted">${esc(shortMint(p.mint))}</div>` : ""}</td>
    <td class="num">${usd(p.entry_usd)}</td>
    <td class="num">${usd(p.last_usd)}</td>
    <td class="num ${cls(p.ret)}">${pctFrac(p.ret)}</td>
    <td class="num">${stocks ? usd(p.value_usd) : sol(p.value_sol)}</td>
    <td class="num ${stocks ? cls(p.upnl_usd) : cls(p.upnl_sol)}">${stocks ? usd(p.upnl_usd) : sol(p.upnl_sol)}</td>
    <td class="num">${esc(fmtHKT(p.opened_at))}</td>
    <td>${esc(p.why || p.reason || "暫無數據")}</td>
  </tr>`).join("");
  const tradeRows = trades.map((t) => {
    const pnl = stocks ? (t.pnl != null && t.pnl !== "" ? t.pnl : t.pnl_usd) : t.pnl_sol;
    const price = stocks ? (t.price != null && t.price !== "" ? t.price : t.price_usd) : t.price_usd;
    return `<tr>
      <td class="num">${esc(fmtHKT(t.time_hkt || t.ts))}</td>
      <td>${esc(sideName(t.side || t.action))}</td>
      <td>${esc(t.symbol)}</td>
      <td class="num">${usd(price)}</td>
      <td class="num">${esc(dash(t.qty != null && t.qty !== "" ? t.qty : t.sol))}</td>
      <td>${esc(dash(t.reason))}</td>
      <td class="num ${cls(Number(pnl))}">${pnl == null || pnl === "" ? "—" : esc(String(pnl))}</td>
    </tr>`;
  }).join("");
  const valueHead = stocks ? "市值（美元）" : "市值";
  const upHead = stocks ? "浮動（美元）" : "浮動";
  return `<article class="card lb-book" id="book-${esc(b.id || "")}">
    <h3><span class="num">${esc(b.id || "—")}</span> ${esc(b.label || "—")}${comboBadge(combo)}${familyBadge(family)}</h3>
    <p class="note">權益 ${usd(b.equity_usd, 2)} · 回報 ${pctPoints(b.ret_pct)} · 持倉 ${esc(String(b.open_positions == null ? positions.length : b.open_positions))} · 贏/平 ${esc(dash(b.wins))} / ${esc(dash(b.closed))}</p>
    <section class="book-sec" aria-label="持倉">
      <h4>持倉</h4>
      ${positions.length ? `<div class="scroll"><table><thead><tr><th>代號</th><th>入場</th><th>而家</th><th>回報</th><th>${valueHead}</th><th>${upHead}</th><th>開倉（香港）</th><th>原因</th></tr></thead><tbody>${posRows}</tbody></table></div>` : `<p class="muted">未有持倉</p>`}
    </section>
    <section class="book-sec" aria-label="成交">
      <h4>成交</h4>
      ${trades.length ? `<div class="scroll"><table><thead><tr><th>時間（香港）</th><th>方向</th><th>代號</th><th>價格</th><th>數量</th><th>原因</th><th>盈虧</th></tr></thead><tbody>${tradeRows}</tbody></table></div>` : `<p class="muted">未有成交</p>`}
    </section>
  </article>`;
}


function leaderboardHtml(item, market) {
  boardMarket = market === "stocks" ? "stocks" : "crypto";
  const blanks = `<div class="kpis lb-kpis">${kpi("帳本", "—")}${kpi("已啟動", "—")}${kpi("起始", "—")}${kpi("更新（香港）", "—")}</div>`;
  if (!item || !item.data || typeof item.data !== "object") {
    return `${blanks}<p class="muted">等緊 Demo 排行榜傳上嚟。${esc(matrixWait(undefined, boardMarket))}會喺度按名次排。</p>`;
  }
  const d = item.data;
  const received = parseTime(item.received_at);
  const stale = received != null && Date.now() - received > 10 * 60 * 1000;
  const rows = (Array.isArray(d.books) ? d.books : []).filter((b) => b && typeof b === "object");
  rows.sort((a, b) => {
    const ra = rankNum(a);
    const rb = rankNum(b);
    if (ra == null && rb == null) return String(a.id || "").localeCompare(String(b.id || ""));
    if (ra == null) return 1;
    if (rb == null) return -1;
    if (ra !== rb) return ra - rb;
    return String(a.id || "").localeCompare(String(b.id || ""));
  });
  const start = d.start_usd == null || d.start_usd === "" ? "—" : usd(d.start_usd, 0);
  const counts = (d.initialized_count != null || d.book_count != null)
    ? ` · 已啟動 ${esc(dash(d.initialized_count))} / ${esc(dash(d.book_count))}` : "";
  const updated = d.updated_hkt ? String(d.updated_hkt) : "—";
  const extra = d.disclaimer == null ? "" : String(d.disclaimer).trim();
  const norm = (s) => s.replace(/[。．.\s]/g, "");
  const extraHtml = extra && norm(extra) !== norm("模擬盤，唔係真錢，唔係投資建議")
    ? `<p class="note">${esc(extra)}</p>` : "";
  const body = rows.length ? `<div class="scroll lb-scroll"><table class="lb"><thead><tr>
      <th>排名</th><th>編號</th><th>名稱</th><th>權益（美元）</th><th>回報</th><th>贏 / 平倉</th><th>Kill / 狀態</th><th>參數</th>
    </tr></thead><tbody>${rows.map((b) => {
      const rank = rankNum(b);
      const combo = bookCombo(b);
      const idle = b.initialized === false || b.status === "not_started" || b.status === "missing_config";
      const killed = b.kill === true;
      const ret = b.ret_pct == null || b.ret_pct === "" ? null : Number(b.ret_pct);
      const wins = b.wins == null || b.wins === "" ? "—" : String(b.wins);
      const closed = b.closed == null || b.closed === "" ? "—" : String(b.closed);
      const kill = killed ? `<span class="dn">已停 kill</span>` : (b.kill === false ? `<span class="muted">kill 未觸發</span>` : `<span class="muted">kill —</span>`);
      const tone = killed ? "muted" : (b.status === "running" ? "up" : (b.status === "not_started" || b.status === "missing_config" ? "wait" : ""));
      return `<tr class="${idle ? "idle" : ""} ${killed ? "killed" : ""}">
        <td class="num">${rank == null ? "—" : esc(String(rank))}</td>
        <td class="num">${esc(b.id || "—")}</td>
        <td><b>${esc(b.label || "—")}</b>${comboBadge(combo)}${familyBadge(bookFamily(b))}${b.note ? `<div class="muted">${esc(b.note)}</div>` : ""}</td>
        <td class="num">${usd(b.equity_usd, 2)}</td>
        <td class="num ${cls(ret)}">${pctPoints(b.ret_pct)}${b.ret_sol_pct == null || b.ret_sol_pct === "" ? "" : `<div class="muted">SOL ${esc(pctPoints(b.ret_sol_pct))}</div>`}</td>
        <td class="num">${esc(wins)} / ${esc(closed)}${b.open_positions == null || b.open_positions === "" ? "" : `<div class="muted">持倉 ${esc(String(b.open_positions))}</div>`}</td>
        <td>${kill}<div class="${tone}">${esc(statusLabel(b.status))}</div></td>
        <td class="params">${esc(shortParams(b.params, combo))}</td>
      </tr>`;
    }).join("")}</tbody></table></div>` : `<p class="muted">未有帳本。${esc(matrixWait(d.book_count, boardMarket))}會喺度按名次排。</p>`;
  const details = rows.map(demoBookDetail).join("");
  const shown = `<div class="kpis lb-kpis">${kpi("帳本", esc(dash(d.book_count != null ? d.book_count : rows.length)))}${kpi("已啟動", esc(dash(d.initialized_count)))}${kpi("起始", esc(start))}${kpi("更新（香港）", esc(updated))}</div>`;
  return `${shown}<div class="lb-head">
      <p class="note">今次顯示 <b class="num">${rows.length}</b> 本</p>
      <p class="note">起始 ${esc(start)}${counts}${stale ? ` · <span class="stale">數據可能過時（我部電腦暫停中）</span>` : ` · ${esc(ago(received))}`}</p>
    </div>
    ${extraHtml}
    ${body}
    <div class="lb-books">${details || ""}</div>
    ${d.params_source ? `<p class="note">參數來源：${esc(d.params_source)}</p>` : ""}`;
}

function bookCard(name, book, item) {
  if (!item || !item.data) {
    return `<article class="card book-card"><h2>${esc(name)}</h2>
      <div class="kpis">${kpi("而家權益（美元）", "—")}${kpi("回報", "—")}${kpi("已實現", "—")}${kpi("未實現", "—")}</div>
      <p class="muted">等緊數據傳上嚟</p></article>`;
  }
  const d = item.data;
  const cfg = d.config || {};
  const received = parseTime(item.received_at);
  const saved = parseTime(d.state_saved_hkt);
  const stale = received != null && Date.now() - received > 10 * 60 * 1000;
  const positions = Array.isArray(d.positions) ? d.positions : [];
  const trades = (Array.isArray(d.trades) ? d.trades.slice() : []).sort((a, b) => (parseTime(b.time_hkt || b.ts) || 0) - (parseTime(a.time_hkt || a.ts) || 0));
  const crypto = book === "crypto";
  const cost = crypto ? cryptoCost(cfg) : stockCost(cfg);
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
  return `<article class="card book-card">
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
    <section class="book-sec" aria-label="權益曲線"><h3>權益曲線</h3>
    ${chart(equityPoints(book, d))}</section>
    <section class="book-sec" aria-label="持倉"><h4>持倉</h4>
    ${positions.length ? `<div class="scroll"><table><thead><tr><th>代號</th><th>入場</th><th>而家</th><th>回報</th><th>市值</th><th>浮動</th><th>開倉（香港）</th><th>原因</th></tr></thead><tbody>${posRows}</tbody></table></div>` : `<p class="muted">未有持倉</p>`}</section>
    <section class="book-sec" aria-label="成交"><h4>成交</h4>
    ${trades.length ? `<div class="scroll"><table><thead><tr><th>時間（香港）</th><th>方向</th><th>代號</th><th>價格</th><th>數量</th><th>原因</th><th>盈虧</th></tr></thead><tbody>${tradeRows}</tbody></table></div>` : `<p class="muted">未有成交</p>`}</section>
    <p class="note">成本假設：${esc(cost)}</p>
    ${cfg.trading_hours ? `<p class="note">${esc(cfg.trading_hours)}</p>` : ""}
  </article>`;
}


function funnelHtml(item) {
  const data = item && item.data ? item.data : item;
  const f = data && data.funnel;
  if (!f || !Array.isArray(f.stages) || !f.stages.length) {
    const names = ["Scout", "Filter", "Analyst", "Sniper", "Guard"];
    const stages = names.map((n) => `<div class="funnel-stage"><b>${n}</b><div class="counts">見過 — · 過 — · 跳過 —</div></div>`).join("");
    return `<p class="muted">等緊 Copy Funnel 傳上嚟（引擎會推 Scout→Filter→Analyst→Sniper→Guard）。</p><div class="funnel-stages">${stages}</div>`;
  }
  const scout = f.scout || (data && data.scout) || {};
  const stages = f.stages.map((s) => `<div class="funnel-stage">
    <b>${esc(s.label || s.id)}</b>
    <div class="counts">見過 ${esc(dash(s.seen))} · 過 ${esc(dash(s.passed))} · 跳過 ${esc(dash(s.skipped))}</div>
    <div class="detail">${esc(s.detail || "")}</div>
  </div>`).join("");
  const events = Array.isArray(f.events) ? f.events : [];
  const log = events.length ? `<ol class="funnel-log">${events.map((e) => {
    const act = String(e.action || "");
    const tag = act === "skip" ? "skip" : act === "copy" ? "copy" : act === "exit" ? "exit" : "pass";
    return `<li><time class="num">${esc(fmtHKT(e.ts))}</time>
      <span class="tag ${tag}">${esc(act || "—")}</span>
      <b>${esc(e.stage || "")}</b> ${esc(e.symbol || "—")}
      <div class="muted">${esc(e.reason || "")}</div></li>`;
  }).join("")}</ol>` : `<p class="muted">未有 skipped／copied 日誌</p>`;
  const scoutLine = `Scout 錢包 ${esc(dash(scout.wallets_n))} · flow ${esc(dash(scout.flow_n))} · 對上池 ${esc(dash(scout.matched))}${scout.min_buy_usd != null ? ` · 大額門檻 $${esc(String(scout.min_buy_usd))}` : ""}`;
  return `<p class="note">${esc(f.disclaimer || "模擬盤 Copy Funnel")}</p>
    <p class="note">${scoutLine}</p>
    <div class="funnel-stages">${stages}</div>
    <h2 style="margin-top:12px">最近 skipped／copied</h2>
    ${log}`;
}

const METHOD_SPECS = [
  {id: "M1", code: "MomBreak", name_zh: "動量突破", name_en: "Momentum Breakout", label: "M1 MomBreak｜動量突破"},
  {id: "M2", code: "TrendMA", name_zh: "均線趨勢", name_en: "Trend Following MA", label: "M2 TrendMA｜均線趨勢"},
  {id: "M3", code: "VolBreak", name_zh: "波動突破", name_en: "Volatility Breakout", label: "M3 VolBreak｜波動突破"},
  {id: "M4", code: "MeanRev", name_zh: "均值回歸", name_en: "Mean Reversion", label: "M4 MeanRev｜均值回歸"},
  {id: "M5", code: "XSecMom", name_zh: "相對強弱", name_en: "Cross-Sectional Momentum", label: "M5 XSecMom｜相對強弱"},
];

function methodRows(d) {
  const live = d && Array.isArray(d.books) ? d.books.filter((b) => b && typeof b === "object") : [];
  if (!live.length) return METHOD_SPECS.map((s) => Object.assign({waiting: true, start_usd: 100}, s));
  const byId = {};
  live.forEach((b) => {
    if (b.id != null && b.id !== "") byId[String(b.id)] = b;
  });
  const seen = {};
  const rows = [];
  METHOD_SPECS.forEach((s) => {
    const hit = byId[s.id];
    if (hit) {
      seen[s.id] = true;
      rows.push(Object.assign({}, s, hit));
    } else {
      rows.push(Object.assign({waiting: true, start_usd: 100}, s));
    }
  });
  live.forEach((b) => {
    const id = b.id == null ? "" : String(b.id);
    if (id && seen[id]) return;
    rows.push(b);
  });
  return rows;
}

function methodWinRate(b) {
  if (!b || b.waiting) return "—";
  const given = b.win_rate_pct;
  if (given != null && given !== "" && Number.isFinite(Number(given))) {
    return Number(given).toFixed(1) + "%";
  }
  const closed = Number(b.closed);
  const wins = Number(b.wins);
  if (Number.isFinite(closed) && closed > 0 && Number.isFinite(wins)) {
    return ((wins / closed) * 100).toFixed(1) + "% · " + wins + " 贏 / " + closed + " 平倉";
  }
  const w = b.wins == null || b.wins === "" ? "0" : String(b.wins);
  const c = b.closed == null || b.closed === "" ? "0" : String(b.closed);
  return "未有平倉 · " + w + " 贏 / " + c + " 平倉";
}

function methodWarnings(b) {
  const out = [];
  if (b && b.warning) out.push(String(b.warning));
  const flags = b && b.backtest && Array.isArray(b.backtest.warning_flags) ? b.backtest.warning_flags : [];
  flags.forEach((f) => { if (f) out.push(String(f)); });
  return out;
}

function methodPositions(b) {
  const positions = Array.isArray(b.positions) ? b.positions : [];
  if (!positions.length) return `<p class="muted">${b.waiting ? "等緊數據" : "未有持倉"}</p>`;
  const rows = positions.map((p) => {
    const qty = num(p.qty, 4);
    return `<tr>
    <td><b>${esc(p.symbol)}</b></td>
    <td class="num">${esc(dash(qty == null ? p.qty : qty))}</td>
    <td class="num">${usd(p.entry_usd)}</td>
    <td class="num">${usd(p.last_usd)}</td>
    <td class="num ${cls(Number(p.upnl_usd))}">${usd(p.upnl_usd, 2)}</td>
    <td>${esc(p.why || "—")}</td>
  </tr>`;
  }).join("");
  return `<div class="scroll"><table><thead><tr><th>代號</th><th>數量</th><th>入場</th><th>而家</th><th>浮動</th><th>原因</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function methodCard(b) {
  const label = b.label || `${b.id || ""} ${b.code || ""}｜${b.name_zh || ""}`.replace(/｜$/, "");
  const zh = b.name_zh ? String(b.name_zh) : "";
  const en = b.name_en ? String(b.name_en) : "";
  const ret = b.ret_pct == null || b.ret_pct === "" ? null : Number(b.ret_pct);
  const start = b.start_usd == null || b.start_usd === "" ? 100 : b.start_usd;
  const openN = b.waiting ? "—" : String(b.open_positions == null ? (Array.isArray(b.positions) ? b.positions.length : 0) : b.open_positions);
  const flags = b.waiting ? [] : methodWarnings(b);
  const bt = !b.waiting && b.backtest && typeof b.backtest === "object" ? b.backtest : null;
  const dd = bt && bt.max_dd_pct != null && bt.max_dd_pct !== "" && Number.isFinite(Number(bt.max_dd_pct))
    ? Number(bt.max_dd_pct).toFixed(2) + "%" : "—";
  const btLine = bt ? `<p class="note">回測淨利 ${esc(pctPoints(bt.net_pct))} · 最大回撤 ${esc(dd)} · 回測平倉 ${esc(dash(bt.closed))}</p>` : "";
  const warn = flags.length
    ? `<p class="method-warn" role="note"><b>WARNING</b> ${esc(flags.join(" · "))}</p>`
    : `<p class="note">${b.waiting ? "回測警示：等緊數據" : "回測警示：無"}</p>`;
  const eq = usd(b.equity_usd, 2);
  return `<article class="card method-card" id="method-${esc(b.id || "")}">
    <h3><span class="num">${esc(b.id || "—")}</span> ${esc(b.code || "")}</h3>
    <p class="method-name">${esc(zh || label)}${en ? `<span class="en">${esc(en)}</span>` : ""}</p>
    <p class="note">${esc(label)}</p>
    <div class="kpis">
      ${kpi("權益", `<span class="${cls(ret)}">${eq}</span>`)}
      ${kpi("起始", usd(start, 0))}
      ${kpi("勝率", esc(methodWinRate(b)))}
      ${kpi("持倉", esc(openN))}
    </div>
    <p class="note">${esc(b.note || (b.waiting ? "等緊數據傳上嚟" : "暫無簡介"))}</p>
    ${warn}
    ${btLine}
    <section class="book-sec" aria-label="持倉"><h4>持倉</h4>${methodPositions(b)}</section>
  </article>`;
}

function methodsHtml(item) {
  const d = item && item.data && typeof item.data === "object" ? item.data : null;
  const rows = methodRows(d);
  const received = item ? parseTime(item.received_at) : null;
  const stale = received != null && Date.now() - received > 10 * 60 * 1000;
  const updated = d && (d.generated_hkt || d.updated_hkt) ? String(d.generated_hkt || d.updated_hkt) : "";
  const start = d && d.start_usd != null && d.start_usd !== "" ? d.start_usd : 100;
  const freshness = !d ? " · 等緊五方法紙盤傳上嚟" : (stale ? ` · <span class="stale">數據可能過時（我部電腦暫停中）</span>` : (received ? " · " + esc(ago(received)) : ""));
  return `<p class="note">今次 ${rows.length} 本 · 起始 ${esc(usd(start, 0))}${updated ? " · " + esc(updated) : ""}${freshness}</p>
    <div class="method-grid">${rows.map(methodCard).join("")}</div>`;
}

const GOLD_SPECS = [
  {id: "G1", code: "TrendMA", name_zh: "均線趨勢", name_en: "Trend Following MA", label: "G1 TrendMA｜均線趨勢｜XAUUSD"},
  {id: "G2", code: "MomBreak", name_zh: "動量突破", name_en: "Momentum Breakout", label: "G2 MomBreak｜動量突破｜XAUUSD"},
  {id: "G4", code: "MeanRev", name_zh: "均值回歸", name_en: "Mean Reversion", label: "G4 MeanRev｜均值回歸｜XAUUSD", warning: "逆勢；均值回歸，趨勢市風險高"},
  {id: "G5", code: "TrendMASlow", name_zh: "慢均線 50／200", name_en: "Slow Trend MA", label: "G5 TrendMASlow｜慢均線 50／200｜XAUUSD"},
];
const GOLD_HOLD = {
  id: "G3", code: "VolBreak", name_zh: "波動突破", name_en: "Volatility Breakout",
  label: "G3 VolBreak｜波動突破｜XAUUSD", hold: true,
};

function goldSpec(id) {
  if (id === "G3") return GOLD_HOLD;
  for (let i = 0; i < GOLD_SPECS.length; i++) {
    if (GOLD_SPECS[i].id === id) return GOLD_SPECS[i];
  }
  return null;
}

function goldMerge(spec, hit) {
  const row = Object.assign({}, spec || {}, hit || {});
  if ((row.warning == null || row.warning === "") && spec && spec.warning) row.warning = spec.warning;
  if (spec && spec.hold) row.hold = true;
  if (hit && hit.live_enabled === false) row.hold = true;
  const status = String((hit && hit.status) || row.status || "").toLowerCase();
  if (status === "hold" || status === "paused") row.hold = true;
  if (String(row.id || "") === "G3") row.hold = true;
  if (!row.symbol) row.symbol = "XAUUSD";
  if (!row.yahoo_proxy) row.yahoo_proxy = "GC=F";
  if (row.start_usd == null || row.start_usd === "") row.start_usd = 100;
  return row;
}

function goldRows(d) {
  const live = d && Array.isArray(d.books) ? d.books.filter((b) => b && typeof b === "object") : [];
  const base = {
    symbol: d && d.symbol ? d.symbol : "XAUUSD",
    yahoo_proxy: d && d.yahoo_proxy ? d.yahoo_proxy : "GC=F",
    start_usd: d && d.start_usd != null && d.start_usd !== "" ? d.start_usd : 100,
  };
  if (!live.length) return GOLD_SPECS.map((s) => Object.assign({waiting: true}, base, s));
  const byId = {};
  live.forEach((b) => {
    if (b.id != null && b.id !== "") byId[String(b.id)] = b;
  });
  const seen = {};
  const rows = [];
  ["G1", "G2", "G3", "G4", "G5"].forEach((id) => {
    const spec = goldSpec(id);
    const hit = byId[id];
    if (!hit) {
      if (id === "G3") return;
      rows.push(Object.assign({waiting: true}, base, spec));
      return;
    }
    seen[id] = true;
    rows.push(goldMerge(Object.assign({}, base, spec), hit));
  });
  live.forEach((b) => {
    const id = b.id == null ? "" : String(b.id);
    if (id && seen[id]) return;
    rows.push(goldMerge(Object.assign({}, base, id === "G3" ? {hold: true} : {}), b));
  });
  return rows;
}

function goldBacktest(b) {
  const bt = b && b.backtest && typeof b.backtest === "object" ? Object.assign({}, b.backtest) : {};
  if ((bt.net_pct == null || bt.net_pct === "") && b && b.backtest_net_pct != null) bt.net_pct = b.backtest_net_pct;
  if ((bt.max_dd_pct == null || bt.max_dd_pct === "") && b && b.backtest_max_dd_pct != null) bt.max_dd_pct = b.backtest_max_dd_pct;
  if ((bt.closed == null || bt.closed === "") && b && b.backtest_closed != null) bt.closed = b.backtest_closed;
  if (bt.net_pct == null && bt.max_dd_pct == null && bt.closed == null) return null;
  return bt;
}

function goldWarnings(b) {
  const out = [];
  if (b && b.warning) out.push(String(b.warning));
  const nested = b && b.backtest && Array.isArray(b.backtest.warning_flags) ? b.backtest.warning_flags : [];
  const flat = b && Array.isArray(b.warning_flags) ? b.warning_flags : [];
  nested.concat(flat).forEach((f) => {
    if (f && out.indexOf(String(f)) < 0) out.push(String(f));
  });
  return out;
}

function goldRet(b) {
  if (!b || b.waiting) return null;
  if (b.ret_pct != null && b.ret_pct !== "" && Number.isFinite(Number(b.ret_pct))) return Number(b.ret_pct);
  const eq = Number(b.equity_usd);
  const start = Number(b.start_usd == null || b.start_usd === "" ? 100 : b.start_usd);
  if (Number.isFinite(eq) && Number.isFinite(start) && start) return ((eq - start) / start) * 100;
  return null;
}

function goldOpenCount(b) {
  if (!b || b.waiting) return "—";
  if (b.open_positions != null && b.open_positions !== "") return String(b.open_positions);
  if (Array.isArray(b.positions)) return String(b.positions.length);
  if (b.positions != null && b.positions !== "" && Number.isFinite(Number(b.positions))) return String(b.positions);
  return "0";
}

function goldPositions(b) {
  const positions = Array.isArray(b.positions) ? b.positions : [];
  if (!positions.length) {
    const n = goldOpenCount(b);
    if (!b.waiting && n !== "—" && n !== "0") return `<p class="muted">持倉 ${esc(n)}，未有明細</p>`;
    return `<p class="muted">${b.waiting ? "等緊數據" : "未有持倉"}</p>`;
  }
  const rows = positions.map((p) => `<tr>
    <td><b>${esc(p.symbol || b.symbol || "XAUUSD")}</b></td>
    <td class="num">${esc(dash(p.qty))}</td>
    <td class="num">${usd(p.entry_usd)}</td>
    <td class="num">${usd(p.last_usd)}</td>
    <td class="num ${cls(Number(p.upnl_usd))}">${usd(p.upnl_usd, 2)}</td>
    <td>${esc(p.why || p.reason || "—")}</td>
  </tr>`).join("");
  return `<div class="scroll"><table><thead><tr><th>代號</th><th>數量</th><th>入場</th><th>而家</th><th>浮動</th><th>原因</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function goldHoldLine(b) {
  const bt = goldBacktest(b);
  const dd = bt && bt.max_dd_pct != null && bt.max_dd_pct !== "" && Number.isFinite(Number(bt.max_dd_pct))
    ? Number(bt.max_dd_pct) : null;
  const why = dd != null && dd > 20
    ? "回測最大回撤 " + dd.toFixed(2) + "% 高過 20%，未開模擬倉"
    : "未開模擬倉";
  return `<p class="gold-hold" role="note"><b>HOLD</b> ${esc(why)}</p>`;
}

function goldCard(b) {
  const label = b.label || `${b.id || ""} ${b.code || ""}｜${b.name_zh || ""}`.replace(/｜$/, "");
  const zh = b.name_zh ? String(b.name_zh) : "";
  const en = b.name_en ? String(b.name_en) : "";
  const ret = goldRet(b);
  const start = b.start_usd == null || b.start_usd === "" ? 100 : b.start_usd;
  const flags = goldWarnings(b);
  const hold = b.hold === true;
  const bt = !b.waiting ? goldBacktest(b) : null;
  const dd = bt && bt.max_dd_pct != null && bt.max_dd_pct !== "" && Number.isFinite(Number(bt.max_dd_pct))
    ? Number(bt.max_dd_pct).toFixed(2) + "%" : "—";
  const btLine = bt ? `<p class="note">回測淨利 ${esc(pctPoints(bt.net_pct))} · 最大回撤 ${esc(dd)}</p>` : "";
  const warn = hold
    ? goldHoldLine(b)
    : (flags.length
      ? `<p class="method-warn" role="note"><b>WARNING</b> ${esc(flags.join(" · "))}</p>`
      : `<p class="note">${b.waiting ? "回測警示：等緊數據" : "回測警示：無"}</p>`);
  const badge = hold ? `<span class="combo">HOLD</span>` : (flags.length ? `<span class="combo family">WARNING</span>` : "");
  const sym = b.symbol || "XAUUSD";
  const proxy = b.yahoo_proxy || "GC=F";
  const tick = b.last_tick_hkt || b.state_saved_hkt;
  return `<article class="card method-card${hold ? " is-hold" : ""}" id="gold-${esc(b.id || "")}">
    <h3><span class="num">${esc(b.id || "—")}</span> ${esc(b.code || "")}${badge}</h3>
    <p class="method-name">${esc(zh || label)}${en ? `<span class="en">${esc(en)}</span>` : ""}</p>
    <p class="note">${esc(label)}</p>
    <p class="note">只做 ${esc(sym)}｜代理 ${esc(proxy)}｜模擬盤</p>
    <div class="kpis">
      ${kpi("權益", `<span class="${cls(ret)}">${usd(b.equity_usd, 2)}</span>`)}
      ${kpi("現金", b.waiting ? "—" : usd(b.cash_usd, 2))}
      ${kpi("已平倉", b.waiting ? "—" : esc(dash(b.closed)))}
      ${kpi("持倉", esc(goldOpenCount(b)))}
    </div>
    <p class="note">起始 ${esc(usd(start, 0))}${ret == null ? "" : " · 回報 " + esc(pctPoints(ret))}${tick ? " · 最後 tick " + esc(fmtHKT(tick)) : ""}</p>
    <p class="note">${esc(b.note || (b.waiting ? "等緊數據傳上嚟" : "只做 XAUUSD｜代理 GC=F｜模擬盤"))}</p>
    ${warn}
    ${btLine}
    <section class="book-sec" aria-label="持倉"><h4>持倉</h4>${goldPositions(b)}</section>
  </article>`;
}

function goldHtml(item) {
  const d = item && item.data && typeof item.data === "object" ? item.data : null;
  const rows = goldRows(d);
  const received = item ? parseTime(item.received_at) : null;
  const stale = received != null && Date.now() - received > 10 * 60 * 1000;
  const updated = d && (d.generated_hkt || d.updated_hkt) ? String(d.generated_hkt || d.updated_hkt) : "";
  const start = d && d.start_usd != null && d.start_usd !== "" ? d.start_usd : 100;
  const sym = d && d.symbol ? String(d.symbol) : "XAUUSD";
  const proxy = d && d.yahoo_proxy ? String(d.yahoo_proxy) : "GC=F";
  const freshness = !d ? " · 等緊黃金紙盤傳上嚟" : (stale ? ` · <span class="stale">數據可能過時（我部電腦暫停中）</span>` : (received ? " · " + esc(ago(received)) : ""));
  return `<p class="note">只做 ${esc(sym)}｜代理 ${esc(proxy)}｜模擬盤</p>
    <p class="note">今次 ${rows.length} 本 · 起始 ${esc(usd(start, 0))}${updated ? " · " + esc(updated) : ""}${freshness}</p>
    <div class="method-grid">${rows.map(goldCard).join("")}</div>`;
}

async function load() {
  const r = await fetch("/api/paper");
  if (!r.ok) throw new Error("讀唔到成績");
  const j = await r.json();
  const pageMarket = document.body && document.body.dataset.market === "stocks" ? "stocks" : "crypto";
  const lb = $("#leaderboard");
  if (lb) {
    lb.innerHTML = leaderboardHtml(pageMarket === "stocks" ? j.leaderboard_stocks : j.leaderboard, pageMarket);
    lb.removeAttribute("aria-busy");
  }
  const methods = $("#methods");
  if (methods) {
    methods.innerHTML = methodsHtml(j && j.leaderboard_methods);
    methods.removeAttribute("aria-busy");
  }
  const gold = $("#gold");
  if (gold) {
    gold.innerHTML = goldHtml(j && j.leaderboard_gold);
    gold.removeAttribute("aria-busy");
  }
  const funnel = $("#funnel");
  if (funnel) funnel.innerHTML = funnelHtml(j && j.crypto);
  const books = $("#books");
  if (books) books.innerHTML = `<div class="books">${bookCard("加密貨幣", "crypto", j.crypto)}${bookCard("美股", "stocks", j.stocks)}</div>`;
}
function tickClock() {
  const el = $("#clock");
  if (!el) return;
  el.textContent = new Intl.DateTimeFormat("zh-HK", {timeZone: "Asia/Hong_Kong", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"}).format(new Date()) + " HKT";
}
tickClock();
setInterval(tickClock, 1000);
load().catch((e) => {
  const lb = $("#leaderboard");
  if (lb) lb.textContent = e.message;
  const methods = $("#methods");
  if (methods) methods.textContent = e.message;
  const gold = $("#gold");
  if (gold) gold.textContent = e.message;
  const funnel = $("#funnel");
  if (funnel) funnel.textContent = e.message;
  const books = $("#books");
  if (books) books.textContent = e.message;
});
setInterval(() => load().catch(() => {}), 30000);
