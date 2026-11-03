"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const usd = (v, d = 2) => v == null ? "–" : "$" + Number(v).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
const pct = (p) => (p * 100).toFixed(1) + "%";
const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "#";
const loading = (msg) => `<div class="card loading"><div class="spin"></div><div>${esc(msg)}</div></div>`;
const errCard = (msg, detail) => `<div class="card"><p class="err"><b>出錯：</b>${esc(msg)}</p>${detail ? `<pre>${esc(detail)}</pre>` : ""}</div>`;
const kv = (pairs) => `<div class="kv">${pairs.map(([k, v]) => `<div>${esc(k)}</div><div>${v}</div>`).join("")}</div>`;

async function getJSON(url) {
  let r;
  try { r = await fetch(url); } catch (e) { throw new Error("連唔到伺服器"); }
  let j = null;
  try { j = await r.json(); } catch (e) { throw new Error("伺服器回覆唔係 JSON（HTTP " + r.status + "）"); }
  if (!r.ok || j.error) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}

// tabs
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + name));
}

// session hint
async function refreshSession() {
  const t = $("#rtime").value.trim();
  try {
    const s = await getJSON("/api/session" + (t ? "?time=" + encodeURIComponent(t) : ""));
    $("#sessionhint").textContent = s.live
      ? `美股開緊市：用即市數據（紐約時間 ${s.time}，Yahoo 有延遲）。`
      : `美股未開市／已收市：會重播最近一個交易日 ${s.day}，當作紐約時間 ${s.time} 去睇（而家紐約係 ${s.ny_now}）。`;
  } catch (e) { $("#sessionhint").textContent = e.message; }
}
$("#rtime").addEventListener("change", refreshSession);
refreshSession();

const STATUS = {
  triggered: ["已觸發", "pass", "有一條 5 分鐘 K 線收市高過開市 15 分鐘區間嘅最高位，即係「突破」咗。"],
  waiting: ["未觸發", "wait", "到呢個時間為止，冇任何一條 5 分鐘 K 線收市高過開市區間最高位。冇訊號就唔入市。"],
  expired: ["已過期", "block", "已經過咗最遲入市時間（15:30），呢個訊號唔再適用。"],
};

function bars(mc) {
  const rows = [
    ["先中目標（賺）", mc.p_target, "var(--green)"],
    ["先中止蝕（蝕）", mc.p_stop, "var(--red)"],
    ["兩邊都唔中（收市價決定）", mc.p_neither, "var(--gray)"],
  ];
  return `<div class="bars">${rows.map(([l, p, c]) => `<div class="b"><div class="lab"><span>${l}</span><b>${pct(p)}</b></div><div class="track"><div class="fill" style="width:${(p * 100).toFixed(1)}%;background:${c}"></div></div></div>`).join("")}</div>`;
}

function fan(mc, plan) {
  const b = mc.bands || [];
  if (b.length < 2) return "";
  const W = 700, H = 230, L = 52, R = 12, T = 12, B = 24;
  let lo = Math.min(plan.stop, ...b.map((x) => x[0])), hi = Math.max(plan.target, ...b.map((x) => x[4]));
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const x = (i) => L + (W - L - R) * i / (b.length - 1), y = (v) => T + (H - T - B) * (hi - v) / (hi - lo);
  const area = (a, c) => b.map((r, i) => `${x(i)},${y(r[a])}`).join(" ") + " " + b.map((r, i) => `${x(b.length - 1 - i)},${y(b[b.length - 1 - i][c])}`).join(" ");
  const line = (k) => b.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r[k])}`).join("");
  const hl = (v, col, lab) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="${col}" stroke-dasharray="4 4"/><text x="4" y="${y(v) + 4}">${esc(lab)}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="模擬價格範圍">
    <polygon points="${area(0, 4)}" fill="var(--blue)" opacity=".12"/>
    <polygon points="${area(1, 3)}" fill="var(--blue)" opacity=".22"/>
    <path d="${line(2)}" fill="none" stroke="var(--blue)" stroke-width="2"/>
    ${hl(plan.target, "var(--green)", plan.target.toFixed(2))}${hl(plan.entry, "var(--gray)", plan.entry.toFixed(2))}${hl(plan.stop, "var(--red)", plan.stop.toFixed(2))}
    <text x="${L}" y="${H - 6}">入市 ${esc(plan.entry_time || "")}</text><text x="${W - R - 40}" y="${H - 6}">收市</text></svg>
    <p class="explain">藍色線係 10,000 次模擬嘅中位數價錢；深色帶係中間 50%，淺色帶係中間 90%。綠虛線＝目標，灰＝入市價，紅＝止蝕。</p>`;
}

