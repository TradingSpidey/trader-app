"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const usd = (v, d = 2) => v == null || v === "" || Number.isNaN(Number(v)) ? "–" : "$" + Number(v).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
const pct = (p) => p == null || Number.isNaN(Number(p)) ? "–" : (Number(p) * 100).toFixed(1) + "%";
const num = (v) => `<span class="num">${v}</span>`;
const clsOf = (n) => n > 0 ? "up" : n < 0 ? "dn" : "flat";
const signed = (n, d = 2) => n == null || Number.isNaN(Number(n)) ? "–" : (Number(n) > 0 ? "+" : "") + Number(n).toFixed(d);
const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "#";
const attr = (v) => esc(v == null ? "" : v);

const loading = (msg) => `<div class="loading" role="status"><div class="spin"></div><div>${esc(msg)}</div></div>`;
const errCard = (msg, detail) => `<div class="card state" role="alert"><div class="state-ico" aria-hidden="true">!</div><div><div class="state-title">讀唔到</div><p class="err">${esc(msg)}</p>${detail ? `<pre>${esc(detail)}</pre>` : ""}<p class="explain">請稍後再試。免費數據源有時會慢或者限流。</p></div></div>`;
const kv = (pairs) => `<div class="kv">${pairs.map(([k, v]) => `<div>${esc(k)}</div><div>${v}</div>`).join("")}</div>`;

