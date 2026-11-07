"""Latest $50 paper books pushed from the always-on machine. No trading here."""
import json
import os
import threading
from datetime import datetime, timedelta, timezone

BOOKS = ("crypto", "stocks")
LEADERBOARD = "leaderboard"
LEADERBOARD_STOCKS = "leaderboard_stocks"
LEADERBOARD_METHODS = "leaderboard_methods"
LEADERBOARD_GOLD = "leaderboard_gold"
LEADERBOARD_BTC = "leaderboard_btc"
LEADERBOARD_QUANT_V2 = "leaderboard_quant_v2"
# Footer on /paper/v2. Kept here so the page and the API share one string.
QUANT_V2_DISCLAIMER = "模擬盤，唔係真錢，唔係投資建議。QUANT_V2 係平行 stub；舊紙盤照跑。"
# Smoke seed from the 2026-11-07 QUANT_V2 demo fill. Shown until a push arrives.
# Paper only. This dict is not a live book and is never written onto the old books.
QUANT_V2_SEED = {
    "track": "QUANT_V2",
    "symbol": "BTCUSDT",
    "venue": "Binance",
    "interval": "1h",
    "bars": 48,
    "equity_usd": 99.99,
    "cash_usd": 89.99,
    "score": None,
    "direction": "LONG",
    "last_price": 75938.69,
    "updated_hkt": "2026-11-07 20:39:37 HKT",
    "stub": True,
    "fills": [
        {
            "ts_hkt": "2026-11-07 20:39:37 HKT",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "notional_usd": 10.0,
            "price": 75938.69,
            "qty": 0.00013168,
            "kind": "smoke",
        }
    ],
}
MAX_BODY = 2 * 1024 * 1024
_lock = threading.Lock()
_mem = {
    "crypto": None,
    "stocks": None,
    "leaderboard": None,
    "leaderboard_stocks": None,
    "leaderboard_methods": None,
    "leaderboard_gold": None,
    "leaderboard_btc": None,
    "leaderboard_quant_v2": None,
}


def store_dir():
    return os.environ.get("PAPER_STORE_DIR") or "/tmp/paper_store"


def reset_memory():
    with _lock:
        _mem["crypto"] = None
        _mem["stocks"] = None
        _mem["leaderboard"] = None
        _mem["leaderboard_stocks"] = None
        _mem["leaderboard_methods"] = None
        _mem["leaderboard_gold"] = None
        _mem["leaderboard_btc"] = None
        _mem["leaderboard_quant_v2"] = None


def _path(book):
    return os.path.join(store_dir(), book + ".json")


def _parse_object(raw):
    if raw is None:
        raw = b""
    if len(raw) > MAX_BODY:
        return None, ({"error": "內容太大"}, 400)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, TypeError):
        return None, ({"error": "JSON 唔啱"}, 400)
    if not isinstance(data, dict):
        return None, ({"error": "JSON 唔啱"}, 400)
    return data, None


def _commit(key, payload):
    with _lock:
        _mem[key] = payload
        try:
            os.makedirs(store_dir(), exist_ok=True)
            dest = _path(key)
            tmp = dest + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp, dest)
        except OSError:
            return {"error": "寫唔到檔"}, 500
    return None


def ingest(book, raw):
    if book not in BOOKS:
        return {"error": "書名唔啱"}, 400
    data, err = _parse_object(raw)
    if err:
        return err
    payload = {
        "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "book": book,
        "data": data,
    }
    failed = _commit(book, payload)
    if failed:
        return failed
    return {"ok": True, "book": book, "received_at": payload["received_at"]}, 200


