"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function num(v, d) {
  if (v == null || Number.isNaN(Number(v))) return null;
  return Number(v).toLocaleString("en-US", {maximumFractionDigits: d});
}
function sol(v, sign) {
  const n = num(v, 4);
  if (n == null) return "—";
  const s = Number(v);
  return (sign ? (s > 0 ? "+" : "") : "") + n + " SOL";
}
function usd(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const d = Math.abs(n) >= 100 ? 0 : Math.abs(n) >= 1 ? 2 : 8;
  return "$" + n.toLocaleString("en-US", {maximumFractionDigits: d});
}
function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
}
function cls(v) { return v > 0 ? "up" : v < 0 ? "dn" : ""; }

const FACES = {
  scan: "M6 10h20v14H6zM10 6h4v4h-4zM18 6h4v4h-4zM10 16h4M18 16h4",
  sniper: "M8 8h16v16H8zM4 12h4M24 12h4M12 18h8",
  whale: "M4 16c4-8 20-8 24 0c-4 8-20 8-24 0zM12 15h2M18 15h2M12 19h8",
  search: "M8 8h10v10H8zM16 16l8 8",
  rug: "M16 4l12 22H4zM16 12v6M16 22h0",
  exit: "M6 8h12v16H6zM18 12h8M22 8v12",
  risk: "M8 6h16v6H8zM8 14h16v12H8z",
  dev: "M6 20V8h8l4 4v8zM14 8v4h4",
  chief: "M8 12a8 8 0 1 1 16 0v2H8zM12 12h2M18 12h2M12 18h8",
};

function avatar(id, large) {
  const d = FACES[id] || FACES.chief;
  return `<div class="ava ${large ? "lg" : ""}" style="--c:var(--bot, #3ee0ff)"><svg viewBox="0 0 32 32" fill="none" stroke="var(--c, #3ee0ff)" stroke-width="1.7" stroke-linecap="round"><path d="${d}"/></svg></div>`;
}

function metric(m) {
  let shown = m.value;
  if (typeof shown === "number") {
    if (m.label.includes("升跌") || m.label.includes("回報")) shown = pct(shown);
    else if (m.label.includes("百分比")) shown = num(shown, 2) + "%";
    else if (m.label.includes("SOL")) shown = sol(shown, false);
    else if (m.label.includes("流動性")) shown = usd(shown);
    else shown = num(shown, 4);
  }
  if (shown == null || shown === "") shown = "暫無數據";
  return `<div><dt>${esc(m.label)}</dt><dd title="${esc(m.source || "")}">${esc(shown)}</dd></div>`;
}

function spark(candles) {
  const rows = (candles || []).filter((c) => c && c.c != null);
  if (rows.length < 2) return `<p class="muted">暫無走勢</p>`;
  const w = 280, h = 42, p = 2;
  const cs = rows.map((c) => c.c);
  let lo = Math.min(...cs), hi = Math.max(...cs);
  if (hi === lo) { hi += 1; lo -= 1; }
  const x = (i) => p + (w - p * 2) * i / (cs.length - 1);
  const y = (v) => p + (h - p * 2) * (hi - v) / (hi - lo);
  const line = cs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const up = cs[cs.length - 1] >= cs[0];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="公開 5 分鐘收市價"><path d="${line}" fill="none" stroke="${up ? "#3dffb0" : "#ff5d7a"}" stroke-width="2"/></svg>`;
}

