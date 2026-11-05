"""US-stock paper desk. Yahoo quotes only. Nothing here can place a real order."""
import datetime
import os
import threading
import time

from traderapp import pipeline

START_USD = float(os.environ.get("DESK_STOCK_START_USD") or "10000")
# Buys fill above the Yahoo quote, sells below it. 0.001 = 0.1% per side.
SLIPPAGE_PER_SIDE = float(os.environ.get("DESK_STOCK_SLIPPAGE_PER_SIDE") or "0.001")
# Charged on each buy and each sell. A rate, if set, still cannot go under this.
COMMISSION_MIN_USD = float(os.environ.get("DESK_STOCK_COMMISSION_USD") or "0.01")
COMMISSION_RATE = float(os.environ.get("DESK_STOCK_COMMISSION_RATE") or "0")
UNIVERSE = pipeline.LIQUID[:20]
MAX_POSITIONS = 3
MAX_ORDER_USD = 2000.0
MAX_POSITION_PCT = 0.20
MAX_DAILY_LOSS_PCT = 0.05
MIN_PRICE = 5.0
MIN_AVG_VOL = 1_000_000.0
TP = 0.03
SL = 0.015
GAP_SIGNAL = 1.5
RVOL_FLAG = 2.0
TICK_SEC = 60
LIST_TTL = 180

_lock = threading.Lock()
_state = None
_cache = {}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _iso(dt=None):
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blank(start=None):
    cash = float(start if start is not None else START_USD)
    return {
        "started_at": _iso(), "start_usd": cash, "cash_usd": cash,
        "positions": [], "closed": [], "feed": [], "seq": 1, "kill": False,
        "last_tick": 0.0, "quotes": [], "errors": [], "route": [], "focus": {},
        "realized_by": {}, "session": {}, "news": None, "congress": None,
        "market_at": None,
    }


def _book():
    global _state
    if _state is None:
        _state = _blank()
    return _state


def _log(bot, text, kind):
    _book()["feed"].append({"ts": _iso(), "bot": bot, "text": text, "kind": kind})
    del _book()["feed"][:-48]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _costs_note():
    slip = SLIPPAGE_PER_SIDE * 100.0
    note = "買入成交高過 Yahoo 報價 %.1f%%，賣出低過報價 %.1f%%。每邊手續費最少 $%.2f。" % (
        slip, slip, COMMISSION_MIN_USD)
    if COMMISSION_RATE > 0:
        note += "手續費亦唔低過成交金額 %.2f%%。" % (COMMISSION_RATE * 100.0)
    return note


def _buy_fill(quote):
    """Execution price for a buy: worse (higher) than the quote."""
    q = _f(quote)
    if q is None or q <= 0:
        return None
    px = q * (1.0 + SLIPPAGE_PER_SIDE)
    return px if px > 0 else None


def _sell_fill(quote):
    """Execution price for a sell: worse (lower) than the quote."""
    q = _f(quote)
    if q is None or q <= 0:
        return None
    px = q * (1.0 - SLIPPAGE_PER_SIDE)
    return px if px > 0 else None


def _commission_usd(notional):
    """Per-side commission. At least COMMISSION_MIN_USD."""
    gross = abs(_f(notional) or 0.0)
    rate = COMMISSION_RATE if COMMISSION_RATE > 0 else 0.0
    floor = COMMISSION_MIN_USD if COMMISSION_MIN_USD > 0 else 0.0
    return max(floor, gross * rate)


def _plan_buy(quote, budget):
    """Size a buy so cash out (slipped notional + commission) stays within budget."""
    fill = _buy_fill(quote)
    budget = _f(budget)
    if fill is None or budget is None or budget <= 0:
        return None
    rate = COMMISSION_RATE if COMMISSION_RATE > 0 else 0.0
    floor = COMMISSION_MIN_USD if COMMISSION_MIN_USD > 0 else 0.0
    qty = None
    if rate:
        qty_rate = budget / (fill * (1.0 + rate))
        if qty_rate * fill * rate + 1e-12 >= floor:
            qty = qty_rate
    if qty is None:
        if budget <= floor:
            return None
        qty = (budget - floor) / fill
    if qty <= 0:
        return None
    notional = qty * fill
    fee = _commission_usd(notional)
    cash_out = notional + fee
    if cash_out - budget > 1e-8:
        if budget <= fee:
            return None
        qty = (budget - fee) / fill
        if qty <= 0:
            return None
        notional = qty * fill
        fee = _commission_usd(notional)
        cash_out = notional + fee
    return {
        "quote": float(quote), "fill": fill, "qty": qty, "notional": notional,
        "commission_usd": fee, "cash_out": cash_out,
    }