function verdictCard(res) {
  const st = res.steps;
  if (res.stopped_at === "no_trigger") {
    const e = st.entry.data;
    return `<div class="card verdict none"><div class="step">結論</div><div class="big">冇訊號，唔入市</div>
      <p>${esc(res.ticker)} 喺 ${esc(res.session.day)} 紐約時間 ${esc(res.session.time)} 之前，未有 5 分鐘 K 線收市突破開市區間高位 ${usd(e.opening_range && e.opening_range.high)}。
      跟呢套規則，今次唔應該落單，所以後面嘅出場計劃、時光機同注碼都冇做。</p>
      <p class="explain">可以試吓改「重播時間」（例如 13:00），或者去「掃描市場」搵有觸發嘅股票。</p></div>`;
  }
  const tm = st.timemachine && st.timemachine.data;
  if (!tm || !tm.mc) return `<div class="card verdict none"><div class="big">時光機冇結果</div><p>睇唔到勝率，所以冇結論。</p></div>`;
  const m = tm.mc, edge = (m.p_target - m.p_stop) * 100;
  let cls = "coin", big = "差唔多擲毫", txt = "先中目標同先中止蝕嘅機會好接近，模擬冇顯示明顯優勢。";
  if (edge >= 5 && m.avg_R > 0) { cls = "good"; big = "模擬略為有利"; txt = "先中目標嘅機會高過先中止蝕，但呢個只係用過去 60 日數據砌出嚟嘅模擬，唔代表會贏。"; }
  else if (edge <= -5 || m.avg_R < -0.1) { cls = "bad"; big = "模擬偏唔利"; txt = "先中止蝕嘅機會較高，或者平均結果係蝕。"; }
  const risk = st.risk && st.risk.data && st.risk.data.results && st.risk.data.results[0];
  return `<div class="card verdict ${cls}"><div class="step">結論</div><div class="big">${big}</div>
    <p>${txt}</p>
    <p>先中目標 <b>${pct(m.p_target)}</b> ・ 先中止蝕 <b>${pct(m.p_stop)}</b> ・ 平均每單 <b>${m.avg_R >= 0 ? "+" : ""}${m.avg_R}R</b>${risk ? ` ・ 風控 <span class="pill ${risk.verdict === "PASS" ? "pass" : "block"}">${esc(risk.verdict)}</span>` : ""}</p>
    <p class="explain">工具原文：${esc(tm.verdict)}　R＝每股風險；+1R 即係賺返一份風險，−1R 即係蝕一份。</p></div>`;
}

function newsCard(s, ticker) {
  if (!s) return "";
  if (!s.ok || !s.data) return `<div class="card"><div class="step">① 新聞</div>${errCard("讀唔到新聞", s.err)}</div>`;
  const d = s.data, mv = (d.moves || [])[0], items = (d.items || []).slice(0, 8);
  return `<div class="card news"><div class="step">① 新聞</div><h2>${esc(ticker)} 最近 4 日新聞</h2>
    ${mv ? `<p>最新價 <b>${usd(mv.price)}</b>，比上日收市 ${usd(mv.prev_close)} ${mv.pct >= 0 ? "升" : "跌"} <b>${Math.abs(mv.pct).toFixed(2)}%</b>${mv.moving ? '　<span class="pill wait">大幅波動</span>' : ""}</p>` : ""}
    ${items.length ? `<ul>${items.map((n) => `<li><a href="${esc(safeUrl(n.link))}" target="_blank" rel="noopener">${esc(n.title)}</a><div class="meta">${esc(n.source)} ・ ${esc(new Date(n.time).toLocaleString("zh-HK", {timeZone: "America/New_York", dateStyle: "short", timeStyle: "short"}))}（紐約）${n.tags && n.tags.length ? " ・ " + esc(n.tags.join(", ")) : ""}</div></li>`).join("")}</ul>` : "<p>呢段時間冇搵到新聞。</p>"}
    <p class="explain">標題只係線索，唔係事實；有 earnings 標籤即係同業績有關，要小心業績前後嘅大上大落。</p></div>`;
}

