"""SPIDEY paper desk. Public Solana quotes only. Nothing here can sign or send a transaction."""
import datetime
import json
import os
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
# 0.5 SOL on a 10 SOL book. configure() uses the same ratio.
DAILY_LOSS_OF_START = 0.05
MAX_DAILY_LOSS_SOL = DAILY_LOSS_OF_START * START_SOL
MIN_LIQ_WATCH = 15000.0
MIN_LIQ_TRADE = 50000.0
TP = 0.05
SL = 0.06
MOMENTUM_H1 = 8.0
MOMENTUM_H1_MAX = 20.0
FRESH_MINUTES = 180
FRESH_VOL_H1 = 8000.0
FDV_LIQ_MAX = 400.0
TICK_SEC = 30
OHLCV_CAP = 2
LIST_TTL = 100
RPC_URL = (os.environ.get("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com").strip()
TOP10_BLOCK = 80.0

_lock = threading.Lock()
_cache = {}
_sec = {}
_state = None
_phase = {"n": 0}
_BUCKETS = {
    "gt": {"cap": 18, "tokens": 18.0, "rate": 18 / 60.0, "ts": time.time(), "state": "未查"},
    "ds": {"cap": 24, "tokens": 24.0, "rate": 24 / 60.0, "ts": time.time(), "state": "未查"},
    "rpc": {"cap": 8, "tokens": 8.0, "rate": 8 / 60.0, "ts": time.time(), "state": "未查"},
}


def configure(start_sol=None, **_ignored):
    """Point the paper book at a starting size. Loss cap stays 5% of that size.

    paper50 calls this. It does not reset open positions.
    """
    global START_SOL, MAX_DAILY_LOSS_SOL
    if start_sol is not None:
        START_SOL = float(start_sol)
    MAX_DAILY_LOSS_SOL = DAILY_LOSS_OF_START * START_SOL
    return {"start_sol": START_SOL, "max_daily_loss_sol": MAX_DAILY_LOSS_SOL}


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


def _take(source):
    b = _BUCKETS[source]
    now = time.time()
    b["tokens"] = min(b["cap"], b["tokens"] + (now - b["ts"]) * b["rate"])
    b["ts"] = now
    if b["tokens"] < 1:
        b["state"] = "限速中"
        return False
    b["tokens"] -= 1
    return True


def _key(url, body):
    if body is None:
        return url
    return url + "\n" + json.dumps(body, sort_keys=True, separators=(",", ":"))


def _http_get(url, source, body=None, timeout=12, retry=True):
    if not _take(source):
        return None, "限速中"
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _BUCKETS[source]["state"] = "正常"
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            _BUCKETS[source]["state"] = "限速中"
            _BUCKETS[source]["tokens"] = 0
            if retry:
                time.sleep(1.2)
                _BUCKETS[source]["tokens"] = max(_BUCKETS[source]["tokens"], 1)
                return _http_get(url, source, body=body, timeout=timeout, retry=False)
            return None, "HTTP 429"
        _BUCKETS[source]["state"] = "出錯"
        return None, "HTTP %s" % e.code
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        _BUCKETS[source]["state"] = "出錯"
        return None, e.__class__.__name__


def _cached(url, ttl, source, body=None):
    key = _key(url, body)
    now = time.time()
    hit = _cache.get(key)
    if hit and hit.get("data") is not None and now - hit["t"] < ttl:
        return hit["data"], None, int(now - hit["t"])
    data, err = _http_get(url, source, body=body)
    if data is not None:
        _cache[key] = {"t": now, "data": data, "error": None}
        if len(_cache) > 140:
            for k in sorted(_cache, key=lambda k: _cache[k]["t"])[:40]:
                _cache.pop(k, None)
        return data, None, 0
    if hit and hit.get("data") is not None:
        return hit["data"], err, int(now - hit["t"])
    return None, err, None


def _peek(url, body=None):
    hit = _cache.get(_key(url, body))
    if not hit or hit.get("data") is None:
        return None, None
    return hit["data"], int(time.time() - hit["t"])


def _fresh(url, ttl, body=None):
    hit = _cache.get(_key(url, body))
    return bool(hit and hit.get("data") is not None and time.time() - hit["t"] < ttl)


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
            "change_h6": _f(pc.get("h6")),
            "change_h24": _f(pc.get("h24")),
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


def _parse_ds_pairs(doc, origin):
    rows = doc if isinstance(doc, list) else ((doc or {}).get("pairs") or [])
    best = {}
    now_ms = time.time() * 1000
    for r in rows:
        base = r.get("baseToken") or {}
        mint = base.get("address")
        symbol = _sym(base.get("symbol"))
        if not mint or mint in SKIP_MINTS or symbol.upper() in SKIP_SYMS:
            continue
        pc = r.get("priceChange") or {}
        tx = (r.get("txns") or {}).get("h1") or {}
        vol = r.get("volume") or {}
        created = _f(r.get("pairCreatedAt"))
        age = None if created is None else max(0.0, (now_ms - created) / 60000.0)
        pool = {
            "pool": r.get("pairAddress"),
            "symbol": symbol or "—",
            "name": base.get("name") or symbol,
            "mint": mint,
            "quote_symbol": (r.get("quoteToken") or {}).get("symbol"),
            "quote_mint": (r.get("quoteToken") or {}).get("address"),
            "price_usd": _f(r.get("priceUsd")),
            "quote_usd": None,
            "liq_usd": _f((r.get("liquidity") or {}).get("usd")),
            "fdv_usd": _f(r.get("fdv")),
            "change_h1": _f(pc.get("h1")),
            "change_m5": _f(pc.get("m5")),
            "change_h6": _f(pc.get("h6")),
            "change_h24": _f(pc.get("h24")),
            "buys_h1": _i(tx.get("buys")),
            "sells_h1": _i(tx.get("sells")),
            "buyers_h1": None,
            "sellers_h1": None,
            "vol_h1": _f(vol.get("h1")) if isinstance(vol, dict) else None,
            "created_at": None,
            "age_min": age,
            "origin": origin,
            "source": "DexScreener",
        }
        prev = best.get(mint)
        if prev is None or (pool.get("liq_usd") or 0) > (prev.get("liq_usd") or 0):
            best[mint] = pool
    return list(best.values())


def _sol_mints(doc):
    rows = doc if isinstance(doc, list) else []
    out = []
    for r in rows:
        if r.get("chainId") != "solana":
            continue
        mint = r.get("tokenAddress")
        if mint and mint not in SKIP_MINTS and mint not in out:
            out.append(mint)
    return out


def _ds_pools(boosts, profiles):
    boost_mints = _sol_mints(boosts)[:15]
    profile_mints = [m for m in _sol_mints(profiles) if m not in boost_mints][:10]
    mints = boost_mints + profile_mints
    if not mints:
        return []
    doc, _err, _age = _cached(DS + "/tokens/v1/solana/" + ",".join(mints[:20]), 70, "ds")
    pairs = _parse_ds_pairs(doc, "熱門")
    boost_set = set(boost_mints)
    for p in pairs:
        if p["mint"] not in boost_set and p.get("age_min") is not None and p["age_min"] <= 360:
            p["origin"] = "新池"
        elif p["mint"] not in boost_set:
            p["origin"] = "熱門"
    return pairs


def _load_market(st):
    errors = []
    phase = _phase["n"]
    _phase["n"] += 1
    new_url = GT + "/new_pools?include=base_token,quote_token&page=1"
    tr_url = GT + "/trending_pools?include=base_token,quote_token&page=1"
    new_stale = not _fresh(new_url, LIST_TTL)
    tr_stale = not _fresh(tr_url, LIST_TTL)
    fetch_new = new_stale and (not tr_stale or phase % 2 == 0)
    fetch_tr = tr_stale and (not new_stale or phase % 2 == 1)
    if fetch_new:
        new, nerr, _nage = _cached(new_url, LIST_TTL, "gt")
    else:
        new, _nage = _peek(new_url)
        nerr = None
    if fetch_tr:
        trend, terr, _tage = _cached(tr_url, LIST_TTL, "gt")
    else:
        trend, _tage = _peek(tr_url)
        terr = None
    pools = []
    if new:
        pools.extend(_parse_pools(new, "新池"))
    elif nerr:
        errors.append("GeckoTerminal 新池：" + nerr)
    gt_trend = _parse_pools(trend, "熱門") if trend else []
    if gt_trend:
        pools.extend(gt_trend)
    elif terr and not trend:
        errors.append("GeckoTerminal 熱門：" + terr)
    boosts, _berr, _ = _cached(DS + "/token-boosts/top/v1", 120, "ds")
    profiles, _perr, _ = _cached(DS + "/token-profiles/latest/v1", 120, "ds")
    if not gt_trend or not any(p.get("origin") == "新池" for p in pools):
        for p in _ds_pools(boosts, profiles):
            if not gt_trend and p.get("origin") != "新池":
                p["origin"] = "熱門"
            pools.append(p)
    sol_doc, serr, _ = _cached(DS + "/tokens/v1/solana/" + SOL_MINT, 90, "ds")
    sol_usd, sol_source = _sol_from_ds(sol_doc), "DexScreener SOL/USDC"
    if serr and not sol_usd:
        errors.append("DexScreener SOL：" + serr)
    if not sol_usd:
        for p in pools:
            if p.get("quote_mint") == SOL_MINT and p.get("quote_usd"):
                sol_usd, sol_source = p["quote_usd"], "GeckoTerminal 池報價"
                break
    by_mint = {}
    for p in pools:
        prev = by_mint.get(p["mint"])
        rank = 1 if p.get("origin") == "熱門" else 0
        prev_rank = 1 if prev and prev.get("origin") == "熱門" else 0
        if prev is None or (p.get("liq_usd") or 0) > (prev.get("liq_usd") or 0) + 1 or (rank > prev_rank and (p.get("liq_usd") or 0) >= (prev.get("liq_usd") or 0) * 0.5):
            if prev and prev.get("origin") == "新池" and p.get("origin") == "熱門":
                p = dict(p, origin="熱門")
            by_mint[p["mint"]] = p
    merged = list(by_mint.values())
    if merged:
        st["pools"] = merged
        st["market_at"] = time.time()
    elif st.get("pools"):
        errors.append("今輪冇新行情，沿用上一份")
    st["profiles"] = _index_side(profiles or [], "tokenAddress")
    st["boosts"] = _index_side(boosts or [], "tokenAddress")
    if sol_usd:
        st["sol_usd"] = sol_usd
        st["sol_source"] = sol_source
    st["errors"] = errors
    return st.get("pools") or []


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


def _rpc(method, params, ttl=600):
    return _cached(RPC_URL, ttl, "rpc", body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def _short(addr):
    if not addr or len(addr) < 10:
        return addr or ""
    return addr[:4] + "…" + addr[-4:]


def _creator_rpc(mint):
    sigs, err, _age = _rpc("getSignaturesForAddress", [mint, {"limit": 1000}])
    rows = (sigs or {}).get("result") if isinstance(sigs, dict) else None
    if rows is None:
        return None, err or "攞唔到簽名"
    if len(rows) >= 1000:
        return None, "簽名多過 1000 筆，呢一頁搵唔到最早嘅創建交易"
    if not rows:
        return None, "呢個鑄幣地址冇簽名"
    sig = rows[-1].get("signature")
    tx, err2, _age = _rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
    result = (tx or {}).get("result") if isinstance(tx, dict) else None
    if not result:
        return None, err2 or "攞唔到創建交易"
    keys = (((result.get("transaction") or {}).get("message") or {}).get("accountKeys") or [])
    payer = None
    for k in keys:
        if isinstance(k, dict) and k.get("signer"):
            payer = k.get("pubkey")
            break
        if isinstance(k, str):
            payer = k
            break
    if not payer:
        return None, "創建交易睇唔到付款人"
    accs, err3, _age = _rpc("getTokenAccountsByOwner", [payer, {"mint": mint}, {"encoding": "jsonParsed"}])
    tokens = None
    vals = ((accs or {}).get("result") or {}).get("value") if isinstance(accs, dict) else None
    if isinstance(vals, list):
        total = 0.0
        for v in vals:
            ui = ((((v.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}).get("tokenAmount") or {}
            n = _f(ui.get("uiAmount"))
            if n is None and ui.get("amount") is not None:
                dec = _i(ui.get("decimals")) or 0
                raw = _f(ui.get("amount"))
                n = None if raw is None else raw / (10 ** dec)
            if n:
                total += n
        tokens = total
    return {"address": payer, "tokens": tokens, "holding_reason": None if tokens is not None else (err3 or "攞唔到持倉")}, None


def _security(mint):
    hit = _sec.get(mint)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    out = {
        "mint_state": "unknown", "mint_text": "暫無數據", "mint_reason": None,
        "freeze_state": "unknown", "freeze_text": "暫無數據", "freeze_reason": None,
        "top10_pct": None, "top10_reason": None,
        "developer_address": None, "developer_holding_percentage": None,
        "dev_tokens": None, "dev_source": None, "dev_reason": None,
        "holders_count": None, "description": None, "is_honeypot": None,
        "source": "Solana RPC",
    }
    acct, err, _age = _rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    info = ((((acct or {}).get("result") or {}).get("value") or {}).get("data") or {}).get("parsed") or {}
    info = info.get("info") if isinstance(info, dict) else None
    if not info:
        out["mint_reason"] = err or "RPC 冇鑄幣帳戶"
        out["freeze_reason"] = out["mint_reason"]
    else:
        mint_auth = info.get("mintAuthority")
        freeze_auth = info.get("freezeAuthority")
        out["mint_state"] = "off" if mint_auth in (None, "null") else "on"
        out["mint_text"] = "已放棄" if out["mint_state"] == "off" else str(mint_auth)
        out["freeze_state"] = "off" if freeze_auth in (None, "null") else "on"
        out["freeze_text"] = "已放棄" if out["freeze_state"] == "off" else str(freeze_auth)
        supply = _f(info.get("supply"))
        decimals = _i(info.get("decimals")) or 0
        largest, err2, _age = _rpc("getTokenLargestAccounts", [mint])
        vals = ((largest or {}).get("result") or {}).get("value") if isinstance(largest, dict) else None
        if not isinstance(vals, list):
            out["top10_reason"] = err2 or "冇最大戶口"
        elif not supply:
            out["top10_reason"] = "供應量為 0"
        else:
            total, ok = 0.0, True
            for v in vals[:10]:
                ui = _f(v.get("uiAmount"))
                if ui is None:
                    raw = _f(v.get("amount"))
                    ui = None if raw is None else raw / (10 ** decimals)
                if ui is None:
                    ok = False
                    break
                total += ui
            whole = supply / (10 ** decimals)
            if ok and whole > 0:
                out["top10_pct"] = total / whole * 100.0
            else:
                out["top10_reason"] = "戶口數量唔齊"
    gdoc, gerr, _age = _cached(GT + "/tokens/%s/info" % mint, 600, "gt")
    g = _parse_info(gdoc) if gdoc else None
    if g:
        out["is_honeypot"] = g.get("is_honeypot")
        out["holders_count"] = g.get("holders_count")
        out["description"] = g.get("description")
        if g.get("developer_address"):
            out["developer_address"] = g["developer_address"]
            out["developer_holding_percentage"] = g.get("developer_holding_percentage")
            out["dev_source"] = "GeckoTerminal"
    if not out.get("developer_address"):
        if out.get("mint_reason"):
            out["dev_reason"] = out["mint_reason"]
            dev, why = None, out["mint_reason"]
        else:
            dev, why = _creator_rpc(mint)
        if dev and dev.get("address"):
            out["developer_address"] = dev["address"]
            out["dev_tokens"] = dev.get("tokens")
            out["dev_source"] = "Solana RPC"
            if dev.get("holding_reason") and out.get("dev_tokens") is None:
                out["dev_reason"] = dev["holding_reason"]
        else:
            out["dev_reason"] = why or gerr or "公開資料冇開發者地址"
    if out.get("top10_pct") is None and "429" in str(out.get("top10_reason") or ""):
        _sec[mint] = (time.time() - 540, out)
    else:
        _sec[mint] = (time.time(), out)
    return out


def _ohlcv(pool):
    if not pool:
        return None
    url = GT + "/pools/%s/ohlcv/minute?aggregate=5&limit=30&currency=usd" % pool
    doc, _err, _age = _cached(url, 120, "gt")
    rows = (((doc or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    if not rows:
        return None
    candles = sorted((
        {"t": int(r[0]), "c": _sig(_f(r[4])), "kind": "ohlcv"}
        for r in rows if len(r) >= 5 and _f(r[4]) is not None
    ), key=lambda x: x["t"])
    return candles or None


def _change_candles(pool):
    if not pool or not pool.get("price_usd"):
        return None
    px = pool["price_usd"]
    now = int(time.time())
    pts = []
    for key, secs in (("change_h24", 86400), ("change_h6", 21600), ("change_h1", 3600), ("change_m5", 300)):
        ch = pool.get(key)
        if ch is None:
            continue
        denom = 1 + ch / 100.0
        if denom <= 0:
            continue
        pts.append({"t": now - secs, "c": _sig(px / denom), "kind": "change"})
    pts.append({"t": now, "c": _sig(px), "kind": "change"})
    return pts if len(pts) >= 2 else None


def _whale_trades(pool_addr):
    if not pool_addr:
        return [], "未有池地址"
    url = "https://api.geckoterminal.com/api/v2/networks/solana/pools/%s/trades" % pool_addr
    doc, err, _age = _cached(url, 75, "gt")
    parsed = []
    for raw in (doc or {}).get("data") or []:
        a = raw.get("attributes") or {}
        vol = _f(a.get("volume_in_usd"))
        wallet = a.get("tx_from_address")
        if not wallet or vol is None:
            continue
        parsed.append({
            "kind": "買" if a.get("kind") == "buy" else "賣" if a.get("kind") == "sell" else (a.get("kind") or ""),
            "usd": _sig(vol),
            "wallet": wallet,
            "wallet_short": _short(wallet),
            "url": "https://solscan.io/account/" + wallet,
        })
    big = [t for t in parsed if t["usd"] >= 500]
    if big:
        big.sort(key=lambda t: t["usd"], reverse=True)
        return big[:5], None
    if parsed:
        parsed.sort(key=lambda t: t["usd"], reverse=True)
        top = parsed[:5]
        return top, "最近未見 $500 以上，顯示最大 %d 筆。" % len(top)
    if err and doc:
        return [], "成交用緊舊資料都係空（%s）" % err
    if err:
        return [], "成交暫時攞唔到（%s）" % err
    return [], "呢個池暫時冇成交紀錄"


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
    if not info:
        unknown.append("鑄幣權")
        blocked = True
    else:
        if info.get("mint_state") == "on":
            reasons.append("鑄幣權未放棄")
            blocked = True
        elif info.get("mint_state") != "off":
            unknown.append("鑄幣權" + (("：" + info["mint_reason"]) if info.get("mint_reason") else ""))
            blocked = True
        if info.get("freeze_state") == "on":
            reasons.append("凍結權未放棄")
            blocked = True
        elif info.get("freeze_state") != "off":
            unknown.append("凍結權" + (("：" + info["freeze_reason"]) if info.get("freeze_reason") else ""))
            blocked = True
        top = info.get("top10_pct")
        if top is not None and top > TOP10_BLOCK:
            reasons.append("十大持倉 %.1f%% 高過 %.0f%%" % (top, TOP10_BLOCK))
            blocked = True
        if info.get("is_honeypot") is True:
            reasons.append("資料標記為蜜罐")
            blocked = True
    return {"blocked": blocked, "reasons": reasons, "unknown": unknown, "info": info}


def _sniper_ok(pool):
    chg, vol, age = pool.get("change_h1"), pool.get("vol_h1") or 0, pool.get("age_min")
    buys, sells = pool.get("buys_h1"), pool.get("sells_h1")
    flow_ok = True if buys is None or sells is None else buys >= sells
    momentum = chg is not None and MOMENTUM_H1 <= chg <= MOMENTUM_H1_MAX
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
    if room <= 0:
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
        fresh_checks = 0
        for pool, why in signals:
            if pool["mint"] in traded or pool["mint"] in {p["mint"] for p in st["positions"]}:
                continue
            if not pool.get("price_usd") or pool["price_usd"] <= 0:
                continue
            cached = _sec.get(pool["mint"])
            if not (cached and time.time() - cached[0] < 600):
                if fresh_checks >= 1:
                    break
                fresh_checks += 1
            info = _security(pool["mint"])
            checked = (pool, why, _rug(pool, info))
            focus["rug"] = pool
            focus["rug_result"] = checked[2]
            if checked[2]["blocked"]:
                continue
            pick = checked
            break
        if checked and checked[2]["blocked"] and pick is None:
            route.append("防Rug 擋下 %s：%s" % (checked[0]["symbol"], "；".join(checked[2]["reasons"] + ["暫無：" + "、".join(checked[2]["unknown"])] if checked[2]["unknown"] else checked[2]["reasons"])))
        elif pick is None:
            route.append("狙擊今輪冇同時過防Rug 嘅訊號" if signals else "狙擊今輪冇入市訊號")
        else:
            pool, why, rug = pick
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

    rug_target = focus.get("rug") or (signals[0][0] if signals else None) or (newest[0] if newest else None) or (trending[0] if trending else None)
    if rug_target and "rug_result" not in focus:
        focus["rug"] = rug_target
        focus["rug_result"] = _rug(rug_target, _security(rug_target["mint"]))
    if "dev" not in focus:
        focus["dev"] = rug_target or (newest[0] if newest else None) or (trending[0] if trending else None)
    focus["exit"] = st["positions"][0] if st["positions"] else None
    whale = focus.get("whale")
    trades, trades_note = _whale_trades(whale.get("pool") if isinstance(whale, dict) else None)
    st["whale_trades"] = trades
    st["whale_note"] = trades_note
    want = []
    for key in ("sniper", "exit", "search", "scan"):
        node = focus.get(key)
        pool = node.get("pool") if isinstance(node, dict) else None
        if pool and pool not in want:
            want.append(pool)
    charts = {}
    for pool in want[:OHLCV_CAP]:
        rows = _ohlcv(pool)
        if rows:
            charts[pool] = rows
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
        "掃描：大約每 %d 秒更新。GeckoTerminal 新池同熱門池會錯開請求；熱門失敗就用 DexScreener 推廣榜同最新簡介，再讀對應池嘅價、流動性同升跌。上一份成功嘅行情會保留。跳過 SOL／USDC／USDT。" % TICK_SEC,
        "狙擊先要滿足其中一項：1 小時升幅至少 %.0f%% 而且唔超過 %.0f%%（唔追升得太急），或者池齡少過 %d 分鐘而且 1 小時成交至少 $%s；同時 1 小時買入宗數唔少過賣出（有呢兩個數先比較）。新池呢條路唔受 %.0f%% 上限限制。" % (MOMENTUM_H1, MOMENTUM_H1_MAX, FRESH_MINUTES, _fmt_int(FRESH_VOL_H1), MOMENTUM_H1_MAX),
        "防Rug 先至可以模擬買入：流動性至少 $%s；全稀釋市值／流動性唔高過 %.0f 倍；Solana RPC 見到鑄幣權同凍結權係已放棄（null）。十大持倉高過 %.0f%% 就擋。蜜罐標記為真就擋。鑄幣權或凍結權未知就唔落單；十大持倉未知只會寫明原因，唔當安全。" % (_fmt_int(MIN_LIQ_TRADE), FDV_LIQ_MAX, TOP10_BLOCK),
        "大戶讀 GeckoTerminal 該池最近成交，顯示 $500 以上或者最大幾筆，錢包連去 Solscan。冇成交就寫原因。",
        "項目方先用 GeckoTerminal 嘅 developer_address。冇嘅話，用鑄幣地址最早一筆簽名（一頁少過 1000 筆先算最早）嘅付款人，再讀佢而家持有幾多。簽名太多或者 RPC 失敗會寫原因。",
        "風控：起始 %.4g SOL。每倉最多 %.0f%% 權益或者 %.1f SOL，邊個細用邊個。最多 %d 個倉。止蝕 %.0f%%。模擬虧損去到 %.4g SOL 就停止並用最後報價平倉。" % (
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
        if not isinstance(node, dict):
            return None, None
        pool_id = node.get("pool")
        rows = charts.get(pool_id) if pool_id in charts else None
        if rows and len(rows) >= 2:
            return rows, "ohlcv"
        src = node if node.get("price_usd") and (node.get("change_h1") is not None or node.get("change_m5") is not None) else None
        if src is None:
            for p in st["pools"]:
                if (pool_id and p.get("pool") == pool_id) or (node.get("mint") and p.get("mint") == node.get("mint")):
                    src = p
                    break
        alt = _change_candles(src)
        return (alt, "change") if alt else (None, None)

    def bot(i, name, role, en, status, detail, metrics, node, pnl, pnl_note, tone, trades=None, trades_note=None):
        candles, kind = chart_for(node)
        return {
            "id": i, "name": name, "role": role, "en": en, "status": status, "detail": detail,
            "metrics": metrics, "focus": _pub_pool(node) if isinstance(node, dict) else None,
            "candles": candles, "candles_kind": kind,
            "paper_pnl_sol": None if pnl is None else round(pnl, 6),
            "paper_note": pnl_note, "tone": tone,
            "trades": trades or [], "trades_note": trades_note,
        }

    scan = [p for p in st["pools"] if p.get("origin") == "新池"]
    scan.sort(key=lambda p: p.get("age_min") if p.get("age_min") is not None else 1e12)
    trend = [p for p in st["pools"] if p.get("origin") == "熱門"]
    whale = focus.get("whale")
    sniper = focus.get("sniper")
    rug_p, rug_r = focus.get("rug"), focus.get("rug_result")
    dev_p = focus.get("dev")
    dev_info = _sec[dev_p["mint"]][1] if dev_p and dev_p.get("mint") in _sec else None
    watch = sniper or (max(st["pools"], key=lambda p: p.get("liq_usd") or 0) if st["pools"] else None)
    rug_info = (rug_r or {}).get("info") or {}
    exit_p = st["positions"][0] if st["positions"] else None

    def m(label, value, source):
        return {"label": label, "value": value if value not in (None, "") else "暫無數據", "source": source}

    bots = [
        bot("scan", "掃描", "新池", "SCAN",
            "讀緊 %s 新池" % (scan[0]["source"] if scan else "公開來源") if scan else "新池列表暫無",
            "今輪新池 %d 個。" % len(scan),
            [m("新池數目", len(scan), scan[0]["source"] if scan else ""),
             m("最新", scan[0]["symbol"] if scan else None, scan[0]["source"] if scan else ""),
             m("池齡（分鐘）", None if not scan or scan[0].get("age_min") is None else round(scan[0]["age_min"], 1), scan[0]["source"] if scan else "")],
            scan[0] if scan else None, None, "呢個崗位只掃描，唔落單", "working" if scan else "idle"),
        bot("sniper", "狙擊", "入市訊號", "SNIPER",
            "有 %d 個訊號" % len(st.get("signals") or []) if st.get("signals") else "今輪冇入市訊號",
            "、".join(st["signals"][0][1]) if st.get("signals") else "未有代幣同時滿足升幅或者新池成交，同埋買賣宗數。",
            [m("訊號數目", len(st.get("signals") or []), "規則"),
             m("首位" if sniper else "觀察", watch["symbol"] if watch else None, (watch or {}).get("source"))],
            sniper or watch, upnl, "未平倉模擬盈虧（計入狙擊開嘅倉）" if upnl is not None else "未有可計價嘅模擬倉",
            "paper" if st.get("signals") else "idle"),
        bot("whale", "大戶", "成交流向", "WHALE",
            "睇緊 %s 嘅成交錢包" % whale["symbol"] if whale else "暫無成交",
            st.get("whale_note") or "錢包來自 GeckoTerminal 最近成交。",
            [m("1 小時買入", None if not whale else whale.get("buys_h1"), whale.get("source") if whale else ""),
             m("1 小時賣出", None if not whale else whale.get("sells_h1"), whale.get("source") if whale else ""),
             m("1 小時買家", None if not whale else whale.get("buyers_h1"), whale.get("source") if whale else "")],
            whale, None, "呢個崗位只觀察成交，唔落單", "working" if whale else "idle",
            trades=st.get("whale_trades") or [], trades_note=st.get("whale_note")),
        bot("search", "搜尋", "熱門", "SEARCH",
            "熱門池 %d 個" % len(trend) if trend else "熱門列表暫無",
            "次序跟 %s。" % (trend[0]["source"] if trend else "公開榜") + " DexScreener 推廣量係推廣分數，唔係價格。",
            [m("榜首", trend[0]["symbol"] if trend else None, trend[0]["source"] if trend else ""),
             m("1 小時升跌", None if not trend else trend[0].get("change_h1"), trend[0]["source"] if trend else ""),
             m("推廣代幣", len(st.get("boosts") or {}), "DexScreener")],
            trend[0] if trend else None, None, "呢個崗位只搜尋，唔落單", "working" if trend else "idle"),
        bot("rug", "防Rug", "風險檢查", "RUG",
            ("擋 %s" % rug_p["symbol"]) if rug_r and rug_r.get("blocked") and rug_p else (
                ("%s %s" % (rug_p["symbol"], "資料齊，未擋" if rug_info.get("top10_pct") is not None else "鑄幣權已查，十大持倉未齊")) if rug_p and rug_r else "今輪未查"),
            "；".join((rug_r or {}).get("reasons") or []) or ("暫未齊：" + "、".join(rug_r.get("unknown") or []) if rug_r and rug_r.get("unknown") else "未有需要寫低嘅風險。"),
            [m("流動性", None if not rug_p else rug_p.get("liq_usd"), (rug_p or {}).get("source") or ""),
             m("鑄幣權", rug_info.get("mint_text") if rug_info.get("mint_state") in ("on", "off") else ("暫無數據（%s）" % rug_info["mint_reason"] if rug_info.get("mint_reason") else None), "Solana RPC"),
             m("凍結權", rug_info.get("freeze_text") if rug_info.get("freeze_state") in ("on", "off") else ("暫無數據（%s）" % rug_info["freeze_reason"] if rug_info.get("freeze_reason") else None), "Solana RPC"),
             m("十大持倉", ("%.1f%%" % rug_info["top10_pct"]) if rug_info.get("top10_pct") is not None else ("暫無數據（%s）" % rug_info["top10_reason"] if rug_info.get("top10_reason") else None), "Solana RPC")],
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
            "每日模擬虧損上限 %.4g SOL。" % MAX_DAILY_LOSS_SOL,
            [m("權益 SOL", None if equity is None else round(equity, 4), "模擬盤"),
             m("已用虧損額", None if loss is None else round(loss, 4), "模擬盤"),
             m("現金 SOL", round(st["cash_sol"], 4), "模擬盤")],
            None, st["realized_by"].get("RISK"),
            "停止平倉嘅模擬盈虧" if "RISK" in st["realized_by"] else "未有因為停止而平倉",
            "block" if st["kill"] else "working"),
        bot("dev", "項目方", "開發者錢包", "DEV",
            "有開發者地址" if dev_info and dev_info.get("developer_address") else "開發者地址未確定",
            (dev_info or {}).get("dev_reason") or (dev_info or {}).get("description") or "先睇 GeckoTerminal，冇先至用鑄幣地址最早一筆簽名。",
            [m("地址", dev_info.get("developer_address") if dev_info and dev_info.get("developer_address") else ("暫無數據（%s）" % dev_info["dev_reason"] if dev_info and dev_info.get("dev_reason") else None), (dev_info or {}).get("dev_source") or ""),
             m("持倉", ("%s%%" % round(dev_info["developer_holding_percentage"], 2)) if dev_info and dev_info.get("developer_holding_percentage") is not None else (None if not dev_info or dev_info.get("dev_tokens") is None else "%.4g 枚" % dev_info["dev_tokens"]), (dev_info or {}).get("dev_source") or ""),
             m("持有人數", None if not dev_info else dev_info.get("holders_count"), "GeckoTerminal")],
            dev_p, None, "呢個崗位只追蹤公開欄位，唔落單", "working" if dev_info and dev_info.get("developer_address") else "idle"),
    ]
    tape_rows = trend or [p for p in st["pools"] if p.get("change_h1") is not None]
    tape = []
    for p in tape_rows[:14]:
        tape.append({"symbol": p["symbol"], "mint": p.get("mint"), "change_h1": _sig(p.get("change_h1")), "price_usd": _sig(p.get("price_usd")), "source": p.get("source")})
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
        "market": "crypto",
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
            "win_rate_text": None if closed_n else "未有已平倉交易",
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
        "health": {
            "geckoterminal": _BUCKETS["gt"]["state"],
            "dexscreener": _BUCKETS["ds"]["state"],
            "solana_rpc": _BUCKETS["rpc"]["state"],
        },
        "market_age_sec": None if not st.get("market_at") else int(time.time() - st["market_at"]),
        "sources": {"market": ["GeckoTerminal", "DexScreener", "Solana RPC"], "paper": "本進程模擬"},
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


_PERSIST = ("started_at", "cash_sol", "positions", "closed", "feed", "seq", "kill", "realized_by")


def export_book():
    with _lock:
        st = _book()
        return {k: st.get(k) for k in _PERSIST}


def import_book(data):
    if not isinstance(data, dict):
        return False
    with _lock:
        st = _book()
        for k in _PERSIST:
            if k in data and data[k] is not None:
                st[k] = data[k]
        if not isinstance(st.get("realized_by"), dict):
            st["realized_by"] = {}
        if not isinstance(st.get("positions"), list):
            st["positions"] = []
        if not isinstance(st.get("closed"), list):
            st["closed"] = []
        if not isinstance(st.get("feed"), list):
            st["feed"] = []
        return True
