"""Trader 研究室: a small web front end for the day-trader-skill tools. Paper trading only."""
import os
import sys

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from traderapp import desk, pipeline  # noqa: E402

app = Flask(__name__)


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


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/favicon.ico")
def favicon():
    return "", 204


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8080")))