function skelCards(n) {
  return `<div class="kpis" aria-hidden="true">${Array.from({length: n}, () => `<div class="kpi"><div class="skel skel-l"></div><div class="skel skel-n"></div></div>`).join("")}</div>`;
}
function skeletonTrade() {
  return `<div aria-busy="true">${loading("拎緊數據同模擬緊 10,000 次…通常 5 至 30 秒。")}${skelCards(4)}<div class="card"><div class="skel skel-chart"></div></div></div>`;
}
function skeletonTable(msg) {
  const cells = (tag) => Array.from({length: 4}, () => `<${tag}><div class="skel skel-l"></div></${tag}>`).join("");
  const rows = Array.from({length: 6}, () => `<tr>${cells("td")}</tr>`).join("");
  return `<div class="card" aria-busy="true">${loading(msg)}<div class="tablewrap"><table><thead><tr>${cells("th")}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

async function getJSON(url) {
  let r;
  try { r = await fetch(url); } catch (e) { throw new Error("連唔到伺服器"); }
  let j = null;
  try { j = await r.json(); } catch (e) { throw new Error("伺服器回覆唔係 JSON（HTTP " + r.status + "）"); }
  if (!r.ok || j.error) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}

document.querySelectorAll(".sidebar button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".sidebar button").forEach((x) => {
    const on = x.dataset.tab === name;
    x.classList.toggle("active", on);
    if (on) x.setAttribute("aria-current", "page"); else x.removeAttribute("aria-current");
  });
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + name));
}

async function refreshSession() {
  const t = $("#rtime").value.trim();
  try {
    const s = await getJSON("/api/session" + (t ? "?time=" + encodeURIComponent(t) : ""));
    const dot = $("#sessiondot");
    dot.classList.toggle("live", !!s.live);
    dot.classList.toggle("replay", !s.live);
    $("#sessionshort").textContent = s.live ? `即市 · 紐約 ${s.time}` : `重播 ${s.day} · 紐約 ${s.time}`;
    $("#sessionhint").textContent = s.live
      ? `美股開緊市：用即市數據（紐約時間 ${s.time}，Yahoo 有延遲）。`
      : `美股未開市／已收市：會重播最近一個交易日 ${s.day}，當作紐約時間 ${s.time} 去睇（而家紐約係 ${s.ny_now}）。`;
  } catch (e) {
    $("#sessionshort").textContent = e.message;
    $("#sessionhint").textContent = e.message;
  }
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
  return `<div class="bars">${rows.map(([l, p, c]) => `<div class="b"><div class="lab"><span>${l}</span><b class="num">${pct(p)}</b></div><div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, p * 100)).toFixed(1)}%;background:${c}"></div></div></div>`).join("")}</div>`;
}

function fan(mc, plan) {
  const b = mc.bands || [];
  if (!plan || b.length < 2 || plan.entry == null || plan.stop == null || plan.target == null) return "";
  const W = 700, H = 230, L = 52, R = 12, T = 16, B = 24;
  let lo = Math.min(plan.stop, ...b.map((x) => x[0])), hi = Math.max(plan.target, ...b.map((x) => x[4]));
  if (!(hi > lo)) return "";
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const x = (i) => L + (W - L - R) * i / (b.length - 1), y = (v) => T + (H - T - B) * (hi - v) / (hi - lo);
  const area = (a, c) => b.map((r, i) => `${x(i)},${y(r[a])}`).join(" ") + " " + b.map((r, i) => `${x(b.length - 1 - i)},${y(b[b.length - 1 - i][c])}`).join(" ");
  const line = (k) => b.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r[k])}`).join("");
  const hl = (v, col, lab) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="${col}" stroke-dasharray="4 4"/><text x="4" y="${y(v) + 4}">${esc(lab)}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="模擬價格範圍">
    <polygon points="${area(0, 4)}" fill="#5a8caa" opacity=".16"/>
    <polygon points="${area(1, 3)}" fill="#5a8caa" opacity=".32"/>
    <path d="${line(2)}" fill="none" stroke="#8ec8e0" stroke-width="2"/>
    ${hl(plan.target, "#2fce85", plan.target.toFixed(2))}${hl(plan.entry, "#9aa6b4", plan.entry.toFixed(2))}${hl(plan.stop, "#ff5d6c", plan.stop.toFixed(2))}
    <text x="${L}" y="${H - 6}">入市 ${esc(plan.entry_time || "")}</text><text x="${W - R - 40}" y="${H - 6}">收市</text></svg>
    <p class="explain">淺色線係模擬嘅中位數價錢；深色帶係中間 50%，淺色帶係中間 90%。綠虛線＝目標，灰＝入市價，紅＝止蝕。</p>`;
}

function histChart(mc, plan) {
  const h = mc && mc.hist;
  if (!h || !Array.isArray(h.bins) || !h.bins.length || h.lo == null || h.hi == null || !(h.hi > h.lo)) return "";
  const bins = h.bins;
  const max = Math.max(...bins);
  const w = (h.hi - h.lo) / bins.length;
  const stop = plan && plan.stop, entry = plan && plan.entry, target = plan && plan.target;
  const tone = (mid) => {
    if (stop != null && mid < stop) return "dn";
    if (target != null && mid > target) return "up";
    return "md";
  };
  const cols = bins.map((n, i) => {
    const a = h.lo + i * w, b0 = a + w, mid = (a + b0) / 2;
    const ht = max ? Math.round((n / max) * 140) : 0;
    return `<div class="hb ${tone(mid)}" style="height:${ht}px" title="${attr(usd(a))}–${attr(usd(b0))} · ${attr(n)} 次"></div>`;
  }).join("");
  const inside = [];
  const outside = [];
  const consider = (price, label, cls) => {
    if (price == null || Number.isNaN(Number(price))) return;
    if (price < h.lo || price > h.hi) { outside.push(`<span class="hist-out">${esc(label)} ${num(usd(price))} 喺圖外</span>`); return; }
    inside.push({left: ((Number(price) - h.lo) / (h.hi - h.lo)) * 100, label, cls});
  };
  consider(stop, "止蝕", "stop");
  consider(entry, "入市", "entry");
  consider(target, "目標", "target");
  if (mc.median_close != null) consider(mc.median_close, "中位", "mid");
  inside.sort((a, b) => a.left - b.left);
  const used = [[], []];
  inside.forEach((m) => {
    let row = 0;
    for (let r = 0; r < used.length; r++) {
      const last = used[r][used[r].length - 1];
      if (!last || m.left - last >= 9) { row = r; break; }
      row = r;
    }
    const last = used[row][used[row].length - 1];
    if (last && m.left - last < 9) row = row === 0 ? 1 : 0;
    used[row].push(m.left);
    m.row = row;
  });
  const marks = inside.map((m) => `<div class="mark ${m.cls}${m.row ? " r1" : ""}" style="left:${m.left}%"><span>${esc(m.label)}</span></div>`);
  return `<div class="hist" role="img" aria-label="模擬收市價分佈，${bins.length} 柱">
    <p class="hist-note">橫軸係 ${Number(mc.replays).toLocaleString()} 次模擬收市價嘅第 1 至第 99 百分位（${num(usd(h.lo))}–${num(usd(h.hi))}）。超出呢段嘅次數冇畫入去。柱愈高＝次數愈多。</p>
    <div class="hist-plot">${cols}${marks.join("")}</div>
    <div class="hist-axis num"><span>${usd(h.lo)}</span><span>${usd(mc.median_close)}</span><span>${usd(h.hi)}</span></div>
    ${outside.join("")}
  </div>`;
}

function verdictCard(res) {
  const st = res.steps;
  if (res.stopped_at === "no_trigger") {
    const e = st.entry.data;
    return `<div class="card verdict none"><div class="step">結論</div><div class="big">冇訊號，唔入市</div>
      <p>${esc(res.ticker)} 喺 ${esc(res.session.day)} 紐約時間 ${esc(res.session.time)} 之前，未有 5 分鐘 K 線收市突破開市區間高位 ${num(usd(e.opening_range && e.opening_range.high))}。
      跟呢套規則，今次唔應該落單，所以後面嘅出場計劃、時光機同注碼都冇做。</p>
      <p class="explain">可以試吓改「重播時間」（例如 13:00），或者去「掃描市場」搵有觸發嘅股票。</p></div>`;
  }
  const tm = st.timemachine && st.timemachine.data;
  if (!tm || !tm.mc) return `<div class="card verdict none"><div class="big">時光機冇結果</div><p>睇唔到勝率，所以冇結論。</p></div>`;
  const m = tm.mc, edge = (m.p_target - m.p_stop) * 100;
  let vcls = "coin", big = "差唔多擲毫", txt = "先中目標同先中止蝕嘅機會好接近，模擬冇顯示明顯優勢。";
  if (edge >= 5 && m.avg_R > 0) { vcls = "good"; big = "模擬略為有利"; txt = "先中目標嘅機會高過先中止蝕，但呢個只係用過去 60 日數據砌出嚟嘅模擬，唔代表會贏。"; }
  else if (edge <= -5 || m.avg_R < -0.1) { vcls = "bad"; big = "模擬偏唔利"; txt = "先中止蝕嘅機會較高，或者平均結果係蝕。"; }
  const risk = st.risk && st.risk.data && st.risk.data.results && st.risk.data.results[0];
  return `<div class="card verdict ${vcls}"><div class="step">結論</div><div class="big">${big}</div>
    <p>${txt}</p>
    <p>先中目標 ${num("<b>" + pct(m.p_target) + "</b>")} ・ 先中止蝕 ${num("<b>" + pct(m.p_stop) + "</b>")} ・ 平均每單 ${num("<b>" + (m.avg_R >= 0 ? "+" : "") + m.avg_R + "R</b>")}${risk ? ` ・ 風控 <span class="pill ${risk.verdict === "PASS" ? "pass" : "block"}">${esc(risk.verdict)}</span>` : ""}</p>
    <p class="explain">工具原文：${esc(tm.verdict)}　R＝每股風險；+1R 即係賺返一份風險，−1R 即係蝕一份。</p></div>`;
}

function barQuote(bars) {
  const list = bars && !bars._err && bars.bars;
  if (!list || !list.length) return null;
  const last = list[list.length - 1];
  const prev = bars.prev_close;
  const chg = prev ? (last.c / prev - 1) * 100 : null;
  return {price: last.c, prev, pct: chg, time: last.time};
}

function kpi(label, value, sub, vcls) {
  return `<div class="kpi"><div class="k">${esc(label)}</div><div class="v ${vcls || ""}">${value}</div>${sub ? `<div class="s">${sub}</div>` : ""}</div>`;
}

function kpiRow(res, bars) {
  const st = res.steps || {};
  const e = st.entry && st.entry.ok && st.entry.data;
  const x = st.exit && st.exit.ok && st.exit.data;
  const m = st.timemachine && st.timemachine.ok && st.timemachine.data && st.timemachine.data.mc;
  const q = barQuote(bars);
  const cards = [];
  if (q) {
    const chg = q.pct == null ? "" : `${signed(q.pct)}%`;
    cards.push(kpi("截至 " + q.time, usd(q.price), q.prev != null ? `上日 ${usd(q.prev)}　${chg}` : "", clsOf(q.pct)));
  }
  if (e) {
    const [lab, pcls] = STATUS[e.status] || [e.status, "wait"];
    cards.push(kpi("訊號", `<span class="pill ${pcls}">${esc(lab)}</span>`, esc(res.session.day) + " " + esc(res.session.time)));
    if (e.opening_range) {
      cards.push(kpi("區間高", usd(e.opening_range.high), "9:30–9:45"));
      cards.push(kpi("區間低", usd(e.opening_range.low), "9:30–9:45"));
    }
  }
  if (x) {
    cards.push(kpi("入市", usd(x.entry)));
    cards.push(kpi("止蝕", usd(x.stop), "開市區間中位", "dn"));
    cards.push(kpi("目標", usd(x.target), "1R", "up"));
    cards.push(kpi("每股風險", usd(x.risk_per_share)));
  }
  if (m) {
    cards.push(kpi("先中目標", pct(m.p_target), null, "up"));
    cards.push(kpi("先中止蝕", pct(m.p_stop), null, "dn"));
    cards.push(kpi("平均 R", (m.avg_R >= 0 ? "+" : "") + m.avg_R, null, clsOf(m.avg_R)));
  }
  return cards.length ? `<div class="kpis">${cards.join("")}</div>` : "";
}

function levelsFrom(res) {
  const e = res.steps && res.steps.entry && res.steps.entry.ok && res.steps.entry.data;
  const x = res.steps && res.steps.exit && res.steps.exit.ok && res.steps.exit.data;
  const lines = [];
  const orr = e && e.opening_range;
  if (orr && orr.high != null) lines.push({price: orr.high, color: "#e0b15a", title: "區間高", dashed: true});
  if (orr && orr.low != null) lines.push({price: orr.low, color: "#e0b15a", title: "區間低", dashed: true});
  if (x && x.entry != null) lines.push({price: x.entry, color: "#d5dde6", title: "入市", dashed: false});
  if (x && x.stop != null) lines.push({price: x.stop, color: "#ff5d6c", title: "止蝕", dashed: false});
  if (x && x.target != null) lines.push({price: x.target, color: "#2fce85", title: "目標", dashed: false});
  return lines;
}

function legendHtml(lines) {
  if (!lines.length) return "";
  return `<ul class="legend">${lines.map((l) => `<li><i class="${l.dashed ? "dashed" : ""}" style="border-top-color:${l.color}"></i>${esc(l.title)} ${num(usd(l.price))}</li>`).join("")}</ul>`;
}

function ohlcTable(rows) {
  if (!rows || !rows.length) return "";
  const body = rows.map((b) => `<tr data-time="${attr(b.time)}" data-o="${attr(b.o)}" data-h="${attr(b.h)}" data-l="${attr(b.l)}" data-c="${attr(b.c)}" data-v="${attr(b.v)}">
    <td class="num">${esc(b.time)}</td>
    <td class="n">${usd(b.o)}</td><td class="n">${usd(b.h)}</td><td class="n">${usd(b.l)}</td>
    <td class="n ${clsOf(b.c - b.o)}">${usd(b.c)}</td><td class="n">${Number(b.v).toLocaleString("en-US")}</td></tr>`).join("");
  return `<details class="ohlc"><summary>睇晒 ${rows.length} 條 K 線數字</summary>
    <div class="tablewrap"><table class="sortable"><thead><tr>
      <th data-k="time">時間</th><th class="n" data-k="o" data-t="num">開</th><th class="n" data-k="h" data-t="num">高</th>
      <th class="n" data-k="l" data-t="num">低</th><th class="n" data-k="c" data-t="num">收</th><th class="n" data-k="v" data-t="num">量</th>
    </tr></thead><tbody>${body}</tbody></table></div></details>`;
}

function chartCard(res, bars) {
  const q = barQuote(bars);
  const lines = levelsFrom(res);
  const headPx = q ? `<div class="quote"><div class="px ${clsOf(q.pct)}">${usd(q.price)}</div><div class="${clsOf(q.pct)}">${q.time} 收${q.pct == null ? "" : "　" + signed(q.pct) + "%"}</div></div>` : "";
  let body;
  if (!bars || bars._err) {
    body = errCard(bars && bars._err || "讀唔到 K 線");
  } else if (!bars.bars || !bars.bars.length) {
    body = `<p class="empty">呢個時段未有已收市嘅 5 分鐘 K 線。</p>`;
  } else if (!window.LightweightCharts) {
    body = `<p class="explain">K 線圖庫未載入，下面係同一批 Yahoo 數字。</p>${ohlcTable(bars.bars)}`;
  } else {
    body = `<div id="candle" class="chart-box" role="img" aria-label="${esc(res.ticker)} 5 分鐘 K 線"></div>${legendHtml(lines)}${ohlcTable(bars.bars)}`;
  }
  const when = bars && bars.session ? `${esc(bars.session.day)} 紐約 ${esc(bars.session.time)} 為止` : "";
  return `<div class="card"><div class="card-h"><div><div class="step">K 線</div><h2>${esc(res.ticker)} 5 分鐘</h2><p class="explain" style="margin:0">Yahoo（免費、非官方、會延遲）${when ? " · " + when : ""}。只畫已收市嘅線。</p></div>${headPx}</div>${body}</div>`;
}

let candleChart = null;
let candleObserver = null;
function clearCharts() {
  if (candleObserver) { candleObserver.disconnect(); candleObserver = null; }
  if (candleChart) { candleChart.remove(); candleChart = null; }
}

function nyParts(ts, opts) {
  return new Intl.DateTimeFormat("zh-HK", Object.assign({timeZone: "America/New_York", hourCycle: "h23"}, opts)).format(new Date(ts * 1000));
}

function mountCandle(res, bars) {
  const el = $("#candle");
  const rows = bars && bars.bars;
  if (!el || !rows || !rows.length || !window.LightweightCharts) return;
  const LW = window.LightweightCharts;
  const data = [];
  const seen = new Set();
  rows.forEach((b) => {
    if (seen.has(b.t) || b.o == null || b.h == null || b.l == null || b.c == null) return;
    seen.add(b.t);
    data.push({time: b.t, open: b.o, high: b.h, low: b.l, close: b.c, vol: b.v || 0});
  });
  data.sort((a, b) => a.time - b.time);
  if (!data.length) return;
  candleChart = LW.createChart(el, {
    autoSize: true,
    layout: {background: {type: "solid", color: "#10141a"}, textColor: "#8b97a8", fontFamily: '"IBM Plex Mono", "Noto Sans TC", sans-serif', fontSize: 11, attributionLogo: false},
    grid: {vertLines: {color: "#1a212b"}, horzLines: {color: "#1a212b"}},
    crosshair: {vertLine: {color: "#3a4656", labelBackgroundColor: "#1c2430"}, horzLine: {color: "#3a4656", labelBackgroundColor: "#1c2430"}},
    rightPriceScale: {borderColor: "#2a3340", scaleMargins: {top: 0.08, bottom: 0.26}},
    timeScale: {borderColor: "#2a3340", timeVisible: true, secondsVisible: false, tickMarkFormatter: (t) => typeof t === "number" ? nyParts(t, {hour: "2-digit", minute: "2-digit"}) : ""},
    localization: {locale: "zh-HK", timeFormatter: (t) => typeof t === "number" ? nyParts(t, {month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit"}) : ""},
    handleScroll: {mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false},
    handleScale: {mouseWheel: true, pinch: true, axisPressedMouseMove: true},
  });
  const candles = candleChart.addCandlestickSeries({
    upColor: "#2fce85", downColor: "#ff5d6c", borderUpColor: "#2fce85", borderDownColor: "#ff5d6c",
    wickUpColor: "#2fce85", wickDownColor: "#ff5d6c",
  });
  candles.setData(data.map(({time, open, high, low, close}) => ({time, open, high, low, close})));
  const vol = candleChart.addHistogramSeries({priceFormat: {type: "volume"}, priceScaleId: "vol", priceLineVisible: false, lastValueVisible: false});
  candleChart.priceScale("vol").applyOptions({scaleMargins: {top: 0.78, bottom: 0}, visible: false, borderVisible: false});
  vol.setData(data.map((b) => ({time: b.time, value: b.vol, color: b.close >= b.open ? "rgba(47,206,133,.5)" : "rgba(255,93,108,.5)"})));
  candles.priceScale().applyOptions({scaleMargins: {top: 0.08, bottom: 0.26}});
  levelsFrom(res).forEach((l) => {
    if (l.price == null || Number.isNaN(Number(l.price))) return;
    candles.createPriceLine({
      price: Number(l.price), color: l.color, lineWidth: 1, title: "",
      lineStyle: l.dashed ? LW.LineStyle.Dashed : LW.LineStyle.Solid,
      axisLabelVisible: false,
    });
  });
  const fit = () => { if (candleChart) candleChart.timeScale().fitContent(); };
  fit();
  if (window.ResizeObserver) {
    candleObserver = new ResizeObserver(fit);
    candleObserver.observe(el);
  }
}

function newsCard(s, ticker) {
  if (!s) return "";
  if (!s.ok || !s.data) return `<div class="card"><div class="step">① 新聞</div>${errCard("讀唔到新聞", s.err)}</div>`;
  const d = s.data, mv = (d.moves || [])[0], items = (d.items || []).slice(0, 8);
  return `<div class="card news"><div class="step">① 新聞</div><h2>${esc(ticker)} 最近 4 日新聞</h2>
    ${mv && mv.price != null ? `<p>最新價 ${num("<b>" + usd(mv.price) + "</b>")}${mv.prev_close != null ? `，比上日收市 ${num(usd(mv.prev_close))}` : ""}${mv.pct == null ? "" : ` ${mv.pct >= 0 ? "升" : "跌"} ${num("<b class=\"" + clsOf(mv.pct) + "\">" + Math.abs(mv.pct).toFixed(2) + "%</b>")}`}${mv.moving ? '　<span class="pill wait">大幅波動</span>' : ""}</p>` : ""}
    ${items.length ? `<ul>${items.map((n) => `<li><a href="${esc(safeUrl(n.link))}" target="_blank" rel="noopener">${esc(n.title)}</a><div class="meta">${esc(n.source)} ・ ${esc(new Date(n.time).toLocaleString("zh-HK", {timeZone: "America/New_York", dateStyle: "short", timeStyle: "short"}))}（紐約）${n.tags && n.tags.length ? " ・ " + esc(n.tags.join(", ")) : ""}</div></li>`).join("")}</ul>` : "<p class=\"empty\">呢段時間冇搵到新聞。</p>"}
    <p class="explain">標題只係線索，唔係事實；有 earnings 標籤即係同業績有關，要小心業績前後嘅大上大落。</p></div>`;
}

function entryCard(s, res) {
  if (!s.ok) return `<div class="card"><div class="step">② 入市訊號</div>${errCard("入市檢查失敗", s.err)}</div>`;
  const e = s.data, [lab, pcls, ex] = STATUS[e.status] || [e.status, "wait", e.reason || ""];
  const pairs = [
    ["狀態", `<span class="pill ${pcls}">${esc(lab)}</span>`],
    ["開市區間（9:30–9:45）", `高 ${num(usd(e.opening_range && e.opening_range.high))} ／ 低 ${num(usd(e.opening_range && e.opening_range.low))}`],
  ];
  if (e.trigger) pairs.push(["觸發", `${esc(e.trigger.time)} 收 ${num(usd(e.trigger.price))}（高過區間 ${num(esc(e.trigger.pct_over) + "%")}）`]);
  if (e.last) pairs.push(["最後一條 K 線", `${esc(e.last.bar_start)} 收 ${num(usd(e.last.close))}`]);
  return `<div class="card"><div class="step">② 入市訊號（開市區間突破）</div><h2>${esc(res.session.day)} 紐約 ${esc(res.session.time)}</h2>${kv(pairs)}
    <p class="explain">${esc(ex)}${e.minutes_since ? ` 訊號係 ${e.minutes_since} 分鐘前出現，遲入市價錢已經唔同。` : ""}</p></div>`;
}

function exitCard(s) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">③ 出場計劃</div>${errCard("出場計劃失敗", s.err)}</div>`;
  const p = s.data;
  return `<div class="card"><div class="step">③ 出場計劃（入市前定好）</div>${kv([
    ["入市價", num(usd(p.entry))], ["止蝕", `${num(usd(p.stop))}（開市區間中位）`], ["目標", `${num(usd(p.target))}（賺返一份風險，1R）`],
    ["每股風險", num(usd(p.risk_per_share))], ["最遲平倉", `紐約 ${esc(p.flat_by)}，唔留過夜`]])}
    <p class="explain">止蝕係「跌到呢度就認輸走人」；目標係「升到呢度就食糊」。每股風險＝入市價減止蝕價。</p></div>`;
}

