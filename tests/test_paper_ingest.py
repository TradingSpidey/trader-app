import json
import os
import tempfile
import unittest

os.environ.setdefault("PAPER_STORE_DIR", tempfile.mkdtemp(prefix="paper-test-"))

from app import app  # noqa: E402
from traderapp import paper_store  # noqa: E402


SAMPLES = "/home/ubuntu/.cursor/projects/workspace/uploads"
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _sample(name):
    roots = [FIXTURES]
    if os.path.isdir(SAMPLES):
        roots.append(SAMPLES)
    for root in roots:
        for fn in sorted(os.listdir(root)):
            if fn.startswith(name) and fn.endswith(".json"):
                with open(os.path.join(root, fn), encoding="utf-8") as fh:
                    return json.load(fh)
    raise AssertionError("missing " + name)


class PaperIngestTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.tmp = tempfile.mkdtemp(prefix="paper-store-")
        os.environ["PAPER_STORE_DIR"] = self.tmp
        os.environ.pop("PAPER_INGEST_TOKEN", None)
        paper_store.reset_memory()

    def test_unset_token_is_503(self):
        res = self.client.post("/api/paper/ingest/crypto", data=b"{}", content_type="application/json")
        self.assertEqual(res.status_code, 503)

    def test_wrong_token_is_401(self):
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        res = self.client.post("/api/paper/ingest/crypto", data=b"{}", headers={"Authorization": "Bearer nope"})
        self.assertEqual(res.status_code, 401)
        self.assertNotIn(b"correct-token", res.data)

    def test_bad_book_and_json(self):
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token"}
        bad = self.client.post("/api/paper/ingest/forex", data=b"{}", headers=headers)
        self.assertEqual(bad.status_code, 400)
        junk = self.client.post("/api/paper/ingest/crypto", data=b"not-json", headers=headers)
        self.assertEqual(junk.status_code, 400)

    def test_ok_and_page(self):
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        crypto = _sample("sample_crypto")
        stocks = _sample("sample_stocks")
        ok = self.client.post("/api/paper/ingest/crypto", data=json.dumps(crypto), headers=headers)
        self.assertEqual(ok.status_code, 200)
        self.assertIn("received_at", ok.get_json())
        ok2 = self.client.post("/api/paper/ingest/stocks", data=json.dumps(stocks), headers=headers)
        self.assertEqual(ok2.status_code, 200)
        paper_store.reset_memory()
        body = self.client.get("/api/paper").get_json()
        self.assertEqual(body["crypto"]["data"]["config"]["start_usd"], 50.0)
        self.assertEqual(body["crypto"]["data"]["positions"][0]["symbol"], "Dacity")
        self.assertEqual(body["stocks"]["data"]["positions"][0]["symbol"], "AVGO")
        self.assertTrue(body["crypto"]["received_at"])
        page = self.client.get("/paper")
        self.assertEqual(page.status_code, 200)
        self.assertIn("$50 模擬盤成績".encode(), page.data)
        self.assertIn("等緊數據傳上嚟".encode(), page.data)
        self.assertIn("模擬盤，唔係真錢，唔係投資建議".encode(), page.data)
        self.assertIn(b"Paper trading only. Not real money. Not investment advice.", page.data)
        self.assertIsNone(body["leaderboard"])

    def test_leaderboard_auth_and_shape(self):
        missing = self.client.post("/api/paper/ingest/leaderboard", data=b"{}", content_type="application/json")
        self.assertEqual(missing.status_code, 503)
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        bad_token = self.client.post(
            "/api/paper/ingest/leaderboard", data=b"{}", headers={"Authorization": "Bearer nope"})
        self.assertEqual(bad_token.status_code, 401)
        self.assertNotIn(b"correct-token", bad_token.data)
        junk = self.client.post("/api/paper/ingest/leaderboard", data=b"not-json", headers=headers)
        self.assertEqual(junk.status_code, 400)
        not_list = self.client.post(
            "/api/paper/ingest/leaderboard", data=json.dumps({"books": "nope"}), headers=headers)
        self.assertEqual(not_list.status_code, 400)
        self.assertIsNone(self.client.get("/api/paper").get_json()["leaderboard"])

    def test_leaderboard_overwrite_and_pages(self):
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        crypto = _sample("sample_crypto")
        self.client.post("/api/paper/ingest/crypto", data=json.dumps(crypto), headers=headers)
        first = {"updated_hkt": "2026-11-06 12:00:00 HKT", "disclaimer": "old", "books": []}
        ok = self.client.post("/api/paper/ingest/leaderboard", data=json.dumps(first), headers=headers)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["book"], "leaderboard")
        sample_path = os.path.join(os.path.dirname(__file__), "fixtures", "leaderboard.sample.json")
        with open(sample_path, encoding="utf-8") as fh:
            sample = json.load(fh)
        sample["books"].append({
            "id": "D00",
            "label": "未開",
            "initialized": False,
            "rank": None,
            "status": "not_started",
            "kill": False,
            "wins": None,
            "closed": None,
            "equity_usd": None,
            "ret_pct": None,
            "params": None,
        })
        sample["books"][0]["positions"] = [{
            "symbol": "TEST",
            "mint": "So11111111111111111111111111111111111111112",
            "side": "long",
            "entry_usd": 1.25,
            "last_usd": 1.3,
            "qty": 10,
            "value_sol": 0.14,
            "upnl_sol": 0.01,
            "ret": 0.04,
            "opened_at": "2026-11-06T12:00:00Z",
            "why": "fixture",
        }]
        sample["books"][0]["trades"] = [{
            "time_hkt": "2026-11-06 20:00:00 HKT",
            "symbol": "TEST",
            "mint": "So11111111111111111111111111111111111111112",
            "side": "buy",
            "price_usd": 1.25,
            "qty": 10,
            "sol": 0.14,
            "reason": "fixture fill",
            "pnl_sol": None,
            "pnl_usd": None,
            "fill_id": "fix-1",
        }]
        again = self.client.post("/api/paper/ingest/leaderboard", data=json.dumps(sample), headers=headers)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.get_json()["books"], 11)
        paper_store.reset_memory()
        body = self.client.get("/api/paper").get_json()
        self.assertEqual(body["crypto"]["data"]["config"]["start_usd"], 50.0)
        board = body["leaderboard"]["data"]
        self.assertEqual(board["updated_hkt"], sample["updated_hkt"])
        self.assertNotEqual(board["updated_hkt"], first["updated_hkt"])
        self.assertEqual(board["books"][0]["id"], "D02")
        self.assertEqual(board["books"][0]["positions"][0]["symbol"], "TEST")
        self.assertEqual(board["books"][0]["positions"][0]["upnl_sol"], 0.01)
        self.assertEqual(board["books"][0]["trades"][0]["fill_id"], "fix-1")
        self.assertIsNone(board["books"][0]["trades"][0]["pnl_sol"])
        self.assertEqual(board["books"][-1]["rank"], None)
        self.assertEqual(board["books"][-1]["status"], "not_started")
        page = self.client.get("/paper")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'href="/paper/demo"', page.data)
        self.assertIn(b'id="books"', page.data)
        demo = self.client.get("/paper/demo")
        self.assertEqual(demo.status_code, 200)
        demo_text = demo.data.decode()
        title = "Demo 排行榜（78 本 · 角色交叉組合 V6）"
        sub = "CTRL 對照；CX＝E×K×N×S0G0；QX＝同網格×S1G1 品質；AX＝E1/E2×K×N×S2G2 進攻；ZX＝SCAN/RUG 混拼。預設顯示持倉同成交同 combo。"
        self.assertEqual(demo_text.count(title), 3)
        self.assertIn(sub, demo_text)
        page_home = page.data.decode()
        self.assertIn(title, page_home)
        self.assertIn("並行 Demo 係 78 本交叉組合（CTRL + CX/QX/AX/ZX）。", page_home)
        js_path = os.path.join(os.path.dirname(__file__), "..", "static", "paper.js")
        with open(js_path, encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("等緊 Demo 排行榜傳上嚟。", js)
        self.assertIn("本交叉組合（CTRL + CX/QX/AX/ZX）", js)
        self.assertIn(': "78"', js)
        self.assertIn("bookCombo", js)
        self.assertIn("matrixWait", js)
        self.assertIn("(Array.isArray(d.books) ? d.books : [])", js)
        self.assertIn("rows.map(demoBookDetail)", js)
        self.assertNotIn("books.slice", js)
        self.assertNotIn("rows.slice", js)
        for stale in ("51 本", "43 本", "V4", "V5", "MX", "單角色", "R0–R9", "十本", "角色矩陣", "EXIT/RISK"):
            self.assertNotIn(stale, demo_text)
            self.assertNotIn(stale, page_home)
            self.assertNotIn(stale, js)
        self.assertNotIn("D01–D10", page_home)
        self.assertNotIn("D01–D10", demo_text)
        self.assertIn("模擬盤，唔係真錢，唔係投資建議".encode(), demo.data)
        self.assertIn(b"Paper trading only. Not real money. Not investment advice.", demo.data)
        self.assertNotIn(b'id="books"', demo.data)
        self.assertIn("等緊 Demo 排行榜傳上嚟".encode(), demo.data)
        self.assertNotIn(b'id="funnel"', demo.data)

    def test_leaderboard_keeps_every_book(self):
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        books = [{
            "id": "B%02d" % i,
            "label": "book-%d" % i,
            "combo": "E1-K0-N1-S1-G1",
            "rank": i + 1,
            "initialized": True,
            "status": "running",
            "kill": False,
            "equity_usd": 50,
            "ret_pct": 0,
            "wins": 0,
            "closed": 0,
            "positions": [],
            "trades": [],
            "params": {},
        } for i in range(78)]
        books[0]["positions"] = [{"symbol": "TEST", "ret": 0.01}]
        books[0]["trades"] = [{"symbol": "TEST", "side": "buy"}]
        payload = {
            "updated_hkt": "2026-11-06 21:00:00 HKT",
            "book_count": 78,
            "matrix_version": 6,
            "matrix_label": "MATRIX_V6",
            "books": books,
        }
        res = self.client.post("/api/paper/ingest/leaderboard", data=json.dumps(payload), headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["books"], 78)
        paper_store.reset_memory()
        board = self.client.get("/api/paper").get_json()["leaderboard"]["data"]
        self.assertEqual(board["book_count"], 78)
        self.assertEqual(board["matrix_version"], 6)
        self.assertEqual(len(board["books"]), 78)
        self.assertEqual([b["id"] for b in board["books"]], ["B%02d" % i for i in range(78)])
        self.assertEqual(board["books"][0]["combo"], "E1-K0-N1-S1-G1")
        self.assertEqual(board["books"][0]["positions"][0]["symbol"], "TEST")
        self.assertEqual(board["books"][0]["trades"][0]["side"], "buy")
        self.assertEqual(board["books"][-1]["id"], "B77")

    def test_funnel_passthrough_and_page(self):
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        crypto = _sample("sample_crypto")
        crypto["funnel"] = {
            "disclaimer": "模擬盤 Copy Funnel",
            "scout": {"wallets_n": 12, "flow_n": 40, "matched": 7, "min_buy_usd": 500},
            "stages": [
                {"id": "scout", "label": "Scout", "seen": 40, "passed": 12, "skipped": 28, "detail": "錢包"},
                {"id": "filter", "label": "Filter", "seen": 12, "passed": 8, "skipped": 4, "detail": "流動性"},
                {"id": "analyst", "label": "Analyst", "seen": 8, "passed": 3, "skipped": 5, "detail": "分析"},
                {"id": "sniper", "label": "Sniper", "seen": 3, "passed": 1, "skipped": 2, "detail": "入場"},
                {"id": "guard", "label": "Guard", "seen": 1, "passed": 1, "skipped": 0, "detail": "風控"},
            ],
            "events": [
                {"ts": "2026-11-06T12:00:00Z", "action": "skip", "stage": "Filter", "symbol": "SKIP", "reason": "流動性不足"},
                {"ts": "2026-11-06T12:01:00Z", "action": "copy", "stage": "Guard", "symbol": "COPY", "reason": "過晒風控"},
            ],
        }
        ok = self.client.post("/api/paper/ingest/crypto", data=json.dumps(crypto), headers=headers)
        self.assertEqual(ok.status_code, 200)
        paper_store.reset_memory()
        body = self.client.get("/api/paper").get_json()
        funnel = body["crypto"]["data"]["funnel"]
        self.assertEqual([s["label"] for s in funnel["stages"]], ["Scout", "Filter", "Analyst", "Sniper", "Guard"])
        self.assertEqual(funnel["stages"][0]["seen"], 40)
        self.assertEqual([e["action"] for e in funnel["events"]], ["skip", "copy"])
        page = self.client.get("/paper")
        self.assertIn(b'id="funnel"', page.data)
        self.assertIn("Copy Funnel（模擬）".encode(), page.data)
        self.assertIn("Scout→Filter→Analyst→Sniper→Guard".encode(), page.data)
        self.assertIn("數字嚟自引擎，唔係宣傳回報".encode(), page.data)
        self.assertIn("模擬盤，唔係真錢，唔係投資建議".encode(), page.data)
        demo = self.client.get("/paper/demo")
        self.assertNotIn(b'id="funnel"', demo.data)
        self.assertIn(b'id="leaderboard"', demo.data)

    def test_stocks_leaderboard_is_separate(self):
        missing = self.client.post("/api/paper/ingest/leaderboard_stocks", data=b"{}", content_type="application/json")
        self.assertEqual(missing.status_code, 503)
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        bad = self.client.post(
            "/api/paper/ingest/leaderboard_stocks", data=b"{}", headers={"Authorization": "Bearer nope"})
        self.assertEqual(bad.status_code, 401)
        not_list = self.client.post(
            "/api/paper/ingest/leaderboard_stocks", data=json.dumps({"books": "nope"}), headers=headers)
        self.assertEqual(not_list.status_code, 400)
        crypto_books = [{"id": "C0", "label": "crypto", "combo": "CX", "rank": 1, "equity_usd": 50, "positions": [], "trades": []}]
        crypto = self.client.post(
            "/api/paper/ingest/leaderboard",
            data=json.dumps({"book_count": 1, "books": crypto_books, "matrix_version": 6}),
            headers=headers)
        self.assertEqual(crypto.status_code, 200)
        self.assertEqual(crypto.get_json()["book"], "leaderboard")
        books = []
        for i in range(36):
            books.append({
                "id": "S%02d" % i,
                "label": "stock-%d" % i,
                "combo": "E1K0N1S0",
                "family": "SX" if i else "CTRL",
                "rank": i + 1,
                "initialized": True,
                "status": "running",
                "kill": False,
                "equity_usd": 50,
                "ret_pct": 0,
                "wins": 0,
                "closed": 0,
                "positions": [],
                "trades": [],
                "params": {"combo": "E1K0N1S0", "family": "SX" if i else "CTRL"},
            })
        books[0]["positions"] = [{"symbol": "AVGO", "entry_usd": 10, "last_usd": 11, "ret": 0.1, "value_usd": 11, "upnl_usd": 1}]
        books[0]["trades"] = [{"symbol": "AVGO", "side": "buy", "price": 10, "qty": 1, "pnl_usd": None, "reason": "fixture"}]
        payload = {
            "market": "stocks",
            "matrix_version": 1,
            "book_count": 36,
            "updated_hkt": "2026-11-06 21:10:00 HKT",
            "books": books,
        }
        res = self.client.post("/api/paper/ingest/leaderboard_stocks", data=json.dumps(payload), headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["book"], "leaderboard_stocks")
        self.assertEqual(res.get_json()["books"], 36)
        paper_store.reset_memory()
        body = self.client.get("/api/paper").get_json()
        self.assertEqual(body["leaderboard"]["data"]["books"][0]["id"], "C0")
        board = body["leaderboard_stocks"]["data"]
        self.assertEqual(board["market"], "stocks")
        self.assertEqual(board["matrix_version"], 1)
        self.assertEqual(board["book_count"], 36)
        self.assertEqual(len(board["books"]), 36)
        self.assertEqual([b["id"] for b in board["books"]], ["S%02d" % i for i in range(36)])
        self.assertEqual(board["books"][0]["family"], "CTRL")
        self.assertEqual(board["books"][0]["combo"], "E1K0N1S0")
        self.assertEqual(board["books"][0]["positions"][0]["symbol"], "AVGO")
        self.assertEqual(board["books"][0]["trades"][0]["side"], "buy")
        self.assertEqual(board["books"][-1]["id"], "S35")
        page = self.client.get("/paper")
        self.assertIn("美股 Demo 排行".encode(), page.data)
        self.assertIn(b'href="/paper/demo/stocks"', page.data)
        stocks = self.client.get("/paper/demo/stocks")
        self.assertEqual(stocks.status_code, 200)
        text = stocks.data.decode()
        title = "Demo 排行榜（36 本 · 美股交叉組合 V1）"
        sub = "CTRL 對照；SX＝E×K×N×S0；QX＝S1 品質；AX＝S2 進攻；ZX＝邊角／N2 歸因"
        self.assertEqual(text.count(title), 3)
        self.assertIn(sub, text)
        self.assertIn("模擬盤，唔係真錢，唔係投資建議", text)
        self.assertIn('data-market="stocks"', text)
        self.assertNotIn('id="books"', text)
        self.assertNotIn('id="funnel"', text)
        self.assertIn('id="leaderboard"', text)
        crypto_page = self.client.get("/paper/demo").data.decode()
        self.assertEqual(crypto_page.count("Demo 排行榜（78 本 · 角色交叉組合 V6）"), 3)
        self.assertNotIn(title, crypto_page)

    def test_methods_leaderboard_is_separate(self):
        missing = self.client.post("/api/paper/ingest/leaderboard_methods", data=b"{}", content_type="application/json")
        self.assertEqual(missing.status_code, 503)
        os.environ["PAPER_INGEST_TOKEN"] = "correct-token"
        headers = {"Authorization": "Bearer correct-token", "Content-Type": "application/json"}
        bad = self.client.post(
            "/api/paper/ingest/leaderboard_methods", data=b"{}", headers={"Authorization": "Bearer nope"})
        self.assertEqual(bad.status_code, 401)
        self.assertNotIn(b"correct-token", bad.data)
        not_list = self.client.post(
            "/api/paper/ingest/leaderboard_methods", data=json.dumps({"books": "nope"}), headers=headers)
        self.assertEqual(not_list.status_code, 400)
        crypto = self.client.post(
            "/api/paper/ingest/leaderboard",
            data=json.dumps({"book_count": 1, "books": [{"id": "C0", "label": "crypto"}]}),
            headers=headers)
        self.assertEqual(crypto.status_code, 200)
        stocks = self.client.post(
            "/api/paper/ingest/leaderboard_stocks",
            data=json.dumps({"market": "stocks", "book_count": 1, "books": [{"id": "S0", "label": "stock"}]}),
            headers=headers)
        self.assertEqual(stocks.status_code, 200)
        sample = _sample("methods_leaderboard")
        res = self.client.post(
            "/api/paper/ingest/leaderboard_methods", data=json.dumps(sample), headers=headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["book"], "leaderboard_methods")
        self.assertEqual(body["books"], 5)
        paper_store.reset_memory()
        api = self.client.get("/api/paper").get_json()
        self.assertEqual(api["leaderboard"]["data"]["books"][0]["id"], "C0")
        self.assertEqual(api["leaderboard_stocks"]["data"]["books"][0]["id"], "S0")
        board = api["leaderboard_methods"]["data"]
        self.assertEqual(board["matrix_id"], "METHODS_V1")
        self.assertEqual(board["start_usd"], 100.0)
        self.assertEqual(board["book_count"], 5)
        books = {b["id"]: b for b in board["books"]}
        self.assertEqual(list(books), ["M1", "M4", "M3", "M2", "M5"])
        self.assertEqual(books["M1"]["name_zh"], "動量突破")
        self.assertEqual(books["M1"]["name_en"], "Momentum Breakout")
        self.assertEqual(books["M1"]["equity_usd"], 99.97)
        self.assertEqual(books["M1"]["positions"][0]["symbol"], "KO")
        self.assertEqual(books["M1"]["backtest"]["warning_flags"], [])
        self.assertEqual(books["M2"]["name_zh"], "均線趨勢")
        self.assertEqual(books["M2"]["backtest"]["warning_flags"], ["回測DD>15%"])
        self.assertEqual(books["M3"]["label"], "M3 VolBreak｜波動突破")
        self.assertEqual(books["M3"]["backtest"]["warning_flags"], ["回測DD>15%", "回測淨利≤0"])
        self.assertIn("逆勢", books["M4"]["warning"])
        self.assertIn("策略警示", books["M4"]["backtest"]["warning_flags"])
        self.assertEqual(books["M5"]["name_en"], "Cross-Sectional Momentum")
        self.assertEqual(books["M5"]["label"], "M5 XSecMom｜相對強弱")
        self.assertIn("回測DD>15%", books["M5"]["backtest"]["warning_flags"])
        self.assertIsNone(books["M1"]["win_rate_pct"])
        page = self.client.get("/paper")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'href="/paper/methods"', page.data)
        self.assertIn(b'id="books"', page.data)
        self.assertIn(b'id="funnel"', page.data)
        self.assertIn(b'id="leaderboard"', page.data)
        methods = self.client.get("/paper/methods")
        self.assertEqual(methods.status_code, 200)
        text = methods.data.decode()
        self.assertEqual(text.count("五方法紙盤｜METHODS_V1"), 3)
        self.assertIn("五方法紙盤｜METHODS_V1｜各 $100", text)
        for label in (
            "M1 MomBreak｜動量突破",
            "M2 TrendMA｜均線趨勢",
            "M3 VolBreak｜波動突破",
            "M4 MeanRev｜均值回歸",
            "M5 XSecMom｜相對強弱",
        ):
            self.assertIn(label, text)
        self.assertIn("模擬盤，唔係真錢，唔係投資建議", text)
        self.assertIn("Paper trading only. Not real money. Not investment advice.", text)
        self.assertIn("7 日紙盤淨利 > 0 優先晉級", text)
        self.assertIn("maxDD ≤ 15%", text)
        self.assertIn("平倉 ≥ 15 先認真比較", text)
        self.assertIn("唔保證盈利｜模擬盤", text)
        self.assertNotIn("。", text)
        self.assertIn('id="methods"', text)
        self.assertIn('data-methods="1"', text)
        self.assertNotIn('id="books"', text)
        self.assertNotIn('id="funnel"', text)
        self.assertNotIn('id="leaderboard"', text)
        js_path = os.path.join(os.path.dirname(__file__), "..", "static", "paper.js")
        with open(js_path, encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("leaderboard_methods", js)
        self.assertIn("methodsHtml", js)
        self.assertIn("WARNING", js)
        for label in ("M1 MomBreak｜動量突破", "M3 VolBreak｜波動突破", "M5 XSecMom｜相對強弱"):
            self.assertIn(label, js)
        demo = self.client.get("/paper/demo")
        stocks_page = self.client.get("/paper/demo/stocks")
        desk = self.client.get("/desk")
        self.assertEqual(demo.status_code, 200)
        self.assertEqual(stocks_page.status_code, 200)
        self.assertEqual(desk.status_code, 200)
        self.assertIn("Demo 排行榜（78 本 · 角色交叉組合 V6）", demo.data.decode())
        self.assertIn("Demo 排行榜（36 本 · 美股交叉組合 V1）", stocks_page.data.decode())
        self.assertNotIn("METHODS_V1", demo.data.decode())
        self.assertNotIn("METHODS_V1", stocks_page.data.decode())
        self.assertIn(b'id="books"', self.client.get("/paper").data)
        self.assertNotIn(b'id="methods"', demo.data)


if __name__ == "__main__":
    unittest.main()