def _plan_sell(quote, qty):
    fill = _sell_fill(quote)
    qty = _f(qty)
    if fill is None or qty is None or qty <= 0:
        return None
    notional = qty * fill
    fee = _commission_usd(notional)
    return {
        "quote": float(quote), "fill": fill, "qty": qty, "notional": notional,
        "commission_usd": fee, "proceeds": notional - fee,
    }


def _fill_buy(st, symbol, quote, budget, why, source="Yahoo"):
    """Open one paper long. budget is the most cash that may leave, including commission."""
    available = _f(st.get("cash_usd")) or 0.0
    cap = _f(budget)
    if cap is None:
        return None
    plan = _plan_buy(quote, min(cap, available))
    if plan is None:
        return None
    st["cash_usd"] = available - plan["cash_out"]
    pos = {
        "id": st.get("seq") or 1, "symbol": symbol, "qty": plan["qty"],
        "entry_usd": plan["fill"], "entry_quote_usd": plan["quote"],
        "entry_commission_usd": plan["commission_usd"], "cost_usd": plan["cash_out"],
        "last_usd": plan["quote"], "value_usd": plan["qty"] * plan["quote"],
        "upnl_usd": plan["qty"] * plan["quote"] - plan["cash_out"],
        "ret": plan["quote"] / plan["fill"] - 1.0, "opened_at": _iso(),
        "why": why, "source": source,
    }
    st["positions"].append(pos)
    st["seq"] = int(st.get("seq") or 1) + 1
    return pos


def _bars(series):
    t = series.get("t") or []
    c = series.get("c") or []
    h = series.get("h") or []
    low = series.get("l") or []
    v = series.get("v") or []
    out = []
    for i, ts in enumerate(t):
        if ts is None or i >= len(c) or c[i] is None:
            continue
        out.append({
            "t": int(ts), "c": float(c[i]),
            "h": float(h[i]) if i < len(h) and h[i] is not None else float(c[i]),
            "l": float(low[i]) if i < len(low) and low[i] is not None else float(c[i]),
            "v": float(v[i]) if i < len(v) and v[i] is not None else None,
        })
    return out


def session_now():
    """US session labelled in Hong Kong time. Regular hours follow America/New_York."""
    try:
        from zoneinfo import ZoneInfo
        utc = datetime.datetime.now(datetime.timezone.utc)
        et = utc.astimezone(ZoneInfo("America/New_York"))
        hkt = utc.astimezone(ZoneInfo("Asia/Hong_Kong"))
    except Exception:
        utc = _now()
        et = utc + datetime.timedelta(hours=-5)
        hkt = utc + datetime.timedelta(hours=8)
        et = et.replace(tzinfo=datetime.timezone.utc)
        hkt = hkt.replace(tzinfo=datetime.timezone.utc)
    day = et.date()
    sess = pipeline._scan.session(day)
    t = et.timetz().replace(tzinfo=None) if hasattr(et, "timetz") else et.time()
    if not sess:
        phase = "休市"
    elif t < datetime.time(4, 0) or t >= datetime.time(20, 0):
        phase = "休市"
    elif t < datetime.time(9, 30):
        phase = "盤前"
    elif t < datetime.time(16, 0):
        phase = "開市"
    else:
        phase = "盤後"
    open_et = et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_et = et.replace(hour=16, minute=0, second=0, microsecond=0)
    try:
        oh, ch = open_et.astimezone(hkt.tzinfo), close_et.astimezone(hkt.tzinfo)
        hours = "%s–%s（香港）" % (oh.strftime("%H:%M"), ch.strftime("%H:%M"))
        if ch.date() != oh.date():
            hours = "%s–翌日 %s（香港）" % (oh.strftime("%H:%M"), ch.strftime("%H:%M"))
    except Exception:
        hours = "22:30–翌日 05:00（香港）"
    flat = phase == "開市" and t >= datetime.time(15, 50)
    return {
        "phase": phase, "open": phase == "開市" and not flat, "flatten": flat,
        "et": et.strftime("%Y-%m-%d %H:%M"), "hkt": hkt.strftime("%Y-%m-%d %H:%M"),
        "hours_hkt": hours, "source": "America/New_York",
    }