function render(j) {
  const a = j.account || {};
  const pnl = a.day_pnl_sol;
  $("#stats").innerHTML = `
    <div class="stat"><span>今日模擬盈虧</span><b class="num ${cls(pnl)}">${a.quote_missing ? "—" : sol(pnl, true)}</b></div>
    <div class="stat"><span>勝率（已平倉）</span><b class="num">${a.win_rate == null ? esc(a.win_rate_text || "未有已平倉交易") : (a.win_rate * 100).toFixed(1) + "%"}</b></div>
    <div class="stat"><span>模擬權益</span><b class="num">${sol(a.equity_sol, false)}</b></div>
    <div class="stat"><span>SOL 報價</span><b class="num">${usd(j.sol_usd)}</b></div>`;
  const kill = $("#kill");
  kill.textContent = a.kill ? "解除停止" : "風控停止";
  kill.classList.toggle("danger", !a.kill);
  kill.dataset.on = a.kill ? "0" : "1";

  const tape = j.tape || [];
  const health = j.health || {};
  const hcls = (s) => s === "正常" ? "ok" : s === "限速中" ? "limit" : s === "未查" ? "" : "bad";
  $("#health").innerHTML = [
    ["GeckoTerminal", health.geckoterminal],
    ["DexScreener", health.dexscreener],
    ["Solana RPC", health.solana_rpc],
  ].map(([name, state]) => `<span class="hp ${hcls(state)}">${esc(name)} ${esc(state || "未查")}</span>`).join("");
  $("#tape-age").textContent = j.market_age_sec == null ? "" : "更新於 " + j.market_age_sec + " 秒前";
  $("#tape").innerHTML = tape.length ? tape.map((t) => `<span>${esc(t.symbol)} <b class="${cls(t.change_h1)}">${pct(t.change_h1)}</b></span>`).join("") : `<span class="muted">暫無熱門報價</span>`;

  const route = (j.chief && j.chief.route) || [];
  $("#chief").innerHTML = `
    ${avatar("chief", true)}
    <div>
      <div class="who"><em>CHIEF</em><b>主管</b></div>
      <p class="detail">${route.length ? route.map(esc).join(" → ") : "等緊第一輪行情。"}</p>
      <span class="tag paper">模擬決策</span>
      <span class="tag live">行情唔係模擬</span>
    </div>`;

  const colors = {scan:"#3ee0ff",sniper:"#ffc14d",whale:"#7aa2ff",search:"#c58bff",rug:"#ff5d7a",exit:"#3dffb0",risk:"#ff9f43",dev:"#ff4d9a"};
  $("#bots").innerHTML = (j.bots || []).map((b) => `
    <article class="panel bot" style="--c:${colors[b.id] || "#3ee0ff"};--bot:${colors[b.id] || "#3ee0ff"}">
      <div class="bot-h">${avatar(b.id)}<div class="who"><em>${esc(b.en)}</em><b>${esc(b.name)} · ${esc(b.role)}</b></div></div>
      <p class="detail">${esc(b.status)}。${esc(b.detail || "")}</p>
      <dl class="metrics">${(b.metrics || []).map(metric).join("")}</dl>
      ${spark(b.candles)}
      ${b.candles_kind === "change" ? `<p class="muted">由公開升跌幅反推，唔係 K 線</p>` : ""}
      ${(b.trades || []).length ? `<ul class="trades">${b.trades.map((t) => `<li>${esc(t.kind)} ${esc(usd(t.usd))} <a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.wallet_short)}</a></li>`).join("")}</ul>` : (b.trades_note ? `<p class="muted">${esc(b.trades_note)}</p>` : "")}
      <p class="pnl"><span class="tag paper">模擬</span> ${b.paper_pnl_sol == null ? "—" : `<b class="num ${cls(b.paper_pnl_sol)}">${sol(b.paper_pnl_sol, true)}</b>`} <span class="muted">${esc(b.paper_note || "")}</span></p>
    </article>`).join("");

  $("#roster").innerHTML = `<h2>值班表</h2>` + (j.bots || []).map((b) => `
    <div class="roster-row">
      <i class="dot ${esc(b.tone)}"></i>
      <div><b>${esc(b.name)}</b><div class="muted">${esc(b.status)}</div></div>
      <div class="num ${cls(b.paper_pnl_sol)}">${b.paper_pnl_sol == null ? "—" : sol(b.paper_pnl_sol, true)}</div>
    </div>`).join("");

  const feed = j.feed || [];
  $("#feed").innerHTML = `<h2>動態</h2>` + (feed.length ? `<ol>${feed.map((f) => `<li><time>${esc((f.ts || "").slice(11, 19))} UTC</time><span class="tag ${f.kind === "paper" ? "paper" : "live"}">${f.kind === "paper" ? "模擬" : "行情"}</span><b>${esc(f.bot)}</b> ${esc(f.text)}</li>`).join("")}</ol>` : `<p class="muted">未有動態</p>`);

  const pos = j.positions || [];
  $("#book").innerHTML = `<h2>模擬持倉</h2>` + (pos.length ? pos.map((p) => `
    <div class="pos">
      <div><b>${esc(p.symbol)}</b><div class="muted">${esc(p.why || "")}</div></div>
      <div class="num">入 ${usd(p.entry_usd)}</div>
      <div class="num">而家 ${usd(p.last_usd)}</div>
      <div class="num ${cls(p.upnl_sol)}">${p.upnl_sol == null ? "—" : sol(p.upnl_sol, true)}</div>
    </div>`).join("") : `<p class="muted">未有模擬倉。規則未過就唔會造數。</p>`);

  const radar = j.radar || [];
  $("#radar").innerHTML = `<h2>新池雷達 <span class="tag live">即時行情</span></h2>` + (radar.length ? radar.map((r) => `
    <div class="radar-row">
      <div><a class="ext" href="https://dexscreener.com/solana/${encodeURIComponent(r.mint || "")}" target="_blank" rel="noopener">${esc(r.symbol)}</a></div>
      <div class="num">${r.age_min == null ? "—" : r.age_min + " 分"}</div>
      <div class="num">${usd(r.liq_usd)}</div>
      <div class="num ${cls(r.change_h1)}">${pct(r.change_h1)}</div>
    </div>`).join("") : `<p class="muted">暫無新池</p>`);

  $("#rules").innerHTML = `<h2>規則</h2><ol>${(j.rules || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ol>`;
  const err = (j.errors || []).join(" ");
  $("#foot").innerHTML = `行情來源：${esc((j.sources && j.sources.market || []).join("、"))}。盈虧係${esc(j.sources && j.sources.paper)}。SOL 報價來源：${esc(j.sol_source || "暫無數據")}。${err ? `<span class="err">${esc(err)}</span>` : ""}`;
}

