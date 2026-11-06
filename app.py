"""Trader 研究室: a small web front end for the day-trader-skill tools. Paper trading only."""
import hmac
import os
import sys

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from traderapp import desk, desk_stocks, paper_store, pipeline  # noqa: E402

app = Flask(__name__)


@app.after_request
def _desk_assets_revalidate(resp):
    path = request.path or ""
    if path == "/desk" or path.startswith("/static/desk."):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


def _num(name, default):
    v = (request.args.get(name) or "").replace(",", "").replace("$", "").strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        raise pipeline.RunError("%s 要係數字" % name)


def _wrap(fn):
    try:
        return jsonify(fn())
    except pipeline.RunError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # honest error, no stack trace to the browser
        app.logger.exception("request failed")
        return jsonify({"error": "伺服器出錯：%s" % e.__class__.__name__}), 500


@app.get("/")
def index():
    return render_template("index.html", sec=bool(pipeline.SEC_UA))


@app.get("/api/session")
def api_session():
    return _wrap(lambda: pipeline.pick_session(request.args.get("time") or None))


@app.get("/api/run")
def api_run():
    return _wrap(lambda: pipeline.run_pipeline(request.args.get("ticker", "TSLA"), _num("budget", 5000.0),
                                               _num("max_loss", 50.0), request.args.get("time") or None))


@app.get("/api/bars")
def api_bars():
    return _wrap(lambda: pipeline.run_bars(request.args.get("ticker", ""), request.args.get("time") or None))


@app.get("/api/scan")
def api_scan():
    return _wrap(lambda: pipeline.run_scan(request.args.get("mode", "orb"), request.args.get("time") or None))


@app.get("/api/analyst")
def api_analyst():
    return _wrap(lambda: pipeline.run_analyst(request.args.get("ticker", "")))


@app.get("/api/pelosi")
def api_pelosi():
    return _wrap(lambda: pipeline.run_pelosi(request.args.get("member", "pelosi")))


@app.get("/api/ptr")
def api_ptr():
    return _wrap(lambda: pipeline.run_ptr_fetch(request.args.get("doc", ""), request.args.get("year")))


@app.get("/desk")
def desk_page():
    return render_template("desk.html")


@app.get("/api/desk/state")
def api_desk_state():
    return _wrap(desk.snapshot)


@app.get("/api/desk/log")
def api_desk_log():
    return _wrap(desk.log_view)


@app.post("/api/desk/kill")
def api_desk_kill():
    body = request.get_json(silent=True) or {}
    if "on" in body:
        on = bool(body.get("on"))
    else:
        on = (request.args.get("on") or "1").strip().lower() not in ("0", "false", "off")
    return _wrap(lambda: desk.set_kill(on))


@app.post("/api/desk/reset")
def api_desk_reset():
    return _wrap(desk.reset)


@app.get("/api/desk/stocks/state")
def api_desk_stocks_state():
    return _wrap(desk_stocks.snapshot)


@app.get("/api/desk/stocks/log")
def api_desk_stocks_log():
    return _wrap(desk_stocks.log_view)


@app.post("/api/desk/stocks/kill")
def api_desk_stocks_kill():
    body = request.get_json(silent=True) or {}
    if "on" in body:
        on = bool(body.get("on"))
    else:
        on = (request.args.get("on") or "1").strip().lower() not in ("0", "false", "off")
    return _wrap(lambda: desk_stocks.set_kill(on))


@app.post("/api/desk/stocks/reset")
def api_desk_stocks_reset():
    return _wrap(desk_stocks.reset)


def _bearer():
    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer "):
        return ""
    return header[7:].strip()


def _ingest_denied():
    token = os.environ.get("PAPER_INGEST_TOKEN") or ""
    if not token:
        return jsonify({"error": "未設定接收權杖"}), 503
    got = _bearer()
    if not got or not hmac.compare_digest(got, token):
        return jsonify({"error": "未授權"}), 401
    if request.content_length is not None and request.content_length > paper_store.MAX_BODY:
        return jsonify({"error": "內容太大"}), 400
    return None


@app.post("/api/paper/ingest/leaderboard")
def api_paper_ingest_leaderboard():
    denied = _ingest_denied()
    if denied:
        return denied
    raw = request.get_data(cache=False) or b""
    body, code = paper_store.ingest_leaderboard(raw)
    return jsonify(body), code


@app.post("/api/paper/ingest/leaderboard_stocks")
def api_paper_ingest_leaderboard_stocks():
    denied = _ingest_denied()
    if denied:
        return denied
    raw = request.get_data(cache=False) or b""
    body, code = paper_store.ingest_leaderboard(raw, paper_store.LEADERBOARD_STOCKS)
    return jsonify(body), code


@app.post("/api/paper/ingest/leaderboard_methods")
def api_paper_ingest_leaderboard_methods():
    denied = _ingest_denied()
    if denied:
        return denied
    raw = request.get_data(cache=False) or b""
    body, code = paper_store.ingest_leaderboard(raw, paper_store.LEADERBOARD_METHODS)
    return jsonify(body), code


@app.post("/api/paper/ingest/<book>")
def api_paper_ingest(book):
    denied = _ingest_denied()
    if denied:
        return denied
    raw = request.get_data(cache=False) or b""
    body, code = paper_store.ingest(book, raw)
    return jsonify(body), code


@app.get("/api/paper")
def api_paper():
    return jsonify(paper_store.load_all())


@app.get("/paper")
def paper_page():
    return render_template("paper.html", demo_only=False, stocks_demo=False, methods_demo=False)


@app.get("/paper/methods")
def paper_methods_page():
    return render_template("paper.html", demo_only=False, stocks_demo=False, methods_demo=True)


@app.get("/paper/demo/stocks")
def paper_demo_stocks_page():
    return render_template("paper.html", demo_only=True, stocks_demo=True, methods_demo=False)


@app.get("/paper/demo")
def paper_demo_page():
    return render_template("paper.html", demo_only=True, stocks_demo=False, methods_demo=False)


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/favicon.ico")
def favicon():
    return "", 204


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8080")))