def ingest_leaderboard(raw, key=None):
    """Overwrite one demo leaderboard. Paper only. Crypto stays on `leaderboard`."""
    key = key or LEADERBOARD
    if key not in (LEADERBOARD, LEADERBOARD_STOCKS, LEADERBOARD_METHODS, LEADERBOARD_GOLD, LEADERBOARD_BTC):
        return {"error": "書名唔啱"}, 400
    data, err = _parse_object(raw)
    if err:
        return err
    books = data.get("books", [])
    if not isinstance(books, list):
        return {"error": "books 要係陣列"}, 400
    payload = {
        "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "book": key,
        "data": data,
    }
    failed = _commit(key, payload)
    if failed:
        return failed
    return {"ok": True, "book": key, "received_at": payload["received_at"], "books": len(books)}, 200


def _first(sources, names):
    for src in sources:
        if not isinstance(src, dict):
            continue
        for name in names:
            if name in src and src[name] not in (None, ""):
                return src[name]
    return None


def _quant_fills(data, state):
    for src in (data, state):
        if isinstance(src, dict) and isinstance(src.get("fills"), list):
            return src["fills"]
    for src in (data, state):
        if isinstance(src, dict) and isinstance(src.get("trades"), list):
            return src["trades"]
    return []


def _quant_has_signal(data):
    if not isinstance(data, dict):
        return False
    for key in ("equity_usd", "equity", "cash_usd", "cash", "fills", "trades", "state"):
        val = data.get(key)
        if val not in (None, "", [], {}):
            return True
    return False


def normalize_quant_v2(data):
    """Flatten a demo_book push (flat or state/fills/config) into the v2 page shape."""
    data = data if isinstance(data, dict) else {}
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    sources = (data, state, config)
    fills = []
    for row in _quant_fills(data, state):
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol") or row.get("pair") or _first(sources, ("symbol", "pair")) or "BTCUSDT"
        fills.append({
            "ts_hkt": row.get("ts_hkt") or row.get("time_hkt") or row.get("time") or row.get("ts") or "",
            "symbol": symbol,
            "side": row.get("side") or row.get("action") or "",
            "notional_usd": _num(row.get("notional_usd") if row.get("notional_usd") is not None else row.get("notional") if row.get("notional") is not None else row.get("usd")),
            "price": _num(row.get("price") if row.get("price") is not None else row.get("fill_price") if row.get("fill_price") is not None else row.get("px")),
            "qty": _num(row.get("qty") if row.get("qty") is not None else row.get("quantity")),
            "kind": row.get("kind") or row.get("tag") or "",
        })
    direction = _first(sources, ("direction", "side_bias"))
    if not direction and fills:
        side = str(fills[-1].get("side") or "").upper()
        if side == "BUY":
            direction = "LONG"
        elif side == "SELL":
            direction = "SHORT"
    last_price = _num(_first(sources, ("last_price", "mark", "price")))
    if last_price is None:
        for row in reversed(fills):
            if row.get("price") is not None:
                last_price = row["price"]
                break
    score = _first(sources, ("score", "forecast_score"))
    if score is not None:
        as_num = _num(score)
        score = as_num if as_num is not None else score
    stub = _first(sources, ("stub",))
    return {
        "track": _first(sources, ("track", "matrix_id")) or "QUANT_V2",
        "symbol": _first(sources, ("symbol", "pair")) or "BTCUSDT",
        "venue": _first(sources, ("venue",)) or "",
        "interval": _first(sources, ("interval", "timeframe")) or "",
        "bars": _first(sources, ("bars",)),
        "equity_usd": _num(_first(sources, ("equity_usd", "equity"))),
        "cash_usd": _num(_first(sources, ("cash_usd", "cash"))),
        "score": score,
        "direction": direction or "",
        "last_price": last_price,
        "updated_hkt": _first(sources, ("updated_hkt", "generated_hkt", "asof_hkt")) or "",
        "stub": True if stub is None else bool(stub),
        "fills": fills,
    }