def _cached_lists():
    hit = _cache.get("daily")
    now = time.time()
    if hit and now - hit[0] < LIST_TTL:
        return hit[1], hit[2], None
    scan = pipeline._scan
    try:
        data, failed = scan.fetch_spark(list(UNIVERSE), "5d", "1d", 0)
    except Exception as e:
        _cache["yahoo_state"] = "出錯"
        if hit:
            return hit[1], hit[2], e.__class__.__name__
        return [], 0, e.__class__.__name__
    quotes = []
    for sym in UNIVERSE:
        series = data.get(sym)
        if not series:
            continue
        bars = _bars(series)
        if len(bars) < 2:
            continue
        last, prev = bars[-1], bars[-2]
        vols = [b["v"] for b in bars[:-1] if b.get("v")]
        avg = (sum(vols) / len(vols)) if vols else None
        rvol = (last["v"] / avg) if avg and last.get("v") else None
        gap = (last["c"] / prev["c"] - 1.0) * 100.0 if prev["c"] else None
        quotes.append({
            "symbol": sym, "price": last["c"], "prev": prev["c"], "gap": gap,
            "volume": last.get("v"), "avg_volume": avg, "rvol": rvol,
            "candles": [{"t": b["t"], "c": b["c"]} for b in bars[-8:]],
            "source": "Yahoo",
        })
    failed_n = len(failed or {})
    err = None if quotes else "Yahoo 冇日線"
    _cache["daily"] = (now, quotes, failed_n)
    _cache["yahoo_state"] = "正常" if quotes else "出錯"
    return quotes, failed_n, err


def _daily_chart(sym):
    hit = _cache.get("vol:" + sym)
    if hit and time.time() - hit[0] < LIST_TTL:
        return hit[1]
    scan = pipeline._scan
    try:
        ch = scan.parse_chart(scan.yahoo_get(scan.chart_path(sym, "5d", "1d")), sym)
        bars = _bars(ch)
    except Exception:
        bars = []
    _cache["vol:" + sym] = (time.time(), bars)
    return bars


def _fill_volume(rows):
    ranked = sorted(rows, key=lambda q: abs(q["gap"]) if q.get("gap") is not None else -1, reverse=True)
    for q in ranked[:8]:
        bars = _daily_chart(q["symbol"])
        if len(bars) < 2:
            continue
        last = bars[-1]
        vols = [b["v"] for b in bars[:-1] if b.get("v")]
        avg = (sum(vols) / len(vols)) if vols else None
        q["price"] = last["c"]
        q["volume"] = last.get("v")
        q["avg_volume"] = avg
        q["rvol"] = (last["v"] / avg) if avg and last.get("v") else None
        q["candles"] = [{"t": b["t"], "c": b["c"]} for b in bars[-8:]]


def _intraday(symbols):
    hit = _cache.get("m5")
    now = time.time()
    if hit and now - hit[0] < 120:
        return hit[1]
    scan = pipeline._scan
    try:
        data, _failed = scan.fetch_spark(list(symbols), "1d", "5m", 0)
    except Exception:
        _cache["yahoo_state"] = "出錯"
        return hit[1] if hit else {}
    out = {}
    for sym, series in data.items():
        bars = _bars(series)
        kept = []
        for b in bars:
            et = scan.ts_to_eastern(b["t"])
            if et.time() < datetime.time(9, 30) or et.time() >= datetime.time(16, 0):
                continue
            kept.append(dict(b, et=et))
        out[sym] = kept
    _cache["m5"] = (now, out)
    return out


def _orb(bars):
    """First 15 minutes high/low, then a later close above the high. Real bars only."""
    if not bars:
        return None
    opening = [b for b in bars if b["et"].time() < datetime.time(9, 45)]
    if len(opening) < 3:
        return {"ready": False, "reason": "開市 15 分鐘未完"}
    hi = max(b["h"] for b in opening)
    lo = min(b["l"] for b in opening)
    later = [b for b in bars if b["et"].time() >= datetime.time(9, 45)]
    hit = next((b for b in later if b["c"] > hi), None)
    return {"ready": True, "high": hi, "low": lo, "trigger": None if not hit else {"t": hit["et"].strftime("%H:%M"), "price": hit["c"]}}


def _news(symbol):
    hit = _cache.get("news:" + symbol)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    import tempfile
    work = tempfile.mkdtemp(prefix="desk-news-")
    try:
        args = [pipeline._tool("trader-news", "news.py"), "--tickers", symbol, "--hours", "36", "--json", "--dry-run", "--no-sec"]
        res = pipeline._run(args, work, 40)
        data = pipeline._json(res) or {}
    except Exception as e:
        data = {"error": e.__class__.__name__}
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    _cache["news:" + symbol] = (time.time(), data)
    return data