function entryCard(s, res) {
  if (!s.ok) return `<div class="card"><div class="step">② 入市訊號</div>${errCard("入市檢查失敗", s.err)}</div>`;
  const e = s.data, [lab, cls, ex] = STATUS[e.status] || [e.status, "wait", e.reason || ""];
  const pairs = [
    ["狀態", `<span class="pill ${cls}">${esc(lab)}</span>`],
    ["開市區間（9:30–9:45）", `高 ${usd(e.opening_range && e.opening_range.high)} ／ 低 ${usd(e.opening_range && e.opening_range.low)}`],
  ];
  if (e.trigger) pairs.push(["觸發", `${esc(e.trigger.time)} 收 ${usd(e.trigger.price)}（高過區間 ${e.trigger.pct_over}%）`]);
  if (e.last) pairs.push(["最後一條 K 線", `${esc(e.last.bar_start)} 收 ${usd(e.last.close)}`]);
  return `<div class="card"><div class="step">② 入市訊號（開市區間突破）</div><h2>${esc(res.session.day)} 紐約 ${esc(res.session.time)}</h2>${kv(pairs)}
    <p class="explain">${esc(ex)}${e.minutes_since ? ` 訊號係 ${e.minutes_since} 分鐘前出現，遲入市價錢已經唔同。` : ""}</p></div>`;
}

function exitCard(s) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">③ 出場計劃</div>${errCard("出場計劃失敗", s.err)}</div>`;
  const p = s.data;
  return `<div class="card"><div class="step">③ 出場計劃（入市前定好）</div>${kv([
    ["入市價", usd(p.entry)], ["止蝕", `${usd(p.stop)}（開市區間中位）`], ["目標", `${usd(p.target)}（賺返一份風險，1R）`],
    ["每股風險", usd(p.risk_per_share)], ["最遲平倉", `紐約 ${esc(p.flat_by)}，唔留過夜`]])}
    <p class="explain">止蝕係「跌到呢度就認輸走人」；目標係「升到呢度就食糊」。每股風險＝入市價減止蝕價。</p></div>`;
}

function tmCard(s) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">④ 時光機</div>${errCard("時光機失敗", s.err)}</div>`;
  const t = s.data, m = t.mc, h = t.history || {};
  return `<div class="card"><div class="step">④ 時光機：模擬 ${Number(m.replays).toLocaleString()} 次</div>
    ${bars(m)}${fan(m, t.plan)}
    ${kv([["收市高過入市價", pct(m.p_green)], ["4 點價錢中位數", `${usd(m.median_close)}（90% 落喺 ${usd(m.p5_close)}–${usd(m.p95_close)}）`],
      ["平均結果", `${m.avg_R >= 0 ? "+" : ""}${m.avg_R}R`],
      ["過去真實紀錄", h.sessions ? `過去 ${h.sessions} 日同一規則觸發 ${h.triggered} 次：${h.target} 次中目標、${h.stop} 次中止蝕、${h.close} 次兩邊都唔中（平均 ${h.avg_R >= 0 ? "+" : ""}${h.avg_R}R）` : "–"]])}
    <p class="explain">做法：用呢隻股自己過去約 60 日、同一時段嘅 5 分鐘 K 線隨機抽樣，砌出 10,000 個「餘下嘅交易日」（seed ${m.seed}，每次結果一樣）。係模擬，唔係預測：業績、新聞、停牌都可以做到過去冇出現過嘅事。</p></div>`;
}

