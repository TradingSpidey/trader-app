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
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="公開 5 分鐘收市價"><path d="${line}" fill="none" stroke="${up ? "#2fce85" : "#ff5d6c"}" stroke-width="2"/></svg>`;
}

let market = new URLSearchParams(location.search).get("market") === "stocks" ? "stocks" : "crypto";
let lastAct = "";

function money(v, sign) {
  if (market === "stocks") {
    if (v == null || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    const body = Math.abs(n).toLocaleString("en-US", {maximumFractionDigits: Math.abs(n) >= 100 ? 0 : 2});
    return (n < 0 ? "-$" : (sign && n > 0 ? "+$" : "$")) + body;
  }
  return sol(v, sign);
}
function winText(a) {
  const n = a.closed == null || a.closed === "" ? null : Number(a.closed);
  if (n != null && !Number.isNaN(n) && n < 5) return "樣本太少（已平倉 " + n + " 單）";
  if (a.win_rate == null) return a.win_rate_text || "未有已平倉交易";
  return (Number(a.win_rate) * 100).toFixed(1) + "%";
}
function pnlOf(b) { return market === "stocks" ? b.paper_pnl : b.paper_pnl_sol; }
function upOf(p) { return p.upnl_usd != null ? p.upnl_usd : p.upnl_sol; }

function person(id) {
  const hair = {scan:"#3ee0ff",sniper:"#ffc14d",whale:"#7aa2ff",search:"#c58bff",rug:"#ff5d7a",exit:"#3dffb0",risk:"#ff9f43",dev:"#ff4d9a",chief:"#e8fbff"}[id] || "#3ee0ff";
  const prop = id === "whale"
    ? `<circle cx="12" cy="20" r="5" fill="none" stroke="${hair}" stroke-width="1.6"/><circle cx="42" cy="20" r="5" fill="none" stroke="${hair}" stroke-width="1.6"/><path d="M17 20h20" stroke="${hair}"/>`
    : id === "rug"
      ? `<path d="M40 26h10v12H40z" fill="none" stroke="${hair}" stroke-width="1.6"/>`
      : id === "chief"
        ? `<path d="M18 8h18" stroke="${hair}" stroke-width="2"/>`
        : "";
  return `<svg viewBox="0 0 54 70" class="person" aria-hidden="true">
    <circle cx="27" cy="16" r="10" fill="#f3d2b6"/>
    <path d="M16 14c2-10 20-10 22 0" fill="${hair}"/>
    <rect class="arm" x="4" y="32" width="14" height="5" rx="2" fill="${hair}"/>
    <rect class="arm" x="36" y="32" width="14" height="5" rx="2" fill="${hair}"/>
    <rect x="17" y="28" width="20" height="24" rx="5" fill="#18283a" stroke="${hair}"/>
    <rect x="20" y="52" width="5" height="14" rx="2" fill="#24384e"/>
    <rect x="29" y="52" width="5" height="14" rx="2" fill="#24384e"/>
    ${prop}
  </svg>`;
}

const CREW = ["scan", "sniper", "whale", "search", "chief", "rug", "exit", "risk", "dev"];
const CREW_COLOR = {scan:"#3ee0ff",sniper:"#ffc14d",whale:"#7aa2ff",search:"#c58bff",rug:"#ff5d7a",exit:"#3dffb0",risk:"#ff9f43",dev:"#ff4d9a",chief:"#c5d4e4"};

function pose(b) {
  if (b.id === "rug" && (b.tone === "block" || String(b.status).indexOf("擋") >= 0)) return "shield";
  if (b.id === "whale") return "look";
  if (b.tone === "idle") return "idle";
  return "work";
}
function toneBadge(tone) {
  if (tone === "block") return ["警示", "block"];
  if (tone === "idle") return ["待機", "idle"];
  return ["工作中", "working"];
}
function taskText(b) {
  const raw = b.bubble || b.status || "";
  const text = String(raw).trim();
  return text || "待機";
}
function detailText(b) {
  const parts = [];
  if (b.detail) parts.push(String(b.detail).trim());
  const sym = b.focus && (b.focus.symbol || b.focus.name);
  if (sym) parts.push(String(sym));
  (b.metrics || []).forEach((m) => {
    if (parts.length >= 3 || !m) return;
    if (m.value == null || m.value === "" || m.value === "暫無數據") return;
    parts.push(String(m.label) + " " + String(m.value));
  });
  return parts.filter(Boolean).join(" · ") || "待機";
}
function chiefBot(j) {
  const chief = j.chief || {};
  const route = chief.route || [];
  const account = j.account || {};
  const open = account.open == null ? "—" : String(account.open);
  return {
    id: "chief",
    en: "CHIEF",
    name: "主管",
    status: route.length ? route.join(" → ") : (chief.status || "值班"),
    detail: "持倉 " + open + " · " + (chief.status || "值班"),
    tone: account.kill ? "block" : "working",
    metrics: [],
    candles: null,
  };
}
function drawOffice(j) {
  const byId = {};
  (j.bots || []).forEach((b) => { if (b && b.id) byId[b.id] = b; });
  byId.chief = chiefBot(j);
  const all = CREW.map((id) => byId[id]).filter(Boolean);
  $("#office").innerHTML = all.map((b) => {
    const [toneText, toneCls] = toneBadge(b.tone);
    const task = taskText(b);
    const hasChart = (b.candles || []).filter((c) => c && c.c != null).length >= 2;
    const chart = hasChart ? spark(b.candles) : `<p class="muted flatline">暫無走勢</p>`;
    const chief = b.id === "chief" ? " is-chief" : "";
    return `<button type="button" class="station${chief}" data-id="${esc(b.id)}" style="--c:${CREW_COLOR[b.id] || "#c5d4e4"}" aria-label="${esc((b.en || "") + " " + (b.name || "") + " " + task)}">
      <div class="station-ava">${person(b.id).replace('class="person"', `class="person ${pose(b)}"`)}</div>
      <div class="station-body">
        <div class="station-top">
          <div class="label"><em>${esc(b.en || "")}</em><b>${esc(b.name || "主管")}</b></div>
          <span class="tag tone-badge ${toneCls}">${toneText}</span>
        </div>
        <p class="task"><span class="k">任務</span>${esc(task)}</p>
        <p class="station-detail"><span class="k">詳情</span>${esc(detailText(b))}</p>
        ${chart}
      </div>
    </button>`;
  }).join("");
  $("#office").querySelectorAll(".station").forEach((el) => el.addEventListener("click", () => openDetail(j, el.dataset.id)));
  maybeAct(j);
}
function openDetail(j, id) {
  const b = (j.bots || []).find((x) => x.id === id) || (id === "chief" ? {name:"主管", status:(j.chief || {}).status, detail:((j.chief || {}).route || []).join(" → "), metrics:[]} : null);
  const box = $("#detail");
  if (!b) { box.hidden = true; return; }
  box.hidden = false;
  box.className = "detail-pop panel";
  box.innerHTML = `<h2>${esc(b.name || "主管")}</h2><p>${esc(b.status || "")}</p><p class="muted">${esc(b.detail || "")}</p><dl class="metrics">${(b.metrics || []).map(metric).join("")}</dl><button type="button" class="ghost" id="detail-x">關閉</button>`;
  $("#detail-x").addEventListener("click", () => { box.hidden = true; });
}
function maybeAct(j) {
  const hit = (j.feed || []).find((f) => f.kind === "paper" && /模擬買入|止賺|止蝕/.test(f.text || ""));
  if (!hit) return;
  const key = (hit.ts || "") + (hit.text || "");
  if (key === lastAct) return;
  lastAct = key;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (/止賺/.test(hit.text)) flash("exit", "cheer");
  else if (/止蝕/.test(hit.text)) flash("exit", "slump");
  else handoff();
}
function flash(id, clsName) {
  const svg = document.querySelector(`.station[data-id="${id}"] .person`);
  if (!svg) return;
  svg.classList.add(clsName);
  setTimeout(() => svg.classList.remove(clsName), 4000);
}
function handoff() {
  const order = ["sniper", "rug", "risk", "chief", "exit"];
  let i = 0;
  const step = () => {
    document.querySelectorAll(".station").forEach((el) => el.classList.remove("to-chief"));
    if (i >= order.length) return;
    const el = document.querySelector(`.station[data-id="${order[i]}"]`);
    if (el) el.classList.add("to-chief");
    i += 1;
    setTimeout(step, 1100);
  };
  step();
}

function render(j) {
  market = j.market === "stocks" ? "stocks" : "crypto";
  const a = j.account || {};
  const pnl = market === "stocks" ? a.day_pnl_usd : a.day_pnl_sol;
  const eq = market === "stocks" ? a.equity_usd : a.equity_sol;
  $("#stats").innerHTML = `
    <div class="stat"><span>今日模擬盈虧</span><b class="num ${cls(pnl)}">${a.quote_missing ? "—" : money(pnl, true)}</b></div>
    <div class="stat"><span>勝率（已平倉）</span><b class="num">${esc(winText(a))}</b></div>
    <div class="stat"><span>模擬權益</span><b class="num">${money(eq, false)}</b></div>
    <div class="stat"><span>${market === "stocks" ? "現金" : "SOL 報價"}</span><b class="num">${market === "stocks" ? money(a.cash_usd, false) : usd(j.sol_usd)}</b></div>`;
  const kill = $("#kill");
  kill.textContent = a.kill ? "解除停止" : "風控停止";
  kill.classList.toggle("danger", !a.kill);
  kill.dataset.on = a.kill ? "0" : "1";

  const tape = j.tape || [];
  const health = j.health || {};
  const hcls = (s) => s === "正常" ? "ok" : s === "限速中" ? "limit" : s === "未查" ? "" : "bad";
  const healthNames = {geckoterminal:"GeckoTerminal", dexscreener:"DexScreener", solana_rpc:"Solana RPC", yahoo:"Yahoo", house:"眾議院"};
  $("#health").innerHTML = Object.keys(health).map((k) => `<span class="hp ${hcls(health[k])}">${esc(healthNames[k] || k)} ${esc(health[k] || "未查")}</span>`).join("");
  $("#kicker").textContent = market === "stocks" ? "美股 · Yahoo" : "SOLANA · 公開行情";
  const demo = $("#demo-note");
  if (demo) demo.textContent = market === "stocks" ? "網站示範盤（預設 $10,000，Render 休眠會重置）" : "網站示範盤（10 SOL，Render 休眠會重置）";
  $("#m-crypto").classList.toggle("on", market !== "stocks");
  $("#m-stocks").classList.toggle("on", market === "stocks");
  $("#m-crypto").setAttribute("aria-selected", market !== "stocks" ? "true" : "false");
  $("#m-stocks").setAttribute("aria-selected", market === "stocks" ? "true" : "false");
  const sess = j.session;
  $("#session-line").textContent = sess ? `美股${sess.phase} · 紐約 ${sess.et} · 香港 ${sess.hkt} · 正規 ${sess.hours_hkt}` : "";
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
      <p class="pnl"><span class="tag paper">模擬</span> ${pnlOf(b) == null ? "—" : `<b class="num ${cls(pnlOf(b))}">${money(pnlOf(b), true)}</b>`} <span class="muted">${esc(b.paper_note || "")}</span></p>
    </article>`).join("");

  $("#roster").innerHTML = `<h2>值班表</h2>` + (j.bots || []).map((b) => `
    <div class="roster-row">
      <i class="dot ${esc(b.tone)}"></i>
      <div><b>${esc(b.name)}</b><div class="muted">${esc(b.status)}</div></div>
      <div class="num ${cls(pnlOf(b))}">${pnlOf(b) == null ? "—" : money(pnlOf(b), true)}</div>
    </div>`).join("");

  const feed = j.feed || [];
  $("#feed").innerHTML = `<h2>動態</h2>` + (feed.length ? `<ol>${feed.map((f) => `<li><time>${esc((f.ts || "").slice(11, 19))} UTC</time><span class="tag ${f.kind === "paper" ? "paper" : "live"}">${f.kind === "paper" ? "模擬" : "行情"}</span><b>${esc(f.bot)}</b> ${esc(f.text)}</li>`).join("")}</ol>` : `<p class="muted">未有動態</p>`);

  const pos = j.positions || [];
  $("#book").innerHTML = `<h2>模擬持倉</h2>` + (pos.length ? pos.map((p) => `
    <div class="pos">
      <div><b>${esc(p.symbol)}</b><div class="muted">${esc(p.why || "")}</div></div>
      <div class="num">入 ${usd(p.entry_usd)}</div>
      <div class="num">而家 ${usd(p.last_usd)}</div>
      <div class="num ${cls(upOf(p))}">${upOf(p) == null ? "—" : money(upOf(p), true)}</div>
    </div>`).join("") : `<p class="muted">未有模擬倉。規則未過就唔會造數。</p>`);

  const radar = j.radar || [];
  const radarHead = market === "stocks" ? "美股雷達" : "新池雷達";
  $("#radar").innerHTML = `<h2>${radarHead} <span class="tag live">即時行情</span></h2>` + (radar.length ? radar.map((r) => market === "stocks" ? `
    <div class="radar-row">
      <div><b>${esc(r.symbol)}</b></div>
      <div class="num ${cls(r.gap)}">${pct(r.gap)}</div>
      <div class="num">${usd(r.price)}</div>
      <div class="num">${r.rvol == null ? "—" : r.rvol + "x"}</div>
    </div>` : `
    <div class="radar-row">
      <div><a class="ext" href="https://dexscreener.com/solana/${encodeURIComponent(r.mint || "")}" target="_blank" rel="noopener">${esc(r.symbol)}</a></div>
      <div class="num">${r.age_min == null ? "—" : r.age_min + " 分"}</div>
      <div class="num">${usd(r.liq_usd)}</div>
      <div class="num ${cls(r.change_h1)}">${pct(r.change_h1)}</div>
    </div>`).join("") : `<p class="muted">暫無</p>`);
  drawOffice(j);

  $("#rules").innerHTML = `<h2>規則</h2><ol>${(j.rules || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ol>`;
  const err = (j.errors || []).join(" ");
  $("#foot").innerHTML = `行情來源：${esc((j.sources && j.sources.market || []).join("、"))}。盈虧係${esc(j.sources && j.sources.paper)}。SOL 報價來源：${esc(j.sol_source || "暫無數據")}。${err ? `<span class="err">${esc(err)}</span>` : ""}`;
}

function api(path) {
  return market === "stocks" ? "/api/desk/stocks" + path : "/api/desk" + path;
}
async function pull() {
  const r = await fetch(api("/state"));
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || ("HTTP " + r.status));
  render(j);
}
$("#m-crypto").addEventListener("click", () => { market = "crypto"; history.replaceState(null, "", "/desk"); pull().catch((e) => { $("#foot").textContent = e.message; }); });
$("#m-stocks").addEventListener("click", () => { market = "stocks"; history.replaceState(null, "", "/desk?market=stocks"); pull().catch((e) => { $("#foot").textContent = e.message; }); });

$("#kill").addEventListener("click", async () => {
  $("#kill").disabled = true;
  try {
    const r = await fetch(api("/kill") + "?on=" + $("#kill").dataset.on, {method: "POST"});
    render(await r.json());
  } catch (e) { $("#foot").textContent = e.message; }
  $("#kill").disabled = false;
});
$("#reset").addEventListener("click", async () => {
  $("#reset").disabled = true;
  try {
    const r = await fetch(api("/reset"), {method: "POST"});
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