def ingest_quant_v2(raw):
    """Overwrite the QUANT_V2 paper book only. Does not touch crypto, stocks, or gold."""
    data, err = _parse_object(raw)
    if err:
        return err
    if not _quant_has_signal(data):
        return {"error": "QUANT_V2 內容唔夠"}, 400
    view = normalize_quant_v2(data)
    payload = {
        "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "book": LEADERBOARD_QUANT_V2,
        "data": data,
    }
    failed = _commit(LEADERBOARD_QUANT_V2, payload)
    if failed:
        return failed
    return {
        "ok": True,
        "book": LEADERBOARD_QUANT_V2,
        "received_at": payload["received_at"],
        "symbol": view["symbol"],
        "fills": len(view["fills"]),
    }, 200


def _utc_to_hkt(stamp):
    try:
        dt = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ""
    return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S HKT")


def quant_v2_view():
    """Page model. Seed until the first QUANT_V2 push. Always labelled stub."""
    with _lock:
        if _mem.get(LEADERBOARD_QUANT_V2) is None:
            _mem[LEADERBOARD_QUANT_V2] = _read_disk(LEADERBOARD_QUANT_V2)
        raw = _mem.get(LEADERBOARD_QUANT_V2)
    if not raw or not isinstance(raw.get("data"), dict):
        return {
            "source": "seed",
            "received_at": None,
            "stub": True,
            "disclaimer": QUANT_V2_DISCLAIMER,
            "book": normalize_quant_v2(QUANT_V2_SEED),
        }
    book = normalize_quant_v2(raw.get("data") or {})
    book["stub"] = True
    if not book.get("updated_hkt"):
        book["updated_hkt"] = _utc_to_hkt(raw.get("received_at"))
    return {
        "source": "ingest",
        "received_at": raw.get("received_at"),
        "stub": True,
        "disclaimer": QUANT_V2_DISCLAIMER,
        "book": book,
    }


def _read_disk(book):
    path = _path(book)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def _public(item):
    if not item:
        return None
    data = dict(item.get("data") or {})
    text = data.get("report_text")
    if isinstance(text, str) and len(text) > 12000:
        data["report_text"] = text[:12000] + "…"
    return {"received_at": item.get("received_at"), "data": data}


