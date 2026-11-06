"""Latest $50 paper books pushed from the always-on machine. No trading here."""
import json
import os
import threading
from datetime import datetime, timezone

BOOKS = ("crypto", "stocks")
LEADERBOARD = "leaderboard"
LEADERBOARD_STOCKS = "leaderboard_stocks"
LEADERBOARD_METHODS = "leaderboard_methods"
MAX_BODY = 2 * 1024 * 1024
_lock = threading.Lock()
_mem = {
    "crypto": None,
    "stocks": None,
    "leaderboard": None,
    "leaderboard_stocks": None,
    "leaderboard_methods": None,
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
    if key not in (LEADERBOARD, LEADERBOARD_STOCKS, LEADERBOARD_METHODS):
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
        for book in BOOKS + (LEADERBOARD, LEADERBOARD_STOCKS, LEADERBOARD_METHODS):
            if _mem.get(book) is None:
                _mem[book] = _read_disk(book)
        out = {book: _public(_mem.get(book)) for book in BOOKS}
        out[LEADERBOARD] = _public(_mem.get(LEADERBOARD))
        out[LEADERBOARD_STOCKS] = _public(_mem.get(LEADERBOARD_STOCKS))
        out[LEADERBOARD_METHODS] = _public(_mem.get(LEADERBOARD_METHODS))
        return out
