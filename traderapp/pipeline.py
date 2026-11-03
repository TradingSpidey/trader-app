"""Runs the vendored day-trader-skill tools as subprocesses, one temp folder per run.

Paper trading only: nothing here can place an order. The broker step only renders
the ticket (trader-broker/ticket.py show), which has no network code at all.
"""
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.environ.get("DTS_DIR") or os.path.join(os.path.dirname(HERE), "vendor", "day-trader-skill")
PY = sys.executable
SEC_UA = os.environ.get("SEC_USER_AGENT", "").strip()

TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

# ~100 liquid US names for a fast scan (the full universe takes minutes).
LIQUID = ("AAPL MSFT NVDA AMZN GOOGL GOOG META TSLA AVGO BRK.B JPM V MA LLY UNH XOM WMT COST HD PG "
          "JNJ ORCL NFLX CRM AMD ADBE PEP KO MRK ABBV BAC CVX TMO MCD CSCO ACN ABT LIN WFC DIS "
          "INTC QCOM TXN IBM AMAT GE CAT NOW INTU UBER ISRG PFE GS MS AXP BKNG SPGI LOW HON RTX "
          "BA DE PLTR PANW MU LRCX ADI KLAC SNPS CDNS MRVL CRWD ABNB SHOP COIN HOOD SOFI PYPL SQ "
          "XYZ C SCHW BLK T VZ CMCSA NKE SBUX F GM RIVN LCID NIO BABA PDD JD MELI SNOW DASH ROKU "
          "APP SMCI ARM DELL HPQ").split()


