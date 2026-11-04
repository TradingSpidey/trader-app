"""Headless paper desk. Persists JSON plus trades.csv and equity.csv.

    python -m traderapp.desk_runner --market stocks --start-usd 50 --state-dir DIR
    python -m traderapp.desk_runner --market crypto --state-dir DIR --once
"""
import argparse
import csv
import json
import os
import time


def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append(path, header, row):
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(header)
        w.writerow(row)


def main(argv=None):
    p = argparse.ArgumentParser(description="24/7 paper desk. No wallets, no real orders.")
    p.add_argument("--market", choices=("stocks", "crypto"), required=True)
    p.add_argument("--start-usd", type=float, default=None, help="stock book starting cash when DIR has no state yet")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=float, default=60)
    a = p.parse_args(argv)
    os.makedirs(a.state_dir, exist_ok=True)
    path = os.path.join(a.state_dir, "state.json")
    trades = os.path.join(a.state_dir, "trades.csv")
    equity = os.path.join(a.state_dir, "equity.csv")
    if not os.path.exists(trades):
        with open(trades, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(["ts", "market", "action", "symbol", "qty", "price", "notional", "pnl", "reason"])
    if a.market == "stocks":
        from traderapp import desk_stocks as eng
        book = _load(path)
        if a.start_usd is not None and not book:
            eng.import_book({}, start=a.start_usd)
        elif book:
            eng.import_book(book)
        else:
            eng.import_book({})
    else:
        from traderapp import desk as eng
        book = _load(path)
        if book:
            eng.import_book(book)
    seen_open = set((book or {}).get("csv_opens") or [])
    seen_close = set((book or {}).get("csv_closes") or [])
    while True:
        view = eng.snapshot()
        data = eng.export_book()
        for pos in data.get("positions") or []:
            key = "%s:%s" % (pos.get("symbol"), pos.get("id") or pos.get("opened_at"))
            if key in seen_open:
                continue
            seen_open.add(key)
            _append(trades, ["ts", "market", "action", "symbol", "qty", "price", "notional", "pnl", "reason"], [
                pos.get("opened_at") or view.get("now"), a.market, "buy", pos.get("symbol"),
                pos.get("qty"), pos.get("entry_usd"), pos.get("cost_usd") if pos.get("cost_usd") is not None else pos.get("cost_sol"),
                "", pos.get("why") or "",
            ])
        for c in data.get("closed") or []:
            key = "%s:%s:%s" % (c.get("symbol"), c.get("ts"), c.get("reason"))
            if key in seen_close:
                continue
            seen_close.add(key)
            _append(trades, ["ts", "market", "action", "symbol", "qty", "price", "notional", "pnl", "reason"], [
                c.get("ts"), a.market, "sell", c.get("symbol"), c.get("qty"), c.get("exit_usd"), "",
                c.get("pnl_usd") if c.get("pnl_usd") is not None else c.get("pnl_sol"), c.get("reason") or "",
            ])
        data["csv_opens"] = sorted(seen_open)
        data["csv_closes"] = sorted(seen_close)
        acct = view.get("account") or {}
        eq = acct.get("equity_usd")
        if eq is None:
            eq = acct.get("equity_sol")
        _append(equity, ["ts", "market", "equity", "cash", "phase"], [
            view.get("now"), a.market, eq, acct.get("cash_usd") if acct.get("cash_usd") is not None else acct.get("cash_sol"),
            (view.get("session") or {}).get("phase") or "",
        ])
        _save(path, data)
        phase = (view.get("session") or {}).get("phase") or view.get("market")
        print("%s %s equity=%s positions=%s" % (view.get("now"), phase, eq, acct.get("open")))
        if a.once:
            return 0
        time.sleep(max(5.0, a.interval))


if __name__ == "__main__":
    raise SystemExit(main())