def _congress():
    hit = _cache.get("congress")
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        doc = pipeline.run_pelosi("pelosi")
    except Exception as e:
        doc = {"ok": False, "err": e.__class__.__name__}
    _cache["congress"] = (time.time(), doc)
    return doc


def _mark(st):
    by = {q["symbol"]: q for q in st.get("quotes") or []}
    for pos in st["positions"]:
        q = by.get(pos["symbol"])
        px = q.get("price") if q else None
        pos["last_usd"] = px
        if px:
            pos["value_usd"] = pos["qty"] * px
            pos["upnl_usd"] = pos["value_usd"] - pos["cost_usd"]
            pos["ret"] = px / pos["entry_usd"] - 1.0 if pos.get("entry_usd") else None
        else:
            pos["value_usd"] = pos["upnl_usd"] = pos["ret"] = None


def _equity(st):
    missing = False
    mtm = 0.0
    for pos in st["positions"]:
        if pos.get("value_usd") is None:
            missing = True
        else:
            mtm += pos["value_usd"]
    if missing:
        return None, True
    return st["cash_usd"] + mtm, False


def _close(st, pos, reason, bot):
    plan = _plan_sell(pos.get("last_usd"), pos.get("qty"))
    if plan is None:
        _log(bot, "%s 未平倉：而家冇 Yahoo 報價，唔會估價。" % pos["symbol"], "paper")
        return False
    proceeds = plan["proceeds"]
    pnl = proceeds - pos["cost_usd"]
    st["cash_usd"] += proceeds
    st["realized_by"][bot] = st["realized_by"].get(bot, 0.0) + pnl
    st["closed"].append({
        "symbol": pos["symbol"], "pnl_usd": pnl, "reason": reason, "exit_usd": plan["fill"],
        "exit_quote_usd": plan["quote"], "exit_commission_usd": plan["commission_usd"],
        "proceeds_usd": proceeds, "bot": bot, "ts": _iso(), "qty": pos["qty"],
    })
    _log(bot, "模擬平倉 %s（%s），Yahoo 報價 $%.4g，成交 $%.4g，手續費 $%.2f，模擬盈虧 %+.2f 美元。" % (
        pos["symbol"], reason, plan["quote"], plan["fill"], plan["commission_usd"], pnl), "paper")
    return True


def _flatten(st, bot, reason):
    keep = []
    for pos in list(st["positions"]):
        if not _close(st, pos, reason, bot):
            keep.append(pos)
    st["positions"] = keep


