"""Stock paper fills pay per-side slippage and a minimum commission.

These tests stay off the network and do not reset a persisted book.
"""
import unittest

from traderapp import desk_stocks as ds


class StockFillCostTests(unittest.TestCase):
    def test_defaults(self):
        self.assertAlmostEqual(ds.SLIPPAGE_PER_SIDE, 0.001)
        self.assertAlmostEqual(ds.COMMISSION_MIN_USD, 0.01)
        self.assertAlmostEqual(ds.COMMISSION_RATE, 0.0)

    def test_buy_is_worse_and_sell_is_worse(self):
        self.assertAlmostEqual(ds._buy_fill(10), 10.01)
        self.assertAlmostEqual(ds._sell_fill(10), 9.99)
        self.assertGreater(ds._buy_fill(50), 50)
        self.assertLess(ds._sell_fill(50), 50)

    def test_commission_floor_on_a_tiny_notional(self):
        self.assertAlmostEqual(ds._commission_usd(0.001), 0.01)
        self.assertAlmostEqual(ds._commission_usd(0), 0.01)

    def test_buy_cash_includes_slippage_and_commission(self):
        quote, budget = 100.0, 100.0
        plan = ds._plan_buy(quote, budget)
        buy_px = quote * 1.001
        qty = (budget - 0.01) / buy_px
        self.assertAlmostEqual(plan["fill"], buy_px)
        self.assertAlmostEqual(plan["qty"], qty)
        self.assertAlmostEqual(plan["commission_usd"], 0.01)
        self.assertAlmostEqual(plan["cash_out"], qty * buy_px + 0.01)
        self.assertAlmostEqual(plan["cash_out"], budget)
        self.assertLessEqual(plan["cash_out"], budget + 1e-9)

    def test_fill_buy_debits_cash_and_cost_basis(self):
        st = {"cash_usd": 1000.0, "positions": [], "seq": 1, "realized_by": {}, "closed": []}
        pos = ds._fill_buy(st, "AVGO", 100, 100, "缺口")
        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos["entry_usd"], 100.1)
        self.assertAlmostEqual(pos["entry_quote_usd"], 100)
        self.assertAlmostEqual(pos["entry_commission_usd"], 0.01)
        self.assertAlmostEqual(pos["cost_usd"], 100)
        self.assertAlmostEqual(st["cash_usd"], 900)
        self.assertAlmostEqual(pos["upnl_usd"], pos["qty"] * 100 - pos["cost_usd"])
        self.assertLess(pos["upnl_usd"], 0)
        self.assertLess(pos["ret"], 0)

    def test_buy_cannot_spend_more_cash_than_the_book_holds(self):
        st = {"cash_usd": 50.0, "positions": [], "seq": 1, "realized_by": {}, "closed": []}
        pos = ds._fill_buy(st, "MSFT", 20, 100, "缺口")
        self.assertAlmostEqual(pos["cost_usd"], 50, places=6)
        self.assertGreaterEqual(st["cash_usd"], -1e-9)
        self.assertAlmostEqual(st["cash_usd"], 0, places=6)

    def test_round_trip_pnl_matches_cash(self):
        quote = 100.0
        st = {"cash_usd": 1000.0, "positions": [], "seq": 1, "realized_by": {}, "closed": []}
        pos = ds._fill_buy(st, "AVGO", quote, 100, "缺口")
        pos["last_usd"] = quote
        self.assertTrue(ds._close(st, pos, "平倉", "EXIT"))
        closed = st["closed"][-1]
        sell_px = quote * 0.999
        proceeds = pos["qty"] * sell_px - 0.01
        self.assertAlmostEqual(closed["exit_usd"], sell_px)
        self.assertLess(closed["exit_usd"], quote)
        self.assertAlmostEqual(closed["exit_commission_usd"], 0.01)
        self.assertAlmostEqual(closed["proceeds_usd"], proceeds)
        self.assertAlmostEqual(closed["pnl_usd"], proceeds - pos["cost_usd"])
        self.assertAlmostEqual(st["cash_usd"] - 1000.0, closed["pnl_usd"])
        self.assertAlmostEqual(st["realized_by"]["EXIT"], closed["pnl_usd"])
        self.assertLess(closed["pnl_usd"], -0.20)

    def test_legacy_open_is_not_backfilled(self):
        """A position opened at the quote keeps that cost basis. Only the sell is charged."""
        qty, cost, quote = 0.1, 10.0, 100.0
        st = {"cash_usd": 40.0, "positions": [], "seq": 2, "realized_by": {}, "closed": []}
        pos = {"symbol": "AMZN", "qty": qty, "cost_usd": cost, "entry_usd": quote, "last_usd": quote}
        self.assertTrue(ds._close(st, pos, "到止蝕", "EXIT"))
        proceeds = qty * (quote * 0.999) - 0.01
        closed = st["closed"][-1]
        self.assertAlmostEqual(closed["proceeds_usd"], proceeds)
        self.assertAlmostEqual(closed["pnl_usd"], proceeds - cost)
        self.assertAlmostEqual(st["cash_usd"], 40.0 + proceeds)
        # A backfill would also have charged the buy side (~another 0.1% + $0.01).
        self.assertGreater(closed["pnl_usd"], -0.03)
        self.assertAlmostEqual(pos["cost_usd"], cost)

    def test_missing_quote_does_not_invent_a_fill(self):
        st = {"cash_usd": 10.0, "positions": [], "seq": 1, "realized_by": {}, "closed": []}
        pos = {"symbol": "NVDA", "qty": 1, "cost_usd": 10, "last_usd": None}
        self.assertFalse(ds._close(st, pos, "平倉", "EXIT"))
        self.assertEqual(st["cash_usd"], 10.0)
        self.assertEqual(st["closed"], [])
        self.assertIsNone(ds._plan_buy(0, 100))
        self.assertIsNone(ds._plan_buy(10, 0.005))

    def test_commission_rate_still_respects_the_minimum(self):
        original = ds.COMMISSION_RATE
        try:
            ds.COMMISSION_RATE = 0.01
            plan = ds._plan_buy(100, 101)
            self.assertGreater(plan["commission_usd"], 0.01)
            self.assertAlmostEqual(plan["cash_out"], 101, places=6)
            self.assertAlmostEqual(plan["commission_usd"], plan["notional"] * 0.01, places=6)
            dust = ds._plan_sell(1, 0.2)
            self.assertAlmostEqual(dust["commission_usd"], 0.01)
        finally:
            ds.COMMISSION_RATE = original

    def test_rules_no_longer_say_the_stock_engine_is_free(self):
        text = "\n".join(ds._rules())
        self.assertNotIn("冇計滑價", text)
        self.assertNotIn("冇計手續費", text)
        self.assertIn("0.1%", text)
        self.assertIn("$0.01", text)
        note = ds._costs_note()
        self.assertIn("買入成交高過", note)
        self.assertIn("賣出低過", note)


if __name__ == "__main__":
    unittest.main()
