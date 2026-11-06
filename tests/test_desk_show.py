"""Public /desk books: $100 trial and the tied-demo CTRL baselines.

These tests stay off the network.
"""
import json
import os
import shutil
import unittest
from pathlib import Path

from traderapp import desk
from traderapp import desk_stocks as ds
from traderapp import paper_store


def _pool(**kw):
    base = {
        "change_h1": 10, "vol_h1": 1000, "age_min": 30,
        "buys_h1": 13, "sells_h1": 10, "liq_usd": 200000,
    }
    base.update(kw)
    return base


class CryptoShowTests(unittest.TestCase):
    def setUp(self):
        self._store = os.environ.get("PAPER_STORE_DIR")
        os.environ["PAPER_STORE_DIR"] = "/tmp/desk-show-test-store"
        shutil.rmtree("/tmp/desk-show-test-store", ignore_errors=True)
        paper_store.reset_memory()
        desk.apply_ctrl()
        desk._explicit_start = False
        desk._start_priced = False
        desk.START_SOL = 0.0
        desk._sync_caps()
        desk._state = None

    def tearDown(self):
        paper_store.reset_memory()
        if self._store is None:
            os.environ.pop("PAPER_STORE_DIR", None)
        else:
            os.environ["PAPER_STORE_DIR"] = self._store
        desk.apply_ctrl()
        desk._explicit_start = False
        desk._start_priced = False
        desk.START_SOL = 0.0
        desk._sync_caps()
        desk._state = None

    def test_ctrl_defaults_match_demo_v6_baseline(self):
        self.assertEqual(desk.CTRL_COMBO, "E0-K0-N0-S0-G0")
        self.assertEqual(desk.SHOW_BADGE, "主盤 SHOW｜$100｜Demo 暫定最佳 CTRL")
        self.assertAlmostEqual(desk.START_USD, float(os.environ.get("DESK_START_USD") or "100"))
        self.assertAlmostEqual(desk.TP, 0.05)
        self.assertAlmostEqual(desk.SL, 0.06)
        self.assertAlmostEqual(desk.DAILY_LOSS_OF_START, 0.25)
        self.assertEqual(desk.MAX_POSITIONS, 3)
        self.assertAlmostEqual(desk.MAX_POSITION_PCT, 0.15)
        self.assertAlmostEqual(desk.MOMENTUM_H1, 8)
        self.assertAlmostEqual(desk.MOMENTUM_H1_MAX, 14)
        self.assertEqual(desk.FRESH_MINUTES, 90)
        self.assertAlmostEqual(desk.FRESH_VOL_H1, 25000)
        self.assertAlmostEqual(desk.MIN_LIQ_TRADE, 100000)
        self.assertAlmostEqual(desk.MIN_LIQ_WATCH, 30000)
        self.assertAlmostEqual(desk.FDV_LIQ_MAX, 200)
        self.assertAlmostEqual(desk.TOP10_BLOCK, 45)
        self.assertAlmostEqual(desk.BUY_SELL_MIN_RATIO, 1.25)
        self.assertAlmostEqual(desk.MAX_DEV_HOLD_PCT, 12)
        self.assertEqual(desk.MIN_HOLDERS, 80)
        self.assertTrue(desk.SCOUT_ENABLED)
        self.assertAlmostEqual(desk.SLIPPAGE, 0)
        self.assertAlmostEqual(desk.FEE_SOL, 0)

    def test_configure_accepts_role_knobs_without_clearing_positions(self):
        desk._state = desk._blank()
        desk._state["positions"] = [{"mint": "keep"}]
        out = desk.configure(
            start_sol=1.5, tp=0.08, sl=0.04, daily_loss_of_start=0.1,
            max_positions=2, max_position_pct=0.2, momentum_h1=12, momentum_h1_max=18,
            fresh_minutes=60, fresh_vol_h1=15000, min_liq_trade=80000, min_liq_watch=20000,
            fdv_liq_max=150, top10_block=40, buy_sell_min_ratio=1.5, max_dev_hold_pct=8,
            min_holders=50, scout_enabled=False, slippage=0.01, fee_sol=0.0002,
            ignored_extra="nope",
        )
        self.assertEqual(desk._state["positions"], [{"mint": "keep"}])
        self.assertAlmostEqual(out["start_sol"], 1.5)
        self.assertAlmostEqual(out["tp"], 0.08)
        self.assertAlmostEqual(out["sl"], 0.04)
        self.assertAlmostEqual(out["daily_loss_of_start"], 0.1)
        self.assertEqual(out["max_positions"], 2)
        self.assertAlmostEqual(out["max_position_pct"], 0.2)
        self.assertAlmostEqual(out["momentum_h1"], 12)
        self.assertAlmostEqual(out["momentum_h1_max"], 18)
        self.assertEqual(out["fresh_minutes"], 60)
        self.assertAlmostEqual(out["fresh_vol_h1"], 15000)
        self.assertAlmostEqual(out["min_liq_trade"], 80000)
        self.assertAlmostEqual(out["min_liq_watch"], 20000)
        self.assertAlmostEqual(out["fdv_liq_max"], 150)
        self.assertAlmostEqual(out["top10_block"], 40)
        self.assertAlmostEqual(out["buy_sell_min_ratio"], 1.5)
        self.assertAlmostEqual(out["max_dev_hold_pct"], 8)
        self.assertEqual(out["min_holders"], 50)
        self.assertFalse(out["scout_enabled"])
        self.assertAlmostEqual(out["slippage"], 0.01)
        self.assertAlmostEqual(out["fee_sol"], 0.0002)
        self.assertAlmostEqual(desk.MAX_DAILY_LOSS_SOL, 0.15)
        self.assertAlmostEqual(desk.MAX_ORDER_SOL, 0.3)

    def test_sniper_and_rug_use_ctrl_gates(self):
        ok, _why = desk._sniper_ok(_pool(buys_h1=10, sells_h1=10))
        self.assertFalse(ok)
        ok, _why = desk._sniper_ok(_pool())
        self.assertTrue(ok)
        ok, _why = desk._sniper_ok(_pool(change_h1=30, age_min=10, vol_h1=30000, buys_h1=10, sells_h1=4))
        self.assertTrue(ok)
        desk.configure(scout_enabled=False)
        ok, _why = desk._sniper_ok(_pool(change_h1=30, age_min=10, vol_h1=30000, buys_h1=10, sells_h1=4))
        self.assertFalse(ok)
        info = {
            "mint_state": "off", "freeze_state": "off", "top10_pct": 10,
            "holders_count": 10, "developer_holding_percentage": 4, "is_honeypot": False,
        }
        self.assertTrue(desk._rug({"liq_usd": 150000, "fdv_usd": 15_000_000}, info)["blocked"])
        info["holders_count"] = 90
        info["developer_holding_percentage"] = 20
        self.assertTrue(desk._rug({"liq_usd": 150000, "fdv_usd": 15_000_000}, info)["blocked"])
        info["developer_holding_percentage"] = 4
        self.assertFalse(desk._rug({"liq_usd": 150000, "fdv_usd": 15_000_000}, info)["blocked"])

    def test_reset_sets_cash_from_live_sol_and_clears_positions(self):
        desk._state = desk._blank()
        desk._state["positions"] = [{"mint": "old"}]
        desk._state["cash_sol"] = 9

        def load(st):
            st["sol_usd"] = 200
            st["sol_source"] = "test"
            st["pools"] = []
            st["errors"] = []
            return []

        orig_load, orig_tick = desk._load_market, desk._tick
        desk._load_market = load
        desk._tick = lambda st: None
        try:
            view = desk.reset()
        finally:
            desk._load_market = orig_load
            desk._tick = orig_tick
        self.assertEqual(view["account"]["open"], 0)
        self.assertAlmostEqual(view["account"]["start_sol"], 0.5)
        self.assertAlmostEqual(view["account"]["cash_sol"], 0.5)
        self.assertEqual(view["account"]["trial_usd"], 100)
        self.assertAlmostEqual(view["account"]["day_pnl_sol"], 0)
        self.assertTrue(view["account"]["start_priced"])
        self.assertEqual(view["badge"], desk.SHOW_BADGE)
        self.assertEqual(view["combo"], "E0-K0-N0-S0-G0")
        self.assertIn("約 $100", " ".join(view["rules"]))

    def test_unpriced_book_does_not_invent_pnl(self):
        st = desk._blank()
        st["sol_usd"] = None
        view = desk._view(st)
        self.assertIsNone(view["account"]["day_pnl_sol"])
        self.assertIsNone(view["account"]["day_pnl_usd"])
        self.assertIsNone(view["account"]["start_sol"])
        self.assertFalse(view["account"]["start_priced"])
        self.assertEqual(view["account"]["trial_usd"], 100)

    def test_partial_marks_still_fill_usd_kpis(self):
        st = desk._blank()
        st["sol_usd"] = 90
        st["cash_sol"] = 0.5
        st["start_sol"] = 1.0
        st["positions"] = [{
            "value_sol": None, "qty": 10, "last_usd": 4.5, "cost_sol": 0.5,
            "symbol": "A", "mint": "m", "entry_usd": 4, "upnl_sol": None,
        }]
        view = desk._view(st)
        self.assertAlmostEqual(view["account"]["equity_usd"], 90.0)
        self.assertAlmostEqual(view["account"]["day_pnl_usd"], -10.0)
        self.assertIsNotNone(view["account"]["equity_sol"])

    def test_ingested_main_book_fills_the_strip(self):
        raw = json.dumps({
            "equity_usd": 99.68, "equity_sol": 1.1, "cash_sol": 0.8, "sol_usd": 90.5,
            "wins": 0, "closed_n": 0,
            "config": {"start_usd": 100, "start_sol": 1.105094, "label": "主盤 SHOW"},
            "positions": [{"symbol": "AMD", "entry_usd": 1, "last_usd": 1.1, "upnl_sol": 0.01, "why": "升"}],
        }).encode()
        body, code = paper_store.ingest("crypto", raw)
        self.assertEqual(code, 200, body)
        view = desk._view(desk._blank())
        self.assertTrue(view["account"]["mirror"])
        self.assertAlmostEqual(view["account"]["equity_usd"], 99.68)
        self.assertAlmostEqual(view["account"]["day_pnl_usd"], -0.32)
        self.assertAlmostEqual(view["account"]["start_usd"], 100)
        self.assertEqual(view["positions"][0]["symbol"], "AMD")
        self.assertAlmostEqual(view["positions"][0]["upnl_usd"], round(0.01 * 90.5, 2))
        self.assertEqual(view["badge"], "主盤 SHOW｜$100｜Demo 暫定最佳 CTRL")
        self.assertFalse(view["account"]["quote_missing"])

    def test_open_position_includes_usd_upnl(self):
        st = desk._blank()
        st["sol_usd"] = 100
        st["cash_sol"] = 0.5
        st["start_sol"] = 1.0
        st["positions"] = [{
            "symbol": "BONK", "mint": "m", "qty": 1000, "entry_usd": 0.01,
            "last_usd": 0.012, "cost_sol": 0.1, "upnl_sol": 0.02, "ret": 0.2,
        }]
        view = desk._view(st)
        row = view["positions"][0]
        self.assertEqual(row["symbol"], "BONK")
        self.assertAlmostEqual(row["upnl_sol"], 0.02)
        self.assertAlmostEqual(row["upnl_usd"], 2.0)
        self.assertEqual(view["badge"], "主盤 SHOW｜$100｜Demo 暫定最佳 CTRL")