def _tick(st):
    sess = session_now()
    st["session"] = sess
    st["blocked"] = None
    quotes, failed_n, err = _cached_lists()
    st["quotes"] = quotes
    st["errors"] = []
    if err and not quotes:
        st["errors"].append("Yahoo：" + err)
    elif failed_n:
        st["errors"].append("Yahoo 有 %s 隻冇數據" % failed_n)
    if quotes:
        st["market_at"] = _cache.get("daily", (time.time(),))[0]
    _mark(st)
    route = []
    if sess.get("flatten") and st["positions"]:
        _flatten(st, "EXIT", "收市前平倉")
        route.append("執行：收市前平倉")
    still = []
    for pos in st["positions"]:
        ret = pos.get("ret")
        if ret is None:
            still.append(pos)
            continue
        if ret >= TP:
            if not _close(st, pos, "到止賺 +%.1f%%" % (TP * 100), "EXIT"):
                still.append(pos)
        elif ret <= -SL:
            if not _close(st, pos, "到止蝕 -%.1f%%" % (SL * 100), "EXIT"):
                still.append(pos)
        else:
            still.append(pos)
    st["positions"] = still

    intraday = _intraday([q["symbol"] for q in quotes]) if sess["phase"] == "開市" and quotes else {}
    rows = []
    for q in quotes:
        orb = _orb(intraday.get(q["symbol"])) if sess["phase"] == "開市" else None
        rows.append(dict(q, orb=orb, candles_m5=[{"t": b["t"], "c": b["c"]} for b in (intraday.get(q["symbol"]) or [])][-24:]))
    rows.sort(key=lambda q: abs(q["gap"]) if q.get("gap") is not None else -1, reverse=True)
    _fill_volume(rows)
    st["rows"] = rows
    focus_scan = rows[0] if rows else None
    held = {p["symbol"] for p in st["positions"]} | {c["symbol"] for c in st["closed"]}

    def risk_ok(q):
        reasons = []
        if q.get("price") is None:
            return False, ["股價暫無"]
        if q["price"] < MIN_PRICE:
            reasons.append("股價低過 $%.0f" % MIN_PRICE)
        if q.get("avg_volume") is None:
            reasons.append("平均成交量暫無")
        elif q["avg_volume"] < MIN_AVG_VOL:
            reasons.append("平均成交 %.0f 股，低過 %s" % (q["avg_volume"], "{:,.0f}".format(MIN_AVG_VOL)))
        return not reasons, reasons

    signals = []
    for q in rows:
        if sess["phase"] != "開市":
            continue
        orb = q.get("orb") or {}
        gap_ok = q.get("gap") is not None and q["gap"] >= GAP_SIGNAL and q["price"] > q["prev"]
        orb_ok = bool(orb.get("ready") and orb.get("trigger"))
        if gap_ok or orb_ok:
            ok, why = risk_ok(q)
            note = []
            if gap_ok:
                note.append("缺口 %+.2f%%" % q["gap"])
            if orb_ok:
                note.append("開市區間突破 %s 收 $%.2f" % (orb["trigger"]["t"], orb["trigger"]["price"]))
            signals.append((q, note, ok, why))
    signals.sort(key=lambda x: x[0].get("rvol") or 0, reverse=True)
    whale = max(rows, key=lambda q: q.get("rvol") or -1) if rows else None
    news_sym = (signals[0][0]["symbol"] if signals else (focus_scan["symbol"] if focus_scan else None))
    st["news"] = _news(news_sym) if news_sym else None
    st["congress"] = _congress()
    items = ((st["news"] or {}).get("items") or []) if isinstance(st.get("news"), dict) else []
    earnings = any("earnings" in ",".join(n.get("tags") or []).lower() or "earnings" in (n.get("title") or "").lower() for n in items[:8])

    route.append("時段：%s" % sess["phase"])
    bought = None
    if not sess.get("open"):
        route.append("唔係正規時段，唔開新模擬倉")
    elif st["kill"]:
        route.append("風控停止緊")
    elif len(st["positions"]) >= MAX_POSITIONS:
        route.append("模擬倉已滿")
    else:
        equity, missing = _equity(st)
        start = st["start_usd"]
        loss_cap = start * MAX_DAILY_LOSS_PCT
        if missing or equity is None:
            route.append("有倉未有報價，唔開新倉")
        else:
            used = max(0.0, start - equity)
            room = loss_cap - used
            if room <= 1:
                st["kill"] = True
                _flatten(st, "RISK", "觸發每日虧損上限")
                route.append("已觸發每日虧損上限")
            else:
                pick = None
                blocked = None
                for q, note, ok, why in signals:
                    if q["symbol"] in held or q["symbol"] in {p["symbol"] for p in st["positions"]}:
                        continue
                    if earnings and q["symbol"] == news_sym:
                        blocked = (q, ["新聞提到業績，避開"])
                        continue
                    if not ok:
                        blocked = (q, why)
                        continue
                    pick = (q, note)
                    break
                if pick:
                    q, note = pick
                    budget = room / SL
                    size = min(MAX_ORDER_USD, equity * MAX_POSITION_PCT, budget, st["cash_usd"])
                    if size < 10 or not q.get("price"):
                        route.append("可用模擬現金唔夠")
                    else:
                        pos = _fill_buy(st, q["symbol"], q["price"], size, "、".join(note))
                        if pos is None:
                            route.append("可用模擬現金唔夠")
                        else:
                            bought = q["symbol"]
                            route.append("模擬買入 %s $%.2f" % (q["symbol"], pos["cost_usd"]))
                            _log("CHIEF", "正規時段。模擬買入 %s，%.4f 股，Yahoo 報價 $%.4g，成交 $%.4g，手續費 $%.2f。唔係真單。" % (
                                q["symbol"], pos["qty"], pos["entry_quote_usd"], pos["entry_usd"], pos["entry_commission_usd"]), "paper")
                            _log("SNIPER", "訊號：%s。" % "、".join(note), "market")
                elif blocked:
                    route.append("風險檢查擋 %s：%s" % (blocked[0]["symbol"], "；".join(blocked[1])))
                    st["blocked"] = {"symbol": blocked[0]["symbol"], "reasons": blocked[1]}
                else:
                    route.append("狙擊今輪冇開市訊號")
    st["route"] = route
    st["signals"] = [(q["symbol"], note) for q, note, ok, why in signals[:5]]
    st["focus"] = {"scan": focus_scan, "sniper": signals[0][0] if signals else focus_scan, "whale": whale, "blocked": st.get("blocked")}
    st["last_tick"] = time.time()
    if bought is None:
        summary = "今輪唔落單：" + "；".join(route)
        if not st["feed"] or st["feed"][-1]["text"] != summary:
            _log("CHIEF", summary, "market")


