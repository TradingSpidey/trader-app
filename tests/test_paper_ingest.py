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
        self.assertEqual(board["books"][-1]["rank"], None)
        self.assertEqual(board["books"][-1]["status"], "not_started")
        page = self.client.get("/paper")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'href="/paper/demo"', page.data)
        self.assertIn(b'id="books"', page.data)
        demo = self.client.get("/paper/demo")
        self.assertEqual(demo.status_code, 200)
        self.assertIn("Demo 排行榜 D01–D10".encode(), demo.data)
        self.assertIn("模擬盤，唔係真錢，唔係投資建議".encode(), demo.data)
        self.assertIn(b"Paper trading only. Not real money. Not investment advice.", demo.data)
        self.assertNotIn(b'id="books"', demo.data)
        self.assertIn("等緊 Demo 排行榜傳上嚟".encode(), demo.data)


if __name__ == "__main__":
    unittest.main()
