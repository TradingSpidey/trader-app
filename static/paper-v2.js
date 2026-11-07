/* QUANT_V2 page. Reads only /api/paper/v2. Does not write a book. */
(function () {
  function money(v) {
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (Number.isNaN(n)) return "—";
    return n.toFixed(2);
  }
  function scoreText(v) {
    if (v == null || v === "") return "stub";
    if (typeof v === "number") return v.toFixed(2);
    var n = Number(v);
    if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(n)) return n.toFixed(2);
    return String(v);
  }
  function dirZh(direction) {
    var s = String(direction || "").toUpperCase();
    if (s === "LONG" || s === "BUY") return "做多";
    if (s === "SHORT" || s === "SELL") return "做空";
    if (s === "FLAT" || s === "HOLD") return "觀望";
    return "";
  }
  function sideText(side) {
    var s = String(side || "").toUpperCase();
    if (s === "BUY") return "買入 BUY";
    if (s === "SELL") return "賣出 SELL";
    return side ? String(side) : "—";
  }
  function text(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }
  function paint(view) {
    var book = view && view.book ? view.book : {};
    var symbol = book.symbol || "BTCUSDT";
    text("status-line", "PAPER LIVE · QUANT_V2 · " + symbol);
    text("kpi-equity", money(book.equity_usd));
    text("kpi-cash", money(book.cash_usd));
    text("kpi-score", scoreText(book.score));
    text("kpi-direction", book.direction || "—");
    text("kpi-direction-zh", dirZh(book.direction));
    text("kpi-price", money(book.last_price));
    text("kpi-updated", book.updated_hkt || "—");
    text("live-symbol", symbol);
    var metaEl = document.getElementById("live-meta");
    if (metaEl) {
      var bits = [];
      if (book.venue) bits.push(String(book.venue));
      if (book.interval) bits.push(String(book.interval));
      var line = bits.join(" · ");
      if (book.bars != null && book.bars !== "") line += (line ? " × " : "") + book.bars;
      metaEl.textContent = line;
    }
    var src = document.getElementById("source-line");
    if (src) {
      if (view && view.source === "ingest") {
        src.textContent = "已接收 QUANT_V2 push" + (view.received_at ? " · " + view.received_at : "");
      } else {
        src.textContent = "未收到 push，而家顯示 smoke seed";
      }
    }
    var body = document.getElementById("fills-body");
    if (!body) return;
    body.replaceChildren();
    var fills = book.fills || [];
    if (!fills.length) {
      var empty = document.createElement("tr");
      var cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = "未有模擬成交";
      empty.appendChild(cell);
      body.appendChild(empty);
      return;
    }
    fills.forEach(function (row) {
      var tr = document.createElement("tr");
      [
        ["時間", row.ts_hkt || "—"],
        ["邊", sideText(row.side)],
        ["代號", row.symbol || "—"],
        ["名義", money(row.notional_usd)],
        ["價格", money(row.price)],
        ["標記", row.kind || "smoke"]
      ].forEach(function (pair) {
        var td = document.createElement("td");
        td.className = "num";
        td.setAttribute("data-label", pair[0]);
        td.textContent = pair[1];
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }
  function refresh() {
    fetch("/api/paper/v2", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (view) { if (view) paint(view); })
      .catch(function () {});
  }
  refresh();
  setInterval(refresh, 20000);
})();