def _rules():
    return [
        "掃描：Yahoo 5 日日線，預設 %d 隻流動美股。排名用真實缺口（最新收市對上日收市）。" % len(UNIVERSE),
        "狙擊只喺紐約正規時段（09:30–16:00）先考慮落單：缺口至少 %+.1f%% 而且高過上日收市，或者 15 分鐘開市區間之後有 5 分鐘線收高過區間高位。" % GAP_SIGNAL,
        "風險檢查：股價至少 $%.0f，之前幾日平均成交至少 %s 股。如果新聞標題提到 earnings 就避開嗰隻。冇新聞就唔當作業績日。" % (MIN_PRICE, "{:,.0f}".format(MIN_AVG_VOL)),
        "大戶：今日成交量除以前幾日平均（相對成交量）。公開 Yahoo 圖冇單一錢包。",
        "搜尋：只對焦點股票讀 trader-news 標題。國會崗位讀眾議院公開申報（預設 Pelosi），唔係即時內幕。",
        "風控：起始金額睇 DESK_STOCK_START_USD（預設 $%.0f）。每倉最多 %.0f%% 或 $%.0f。最多 %d 個倉。模擬虧損去到起始 %.0f%% 就停止。" % (
            START_USD, MAX_POSITION_PCT * 100, MAX_ORDER_USD, MAX_POSITIONS, MAX_DAILY_LOSS_PCT * 100),
        "執行：模擬 +%.1f%% 止賺，-%.1f%% 止蝕。紐約 15:50 後用當刻報價決定平倉。可以碎股。%s" % (TP * 100, SL * 100, _costs_note()),
        "唔係正規時段唔會開新模擬倉。模擬倉喺網頁進程入面，瞓着會清走；命令列 runner 先會寫入檔案。",
    ]