function tmCard(s) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">④ 時光機</div>${errCard("時光機失敗", s.err)}</div>`;
  const t = s.data, m = t.mc, h = t.history || {};
  if (!m) return `<div class="card"><div class="step">④ 時光機</div><p class="empty">冇模擬結果。</p></div>`;
  return `<div class="card"><div class="step">④ 時光機：模擬 ${num(Number(m.replays).toLocaleString())} 次</div>
    <h2>結果分佈</h2>${histChart(m, t.plan)}${bars(m)}${fan(m, t.plan)}
    ${kv([["收市高過入市價", num(pct(m.p_green))], ["4 點價錢中位數", `${num(usd(m.median_close))}（90% 落喺 ${num(usd(m.p5_close))}–${num(usd(m.p95_close))}）`],
      ["平均結果", num((m.avg_R >= 0 ? "+" : "") + m.avg_R + "R")],
      ["過去真實紀錄", h.sessions ? `過去 ${h.sessions} 日同一規則觸發 ${h.triggered} 次：${h.target} 次中目標、${h.stop} 次中止蝕、${h.close} 次兩邊都唔中（平均 ${h.avg_R >= 0 ? "+" : ""}${h.avg_R}R）` : "–"]])}
    <p class="explain">做法：用呢隻股自己過去約 60 日、同一時段嘅 5 分鐘 K 線隨機抽樣，砌出 ${Number(m.replays).toLocaleString()} 個「餘下嘅交易日」（seed ${m.seed}，每次結果一樣）。係模擬，唔係預測：業績、新聞、停牌都可以做到過去冇出現過嘅事。</p></div>`;
}