async function pull() {
  const r = await fetch("/api/desk/state");
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || ("HTTP " + r.status));
  render(j);
}

$("#kill").addEventListener("click", async () => {
  $("#kill").disabled = true;
  try {
    const r = await fetch("/api/desk/kill?on=" + $("#kill").dataset.on, {method: "POST"});
    render(await r.json());
  } catch (e) { $("#foot").textContent = e.message; }
  $("#kill").disabled = false;
});
$("#reset").addEventListener("click", async () => {
  $("#reset").disabled = true;
  try {
    const r = await fetch("/api/desk/reset", {method: "POST"});
    render(await r.json());
  } catch (e) { $("#foot").textContent = e.message; }
  $("#reset").disabled = false;
});

const box = $("#particles");
for (let i = 0; i < 18; i++) {
  const dot = document.createElement("i");
  dot.style.left = (Math.random() * 100) + "%";
  dot.style.bottom = (-Math.random() * 40) + "vh";
  dot.style.animationDelay = (-Math.random() * 14) + "s";
  dot.style.animationDuration = (10 + Math.random() * 10) + "s";
  dot.style.background = i % 3 === 0 ? "#ff4d9a" : i % 3 === 1 ? "#3dffb0" : "#3ee0ff";
  box.appendChild(dot);
}

pull().catch((e) => { $("#foot").textContent = e.message; });
setInterval(() => pull().catch(() => {}), 8000);