function budgetCard(s, res) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">⑤ 注碼</div>${errCard("計唔到注碼", s.err)}</div>`;
  const z = s.data.sizing;
  if (z.refusal || !z.qty) return `<div class="card"><div class="step">⑤ 注碼</div><p class="err">${esc(z.refusal || "計出嚟係 0 股")}</p></div>`;
  const NAMES = {"max loss": "每單最多蝕", "position cap": "倉位上限", "max order": "每單金額上限", "cash": "可用現金"};
  return `<div class="card"><div class="step">⑤ 注碼：買幾多股</div><h2>${z.qty} 股，共 ${usd(z.cost)}</h2>
    <div class="tablewrap"><table><tr><th>限制</th><th>計法</th><th class="n">最多</th></tr>
    ${z.limits.map((l) => `<tr><td>${esc(NAMES[l.name] || l.name)}${l.binds ? " ⬅" : ""}</td><td>${esc(l.how)}</td><td class="n">${l.shares} 股</td></tr>`).join("")}</table></div>
    <p class="explain">幾個限制取最細嗰個（⬅）。如果去到止蝕，最多蝕約 ${usd(z.max_loss)}（快市可能蝕多啲）。戶口 ${usd(res.budget, 0)}，每單最多蝕 ${usd(res.max_loss, 0)}。</p></div>`;
}

function riskCard(s) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">⑥ 風控</div>${errCard("風控檢查失敗", s.err)}</div>`;
  const r = (s.data.results || [])[0];
  if (!r) return "";
  const ok = r.verdict === "PASS";
  return `<div class="card"><div class="step">⑥ 風控檢查</div><h2><span class="pill ${ok ? "pass" : "block"}">${esc(r.verdict)}</span> ${ok ? "符合你定落嘅所有限制" : "超出限制，唔准落"}</h2>
    <ul>${(r.reasons || []).concat(r.warnings || [], r.info || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <p class="explain">檢查每單最大虧損、每日虧損上限、每日交易次數、回報比風險、入市時間窗口、倉位大小同現金。PASS 只係「冇犯規」，唔係推介。</p></div>`;
}

function ticketCard(s) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">⑦ 模擬落單票據</div>${errCard("顯示唔到票據", s.err)}</div>`;
  const t = (s.data || [])[0];
  if (!t) return "";
  const i = t.tool_input || {};
  return `<div class="card"><div class="step">⑦ 模擬落單票據（只供參考）</div>
    ${kv([["指令", `買入 ${esc(i.qty)} 股 ${esc(i.symbol)}，市價，當日有效`], ["止蝕單", usd(Number(i.stop_loss_stop_price))], ["止賺單", usd(Number(i.take_profit_limit_price))],
      ["最多蝕", `約 ${usd(t.max_loss)}`], ["狀態", `<span class="pill ${t.ready ? "pass" : "block"}">${t.ready ? "可以落（模擬）" : "未準備好"}</span>`]])}
    <p class="explain">呢個 app 冇連任何券商，呢張票唔會送出。止蝕同止賺係一對「二選一」單：一張成交，另一張自動取消。</p></div>`;
}