def _num(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def show_book(book):
    """Account strip for /desk. Uses the ingested main book when one has arrived."""
    item = load_all().get(book)
    if not item or not isinstance(item.get("data"), dict):
        return None
    data = item["data"]
    cfg = data.get("config") if isinstance(data.get("config"), dict) else {}
    start = _num(cfg.get("start_usd"))
    if start is None:
        start = _num(data.get("start_usd"))
    if start is None:
        start = 100.0
    sol = _num(data.get("sol_usd")) or _num(cfg.get("sol_usd_at_start"))
    eq_sol = _num(data.get("equity_sol"))
    eq_usd = _num(data.get("equity_usd"))
    cash_sol = _num(data.get("cash_sol"))
    cash_usd = _num(data.get("cash_usd"))
    positions = data.get("positions") if isinstance(data.get("positions"), list) else []
    if eq_usd is None and eq_sol is not None and sol:
        eq_usd = eq_sol * sol
    if eq_usd is None and cash_usd is not None:
        pos_usd, known = 0.0, True
        for p in positions:
            if not isinstance(p, dict):
                continue
            if _num(p.get("value_usd")) is not None:
                pos_usd += _num(p.get("value_usd"))
            elif _num(p.get("cost_usd")) is not None and _num(p.get("upnl_usd")) is not None:
                pos_usd += _num(p.get("cost_usd")) + _num(p.get("upnl_usd"))
            elif _num(p.get("cost_usd")) is not None:
                pos_usd += _num(p.get("cost_usd"))
            else:
                known = False
        if known:
            eq_usd = cash_usd + pos_usd
    if eq_usd is None and sol and cash_sol is not None:
        pos_sol, known = 0.0, True
        for p in positions:
            if not isinstance(p, dict):
                continue
            if _num(p.get("value_sol")) is not None:
                pos_sol += _num(p.get("value_sol"))
            elif _num(p.get("qty")) is not None and _num(p.get("last_usd")) is not None:
                pos_sol += _num(p.get("qty")) * _num(p.get("last_usd")) / sol
            elif _num(p.get("cost_sol")) is not None:
                pos_sol += _num(p.get("cost_sol"))
            else:
                known = False
        if known:
            eq_sol = cash_sol + pos_sol
            eq_usd = eq_sol * sol
    if eq_usd is None:
        return None
    start_sol = _num(cfg.get("start_sol"))
    if start_sol is None and sol and sol > 0:
        start_sol = start / sol
    if isinstance(data.get("closed"), list):
        closed_n = len(data["closed"])
    else:
        closed_n = int(_num(data.get("closed_n")) or 0)
    wins = int(_num(data.get("wins")) or 0)
    pub = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        entry = p.get("entry_usd")
        if entry is None:
            entry = p.get("entry")
        last = p.get("last_usd")
        if last is None:
            last = p.get("mark_usd")
        if last is None:
            last = p.get("mark") if p.get("mark") is not None else p.get("price")
        qty = p.get("qty")
        if qty is None:
            qty = p.get("size") if p.get("size") is not None else p.get("shares")
        upnl_sol = p.get("upnl_sol")
        upnl_usd = p.get("upnl_usd")
        if _num(upnl_usd) is None and _num(upnl_sol) is not None and sol:
            upnl_usd = round(_num(upnl_sol) * float(sol), 2)
        value_usd = p.get("value_usd")
        value_sol = p.get("value_sol")
        if qty is None and _num(value_usd) is not None and _num(last):
            qty = _num(value_usd) / _num(last)
        elif qty is None and _num(value_sol) is not None and _num(last) and sol:
            qty = _num(value_sol) * float(sol) / _num(last)
        pub.append({
            "symbol": p.get("symbol"), "mint": p.get("mint"), "qty": qty,
            "entry_usd": entry, "last_usd": last,
            "upnl_sol": upnl_sol, "upnl_usd": upnl_usd,
            "why": p.get("why") or p.get("reason"),
            "cost_sol": p.get("cost_sol"), "value_sol": value_sol,
            "value_usd": value_usd, "cost_usd": p.get("cost_usd"),
        })
    return {
        "mirror": True,
        "label": cfg.get("label") or "",
        "start_usd": start,
        "start_sol": None if start_sol is None else round(start_sol, 6),
        "equity_usd": round(eq_usd, 2),
        "day_pnl_usd": round(eq_usd - start, 2),
        "equity_sol": None if eq_sol is None else round(eq_sol, 6),
        "cash_sol": cash_sol,
        "cash_usd": cash_usd,
        "sol_usd": sol,
        "positions": pub,
        "wins": wins,
        "closed": closed_n,
        "open": len(pub),
    }


def load_leaderboard():
    with _lock:
        if _mem.get(LEADERBOARD) is None:
            _mem[LEADERBOARD] = _read_disk(LEADERBOARD)
        return _public(_mem.get(LEADERBOARD))


def load_all():
    with _lock:
        keys = BOOKS + (
            LEADERBOARD, LEADERBOARD_STOCKS, LEADERBOARD_METHODS,
            LEADERBOARD_GOLD, LEADERBOARD_BTC, LEADERBOARD_QUANT_V2,
        )
        for book in keys:
            if _mem.get(book) is None:
                _mem[book] = _read_disk(book)
        out = {book: _public(_mem.get(book)) for book in BOOKS}
        out[LEADERBOARD] = _public(_mem.get(LEADERBOARD))
        out[LEADERBOARD_STOCKS] = _public(_mem.get(LEADERBOARD_STOCKS))
        out[LEADERBOARD_METHODS] = _public(_mem.get(LEADERBOARD_METHODS))
        out[LEADERBOARD_GOLD] = _public(_mem.get(LEADERBOARD_GOLD))
        out[LEADERBOARD_BTC] = _public(_mem.get(LEADERBOARD_BTC))
        out[LEADERBOARD_QUANT_V2] = _public(_mem.get(LEADERBOARD_QUANT_V2))
        return out