def _view(st):
    sess = st.get("session") or session_now()
    equity, missing = _equity(st)
    start = st["start_usd"]
    wins = sum(1 for c in st["closed"] if c["pnl_usd"] > 0)
    closed_n = len(st["closed"])
    rows = st.get("rows") or st.get("quotes") or []
    focus = st.get("focus") or {}
    scan = sorted(rows, key=lambda q: q.get("gap") if q.get("gap") is not None else -999, reverse=True)
    whale = focus.get("whale")
    sniper = focus.get("sniper")
    blocked = focus.get("blocked") or {}
    news = st.get("news") if isinstance(st.get("news"), dict) else {}
    items = news.get("items") or []
    cong = st.get("congress") if isinstance(st.get("congress"), dict) else {}
    filings = cong.get("data") if isinstance(cong.get("data"), list) else []
    upnl = None
    if st["positions"] and not missing:
        upnl = sum(p.get("upnl_usd") or 0 for p in st["positions"])

    def m(label, value, source):
        return {"label": label, "value": value if value not in (None, "") else "暫無數據", "source": source}

    def candles_of(q):
        if not q:
            return None, None
        if q.get("candles_m5") and len(q["candles_m5"]) >= 2:
            return q["candles_m5"], "ohlcv"
        if q.get("candles") and len(q["candles"]) >= 2:
            return q["candles"], "ohlcv"
        return None, None

    def bot(i, name, role, en, status, detail, metrics, node, pnl, note, tone):
        candles, kind = candles_of(node if isinstance(node, dict) else None)
        return {
            "id": i, "name": name, "role": role, "en": en, "status": status, "detail": detail,
            "metrics": metrics, "candles": candles, "candles_kind": kind,
            "paper_pnl": None if pnl is None else round(pnl, 2), "paper_note": note, "tone": tone,
            "trades": [], "bubble": status,
        }

    top = scan[0] if scan else None
    bots = [
        bot("scan", "掃描", "缺口", "SCAN",
            "掃緊 %d 隻" % len(rows) if rows else "Yahoo 列表暫無",
            "最大缺口 %s %s" % (top["symbol"], "%+.2f%%" % top["gap"]) if top and top.get("gap") is not None else "等緊日線",
            [m("數目", len(rows), "Yahoo"), m("最大缺口", None if not top else top.get("symbol"), "Yahoo"),
             m("缺口", None if not top else round(top["gap"], 2) if top.get("gap") is not None else None, "Yahoo")],
            top, None, "呢個崗位只掃描，唔落單", "working" if rows else "idle"),
        bot("sniper", "狙擊", "開市訊號", "SNIPER",
            "有 %d 個訊號" % len(st.get("signals") or []) if st.get("signals") else ("正規時段先狙擊" if sess["phase"] != "開市" else "今輪冇訊號"),
            "、".join(st["signals"][0][1]) if st.get("signals") else sess["phase"],
            [m("訊號", len(st.get("signals") or []), "規則"), m("觀察", None if not sniper else sniper.get("symbol"), "Yahoo")],
            sniper or top, upnl, "未平倉模擬盈虧" if upnl is not None else "未有可計價嘅模擬倉",
            "paper" if st.get("signals") else "idle"),
        bot("whale", "大戶", "相對成交", "WHALE",
            "相對成交最高 %s" % whale["symbol"] if whale and whale.get("rvol") is not None else "相對成交暫無",
            "Yahoo 日線成交，冇單一錢包。",
            [m("相對成交", None if not whale or whale.get("rvol") is None else round(whale["rvol"], 2), "Yahoo"),
             m("今日成交", None if not whale else whale.get("volume"), "Yahoo")],
            whale, None, "呢個崗位只觀察成交量，唔落單", "working" if whale and (whale.get("rvol") or 0) >= RVOL_FLAG else "idle"),
        bot("search", "搜尋", "新聞", "SEARCH",
            "讀到 %d 則" % len(items) if items else "新聞暫無",
            (items[0].get("title") if items else None) or (news.get("error") or news.get("err") or "未讀到標題"),
            [m("標題數", len(items), "Yahoo／新聞工具"), m("焦點", news_sym_of(st), "規則")],
            sniper or top, None, "呢個崗位只讀新聞，唔落單", "working" if items else "idle"),
        bot("rug", "風險", "入場檢查", "RUG",
            ("擋咗 %s" % blocked.get("symbol")) if blocked.get("reasons") else "未見需要擋嘅股票",
            "；".join(blocked.get("reasons") or []) or "股價同平均成交量達標先可以模擬買入。",
            [m("股價門檻", MIN_PRICE, "規則"), m("被擋", blocked.get("symbol"), "規則")],
            (next((q for q in rows if q["symbol"] == blocked.get("symbol")), None) if blocked else top),
            None, "呢個崗位只否決，唔落單", "block" if blocked.get("reasons") else "working"),
        bot("exit", "執行", "止賺止蝕", "EXIT",
            "睇緊 %d 個模擬倉" % len(st["positions"]) if st["positions"] else "未有模擬倉",
            "止賺 +%.1f%%，止蝕 -%.1f%%。%s" % (TP * 100, SL * 100, "而家要收市前平倉" if sess.get("flatten") else "正規時段尾先強制平"),
            [m("持倉", len(st["positions"]), "模擬盤")],
            st["positions"][0] if st["positions"] else top,
            st["realized_by"].get("EXIT"), "已平倉模擬盈虧" if "EXIT" in st["realized_by"] else "未有平倉",
            "paper" if st["positions"] else "idle"),
        bot("risk", "風控", "倉位同上限", "RISK",
            "停止緊" if st["kill"] else "正常",
            "每日模擬虧損上限 %.0f%%。" % (MAX_DAILY_LOSS_PCT * 100),
            [m("權益", None if equity is None else round(equity, 2), "模擬盤"), m("現金", round(st["cash_usd"], 2), "模擬盤")],
            None, st["realized_by"].get("RISK"), "停止平倉嘅模擬盈虧" if "RISK" in st["realized_by"] else "未有因為停止而平倉",
            "block" if st["kill"] else "working"),
        bot("dev", "國會", "公開申報", "DEV",
            filings[0]["name"] if filings else "申報暫無",
            (filings[0].get("filed") if filings else None) or (cong.get("err") or cong.get("error") or "未讀到眾議院索引"),
            [m("最新申報日", filings[0].get("filed") if filings else None, "眾議院"),
             m("今年份數", len(filings) if filings else None, "眾議院")],
            None, None, "申報可以遲 45 日，唔係內幕快訊，亦唔落單", "working" if filings else "idle"),
    ]
    # fix search focus symbol helper used above — defined below if name error
    return {
        "now": _iso(), "paper": True, "market": "stocks", "brand": "SPIDEY 交易台",
        "session": sess,
        "account": {
            "currency": "USD", "start_usd": start, "cash_usd": round(st["cash_usd"], 2),
            "equity_usd": None if equity is None else round(equity, 2),
            "day_pnl_usd": None if equity is None else round(equity - start, 2),
            "wins": wins, "closed": closed_n,
            "win_rate": None if not closed_n else round(wins / float(closed_n), 4),
            "win_rate_text": None if closed_n else "未有已平倉交易",
            "kill": st["kill"], "open": len(st["positions"]), "quote_missing": missing,
        },
        "bots": bots,
        "chief": {"route": st.get("route") or [], "status": sess["phase"]},
        "tape": [{"symbol": q["symbol"], "change_h1": None if q.get("gap") is None else round(q["gap"], 2), "price_usd": q.get("price"), "source": "Yahoo"} for q in scan[:14]],
        "radar": [{"symbol": q["symbol"], "gap": None if q.get("gap") is None else round(q["gap"], 2), "price": q.get("price"), "rvol": None if q.get("rvol") is None else round(q["rvol"], 2)} for q in scan[:8]],
        "positions": [{
            "symbol": p["symbol"], "qty": round(p["qty"], 6), "entry_usd": p.get("entry_usd"),
            "last_usd": p.get("last_usd"), "upnl_usd": None if p.get("upnl_usd") is None else round(p["upnl_usd"], 2),
            "why": p.get("why"), "source": "Yahoo",
        } for p in st["positions"]],
        "feed": list(reversed(st["feed"][-24:])),
        "rules": _rules(),
        "errors": st.get("errors") or [],
        "health": {"yahoo": _cache.get("yahoo_state") or ("正常" if rows else "未查"), "house": "正常" if filings else ("出錯" if cong.get("err") or cong.get("error") else "未查")},
        "market_age_sec": None if not st.get("market_at") else int(time.time() - st["market_at"]),
        "sources": {"market": ["Yahoo", "眾議院 Clerk"], "paper": "本進程模擬"},
        "sol_source": None,
        "costs": {
            "slippage_per_side": SLIPPAGE_PER_SIDE,
            "commission_min_usd": COMMISSION_MIN_USD,
            "commission_rate": COMMISSION_RATE if COMMISSION_RATE > 0 else 0.0,
            "note": _costs_note(),
        },
    }


