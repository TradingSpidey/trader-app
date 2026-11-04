import json
import os
import tempfile
import unittest

os.environ.setdefault("PAPER_STORE_DIR", tempfile.mkdtemp(prefix="paper-test-"))

from app import app  # noqa: E402
from traderapp import paper_store  # noqa: E402


SAMPLES = "/home/ubuntu/.cursor/projects/workspace/uploads"


def _sample(name):
    for fn in os.listdir(SAMPLES):
        if fn.startswith(name) and fn.endswith(".json"):
            with open(os.path.join(SAMPLES, fn), encoding="utf-8") as fh:
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


if __name__ == "__main__":
    unittest.main()