class StockShowTests(unittest.TestCase):
    def test_ctrl_baseline_and_hundred_dollar_start(self):
        src = Path(__file__).resolve().parents[1].joinpath("traderapp", "desk_stocks.py").read_text(encoding="utf-8")
        self.assertIn('or "100"', src)
        self.assertNotIn('or "10000"', src)
        self.assertEqual(ds.STOCK_COMBO, "E0-K0-N0-S0")
        self.assertEqual(ds.STOCK_BADGE, "主盤 SHOW｜$100｜Demo STOCKS_V1 CTRL")
        self.assertAlmostEqual(ds.TP, 0.03)
        self.assertAlmostEqual(ds.SL, 0.015)
        self.assertAlmostEqual(ds.MAX_DAILY_LOSS_PCT, 0.25)
        self.assertEqual(ds.MAX_POSITIONS, 3)
        self.assertAlmostEqual(ds.MAX_POSITION_PCT, 0.20)
        self.assertAlmostEqual(ds.MAX_ORDER_USD, 2000)
        self.assertAlmostEqual(ds.GAP_SIGNAL, 1.5)
        self.assertAlmostEqual(ds.MIN_PRICE, 5)
        self.assertAlmostEqual(ds.MIN_AVG_VOL, 1_000_000)
        self.assertAlmostEqual(ds.RVOL_FLAG, 2)
        if not os.environ.get("DESK_STOCK_START_USD"):
            self.assertAlmostEqual(ds.START_USD, 100)
            book = ds._blank()
            self.assertAlmostEqual(book["cash_usd"], 100)
            self.assertEqual(book["positions"], [])

    def test_page_keeps_disclaimer_badge_and_crew_cards(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "templates" / "desk.html").read_text(encoding="utf-8")
        js = (root / "static" / "desk.js").read_text(encoding="utf-8")
        self.assertIn("模擬盤，唔係真錢，唔係投資建議。", html)
        self.assertIn("主盤 SHOW｜$100｜Demo 暫定最佳 CTRL", html)
        self.assertIn("/static/desk.js?v=show5", html)
        self.assertIn("/static/desk.css?v=show5", html)
        self.assertLess(html.index('id="stats"'), html.index('id="holdings"'))
        self.assertLess(html.index('id="holdings"'), html.index('id="office"'))
        self.assertIn(">持倉<", html)
        self.assertIn("而家冇持倉", html)
        self.assertNotIn("而家冇持倉。", html)
        self.assertIn("主盤 SHOW｜$100｜Demo STOCKS_V1 CTRL", js)
        self.assertIn("function kpiFigures", js)
        self.assertIn("function renderHoldings", js)
        self.assertIn("未實現盈虧", js)
        self.assertIn("而家冇持倉", js)
        self.assertNotIn("而家冇持倉。", js)
        self.assertIn("function usdAmt", js)
        self.assertIn("function quietSol", js)
        self.assertIn("stat-label", js)
        self.assertIn("stat-sol", js)
        self.assertNotIn('" · " + num(a.equity_sol', js)
        self.assertNotIn('" · " + num(a.start_sol', js)
        self.assertIn("樣本太少", js)
        self.assertIn("（已平倉 ", js)
        css = (root / "static" / "desk.css").read_text(encoding="utf-8")
        self.assertIn(".stat-label", css)
        self.assertIn(".stat-value", css)
        self.assertIn(".stat-sol", css)
        self.assertIn("今日模擬盈虧", html)
        self.assertIn("勝率（已平倉）", html)
        self.assertIn("模擬權益", html)
        self.assertIn(">起始<", html)
        self.assertNotIn("const solPx", js)
        self.assertNotIn("網站示範盤（10 SOL", html)
        self.assertNotIn("10 SOL", js)
        self.assertIn('class="station', js)
        self.assertIn("station-detail", js)
        self.assertIn('const CREW = ["scan", "sniper", "whale", "search", "chief", "rug", "exit", "risk", "dev"]', js)


if __name__ == "__main__":
    unittest.main()