$("#run").addEventListener("click", async () => {
  const q = new URLSearchParams({ticker: $("#ticker").value.trim().toUpperCase(), budget: $("#budget").value, max_loss: $("#maxloss").value});
  if ($("#rtime").value.trim()) q.set("time", $("#rtime").value.trim());
  const btn = $("#run"), out = $("#trade-out");
  btn.disabled = true;
  out.innerHTML = loading("拎緊數據同模擬緊 10,000 次…通常 5 至 30 秒。");
  try {
    const res = await getJSON("/api/run?" + q);
    const st = res.steps;
    out.innerHTML = verdictCard(res) + newsCard(st.news, res.ticker) + entryCard(st.entry, res) + exitCard(st.exit) + tmCard(st.timemachine) +
      budgetCard(st.budget, res) + riskCard(st.risk) + ticketCard(st.ticket) +
      (res.cached ? `<p class="hint">（10 分鐘內有人查過同一組設定，用咗暫存結果，對免費數據源客氣啲。）</p>` : "");
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});

const SETUP = {orb: "開市區間突破", breakout_20d: "20 日收市新高", bull_flag: "牛旗", reclaim_ma20: "重上 20 日線", oversold: "超賣（RSI<30）", oversold_bounce: "超賣反彈"};
$("#scanbtn").addEventListener("click", async () => {
  const mode = $("#scanmode").value, out = $("#scan-out"), btn = $("#scanbtn");
  btn.disabled = true;
  out.innerHTML = loading(mode === "orb" ? "掃緊約 100 張 5 分鐘圖…大約 30 至 60 秒。" : "掃緊約 100 張日線圖…大約 5 秒。");
  try {
    const r = await getJSON("/api/scan?mode=" + mode + ($("#rtime").value.trim() ? "&time=" + encodeURIComponent($("#rtime").value.trim()) : ""));
    if (!r.ok) { out.innerHTML = errCard("掃描失敗", r.err); btn.disabled = false; return; }
    const d = r.data, c = d.counts || {}, hits = d.hits || [];
    const head = mode === "orb"
      ? `<p>${esc(d.as_of)}：${c.fetched} 張圖有數據、${c.scanned} 張可用，<b>${hits.length}</b> 隻突破咗開市區間。</p>`
      : `<p>${esc(d.as_of)}：${c.scanned} 隻夠流通，<b>${hits.length}</b> 隻符合某個日線形態。</p>`;
    const rows = hits.map((h) => mode === "orb"
      ? `<tr class="click" data-s="${esc(h.symbol)}"><td><b>${esc(h.symbol)}</b></td><td>${esc(h.at)}</td><td class="n">${usd(h.price)}</td><td class="n">+${h.pct_over}%</td></tr>`
      : `<tr class="click" data-s="${esc(h.symbol)}"><td><b>${esc(h.symbol)}</b></td><td>${h.setups.map((x) => esc(SETUP[x] || x)).join("、")}</td><td class="n">${usd(h.price)}</td><td class="n">${h.rsi}</td></tr>`).join("");
    out.innerHTML = `<div class="card">${head}<div class="tablewrap"><table><tr>${mode === "orb" ? "<th>股票</th><th>觸發時間</th><th class='n'>價</th><th class='n'>高出區間</th>" : "<th>股票</th><th>形態</th><th class='n'>收市價</th><th class='n'>RSI</th>"}</tr>${rows}</table></div>
      <p class="explain">名單只係「符合某條規則」，唔係買入清單。撳一行就會帶你去分析嗰隻股${mode === "daily" ? "（日線形態唔等於即日有突破訊號）" : ""}。</p></div>`;
    out.querySelectorAll("tr.click").forEach((tr) => tr.addEventListener("click", () => { $("#ticker").value = tr.dataset.s; $("#an-ticker").value = tr.dataset.s; showTab("trade"); window.scrollTo(0, 0); }));
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});

const M = (v) => v == null ? "–" : (v / 1e6).toLocaleString("en-US", {maximumFractionDigits: 0});
const P = (v) => v == null ? "–" : (v > 0 ? "+" : "") + v + "%";
$("#anbtn").addEventListener("click", async () => {
  const out = $("#an-out"), btn = $("#anbtn");
  btn.disabled = true; out.innerHTML = loading("讀緊 SEC 財報…");
  try {
    const r = await getJSON("/api/analyst?ticker=" + encodeURIComponent($("#an-ticker").value.trim().toUpperCase()));
    const x = r.data && r.data[0];
    if (!r.ok || !x || !x.result) { out.innerHTML = errCard("讀唔到業績", r.err || (x && x.error)); btn.disabled = false; return; }
    const res = x.result;
    out.innerHTML = `<div class="card"><h2>${esc(res.entity)}（${esc(x.ticker)}）</h2><div class="tablewrap"><table>
      <tr><th>季度</th><th class="n">收入（百萬美元）</th><th class="n">按年</th><th class="n">毛利率</th><th class="n">經營利潤率</th><th class="n">淨利</th><th class="n">EPS</th></tr>
      ${res.rows.map((q) => `<tr><td>${esc(q.fiscal)}${q.derived ? "*" : ""}</td><td class="n">${M(q.revenue)}</td><td class="n">${P(q.revenue_yoy)}</td><td class="n">${q.gross_margin == null ? "–" : q.gross_margin + "%"}</td><td class="n">${q.operating_margin == null ? "–" : q.operating_margin + "%"}</td><td class="n">${M(q.net_income)}</td><td class="n">${q.eps_diluted == null ? "–" : q.eps_diluted}</td></tr>`).join("")}
      </table></div><p class="explain">最近四季：收入 ${M(res.ttm && res.ttm.revenue)} 百萬、淨利 ${M(res.ttm && res.ttm.net_income)} 百萬美元。* 係用全年減三季推算。數據來自 SEC XBRL。</p></div>`;
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});

$("#ptrbtn").addEventListener("click", async () => {
  const out = $("#ptr-out"), btn = $("#ptrbtn");
  btn.disabled = true; out.innerHTML = loading("讀緊眾議院申報索引…");
  try {
    const r = await getJSON("/api/pelosi?member=" + encodeURIComponent($("#member").value.trim()));
    const list = r.data || [];
    if (!r.ok) { out.innerHTML = errCard("讀唔到申報", r.err); btn.disabled = false; return; }
    if (!list.length) { out.innerHTML = `<div class="card"><p>今年搵唔到呢位議員嘅交易申報。</p></div>`; btn.disabled = false; return; }
    out.innerHTML = `<div class="card"><h2>${esc(list[0].name)} 今年嘅交易申報</h2><div class="tablewrap"><table><tr><th>申報日</th><th>文件</th><th></th></tr>
      ${list.map((f) => `<tr><td>${esc(f.filed)}</td><td><a href="${esc(safeUrl(f.url))}" target="_blank" rel="noopener">${esc(f.doc_id)}</a></td><td><button class="primary" data-doc="${esc(f.doc_id)}" data-year="${esc(f.year)}">睇內容</button></td></tr>`).join("")}
      </table></div><div id="ptr-detail"></div></div>`;
    out.querySelectorAll("button[data-doc]").forEach((b) => b.addEventListener("click", async () => {
      const det = $("#ptr-detail"); det.innerHTML = loading("下載緊 PDF 同讀緊…");
      try {
        const d = await getJSON(`/api/ptr?doc=${b.dataset.doc}&year=${b.dataset.year}`);
        const rows = (d.data && d.data.rows) || [];
        det.innerHTML = rows.length ? `<h2>文件 ${esc(b.dataset.doc)}</h2><div class="tablewrap"><table><tr><th>交易日</th><th>誰</th><th>買／賣</th><th>資產</th><th>金額範圍</th><th class="n">幾多日後申報</th></tr>
          ${rows.map((x) => `<tr><td>${esc(x.date)}</td><td>${esc({spouse: "配偶", self: "本人", joint: "聯名", dependent: "子女"}[x.owner_name] || x.owner_name || "")}</td><td>${esc({purchase: "買入", sale: "賣出", "partial sale": "部分賣出", exchange: "交換"}[x.type_name] || x.type_name)}</td><td>${esc(x.ticker ? x.ticker + " " : "")}${esc(x.asset)}<div class="meta">${esc(x.description || "")}</div></td><td>${esc(x.amount)}</td><td class="n">${x.days_to_disclose == null ? "–" : x.days_to_disclose}</td></tr>`).join("")}</table></div>`
          : errCard("讀唔到呢份文件嘅交易（可能係手寫掃描 PDF）", d.err);
      } catch (e) { det.innerHTML = errCard(e.message); }
    }));
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});

// deep link: /?ticker=ABNB&run=1
const qs = new URLSearchParams(location.search);
if (qs.get("ticker")) $("#ticker").value = qs.get("ticker").toUpperCase();
if (qs.get("time")) $("#rtime").value = qs.get("time");
if (qs.get("tab")) showTab(qs.get("tab"));
if (qs.get("run") === "1") $("#run").click();
