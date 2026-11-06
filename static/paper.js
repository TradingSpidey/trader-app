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
function shortParams(p) {
  const q = p && typeof p === "object" ? p : {};
  const maxPos = q.max_positions == null || q.max_positions === "" ? "—" : String(q.max_positions);
  const bits = [`TP ${pctOfFrac(q.tp)} / SL ${pctOfFrac(q.sl)} · 日虧 ${pctOfFrac(q.daily_loss_of_start)} · 最多 ${maxPos} 倉 · 單倉 ${pctOfFrac(q.max_position_pct)}`];
  const mom = fmtGate(firstParam(q, ["mom", "momentum", "mom_h1", "min_mom"]));
  const liq = fmtLiq(firstParam(q, ["liq", "min_liq", "liq_usd", "min_liq_usd"]));
  const top10 = fmtGate(firstParam(q, ["top10", "top10_pct", "max_top10"]));
  if (mom) bits.push(`MOM ${mom}`);
  if (liq) bits.push(`LIQ ${liq}`);
  if (top10) bits.push(`TOP10 ${top10}`);
  return bits.join(" · ");
}

function demoBookDetail(b) {
  const positions = Array.isArray(b.positions) ? b.positions : [];
  const trades = (Array.isArray(b.trades) ? b.trades.slice() : []).sort((a, c) => (parseTime(c.time_hkt || c.ts) || 0) - (parseTime(a.time_hkt || a.ts) || 0));
  const posRows = positions.map((p) => `<tr>
    <td><b>${esc(p.symbol)}</b><div class="muted">${esc(shortMint(p.mint))}</div></td>
    <td class="num">${usd(p.entry_usd)}</td>
    <td class="num">${usd(p.last_usd)}</td>
    <td class="num ${cls(p.ret)}">${pctFrac(p.ret)}</td>
    <td class="num">${sol(p.value_sol)}</td>
    <td class="num ${cls(p.upnl_sol)}">${sol(p.upnl_sol)}</td>
    <td class="num">${esc(fmtHKT(p.opened_at))}</td>
    <td>${esc(p.why || p.reason || "暫無數據")}</td>
  </tr>`).join("");
  const tradeRows = trades.map((t) => {
    const pnl = t.pnl_sol;
    return `<tr>
      <td class="num">${esc(fmtHKT(t.time_hkt || t.ts))}</td>
      <td>${esc(sideName(t.side || t.action))}</td>
      <td>${esc(t.symbol)}</td>
      <td class="num">${usd(t.price_usd)}</td>
      <td class="num">${esc(dash(t.qty != null && t.qty !== "" ? t.qty : t.sol))}</td>
      <td>${esc(dash(t.reason))}</td>
      <td class="num ${cls(Number(pnl))}">${pnl == null || pnl === "" ? "—" : esc(String(pnl))}</td>
    </tr>`;
  }).join("");
  return `<article class="card lb-book" id="book-${esc(b.id || "")}">
    <h3>${esc(b.id || "—")} · ${esc(b.label || "—")}</h3>
    <p class="note">權益 ${usd(b.equity_usd, 2)} · 回報 ${pctPoints(b.ret_pct)} · 持倉 ${esc(String(b.open_positions == null ? positions.length : b.open_positions))} · 贏/平 ${esc(dash(b.wins))} / ${esc(dash(b.closed))}</p>
    <h4>持倉</h4>
    ${positions.length ? `<div class="scroll"><table><thead><tr><th>代號</th><th>入場</th><th>而家</th><th>回報</th><th>市值</th><th>浮動</th><th>開倉（香港）</th><th>原因</th></tr></thead><tbody>${posRows}</tbody></table></div>` : `<p class="muted">未有持倉</p>`}
    <h4 style="margin-top:10px">成交</h4>
    ${trades.length ? `<div class="scroll"><table><thead><tr><th>時間（香港）</th><th>方向</th><th>代號</th><th>價格</th><th>數量</th><th>原因</th><th>盈虧</th></tr></thead><tbody>${tradeRows}</tbody></table></div>` : `<p class="muted">未有成交</p>`}
  </article>`;
}


function leaderboardHtml(item) {
  if (!item || !item.data || typeof item.data !== "object") {
    return `<p class="muted">等緊 Demo 排行榜傳上嚟。51 本角色矩陣（CTRL + EXIT/RISK/SCAN/SNIPER/RUG ×10）會喺度按名次排。</p>`;
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
  const body = rows.length ? `<div class="scroll"><table class="lb"><thead><tr>
      <th>排名</th><th>編號</th><th>名稱</th><th>權益（美元）</th><th>回報</th><th>贏 / 平倉</th><th>Kill / 狀態</th><th>參數</th>
    </tr></thead><tbody>${rows.map((b) => {
      const rank = rankNum(b);
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
        <td><b>${esc(b.label || "—")}</b>${b.note ? `<div class="muted">${esc(b.note)}</div>` : ""}</td>
        <td class="num">${usd(b.equity_usd, 2)}</td>
        <td class="num ${cls(ret)}">${pctPoints(b.ret_pct)}${b.ret_sol_pct == null || b.ret_sol_pct === "" ? "" : `<div class="muted">SOL ${esc(pctPoints(b.ret_sol_pct))}</div>`}</td>
        <td class="num">${esc(wins)} / ${esc(closed)}${b.open_positions == null || b.open_positions === "" ? "" : `<div class="muted">持倉 ${esc(String(b.open_positions))}</div>`}</td>
        <td>${kill}<div class="${tone}">${esc(statusLabel(b.status))}</div></td>
        <td class="params">${esc(shortParams(b.params))}</td>
      </tr>`;
    }).join("")}</tbody></table></div>` : `<p class="muted">未有帳本</p>`;
  const details = rows.map(demoBookDetail).join("");
  return `<div class="lb-head">
      <p class="note">更新（香港）<b class="num">${esc(updated)}</b></p>
      <p class="note">起始 ${esc(start)}${counts}${stale ? ` · <span class="stale">數據可能過時（我部電腦暫停中）</span>` : ` · ${esc(ago(received))}`}</p>
    </div>
    ${extraHtml}
    ${body}
    <div class="lb-books">${details || ""}</div>
    ${d.params_source ? `<p class="note">參數來源：${esc(d.params_source)}</p>` : ""}`;
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


function funnelHtml(item) {
  const data = item && item.data ? item.data : item;
  const f = data && data.funnel;
  if (!f || !Array.isArray(f.stages) || !f.stages.length) {
    return `<p class="muted">等緊 Copy Funnel 傳上嚟（引擎會推 Scout→Filter→Analyst→Sniper→Guard）。</p>`;
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

async function load() {
  const r = await fetch("/api/paper");
  if (!r.ok) throw new Error("讀唔到成績");
  const j = await r.json();
  const lb = $("#leaderboard");
  if (lb) lb.innerHTML = leaderboardHtml(j && j.leaderboard);
  const funnel = $("#funnel");
  if (funnel) funnel.innerHTML = funnelHtml(j && j.crypto);
  const books = $("#books");
  if (books) books.innerHTML = `<div class="books">${bookCard("加密貨幣", "crypto", j.crypto)}${bookCard("美股", "stocks", j.stocks)}</div>`;
}
load().catch((e) => {
  const lb = $("#leaderboard");
  if (lb) lb.textContent = e.message;
  const funnel = $("#funnel");
  if (funnel) funnel.textContent = e.message;
  const books = $("#books");
  if (books) books.textContent = e.message;
});
setInterval(() => load().catch(() => {}), 30000);
