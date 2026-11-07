"""QUANT_V2 is a parallel stub page. Old paper routes stay on their own books."""
import json
import os
import tempfile
import unittest

os.environ.setdefault("PAPER_STORE_DIR", tempfile.mkdtemp(prefix="paper-v2-"))

from app import app  # noqa: E402
from traderapp import paper_store  # noqa: E402

DISCLAIMER = "模擬盤，唔係真錢，唔係投資建議。QUANT_V2 係平行 stub；舊紙盤照跑。"


class PaperV2Tests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.tmp = tempfile.mkdtemp(prefix="paper-v2-store-")
        os.environ["PAPER_STORE_DIR"] = self.tmp
        os.environ.pop("PAPER_INGEST_TOKEN", None)
        paper_store.reset_memory()

    def test_seed_page_is_paper_live_stub(self):
        page = self.client.get("/paper/v2")
        self.assertEqual(page.status_code, 200)
        self.assertIn("no-cache", page.headers.get("Cache-Control", ""))
        text = page.data.decode()
        self.assertIn("PAPER LIVE", text)
        self.assertIn("PAPER LIVE · QUANT_V2 · BTCUSDT", text)
        for pill in ("Forecast", "Risk", "Execute", "stub"):
            self.assertIn(pill, text)
        self.assertIn("99.99", text)
        self.assertIn("89.99", text)
        self.assertIn("75938.69", text)
        self.assertIn("2026-11-07 20:39:37 HKT", text)
        self.assertIn("LONG", text)
        self.assertIn("做多", text)
        self.assertIn("預測", text)
        self.assertIn("倉位", text)
        self.assertIn("執行", text)
        self.assertIn("AI／LLM 唔落單", text)
        self.assertIn("假單", text)
        self.assertIn("fake orders", text)
        self.assertIn(DISCLAIMER, text)
        self.assertEqual(text.count("。"), DISCLAIMER.count("。"))
        self.assertIn('href="/paper"', text)
        api = self.client.get("/api/paper/v2").get_json()
        self.assertEqual(api["source"], "seed")
        self.assertTrue(api["stub"])
        self.assertEqual(api["disclaimer"], DISCLAIMER)
        self.assertEqual(api["book"]["equity_usd"], 99.99)
        self.assertEqual(api["book"]["cash_usd"], 89.99)
        self.assertEqual(api["book"]["fills"][0]["side"], "BUY")
        self.assertEqual(api["book"]["fills"][0]["notional_usd"], 10.0)
        stored = self.client.get("/api/paper").get_json()
        self.assertIsNone(stored["leaderboard_quant_v2"])
        self.assertIsNone(stored["leaderboard_gold"])
        self.assertIsNone(stored["leaderboard"])

    def test_old_routes_keep_their_pages(self):
        paper = self.client.get("/paper")
        desk = self.client.get("/desk")
        gold = self.client.get("/paper/gold")
        btc = self.client.get("/paper/btc")
        self.assertEqual(paper.status_code, 200)
        self.assertEqual(desk.status_code, 200)
        self.assertEqual(gold.status_code, 200)
        self.assertEqual(btc.status_code, 200)
        paper_html = paper.data.decode()
        desk_html = desk.data.decode()
        gold_html = gold.data.decode()
        btc_html = btc.data.decode()
        self.assertIn("$50 模擬盤成績", paper_html)
        self.assertIn('id="books"', paper_html)
        self.assertIn("SPIDEY 交易台", desk_html)
        self.assertIn("黃金紙盤｜GOLD_V1", gold_html)
        self.assertIn("比特幣紙盤｜BTC_V1", btc_html)
        self.assertNotIn("。", gold_html)
        self.assertNotIn("。", btc_html)
        for html in (paper_html, desk_html, gold_html, btc_html):
            self.assertIn('href="/paper/v2"', html)
            self.assertIn("QUANT V2（實驗）", html)
            self.assertIn('href="/paper/gold"', html)
            self.assertIn('href="/paper/btc"', html)
            self.assertIn('href="/paper"', html)
            self.assertNotIn("PAPER LIVE · QUANT_V2", html)
            self.assertNotIn(DISCLAIMER, html)

    def test_ingest_is_parallel_to_gold(self):
        missing = self.client.post(
            "/api/paper/ingest/leaderboard_quant_v2", data=b"{}", content_type="application/json")
        self.assertEqual(missing.status_code, 503)
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        bad = self.client.post(
            "/api/paper/ingest/leaderboard_quant_v2", data=b"{}", headers={"Authorization": "Bearer nope"})
        self.assertEqual(bad.status_code, 401)
        self.assertNotIn(b"correct-token", bad.data)
        junk = self.client.post(
            "/api/paper/ingest/leaderboard_quant_v2", data=b"not-json", headers=headers)
        self.assertEqual(junk.status_code, 400)
        empty = self.client.post(
            "/api/paper/ingest/leaderboard_quant_v2", data=json.dumps({}), headers=headers)
        self.assertEqual(empty.status_code, 400)
        generic = self.client.post(
            "/api/paper/ingest/leaderboard_quant_v2", data=json.dumps({"equity_usd": 1}), headers=headers)
        self.assertEqual(generic.status_code, 200)
        self.assertEqual(generic.get_json()["book"], "leaderboard_quant_v2")

        gold = self.client.post(
            "/api/paper/ingest/leaderboard_gold",
            data=json.dumps({"matrix_id": "GOLD_V1", "books": [{"id": "G1"}]}),
            headers=headers)
        self.assertEqual(gold.status_code, 200)
        btc = self.client.post(
            "/api/paper/ingest/leaderboard_btc",
            data=json.dumps({"matrix_id": "BTC_V1", "books": [{"id": "B1"}]}),
            headers=headers)
        self.assertEqual(btc.status_code, 200)
        crypto = self.client.post(
            "/api/paper/ingest/crypto",
            data=json.dumps({"config": {"start_usd": 50}, "positions": []}),
            headers=headers)
        self.assertEqual(crypto.status_code, 200)

        payload = {
            "state": {
                "equity_usd": 101.5,
                "cash_usd": 91.25,
                "direction": "SHORT",
                "last_price": 76000.5,
            },
            "fills": [{
                "ts_hkt": "2026-11-07 21:00:00 HKT",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "notional_usd": 11,
                "price": 76000.5,
                "kind": "demo",
            }],
            "config": {"symbol": "BTCUSDT", "venue": "Binance", "interval": "1h", "bars": 48},
        }
        ok = self.client.post(
            "/api/paper/ingest/leaderboard_quant_v2", data=json.dumps(payload), headers=headers)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["fills"], 1)
        paper_store.reset_memory()
        stored = self.client.get("/api/paper").get_json()
        self.assertEqual(stored["leaderboard_gold"]["data"]["books"][0]["id"], "G1")
        self.assertEqual(stored["leaderboard_btc"]["data"]["books"][0]["id"], "B1")
        self.assertEqual(stored["crypto"]["data"]["config"]["start_usd"], 50)
        self.assertEqual(stored["leaderboard_quant_v2"]["data"]["state"]["equity_usd"], 101.5)
        self.assertIsNone(stored["leaderboard"])
        view = self.client.get("/api/paper/v2").get_json()
        self.assertEqual(view["source"], "ingest")
        self.assertTrue(view["stub"])
        self.assertEqual(view["book"]["equity_usd"], 101.5)
        self.assertEqual(view["book"]["cash_usd"], 91.25)
        self.assertEqual(view["book"]["direction"], "SHORT")
        self.assertEqual(view["book"]["last_price"], 76000.5)
        self.assertEqual(view["book"]["fills"][0]["side"], "SELL")
        self.assertEqual(view["disclaimer"], DISCLAIMER)
        page = self.client.get("/paper/v2").data.decode()
        self.assertIn("101.50", page)
        self.assertIn("91.25", page)
        self.assertIn("SHORT", page)
        self.assertIn("做空", page)
        self.assertIn("賣出 SELL", page)
        self.assertIn(DISCLAIMER, page)
        self.assertNotIn("99.99", page)
        gold_page = self.client.get("/paper/gold").data.decode()
        btc_page = self.client.get("/paper/btc").data.decode()
        self.assertNotIn("101.50", gold_page)
        self.assertNotIn("PAPER LIVE · QUANT_V2", gold_page)
        self.assertNotIn("101.50", btc_page)
        self.assertIn("比特幣紙盤｜BTC_V1", btc_page)
        self.assertNotIn("。", btc_page)


if __name__ == "__main__":
    unittest.main()
