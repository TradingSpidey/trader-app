"""Latest $50 paper books pushed from the always-on machine. No trading here."""
import json
import os
import threading
from datetime import datetime, timezone

BOOKS = ("crypto", "stocks")
LEADERBOARD = "leaderboard"
MAX_BODY = 2 * 1024 * 1024
_lock = threading.Lock()
_mem = {"crypto": None, "stocks": None, "leaderboard": None}


def store_dir():
    return os.environ.get("PAPER_STORE_DIR") or "/tmp/paper_store"


def reset_memory():
    with _lock:
        _mem["crypto"] = None
        _mem["stocks"] = None
        _mem["leaderboard"] = None


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


def ingest_leaderboard(raw):
    """Overwrite the latest D01–D10 demo leaderboard. Paper only."""
    data, err = _parse_object(raw)
    if err:
        return err
    books = data.get("books", [])
    if not isinstance(books, list):
        return {"error": "books 要係陣列"}, 400
    payload = {
        "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "book": LEADERBOARD,
        "data": data,
    }
    failed = _commit(LEADERBOARD, payload)
    if failed:
        return failed
    return {"ok": True, "book": LEADERBOARD, "received_at": payload["received_at"], "books": len(books)}, 200


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


def load_leaderboard():
    with _lock:
        if _mem.get(LEADERBOARD) is None:
            _mem[LEADERBOARD] = _read_disk(LEADERBOARD)
        return _public(_mem.get(LEADERBOARD))


def load_all():
    with _lock:
        for book in BOOKS:
            if _mem.get(book) is None:
                _mem[book] = _read_disk(book)
        if _mem.get(LEADERBOARD) is None:
            _mem[LEADERBOARD] = _read_disk(LEADERBOARD)
        out = {book: _public(_mem.get(book)) for book in BOOKS}
        out[LEADERBOARD] = _public(_mem.get(LEADERBOARD))
        return out