function budgetCard(s, res) {
  if (!s) return "";
  if (!s.ok) return `<div class="card"><div class="step">⑤ 注碼</div>${errCard("計唔到注碼", s.err)}</div>`;
  const z = s.data.sizing;
  if (z.refusal || !z.qty) return `<div class="card"><div class="step">⑤ 注碼</div><p class="err">${esc(z.refusal || "計出嚟係 0 股")}</p></div>`;
  const NAMES = {"max loss": "每單最多蝕", "position cap": "倉位上限", "max order": "每單金額上限", "cash": "可用現金"};
  return `<div class="card"><div class="step">⑤ 注碼：買幾多股</div><h2 class="num">${z.qty} 股，共 ${usd(z.cost)}</h2>
    <div class="tablewrap"><table class="sortable"><thead><tr><th data-k="name">限制</th><th>計法</th><th class="n" data-k="shares" data-t="num">最多</th></tr></thead><tbody>
    ${z.limits.map((l) => `<tr data-name="${attr(NAMES[l.name] || l.name)}" data-shares="${attr(l.shares)}"><td>${esc(NAMES[l.name] || l.name)}${l.binds ? " ⬅" : ""}</td><td>${esc(l.how)}</td><td class="n">${l.shares} 股</td></tr>`).join("")}
    </tbody></table></div>
    <p class="explain">幾個限制取最細嗰個（⬅）。如果去到止蝕，最多蝕約 ${num(usd(z.max_loss))}（快市可能蝕多啲）。戶口 ${num(usd(res.budget, 0))}，每單最多蝕 ${num(usd(res.max_loss, 0))}。撳欄位標題可以排序。</p></div>`;
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
    <p><span class="badge">模擬交易</span></p>
    ${kv([["指令", `買入 ${num(esc(i.qty))} 股 ${esc(i.symbol)}，市價，當日有效`], ["止蝕單", num(usd(Number(i.stop_loss_stop_price)))], ["止賺單", num(usd(Number(i.take_profit_limit_price)))],
      ["最多蝕", `約 ${num(usd(t.max_loss))}`], ["狀態", `<span class="pill ${t.ready ? "pass" : "block"}">${t.ready ? "可以落（模擬）" : "未準備好"}</span>`]])}
    <p class="explain">呢個 app 冇連任何券商，呢張票唔會送出。止蝕同止賺係一對「二選一」單：一張成交，另一張自動取消。</p></div>`;
}

function bindSort(root) {
  root.querySelectorAll("table.sortable").forEach((table) => {
    const ths = table.querySelectorAll("thead th[data-k]");
    ths.forEach((th) => {
      th.classList.add("sortable");
      th.tabIndex = 0;
      if (!th.getAttribute("aria-sort")) th.setAttribute("aria-sort", "none");
      const go = () => {
        const k = th.dataset.k;
        const type = th.dataset.t || "text";
        const dir = th.getAttribute("aria-sort") === "ascending" ? "desc" : "asc";
        ths.forEach((x) => x.setAttribute("aria-sort", "none"));
        th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
        const body = table.tBodies[0];
        if (!body) return;
        const mul = dir === "asc" ? 1 : -1;
        [...body.rows].sort((a, b) => {
          const av = a.dataset[k] ?? "", bv = b.dataset[k] ?? "";
          if (type === "num") {
            const an = parseFloat(av), bn = parseFloat(bv);
            const aBad = Number.isNaN(an), bBad = Number.isNaN(bn);
            if (aBad && bBad) return 0;
            if (aBad) return 1;
            if (bBad) return -1;
            return (an - bn) * mul;
          }
          return av.localeCompare(bv, "zh-Hant") * mul;
        }).forEach((r) => body.appendChild(r));
      };
      th.addEventListener("click", go);
      th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
  });
}

function pair(a, b) {
  if (a && b) return `<div class="pair">${a}${b}</div>`;
  return (a || "") + (b || "");
}

function renderTrade(res, bars) {
  const st = res.steps;
  return verdictCard(res) + kpiRow(res, bars) + chartCard(res, bars) +
    pair(entryCard(st.entry, res), exitCard(st.exit)) +
    tmCard(st.timemachine) +
    pair(budgetCard(st.budget, res), riskCard(st.risk)) +
    newsCard(st.news, res.ticker) + ticketCard(st.ticket) +
    (res.cached ? `<p class="hint">（10 分鐘內有人查過同一組設定，用咗暫存結果，對免費數據源客氣啲。）</p>` : "");
}

$("#run").addEventListener("click", async () => {
  const q = new URLSearchParams({ticker: $("#ticker").value.trim().toUpperCase(), budget: $("#budget").value, max_loss: $("#maxloss").value});
  if ($("#rtime").value.trim()) q.set("time", $("#rtime").value.trim());
  const bq = new URLSearchParams({ticker: q.get("ticker")});
  if (q.get("time")) bq.set("time", q.get("time"));
  const btn = $("#run"), out = $("#trade-out");
  btn.disabled = true;
  clearCharts();
  out.innerHTML = skeletonTrade();
  try {
    const [res, bars] = await Promise.all([
      getJSON("/api/run?" + q),
      getJSON("/api/bars?" + bq).catch((e) => ({_err: e.message})),
    ]);
    clearCharts();
    out.innerHTML = renderTrade(res, bars);
    mountCandle(res, bars);
    bindSort(out);
  } catch (e) {
    clearCharts();
    out.innerHTML = errCard(e.message);
  }
  btn.disabled = false;
});
["#ticker", "#budget", "#maxloss", "#rtime"].forEach((id) => {
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") $("#run").click(); });
});

const SETUP = {orb: "開市區間突破", breakout_20d: "20 日收市新高", bull_flag: "牛旗", reclaim_ma20: "重上 20 日線", oversold: "超賣（RSI<30）", oversold_bounce: "超賣反彈"};
$("#scanbtn").addEventListener("click", async () => {
  const mode = $("#scanmode").value, out = $("#scan-out"), btn = $("#scanbtn");
  btn.disabled = true;
  out.innerHTML = skeletonTable(mode === "orb" ? "掃緊約 100 張 5 分鐘圖…大約 30 至 60 秒。" : "掃緊約 100 張日線圖…大約 5 秒。");
  try {
    const r = await getJSON("/api/scan?mode=" + mode + ($("#rtime").value.trim() ? "&time=" + encodeURIComponent($("#rtime").value.trim()) : ""));
    if (!r.ok) { out.innerHTML = errCard("掃描失敗", r.err); btn.disabled = false; return; }
    const d = r.data, c = d.counts || {}, hits = d.hits || [];
    const head = mode === "orb"
      ? `<p>${esc(d.as_of)}：${c.fetched} 張圖有數據、${c.scanned} 張可用，<b>${hits.length}</b> 隻突破咗開市區間。</p>`
      : `<p>${esc(d.as_of)}：${c.scanned} 隻夠流通，<b>${hits.length}</b> 隻符合某個日線形態。</p>`;
    if (!hits.length) {
      out.innerHTML = `<div class="card">${head}<p class="empty">暫時冇符合條件嘅股票。</p></div>`;
      btn.disabled = false; return;
    }
    const rows = hits.map((h) => mode === "orb"
      ? `<tr class="click" data-s="${attr(h.symbol)}" data-sym="${attr(h.symbol)}" data-at="${attr(h.at)}" data-price="${attr(h.price)}" data-over="${attr(h.pct_over)}"><td><b>${esc(h.symbol)}</b></td><td>${esc(h.at)}</td><td class="n">${usd(h.price)}</td><td class="n up">+${esc(h.pct_over)}%</td></tr>`
      : `<tr class="click" data-s="${attr(h.symbol)}" data-sym="${attr(h.symbol)}" data-setup="${attr((h.setups || []).join(","))}" data-price="${attr(h.price)}" data-rsi="${attr(h.rsi)}"><td><b>${esc(h.symbol)}</b></td><td>${h.setups.map((x) => esc(SETUP[x] || x)).join("、")}</td><td class="n">${usd(h.price)}</td><td class="n">${esc(h.rsi)}</td></tr>`).join("");
    const headRow = mode === "orb"
      ? `<th data-k="sym">股票</th><th data-k="at">觸發時間</th><th class="n" data-k="price" data-t="num">價</th><th class="n" data-k="over" data-t="num">高出區間</th>`
      : `<th data-k="sym">股票</th><th data-k="setup">形態</th><th class="n" data-k="price" data-t="num">收市價</th><th class="n" data-k="rsi" data-t="num">RSI</th>`;
    out.innerHTML = `<div class="card">${head}<div class="tablewrap"><table class="sortable"><thead><tr>${headRow}</tr></thead><tbody>${rows}</tbody></table></div>
      <p class="explain">名單只係「符合某條規則」，唔係買入清單。撳欄位標題可以排序。撳一行就會帶你去分析嗰隻股${mode === "daily" ? "（日線形態唔等於即日有突破訊號）" : ""}。</p></div>`;
    bindSort(out);
    out.querySelectorAll("tr.click").forEach((tr) => tr.addEventListener("click", () => { $("#ticker").value = tr.dataset.s; $("#an-ticker").value = tr.dataset.s; showTab("trade"); window.scrollTo(0, 0); }));
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});

const M = (v) => v == null ? "–" : (v / 1e6).toLocaleString("en-US", {maximumFractionDigits: 0});
const P = (v) => v == null ? "–" : (v > 0 ? "+" : "") + v + "%";
$("#anbtn").addEventListener("click", async () => {
  const out = $("#an-out"), btn = $("#anbtn");
  btn.disabled = true; out.innerHTML = skeletonTable("讀緊 SEC 財報…");
  try {
    const r = await getJSON("/api/analyst?ticker=" + encodeURIComponent($("#an-ticker").value.trim().toUpperCase()));
    const x = r.data && r.data[0];
    if (!r.ok || !x || !x.result) { out.innerHTML = errCard("讀唔到業績", r.err || (x && x.error)); btn.disabled = false; return; }
    const res = x.result;
    out.innerHTML = `<div class="card"><div class="step">業績</div><h2>${esc(res.entity)}（${esc(x.ticker)}）</h2><div class="tablewrap"><table class="sortable"><thead><tr>
      <th data-k="q">季度</th><th class="n" data-k="rev" data-t="num">收入（百萬美元）</th><th class="n" data-k="yoy" data-t="num">按年</th>
      <th class="n" data-k="gm" data-t="num">毛利率</th><th class="n" data-k="om" data-t="num">經營利潤率</th>
      <th class="n" data-k="ni" data-t="num">淨利</th><th class="n" data-k="eps" data-t="num">EPS</th>
    </tr></thead><tbody>
      ${res.rows.map((q) => `<tr data-q="${attr(q.fiscal)}" data-rev="${attr(q.revenue)}" data-yoy="${attr(q.revenue_yoy)}" data-gm="${attr(q.gross_margin)}" data-om="${attr(q.operating_margin)}" data-ni="${attr(q.net_income)}" data-eps="${attr(q.eps_diluted)}"><td>${esc(q.fiscal)}${q.derived ? "*" : ""}</td><td class="n">${M(q.revenue)}</td><td class="n ${clsOf(q.revenue_yoy)}">${P(q.revenue_yoy)}</td><td class="n">${q.gross_margin == null ? "–" : q.gross_margin + "%"}</td><td class="n">${q.operating_margin == null ? "–" : q.operating_margin + "%"}</td><td class="n">${M(q.net_income)}</td><td class="n">${q.eps_diluted == null ? "–" : q.eps_diluted}</td></tr>`).join("")}
      </tbody></table></div><p class="explain">最近四季：收入 ${M(res.ttm && res.ttm.revenue)} 百萬、淨利 ${M(res.ttm && res.ttm.net_income)} 百萬美元。* 係用全年減三季推算。數據來自 SEC XBRL。撳欄位標題可以排序。</p></div>`;
    bindSort(out);
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});
$("#an-ticker").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#anbtn").click(); });

const OWNER = {spouse: "配偶", self: "本人", joint: "聯名", dependent: "子女"};
const SIDE = {purchase: "買入", sale: "賣出", "partial sale": "部分賣出", exchange: "交換"};
$("#ptrbtn").addEventListener("click", async () => {
  const out = $("#ptr-out"), btn = $("#ptrbtn");
  btn.disabled = true; out.innerHTML = skeletonTable("讀緊眾議院申報索引…");
  try {
    const r = await getJSON("/api/pelosi?member=" + encodeURIComponent($("#member").value.trim()));
    const list = r.data || [];
    if (!r.ok) { out.innerHTML = errCard("讀唔到申報", r.err); btn.disabled = false; return; }
    if (!list.length) { out.innerHTML = `<div class="card"><p class="empty">今年搵唔到呢位議員嘅交易申報。</p></div>`; btn.disabled = false; return; }
    out.innerHTML = `<div class="card"><div class="step">議員交易</div><h2>${esc(list[0].name)} 今年嘅交易申報</h2><div class="tablewrap"><table class="sortable"><thead><tr><th data-k="filed">申報日</th><th data-k="doc">文件</th><th></th></tr></thead><tbody>
      ${list.map((f) => `<tr data-filed="${attr(f.filed)}" data-doc="${attr(f.doc_id)}"><td class="num">${esc(f.filed)}</td><td><a href="${esc(safeUrl(f.url))}" target="_blank" rel="noopener">${esc(f.doc_id)}</a></td><td><button type="button" class="ghost" data-doc="${attr(f.doc_id)}" data-year="${attr(f.year)}">睇內容</button></td></tr>`).join("")}
      </tbody></table></div><p class="explain">撳欄位標題可以排序。法例容許交易後 45 日先申報，所以係舊消息。</p><div id="ptr-detail"></div></div>`;
    bindSort(out);
    out.querySelectorAll("button[data-doc]").forEach((b) => b.addEventListener("click", async () => {
      const det = $("#ptr-detail"); det.innerHTML = skeletonTable("下載緊 PDF 同讀緊…");
      try {
        const d = await getJSON(`/api/ptr?doc=${encodeURIComponent(b.dataset.doc)}&year=${encodeURIComponent(b.dataset.year)}`);
        const rows = (d.data && d.data.rows) || [];
        det.innerHTML = rows.length ? `<h2>文件 ${esc(b.dataset.doc)}</h2><div class="tablewrap"><table class="sortable"><thead><tr>
          <th data-k="date">交易日</th><th data-k="who">誰</th><th data-k="side">買／賣</th><th data-k="asset">資產</th><th data-k="amt">金額範圍</th><th class="n" data-k="days" data-t="num">幾多日後申報</th>
        </tr></thead><tbody>
          ${rows.map((x) => `<tr data-date="${attr(x.date)}" data-who="${attr(x.owner_name)}" data-side="${attr(x.type_name)}" data-asset="${attr(x.ticker || x.asset)}" data-amt="${attr(x.amount)}" data-days="${attr(x.days_to_disclose)}"><td class="num">${esc(x.date)}</td><td>${esc(OWNER[x.owner_name] || x.owner_name || "")}</td><td>${esc(SIDE[x.type_name] || x.type_name)}</td><td>${esc(x.ticker ? x.ticker + " " : "")}${esc(x.asset)}<div class="meta">${esc(x.description || "")}</div></td><td>${esc(x.amount)}</td><td class="n">${x.days_to_disclose == null ? "–" : x.days_to_disclose}</td></tr>`).join("")}
          </tbody></table></div><p class="explain">撳欄位標題可以排序。金額係申報表格上嘅範圍，唔係精確成交價。</p>`
          : errCard("讀唔到呢份文件嘅交易（可能係手寫掃描 PDF）", d.err);
        bindSort(det);
      } catch (e) { det.innerHTML = errCard(e.message); }
    }));
  } catch (e) { out.innerHTML = errCard(e.message); }
  btn.disabled = false;
});
$("#member").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#ptrbtn").click(); });

const qs = new URLSearchParams(location.search);
if (qs.get("ticker")) { $("#ticker").value = qs.get("ticker").toUpperCase(); $("#an-ticker").value = qs.get("ticker").toUpperCase(); }
if (qs.get("time")) $("#rtime").value = qs.get("time");
if (qs.get("tab")) showTab(qs.get("tab"));
if (qs.get("run") === "1") $("#run").click();