def news_sym_of(st):
    sig = st.get("signals") or []
    if sig:
        return sig[0][0]
    rows = st.get("rows") or []
    return rows[0]["symbol"] if rows else None


def snapshot():
    with _lock:
        st = _book()
        if time.time() - st["last_tick"] >= TICK_SEC or not st["last_tick"]:
            _tick(st)
        return _view(st)


def log_view():
    with _lock:
        st = _book()
        return {"feed": list(reversed(st["feed"])), "closed": list(reversed(st["closed"][-30:]))}


def set_kill(on):
    with _lock:
        st = _book()
        st["kill"] = bool(on)
        if st["kill"]:
            _mark(st)
            _log("RISK", "手動啟動停止。會用最後 Yahoo 報價嘗試平掉模擬倉。", "paper")
            _flatten(st, "RISK", "手動停止")
        else:
            _log("RISK", "已解除停止。正規時段先可以再按規則開模擬倉。", "paper")
        if not st["last_tick"]:
            _tick(st)
        return _view(st)


def reset():
    global _state
    with _lock:
        _state = _blank()
        _log("CHIEF", "美股模擬倉已重置為 $%.2f。" % _state["start_usd"], "paper")
        _tick(_state)
        return _view(_state)


_PERSIST = ("started_at", "start_usd", "cash_usd", "positions", "closed", "feed", "seq", "kill", "realized_by")


def export_book():
    with _lock:
        st = _book()
        return {k: st.get(k) for k in _PERSIST}


def import_book(data, start=None):
    if not isinstance(data, dict):
        return False
    with _lock:
        st = _book()
        if start is not None and not data:
            st["start_usd"] = float(start)
            st["cash_usd"] = float(start)
        for k in _PERSIST:
            if k in data and data[k] is not None:
                st[k] = data[k]
        for key, default in (("positions", []), ("closed", []), ("feed", []), ("realized_by", {})):
            if not isinstance(st.get(key), type(default)):
                st[key] = default
        return True