def _load_scan():
    spec = importlib.util.spec_from_file_location("dts_scan", os.path.join(SKILLS, "trader-scanner", "scan.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_scan = _load_scan()
_entry = None


def _load_entry():
    """The same Yahoo chart reader trader-entry uses. Loaded once, stdlib only."""
    global _entry
    if _entry is None:
        path = os.path.join(SKILLS, "trader-entry", "entry.py")
        spec = importlib.util.spec_from_file_location("dts_entry", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["dts_entry"] = mod
        spec.loader.exec_module(mod)
        _entry = mod
    return _entry


class RunError(Exception):
    pass


def ny_now():
    return _scan.to_eastern(_scan.parse_now(None))


def pick_session(hhmm=None):
    """-> dict(day, time, now_arg, live, note). Latest session whose clock has reached hhmm."""
    now = ny_now()
    t = None
    if hhmm:
        m = TIME_RE.match(hhmm.strip())
        if not m:
            raise RunError("時間格式要係 HH:MM（紐約時間），例如 10:15")
        t = datetime.time(int(m.group(1)), int(m.group(2)))
        if t < datetime.time(9, 50) or t > datetime.time(15, 30):
            raise RunError("重播時間要喺紐約時間 9:50 至 15:30 之間（開市區間 9:30–9:45 之後先有訊號）")
    day = now.date()
    for _ in range(10):
        sess = _scan.session(day)
        if sess:
            close = datetime.datetime.combine(day, sess[1])
            if t is None:
                # no time given: live if the session is running past 9:50, else 10:15 of the last session
                if day == now.date() and datetime.datetime.combine(day, datetime.time(9, 50)) <= now < close:
                    cut = min(now.replace(second=0, microsecond=0), datetime.datetime.combine(day, datetime.time(15, 30)))
                    return {"day": day.isoformat(), "time": cut.strftime("%H:%M"), "now_arg": cut.strftime("%Y-%m-%d %H:%M"),
                            "live": True, "ny_now": now.strftime("%Y-%m-%d %H:%M")}
                tt = datetime.time(10, 15)
            else:
                tt = t
            at = datetime.datetime.combine(day, tt)
            if at > close:
                at = close - datetime.timedelta(minutes=30)
            if at <= now:
                return {"day": day.isoformat(), "time": at.strftime("%H:%M"), "now_arg": at.strftime("%Y-%m-%d %H:%M"),
                        "live": False, "ny_now": now.strftime("%Y-%m-%d %H:%M")}
        day -= datetime.timedelta(days=1)
    raise RunError("搵唔到最近嘅交易日")


def _run(args, cwd, timeout=180):
    env = dict(os.environ)
    if SEC_UA:
        env["SEC_USER_AGENT"] = SEC_UA
    t0 = time.time()
    try:
        p = subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "out": "", "err": "超時（%d 秒）：免費數據源可能慢或者限流，請稍後再試。" % timeout,
                "seconds": round(time.time() - t0, 1)}
    err = p.stderr.strip()
    lines = [l for l in err.splitlines() if l.strip()]
    if len(lines) > 3 and lines[0].startswith("Traceback"):
        err = "數據源出錯（可能係暫時性網絡問題）：" + lines[-1][-300:]
    return {"ok": p.returncode == 0, "code": p.returncode, "out": p.stdout, "err": err,
            "seconds": round(time.time() - t0, 1)}


def _json(res):
    try:
        return json.loads(res["out"]) if res["out"].strip() else None
    except ValueError:
        return None


def _tool(name, script):
    return os.path.join(SKILLS, name, script)


def _write_config(work, budget, max_loss):
    with open(_tool("trader-budget", "config.example.json")) as f:
        cfg = json.load(f)
    cfg.update({
        "budget": budget,
        "max_order_usd": round(budget * 0.8, 2),
        "max_loss_per_trade_usd": max_loss,
        "max_daily_loss_usd": round(max_loss * 3, 2),
        "paper": True,
        "allow_options": False, "allow_margin": False, "allow_short": False,
        "sec_user_agent": SEC_UA or "",
    })
    os.makedirs(os.path.join(work, "trader"), exist_ok=True)
    with open(os.path.join(work, "trader", "config.json"), "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg


# ----------------------------------------------------------------- cache (be polite to free data)
_cache = {}
_lock = threading.Lock()
TTL = 600


def _cacheable(val):
    if not val.get("ok", True):
        return False
    return all(s.get("ok") for s in (val.get("steps") or {}).values())


def _cached(key, fn, keep=None):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return dict(hit[1], cached=True)
    val = fn()
    ok = _cacheable(val) if keep is None else keep(val)
    if not ok:   # never cache a failure: the next try gets a fresh fetch
        return val
    with _lock:
        _cache[key] = (time.time(), val)
        if len(_cache) > 200:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:50]:
                _cache.pop(k, None)
    return val


def validate_ticker(t):
    t = (t or "").strip().upper()
    if not TICKER_RE.match(t):
        raise RunError("股票代號唔啱：要係 1 至 5 個英文字母（例如 TSLA、BRK.B）")
    return t


def run_pipeline(ticker, budget, max_loss, hhmm=None):
    ticker = validate_ticker(ticker)
    if not (100 <= budget <= 10_000_000):
        raise RunError("戶口金額要喺 $100 至 $10,000,000 之間")
    if not (1 <= max_loss <= budget * 0.5):
        raise RunError("每單最多蝕要喺 $1 至戶口一半之間")
    sess = pick_session(hhmm)
    key = ("pipe", ticker, budget, max_loss, sess["now_arg"])
    return _cached(key, lambda: _pipeline(ticker, budget, max_loss, sess))


def _pipeline(ticker, budget, max_loss, sess):
    work = tempfile.mkdtemp(prefix="trader-run-")
    N = sess["now_arg"]
    steps = {}
    out = {"ticker": ticker, "budget": budget, "max_loss": max_loss, "session": sess, "steps": steps,
           "stopped_at": None, "cached": False}
    try:
        cfg = _write_config(work, budget, max_loss)
        out["config"] = {k: cfg[k] for k in ("budget", "cash_buffer_pct", "max_position_pct", "max_order_usd",
                                             "max_loss_per_trade_usd", "max_daily_loss_usd", "max_trades_per_day",
                                             "min_reward_risk", "flat_by", "paper")}
        # 1. news (headlines; SEC 8-Ks only if a User-Agent is configured)
        news_args = [_tool("trader-news", "news.py"), "--tickers", ticker, "--hours", "96", "--json", "--dry-run"]
        if not SEC_UA:
            news_args.append("--no-sec")
        r = _run(news_args, work, 90)
        if not r["ok"]:
            time.sleep(2)
            r = _run(news_args, work, 90)   # one retry: free feeds time out now and then
        steps["news"] = {"ok": r["ok"], "data": _json(r), "err": r["err"], "seconds": r["seconds"]}

        # 2. entry
        r = _run([_tool("trader-entry", "entry.py"), "check", ticker, "--now", N, "--json", "--write"], work, 90)
        ej = _json(r)
        steps["entry"] = {"ok": ej is not None, "data": ej, "err": r["err"], "seconds": r["seconds"]}
        if not ej:
            out["stopped_at"] = "entry"
            return out
        if ej.get("status") != "triggered":
            out["stopped_at"] = "no_trigger"
            return out

        # 3. exit plan (README default: stop at the range midpoint, 1R target)
        r = _run([_tool("trader-exit", "exit.py"), "plan", "--stop", "or-mid", "--target", "1R", "--now", N,
                  "--write", "--json"], work, 90)
        pj = _json(r)
        steps["exit"] = {"ok": r["ok"] and pj is not None, "data": pj, "err": r["err"], "seconds": r["seconds"]}
        if not steps["exit"]["ok"]:
            out["stopped_at"] = "exit"
            return out

        # 4. time machine, 10,000 replays, seed 19
        r = _run([_tool("trader-timemachine", "timemachine.py"), "run", "--now", N, "--json", "--write"], work, 180)
        tj = _json(r)
        if tj:
            tj.pop("data", None)
            hist = tj.get("history") or {}
            hist.pop("trades", None)
        steps["timemachine"] = {"ok": r["ok"] and tj is not None, "data": tj, "err": r["err"], "seconds": r["seconds"]}

        # 5. budget
        r = _run([_tool("trader-budget", "size.py"), "--now", N, "--write", "--json"], work, 60)
        bj = _json(r)
        steps["budget"] = {"ok": r["ok"] and bj is not None, "data": bj, "err": r["err"], "seconds": r["seconds"]}
        if not steps["budget"]["ok"]:
            out["stopped_at"] = "budget"
            return out

        # 6. risk
        r = _run([_tool("trader-risk", "check.py"), "--now", N, "--today", sess["day"], "--json"], work, 60)
        rj = _json(r)
        steps["risk"] = {"ok": rj is not None, "data": rj, "err": r["err"], "seconds": r["seconds"]}

        # 7. paper ticket: show only. Never approve, never place.
        r = _run([_tool("trader-broker", "ticket.py"), "show", "--now", N, "--today", sess["day"], "--json"], work, 60)
        kj = _json(r)
        if isinstance(kj, list):
            for t in kj:
                t.pop("tool", None)
        steps["ticket"] = {"ok": kj is not None, "data": kj, "err": r["err"], "seconds": r["seconds"]}
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _px(x):
    return None if x is None else round(float(x), 4)


def _bars(ticker, sess):
    """Closed 5-minute regular-session bars up to the same New York clock as the pipeline."""
    entry = _load_entry()
    day = datetime.date.fromisoformat(sess["day"])
    try:
        chart = entry.get_chart(ticker, "5m", day, None, ny_now().date())
    except entry.EntryError as e:
        raise RunError("讀唔到 K 線：%s" % e)
    bounds = entry.session(day)
    meta = chart.get("meta") or {}
    out = {"ticker": ticker, "interval": "5m", "session": sess, "source": "yahoo",
           "prev_close": _px(chart.get("prev_close")), "currency": meta.get("currency"),
           "bars": [], "cached": False}
    if not bounds:
        return out
    open_t, close_t = bounds
    open_dt = datetime.datetime.combine(day, open_t)
    close_dt = datetime.datetime.combine(day, close_t)
    cutoff = datetime.datetime.strptime(sess["now_arg"], "%Y-%m-%d %H:%M")
    step = entry.INTERVALS["5m"]
    seen = {}
    for b in chart["bars"]:
        if b["t"] % step:
            continue
        et = entry.to_eastern(entry.utc_of(b["t"]))
        if et.date() != day or not (open_dt <= et < close_dt):
            continue
        if et + datetime.timedelta(seconds=step) > cutoff:
            continue
        seen[int(b["t"])] = {"t": int(b["t"]), "time": et.strftime("%H:%M"),
                             "o": _px(b["o"]), "h": _px(b["h"]), "l": _px(b["l"]), "c": _px(b["c"]),
                             "v": int(b["v"] or 0)}
    out["bars"] = [seen[k] for k in sorted(seen)]
    return out


def run_bars(ticker, hhmm=None):
    ticker = validate_ticker(ticker)
    sess = pick_session(hhmm)
    key = ("bars", ticker, sess["now_arg"])
    return _cached(key, lambda: _bars(ticker, sess), keep=lambda v: bool(v.get("bars")))


def run_scan(mode="orb", hhmm=None):
    if mode not in ("orb", "daily"):
        raise RunError("掃描模式唔啱")
    sess = pick_session(hhmm) if mode == "orb" else {"now_arg": None, "day": ny_now().date().isoformat()}
    key = ("scan", mode, sess.get("now_arg") or sess["day"])

    def go():
        work = tempfile.mkdtemp(prefix="trader-scan-")
        try:
            args = [_tool("trader-scanner", "scan.py"), mode, "--symbols", ",".join(LIQUID), "--json", "--no-write"]
            if mode == "orb":
                args += ["--now", sess["now_arg"]]
            r = _run(args, work, 240)
            j = _json(r)
            return {"mode": mode, "session": sess, "ok": j is not None, "data": j, "err": r["err"],
                    "seconds": r["seconds"], "universe": len(LIQUID), "cached": False}
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return _cached(key, go)


def run_analyst(ticker):
    ticker = validate_ticker(ticker)
    if not SEC_UA:
        raise RunError("業績分析要用 SEC 數據，伺服器未設定 SEC_USER_AGENT（名 + 電郵）。")

    def go():
        work = tempfile.mkdtemp(prefix="trader-an-")
        try:
            r = _run([_tool("trader-analyst", "facts.py"), ticker, "--json"], work, 120)
            return {"ok": r["ok"] and _json(r) is not None, "data": _json(r), "err": r["err"], "cached": False}
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return _cached(("an", ticker), go)


def run_pelosi(member="pelosi"):
    member = (member or "pelosi").strip()
    if not re.match(r"^[A-Za-z .'-]{2,40}$", member):
        raise RunError("議員名唔啱")

    def go():
        work = tempfile.mkdtemp(prefix="trader-ptr-")
        try:
            r = _run([_tool("trader-pelosi", "ptr.py"), "index", "--member", member, "--json"], work, 120)
            return {"ok": _json(r) is not None, "data": _json(r), "err": r["err"], "cached": False}
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return _cached(("ptr", member.lower()), go)


def run_ptr_fetch(doc_id, year=None):
    if not re.match(r"^\d{6,10}$", str(doc_id)):
        raise RunError("文件編號唔啱")
    def go():
        work = tempfile.mkdtemp(prefix="trader-ptrf-")
        try:
            args = [_tool("trader-pelosi", "ptr.py"), "fetch", str(doc_id), "--json", "--pdf-dir", work]
            if year and re.match(r"^\d{4}$", str(year)):
                args += ["--year", str(year)]
            r = _run(args, work, 120)
            return {"ok": _json(r) is not None, "data": _json(r), "err": r["err"], "cached": False}
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return _cached(("ptrf", doc_id), go)
