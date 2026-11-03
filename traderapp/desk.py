"""SPIDEY paper desk. Public Solana quotes only. Nothing here can sign or send a transaction."""
import datetime
import json
import threading
import time
import urllib.error
import urllib.request

UA = "trader-app/paper (research; no orders)"
GT = "https://api.geckoterminal.com/api/v2/networks/solana"
DS = "https://api.dexscreener.com"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
SKIP_MINTS = {SOL_MINT, USDC_MINT, USDT_MINT}
SKIP_SYMS = {"SOL", "WSOL", "USDC", "USDT", "USD"}

START_SOL = 10.0
MAX_POSITIONS = 3
MAX_ORDER_SOL = 1.5
MAX_POSITION_PCT = 0.15
MAX_DAILY_LOSS_SOL = 2.0
MIN_LIQ_WATCH = 15000.0
MIN_LIQ_TRADE = 25000.0
TP = 0.25
SL = 0.12
MOMENTUM_H1 = 8.0
FRESH_MINUTES = 180
FRESH_VOL_H1 = 8000.0
FDV_LIQ_MAX = 400.0
TICK_SEC = 22
INFO_CAP = 2
OHLCV_CAP = 3

_lock = threading.Lock()
_http = {}
_info = {}
_candles = {}
_state = None


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _iso(dt=None):
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blank():
    return {
        "started_at": _iso(),
        "cash_sol": START_SOL,
        "positions": [],
        "closed": [],
        "feed": [],
        "seq": 1,
        "kill": False,
        "last_tick": 0.0,
        "sol_usd": None,
        "sol_source": None,
        "pools": [],
        "profiles": {},
        "boosts": {},
        "errors": [],
        "route": [],
        "focus": {},
        "realized_by": {},
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
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    n = _f(v)
    return None if n is None else int(n)


def _sig(v):
    if v is None:
        return None
    return float("%.8g" % v)


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _cached(url, ttl):
    hit = _http.get(url)
    now = time.time()
    if hit and now - hit[0] < (12 if hit[1][0] == "err" else ttl):
        return (None, hit[1][1]) if hit[1][0] == "err" else (hit[1][1], None)
    try:
        data = _get(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as e:
        _http[url] = (now, ("err", e.__class__.__name__))
        return None, e.__class__.__name__
    _http[url] = (now, ("ok", data))
    if len(_http) > 80:
        for k in sorted(_http, key=lambda k: _http[k][0])[:20]:
            _http.pop(k, None)
    return data, None


def _age_min(iso):
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (_now() - dt).total_seconds() / 60.0)


def _sym(raw):
    s = (raw or "").strip().lstrip("$")
    s = " ".join(s.split())
    return s[:18]


def _parse_pools(doc, origin):
    rows = (doc or {}).get("data") or []
    tokens = {}
    for inc in (doc or {}).get("included") or []:
        if inc.get("type") == "token":
            attrs = inc.get("attributes") or {}
            tokens[inc.get("id")] = {
                "address": attrs.get("address"),
                "symbol": _sym(attrs.get("symbol")),
                "name": attrs.get("name") or "",
            }
    out = []
    for raw in rows:
        a = raw.get("attributes") or {}
        rel = raw.get("relationships") or {}

        def _rel(name):
            node = ((rel.get(name) or {}).get("data") or {})
            return tokens.get(node.get("id")) or {}

        base, quote = _rel("base_token"), _rel("quote_token")
        name = a.get("name") or ""
        symbol = base.get("symbol") or _sym(name.split("/")[0] if "/" in name else name)
        mint = base.get("address")
        if not mint or mint in SKIP_MINTS or symbol.upper() in SKIP_SYMS:
            continue
        tx = ((a.get("transactions") or {}).get("h1") or {})
        vol = a.get("volume_usd") or {}
        pc = a.get("price_change_percentage") or {}
        out.append({
            "pool": a.get("address"),
            "symbol": symbol or "—",
            "name": base.get("name") or symbol,
            "mint": mint,
            "quote_symbol": quote.get("symbol"),
            "quote_mint": quote.get("address"),
            "price_usd": _f(a.get("base_token_price_usd")),
            "quote_usd": _f(a.get("quote_token_price_usd")),
            "liq_usd": _f(a.get("reserve_in_usd")),
            "fdv_usd": _f(a.get("fdv_usd")),
            "change_h1": _f(pc.get("h1")),
            "change_m5": _f(pc.get("m5")),
            "buys_h1": _i(tx.get("buys")),
            "sells_h1": _i(tx.get("sells")),
            "buyers_h1": _i(tx.get("buyers")),
            "sellers_h1": _i(tx.get("sellers")),
            "vol_h1": _f(vol.get("h1")),
            "created_at": a.get("pool_created_at"),
            "age_min": _age_min(a.get("pool_created_at")),
            "origin": origin,
            "source": "GeckoTerminal",
        })
    return out


def _sol_from_ds(doc):
    rows = doc if isinstance(doc, list) else ((doc or {}).get("pairs") or [])
    best, best_liq = None, -1.0
    for r in rows:
        quote = (r.get("quoteToken") or {}).get("symbol") or ""
        px = _f(r.get("priceUsd"))
        liq = _f((r.get("liquidity") or {}).get("usd")) or 0.0
        if quote in ("USDC", "USDT") and px and px > 0 and liq >= best_liq:
            best, best_liq = px, liq
    return best


def _index_side(doc, key):
    rows = doc if isinstance(doc, list) else []
    out = {}
    for r in rows:
        if r.get("chainId") != "solana":
            continue
        mint = r.get("tokenAddress")
        if mint:
            out[mint] = r
    return out


def _load_market(st):
    errors = []
    pools = []
    new, err = _cached(GT + "/new_pools?include=base_token,quote_token&page=1", 40)
    if err:
        errors.append("GeckoTerminal 新池：" + err)
    else:
        pools.extend(_parse_pools(new, "新池"))
    trend, err = _cached(GT + "/trending_pools?include=base_token,quote_token&page=1", 40)
    if err:
        errors.append("GeckoTerminal 熱門：" + err)
    else:
        pools.extend(_parse_pools(trend, "熱門"))
    profiles, err = _cached(DS + "/token-profiles/latest/v1", 70)
    if err:
        errors.append("DexScreener 簡介：" + err)
        profiles = []
    boosts, err = _cached(DS + "/token-boosts/latest/v1", 70)
    if err:
        errors.append("DexScreener 推廣：" + err)
        boosts = []
    sol_doc, err = _cached(DS + "/tokens/v1/solana/" + SOL_MINT, 60)
    sol_usd, sol_source = _sol_from_ds(sol_doc), "DexScreener SOL/USDC"
    if err:
        errors.append("DexScreener SOL：" + err)
    if not sol_usd:
        for p in pools:
            if p.get("quote_mint") == SOL_MINT and p.get("quote_usd"):
                sol_usd, sol_source = p["quote_usd"], "GeckoTerminal 池報價"
                break
    by_mint = {}
    for p in pools:
        prev = by_mint.get(p["mint"])
        if prev is None or (p.get("liq_usd") or 0) > (prev.get("liq_usd") or 0):
            by_mint[p["mint"]] = p
    st["pools"] = list(by_mint.values())
    st["profiles"] = _index_side(profiles, "tokenAddress")
    st["boosts"] = _index_side(boosts, "tokenAddress")
    st["sol_usd"] = sol_usd
    st["sol_source"] = sol_source if sol_usd else None
    st["errors"] = errors
    return st["pools"]


def _authority(v):
    if v is None or v == "":
        return "unknown", "暫無數據"
    s = str(v).strip()
    if s.lower() in ("no", "none", "false", "null"):
        return "off", "已放棄"
    if s.lower() in ("yes", "true"):
        return "on", "未放棄"
    return "on", s


def _parse_info(doc):
    a = ((doc or {}).get("data") or {}).get("attributes") or {}
    if not a:
        return None
    holders = a.get("holders") or {}
    honey = a.get("is_honeypot")
    if isinstance(honey, str) and honey.lower() in ("unknown", "null", ""):
        honey = None
    elif isinstance(honey, str):
        honey = honey.lower() in ("yes", "true", "1")
    return {
        "mint_authority": a.get("mint_authority"),
        "freeze_authority": a.get("freeze_authority"),
        "developer_address": a.get("developer_address") or None,
        "developer_holding_percentage": _f(a.get("developer_holding_percentage")),
        "holders_count": _i(holders.get("count")) if isinstance(holders, dict) else None,
        "holders_distribution": _f(holders.get("distribution_percentage")) if isinstance(holders, dict) else None,
        "is_honeypot": honey if isinstance(honey, bool) else None,
        "gt_score": _f(a.get("gt_score")),
        "description": (a.get("description") or "").strip() or None,
        "twitter": a.get("twitter_handle") or None,
        "source": "GeckoTerminal",
    }


def _info_for(mint, budget):
    hit = _info.get(mint)
    if hit and time.time() - hit[0] < 180:
        return hit[1]
    if budget[0] >= INFO_CAP:
        return hit[1] if hit else None
    budget[0] += 1
    try:
        doc = _get(GT + "/tokens/%s/info" % mint)
        parsed = _parse_info(doc)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        parsed = None
    _info[mint] = (time.time(), parsed)
    return parsed


def _ohlcv(pool, budget):
    if not pool:
        return None
    hit = _candles.get(pool)
    if hit and time.time() - hit[0] < 90:
        return hit[1]
    if budget[0] >= OHLCV_CAP:
        return hit[1] if hit else None
    budget[0] += 1
    url = GT + "/pools/%s/ohlcv/minute?aggregate=5&limit=30&currency=usd" % pool
    try:
        doc = _get(url)
        rows = (((doc or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        rows = None
    candles = None
    if rows:
        candles = sorted(({
            "t": int(r[0]), "c": _sig(_f(r[4])),
        } for r in rows if len(r) >= 5 and _f(r[4]) is not None), key=lambda x: x["t"])
    _candles[pool] = (time.time(), candles)
    return candles


def _rug(pool, info):
    reasons, unknown = [], []
    blocked = False
    liq = pool.get("liq_usd")
    if liq is None:
        unknown.append("流動性")
        blocked = True
    elif liq < MIN_LIQ_TRADE:
        reasons.append("流動性 $%s 低過交易門檻 $%s" % (_fmt_int(liq), _fmt_int(MIN_LIQ_TRADE)))
        blocked = True
    fdv = pool.get("fdv_usd")
    if fdv and liq and liq > 0 and fdv / liq > FDV_LIQ_MAX:
        reasons.append("全稀釋市值／流動性 %.0f 倍，高過 %s" % (fdv / liq, _fmt_int(FDV_LIQ_MAX)))
        blocked = True
    if info is None:
        unknown.append("鑄幣權、凍結權、項目方")
        blocked = True
    else:
        for label, raw in (("鑄幣權", info.get("mint_authority")), ("凍結權", info.get("freeze_authority"))):
            kind, _shown = _authority(raw)
            if kind == "unknown":
                unknown.append(label)
                blocked = True
            elif kind == "on":
                reasons.append(label + "未放棄")
                blocked = True
        if info.get("is_honeypot") is True:
            reasons.append("資料標記為蜜罐")
            blocked = True
    return {"blocked": blocked, "reasons": reasons, "unknown": unknown, "info": info}


def _sniper_ok(pool):
    chg, vol, age = pool.get("change_h1"), pool.get("vol_h1") or 0, pool.get("age_min")
    buys, sells = pool.get("buys_h1"), pool.get("sells_h1")
    flow_ok = True if buys is None or sells is None else buys >= sells
    momentum = chg is not None and chg >= MOMENTUM_H1
    fresh = age is not None and age <= FRESH_MINUTES and vol >= FRESH_VOL_H1 and (chg is None or chg >= 0)
    why = []
    if momentum:
        why.append("1 小時升 %.2f%%" % chg)
    if fresh:
        why.append("新池 %.0f 分鐘、1 小時成交 $%s" % (age, _fmt_int(vol)))
    if not flow_ok:
        why.append("1 小時賣出多過買入，唔符合")
    return bool((momentum or fresh) and flow_ok and (pool.get("liq_usd") or 0) >= MIN_LIQ_TRADE), why


def _mark(st):
    sol = st.get("sol_usd")
    by_pool = {p["pool"]: p for p in st["pools"] if p.get("pool")}
    by_mint = {p["mint"]: p for p in st["pools"]}
    for pos in st["positions"]:
        live = by_pool.get(pos["pool"]) or by_mint.get(pos["mint"])
        pos["last_usd"] = live.get("price_usd") if live else None
        pos["last_source"] = live.get("source") if live else None
        if pos["last_usd"] and sol:
            pos["value_sol"] = pos["qty"] * pos["last_usd"] / sol
            pos["upnl_sol"] = pos["value_sol"] - pos["cost_sol"]
        else:
            pos["value_sol"] = None
            pos["upnl_sol"] = None


def _close(st, pos, reason, bot):
    sol = st.get("sol_usd")
    px = pos.get("last_usd")
    if not sol or not px or px <= 0:
        _log(bot, "%s 未平倉：而家冇可用報價，唔會估價。" % pos["symbol"], "paper")
        return False
    proceeds = pos["qty"] * px / sol
    pnl = proceeds - pos["cost_sol"]
    st["cash_sol"] += proceeds
    st["realized_by"][bot] = st["realized_by"].get(bot, 0.0) + pnl
    st["closed"].append({
        "symbol": pos["symbol"], "mint": pos["mint"], "pnl_sol": pnl, "reason": reason,
        "exit_usd": px, "bot": bot, "ts": _iso(),
    })
    _log(bot, "模擬平倉 %s（%s），報價 $%s，模擬盈虧 %+.6f SOL。呢個係模擬成交。" % (
        pos["symbol"], reason, _fmt_px(px), pnl), "paper")
    return True


def _flatten(st, bot, reason):
    keep = []
    for pos in list(st["positions"]):
        if not _close(st, pos, reason, bot):
            keep.append(pos)
    st["positions"] = keep


def _risk_size(st):
    sol = st.get("sol_usd")
    equity, missing = _equity(st)
    if st["kill"]:
        return None, "風控停止緊，唔開新倉"
    if missing or equity is None or not sol:
        return None, "有倉未有報價或者 SOL 報價暫無，唔開新倉"
    loss = max(0.0, START_SOL - equity)
    room = MAX_DAILY_LOSS_SOL - loss
    if room <= 0.05:
        st["kill"] = True
        _log("RISK", "模擬權益低過每日上限，已啟動停止，之後唔開新倉。", "paper")
        _flatten(st, "RISK", "觸發每日虧損上限")
        return None, "已觸發每日虧損上限"
    budget = room / SL
    size = min(MAX_ORDER_SOL, equity * MAX_POSITION_PCT, budget, st["cash_sol"])
    if size < 0.05:
        return None, "可用模擬 SOL 或者剩餘虧損額度唔夠一張細單"
    return size, None


def _equity(st):
    sol = st.get("sol_usd")
    missing = False
    mtm = 0.0
    for pos in st["positions"]:
        if pos.get("value_sol") is None or not sol:
            missing = True
        else:
            mtm += pos["value_sol"]
    if missing:
        return None, True
    return st["cash_sol"] + mtm, False


def _fmt_int(v):
    return "{:,.0f}".format(v)


def _fmt_px(v):
    if v is None:
        return "—"
    return "%.8g" % v


def _tick(st):
    pools = _load_market(st)
    _mark(st)
    route = []
    info_budget, candle_budget = [0], [0]
    held = {p["mint"] for p in st["positions"]}
    traded = held | {c["mint"] for c in st["closed"]}

    # exits first, at the live quote
    still = []
    for pos in st["positions"]:
        px, entry = pos.get("last_usd"), pos.get("entry_usd")
        if not px or not entry:
            still.append(pos)
            continue
        ret = px / entry - 1.0
        pos["ret"] = ret
        if ret >= TP:
            if not _close(st, pos, "到止賺 +%.0f%%" % (TP * 100), "EXIT"):
                still.append(pos)
        elif ret <= -SL:
            if not _close(st, pos, "到止蝕 -%.0f%%" % (SL * 100), "EXIT"):
                still.append(pos)
        else:
            still.append(pos)
    st["positions"] = still
    route.append("執行睇完 %d 個模擬倉" % len(still))

    newest = sorted([p for p in pools if p.get("origin") == "新池"], key=lambda p: p.get("age_min") if p.get("age_min") is not None else 1e12)
    trending = [p for p in pools if p.get("origin") == "熱門"]
    signals = []
    for p in pools:
        ok, why = _sniper_ok(p)
        if ok:
            signals.append((p, why))
    signals.sort(key=lambda x: (x[0].get("liq_usd") or 0), reverse=True)

    focus = {
        "scan": newest[0] if newest else None,
        "search": trending[0] if trending else None,
        "whale": max(pools, key=lambda p: (p.get("buyers_h1") is not None, p.get("buyers_h1") or -1, p.get("buys_h1") or -1)) if pools else None,
        "sniper": signals[0][0] if signals else None,
    }

    size, risk_block = _risk_size(st)
    bought = None
    if st["kill"]:
        route.append("風控停止緊")
    elif len(st["positions"]) >= MAX_POSITIONS:
        route.append("模擬倉已滿 %d" % MAX_POSITIONS)
    elif size is None:
        route.append(risk_block or "風控未批")
    else:
        route.append("風控可批最多 %.2f SOL" % size)
        pick = None
        checked = None
        for pool, why in signals:
            if pool["mint"] in traded or pool["mint"] in {p["mint"] for p in st["positions"]}:
                continue
            if not pool.get("price_usd") or pool["price_usd"] <= 0:
                continue
            info = _info_for(pool["mint"], info_budget)
            checked = (pool, why, _rug(pool, info))
            if checked[2]["blocked"]:
                continue
            pick = checked
            break
        if checked and checked[2]["blocked"] and pick is None:
            route.append("防Rug 擋下 %s：%s" % (checked[0]["symbol"], "；".join(checked[2]["reasons"] + ["暫無：" + "、".join(checked[2]["unknown"])] if checked[2]["unknown"] else checked[2]["reasons"])))
            focus["rug"] = checked[0]
            focus["rug_result"] = checked[2]
        elif pick is None:
            route.append("狙擊今輪冇同時過防Rug 嘅訊號" if signals else "狙擊今輪冇入市訊號")
            if signals:
                focus["rug"] = signals[0][0]
        else:
            pool, why, rug = pick
            focus["rug"] = pool
            focus["rug_result"] = rug
            focus["dev"] = pool
            if not st.get("sol_usd"):
                route.append("SOL 報價暫無，唔換算，唔落單")
            else:
                cost = min(size, st["cash_sol"])
                qty = cost * st["sol_usd"] / pool["price_usd"]
                st["cash_sol"] -= cost
                st["positions"].append({
                    "id": st["seq"], "symbol": pool["symbol"], "mint": pool["mint"], "pool": pool["pool"],
                    "qty": qty, "entry_usd": pool["price_usd"], "cost_sol": cost, "opened_at": _iso(),
                    "last_usd": pool["price_usd"], "value_sol": cost, "upnl_sol": 0.0, "ret": 0.0,
                    "why": "、".join(why), "source": pool["source"],
                })
                st["seq"] += 1
                bought = pool["symbol"]
                route.append("模擬買入 %s %.2f SOL" % (pool["symbol"], cost))
                _log("CHIEF", "路徑通過。模擬買入 %s，用 %.4f SOL，報價 $%s（%s）。唔係真單。" % (
                    pool["symbol"], cost, _fmt_px(pool["price_usd"]), pool["source"]), "paper")
                _log("SNIPER", "入市訊號：%s。" % "、".join(why), "market")

    if "dev" not in focus:
        focus["dev"] = (newest or trending or [None])[0]
    focus["exit"] = st["positions"][0] if st["positions"] else None
    # candles for a few focus pools only
    want = []
    for key in ("sniper", "scan", "search", "whale", "exit", "dev", "rug"):
        node = focus.get(key)
        pool = node.get("pool") if isinstance(node, dict) else None
        if pool and pool not in want:
            want.append(pool)
    charts = {pool: _ohlcv(pool, candle_budget) for pool in want[:OHLCV_CAP]}
    st["charts"] = charts
    st["focus"] = focus
    st["signals"] = [(p["symbol"], why) for p, why in signals[:5]]
    st["route"] = route
    st["last_tick"] = time.time()
    if bought is None:
        summary = "今輪唔落單：" + "；".join(route)
        if not st["feed"] or st["feed"][-1]["text"] != summary:
            _log("CHIEF", summary, "market")


def _pub_pool(p):
    if not p:
        return None
    return {
        "symbol": p.get("symbol"), "mint": p.get("mint"), "pool": p.get("pool"),
        "price_usd": _sig(p.get("price_usd")), "liq_usd": _sig(p.get("liq_usd")),
        "fdv_usd": _sig(p.get("fdv_usd")), "change_h1": _sig(p.get("change_h1")),
        "change_m5": _sig(p.get("change_m5")), "vol_h1": _sig(p.get("vol_h1")),
        "buys_h1": p.get("buys_h1"), "sells_h1": p.get("sells_h1"),
        "buyers_h1": p.get("buyers_h1"), "sellers_h1": p.get("sellers_h1"),
        "age_min": None if p.get("age_min") is None else round(p["age_min"], 1),
        "origin": p.get("origin"), "source": p.get("source"),
        "quote_symbol": p.get("quote_symbol"),
    }


def _rules():
    return [
        "掃描：每 %d 秒讀 GeckoTerminal Solana 新池同熱門池，加上 DexScreener 最新簡介同推廣。只保留有合約地址嘅代幣，跳過 SOL／USDC／USDT。" % TICK_SEC,
        "狙擊先要滿足其中一項：1 小時升幅至少 %.0f%%，或者池齡少過 %d 分鐘而且 1 小時成交至少 $%s；同時 1 小時買入宗數唔少過賣出（有呢兩個數先比較）。" % (MOMENTUM_H1, FRESH_MINUTES, _fmt_int(FRESH_VOL_H1)),
        "防Rug 先至可以模擬買入：流動性至少 $%s；全稀釋市值／流動性唔高過 %.0f 倍；GeckoTerminal 代幣資料入面鑄幣權同凍結權要係已放棄。蜜罐標記為真就擋。任何一項暫無就唔估，亦唔落單。" % (_fmt_int(MIN_LIQ_TRADE), FDV_LIQ_MAX),
        "大戶只顯示公開嘅買入宗數、買家數同成交額。公開 API 冇錢包地址，所以錢包一欄係暫無數據。",
        "項目方只顯示 GeckoTerminal 嘅 developer_address 同持倉百分比。冇呢兩個欄就寫暫無數據。",
        "風控：起始 %.0f SOL。每倉最多 %.0f%% 權益或者 %.1f SOL，邊個細用邊個。最多 %d 個倉。止蝕 %.0f%%。模擬虧損去到 %.1f SOL 就停止並用最後報價平倉。" % (
            START_SOL, MAX_POSITION_PCT * 100, MAX_ORDER_SOL, MAX_POSITIONS, SL * 100, MAX_DAILY_LOSS_SOL),
        "執行：模擬升到 +%.0f%% 止賺，跌到 -%.0f%% 止蝕。成交價等於當刻公開報價，冇計滑價同手續費。" % (TP * 100, SL * 100),
        "主管只係把上面幾個崗位嘅結果串埋，自己唔另計一個價。模擬倉存在呢個進程記憶體，伺服器瞓着或者重啟會清走。",
    ]


def _view(st):
    sol = st.get("sol_usd")
    equity, missing = _equity(st)
    loss = None if equity is None else max(0.0, START_SOL - equity)
    wins = sum(1 for c in st["closed"] if c["pnl_sol"] > 0)
    losses = sum(1 for c in st["closed"] if c["pnl_sol"] < 0)
    closed_n = len(st["closed"])
    upnl = None
    if st["positions"] and not missing:
        upnl = sum(p.get("upnl_sol") or 0 for p in st["positions"])
    realized = sum(c["pnl_sol"] for c in st["closed"]) if st["closed"] else 0.0
    focus = st.get("focus") or {}
    charts = st.get("charts") or {}

    def chart_for(node):
        pool = node.get("pool") if isinstance(node, dict) else None
        return charts.get(pool) if pool in charts else None

    def bot(i, name, role, en, status, detail, metrics, node, pnl, pnl_note, tone):
        return {
            "id": i, "name": name, "role": role, "en": en, "status": status, "detail": detail,
            "metrics": metrics, "focus": _pub_pool(node) if isinstance(node, dict) else None,
            "candles": chart_for(node), "paper_pnl_sol": None if pnl is None else round(pnl, 6),
            "paper_note": pnl_note, "tone": tone,
        }

    scan = [p for p in st["pools"] if p.get("origin") == "新池"]
    scan.sort(key=lambda p: p.get("age_min") if p.get("age_min") is not None else 1e12)
    trend = [p for p in st["pools"] if p.get("origin") == "熱門"]
    whale = focus.get("whale")
    sniper = focus.get("sniper")
    rug_p, rug_r = focus.get("rug"), focus.get("rug_result")
    dev_p = focus.get("dev")
    dev_info = _info.get(dev_p["mint"])[1] if dev_p and dev_p.get("mint") in _info else None
    exit_p = st["positions"][0] if st["positions"] else None

    def m(label, value, source):
        return {"label": label, "value": value if value not in (None, "") else "暫無數據", "source": source}

    bots = [
        bot("scan", "掃描", "新池", "SCAN",
            "讀緊 GeckoTerminal 新池" if scan else "新池列表暫無",
            "今輪新池 %d 個。" % len(scan),
            [m("新池數目", len(scan), "GeckoTerminal"),
             m("最新", scan[0]["symbol"] if scan else None, "GeckoTerminal"),
             m("池齡（分鐘）", None if not scan or scan[0].get("age_min") is None else round(scan[0]["age_min"], 1), "GeckoTerminal")],
            scan[0] if scan else None, None, "呢個崗位只掃描，唔落單", "working" if scan else "idle"),
        bot("sniper", "狙擊", "入市訊號", "SNIPER",
            "有 %d 個訊號" % len(st.get("signals") or []) if st.get("signals") else "今輪冇入市訊號",
            "、".join(st["signals"][0][1]) if st.get("signals") else "未有代幣同時滿足升幅或者新池成交，同埋買賣宗數。",
            [m("訊號數目", len(st.get("signals") or []), "規則"),
             m("首位", sniper["symbol"] if sniper else None, "GeckoTerminal")],
            sniper, upnl, "未平倉模擬盈虧（計入狙擊開嘅倉）" if upnl is not None else "未有可計價嘅模擬倉",
            "paper" if st.get("signals") else "idle"),
        bot("whale", "大戶", "成交流向", "WHALE",
            "睇緊 %s 嘅公開成交" % whale["symbol"] if whale else "暫無成交宗數",
            "公開 API 冇錢包地址。",
            [m("1 小時買入", None if not whale else whale.get("buys_h1"), "GeckoTerminal"),
             m("1 小時賣出", None if not whale else whale.get("sells_h1"), "GeckoTerminal"),
             m("1 小時買家", None if not whale else whale.get("buyers_h1"), "GeckoTerminal"),
             m("錢包", "暫無數據", "公開 API 冇提供")],
            whale, None, "呢個崗位只觀察成交流向，唔落單", "working" if whale else "idle"),
        bot("search", "搜尋", "熱門", "SEARCH",
            "熱門池 %d 個" % len(trend) if trend else "熱門列表暫無",
            "次序跟 GeckoTerminal 熱門榜。DexScreener 推廣量係推廣分數，唔係價格。",
            [m("榜首", trend[0]["symbol"] if trend else None, "GeckoTerminal"),
             m("1 小時升跌", None if not trend else trend[0].get("change_h1"), "GeckoTerminal"),
             m("推廣代幣", len(st.get("boosts") or {}), "DexScreener")],
            trend[0] if trend else None, None, "呢個崗位只搜尋，唔落單", "working" if trend else "idle"),
        bot("rug", "防Rug", "風險檢查", "RUG",
            "擋落單" if rug_r and rug_r.get("blocked") else ("資料齊，未擋" if rug_r else "今輪未需要擋"),
            "；".join((rug_r or {}).get("reasons") or []) or ("暫無：" + "、".join(rug_r.get("unknown") or []) if rug_r and rug_r.get("unknown") else "未有需要寫低嘅風險。"),
            [m("流動性", None if not rug_p else rug_p.get("liq_usd"), "GeckoTerminal"),
             m("鑄幣權", None if not (rug_r and rug_r.get("info")) else _authority(rug_r["info"].get("mint_authority"))[1], "GeckoTerminal"),
             m("凍結權", None if not (rug_r and rug_r.get("info")) else _authority(rug_r["info"].get("freeze_authority"))[1], "GeckoTerminal")],
            rug_p, None, "呢個崗位只否決，唔落單", "block" if rug_r and rug_r.get("blocked") else "working"),
        bot("exit", "執行", "止賺止蝕", "EXIT",
            "睇緊 %d 個模擬倉" % len(st["positions"]) if st["positions"] else "未有模擬倉",
            "止賺 +%.0f%%，止蝕 -%.0f%%，用當刻報價。" % (TP * 100, SL * 100),
            [m("持倉", len(st["positions"]), "模擬盤"),
             m("最近回報", None if not exit_p or exit_p.get("ret") is None else round(exit_p["ret"] * 100, 2), "模擬盤")],
            exit_p if isinstance(exit_p, dict) else None,
            st["realized_by"].get("EXIT"), "已平倉模擬盈虧（止賺／止蝕）" if "EXIT" in st["realized_by"] else "未有平倉",
            "paper" if st["positions"] else "idle"),
        bot("risk", "風控", "倉位同上限", "RISK",
            "停止緊" if st["kill"] else "正常",
            "每日模擬虧損上限 %.1f SOL。" % MAX_DAILY_LOSS_SOL,
            [m("權益 SOL", None if equity is None else round(equity, 4), "模擬盤"),
             m("已用虧損額", None if loss is None else round(loss, 4), "模擬盤"),
             m("現金 SOL", round(st["cash_sol"], 4), "模擬盤")],
            None, st["realized_by"].get("RISK"),
            "停止平倉嘅模擬盈虧" if "RISK" in st["realized_by"] else "未有因為停止而平倉",
            "block" if st["kill"] else "working"),
        bot("dev", "項目方", "開發者錢包", "DEV",
            "有開發者地址" if dev_info and dev_info.get("developer_address") else "開發者地址暫無",
            (dev_info or {}).get("description") or "只顯示 GeckoTerminal 公開欄位。",
            [m("地址", None if not dev_info else dev_info.get("developer_address"), "GeckoTerminal"),
             m("持倉百分比", None if not dev_info else dev_info.get("developer_holding_percentage"), "GeckoTerminal"),
             m("持有人數", None if not dev_info else dev_info.get("holders_count"), "GeckoTerminal")],
            dev_p, None, "呢個崗位只追蹤公開欄位，唔落單", "working" if dev_info and dev_info.get("developer_address") else "idle"),
    ]
    tape = []
    for p in trend[:14]:
        tape.append({"symbol": p["symbol"], "mint": p.get("mint"), "change_h1": _sig(p.get("change_h1")), "price_usd": _sig(p.get("price_usd")), "source": "GeckoTerminal"})
    seen = {}
    for t in tape:
        seen[t["symbol"]] = seen.get(t["symbol"], 0) + 1
    for t in tape:
        if seen[t["symbol"]] > 1 and t.get("mint"):
            t["symbol"] = "%s·%s" % (t["symbol"], t["mint"][:4])
    radar = []
    for p in scan[:8]:
        radar.append(_pub_pool(p))
    return {
        "now": _iso(),
        "paper": True,
        "brand": "SPIDEY 交易台",
        "sol_usd": _sig(sol),
        "sol_source": st.get("sol_source"),
        "account": {
            "start_sol": START_SOL,
            "cash_sol": round(st["cash_sol"], 6),
            "equity_sol": None if equity is None else round(equity, 6),
            "day_pnl_sol": None if equity is None else round(equity - START_SOL, 6),
            "wins": wins, "losses": losses, "closed": closed_n,
            "win_rate": None if not closed_n else round(wins / closed_n, 4),
            "kill": st["kill"],
            "open": len(st["positions"]),
            "max_open": MAX_POSITIONS,
            "max_daily_loss_sol": MAX_DAILY_LOSS_SOL,
            "quote_missing": missing,
        },
        "bots": bots,
        "chief": {"route": st.get("route") or [], "status": "停止" if st["kill"] else "值班"},
        "tape": tape,
        "radar": radar,
        "positions": [{
            "symbol": p["symbol"], "mint": p["mint"], "qty": _sig(p["qty"]),
            "entry_usd": _sig(p["entry_usd"]), "last_usd": _sig(p.get("last_usd")),
            "cost_sol": round(p["cost_sol"], 6), "upnl_sol": None if p.get("upnl_sol") is None else round(p["upnl_sol"], 6),
            "ret_pct": None if p.get("ret") is None else round(p["ret"] * 100, 2),
            "why": p.get("why"), "source": p.get("source"), "opened_at": p.get("opened_at"),
        } for p in st["positions"]],
        "feed": list(reversed(st["feed"][-24:])),
        "rules": _rules(),
        "errors": st.get("errors") or [],
        "sources": {"market": ["GeckoTerminal", "DexScreener"], "paper": "本進程模擬"},
        "resets_on_sleep": True,
        "realized_sol": round(realized, 6) if st["closed"] else 0.0,
    }


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
            _log("RISK", "手動啟動停止。會用最後公開報價嘗試平掉模擬倉。", "paper")
            _flatten(st, "RISK", "手動停止")
        else:
            _log("RISK", "已解除停止。之後可以再按規則開模擬倉。", "paper")
        if not st["last_tick"]:
            _tick(st)
        return _view(st)


def reset():
    global _state
    with _lock:
        _state = _blank()
        _log("CHIEF", "模擬倉已重置為 %.0f SOL。之前嘅模擬單清走咗。" % START_SOL, "paper")
        _tick(_state)
        return _view(_state)
