# 即日鮮研究室 (trader-app)

A small, mobile-friendly web app in Traditional Chinese (Hong Kong Cantonese) on top of the
open-source [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) tools (MIT).

**Research and education only. Not financial advice. Paper trading only:** the app has no broker
connection, stores no credentials, and cannot place an order. The last step only *renders* the
ticket with `trader-broker/ticket.py show`, which contains no network code.

## What it does

| Tab | What it runs |
| --- | --- |
| 分析一隻股 | news → entry check (15-min opening-range breakout on 5-min bars) → exit plan (stop at range midpoint, 1R target) → time machine (10,000 replays, seed 19) → position size → risk check → paper ticket |
| 掃描市場 | opening-range breakout or daily-pattern scan over ~100 liquid US names; click a hit to analyse it |
| 業績 | SEC XBRL quarterly revenue, margins, growth (needs `SEC_USER_AGENT`) |
| 議員交易 | House Clerk periodic transaction reports for a member (default Pelosi); reads the PDF with `pdftotext` |
| SPIDEY 交易台 (`/desk`) | crypto desk (GeckoTerminal + DexScreener + Solana RPC) and a US-stock desk (Yahoo + House filings). Paper only. The web book is in memory and resets when the process sleeps |

## Headless paper runner

The website book is wiped when the free instance sleeps. To keep a book on another machine:

```bash
python -m traderapp.desk_runner --market stocks --start-usd 50 --state-dir /var/spidey/stocks
python -m traderapp.desk_runner --market crypto --state-dir /var/spidey/crypto --once
```

`--start-usd` is used only when `state.json` does not exist yet (stocks). The default web starting cash is `$DESK_STOCK_START_USD` or $10,000. Each loop writes `state.json`, and appends `trades.csv` and `equity.csv`. Restarting reloads `state.json`. US stocks open new paper trades only during the New York regular session (09:30–16:00), which is 22:30–05:00 Hong Kong time while the US is on standard time. No wallet, no orders.

US-stock paper fills are worse than the Yahoo quote by `DESK_STOCK_SLIPPAGE_PER_SIDE` (default 0.1% per side: buys above the quote, sells below it) and pay `DESK_STOCK_COMMISSION_USD` (default $0.01 minimum on each buy and each sell). Optional `DESK_STOCK_COMMISSION_RATE` (default 0, a fraction of the fill notional) cannot reduce that minimum. Cash, cost basis, and realized PnL include those costs on each new fill. Positions already open keep the cost basis they were filled with; the next sell still pays sell-side slippage and commission. The Solana paper desk is unchanged. The time machine on the research page is a separate simulation and still ignores slippage and fees.

The always-on machine can publish its two $50 books to the site (this is separate from the in-browser demo book, which resets when Render sleeps):

```bash
curl -X POST -H "Authorization: Bearer $PAPER_INGEST_TOKEN" -H "Content-Type: application/json" \
  --data-binary @crypto.json https://<host>/api/paper/ingest/crypto
```

`stocks` is the other book name. The page is `/paper`. If `PAPER_INGEST_TOKEN` is unset the ingest endpoint returns 503.

The same token accepts the latest D01–D10 demo leaderboard (overwrite). No new environment variable:

```bash
curl -X POST -H "Authorization: Bearer $PAPER_INGEST_TOKEN" -H "Content-Type: application/json" \
  --data-binary @leaderboard.json https://<host>/api/paper/ingest/leaderboard
```

`GET /api/paper` adds `leaderboard` (`null` before the first push). The ranked table is on `/paper` and `/paper/demo`. The snapshot is `PAPER_STORE_DIR/leaderboard.json` (default `/tmp/paper_store`), same ephemeral disk as the two books: a restart drops it until the always-on machine pushes again.

`/paper` renders `crypto.data.funnel` when the always-on engine includes it: Scout→Filter→Analyst→Sniper→Guard counts (`seen` / `passed` / `skipped`) and the skipped/copied event log. Those numbers are the engine's own counts. Until a funnel object arrives, the section stays on the waiting line. `/paper/demo` does not show the funnel.

When the US market is closed, the app replays the latest completed session at 10:15 AM New York
time (or the time you type, 09:50–15:30) using the tools' `--now` option. While the market is open
it uses the current (delayed) bars. `/api/bars` returns that same session's closed 5-minute bars
for the chart. Price lines and the Monte Carlo histogram are drawn only from fields the pipeline
actually returns.

Each run happens in its own temporary folder, so no state is shared between users. Identical
requests are cached for 10 minutes to be polite to the free data sources.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export SEC_USER_AGENT="Your Name you@example.com"   # optional; enables SEC filings and the earnings tab
./run.sh                                            # http://localhost:8080
```

Needs Python 3.8+, and `pdftotext` (poppler-utils) for reading congressional PDFs. Or:

```bash
docker build -t trader-app . && docker run -p 8080:8080 -e SEC_USER_AGENT="Your Name you@example.com" trader-app
```

## Layout

```
app.py                      Flask routes (/api/run, /api/bars, /api/scan, /api/analyst, /api/pelosi, /api/ptr, /api/desk/*, /healthz)
traderapp/pipeline.py       runs the vendored tools as subprocesses, validates input, caches
traderapp/desk.py           crypto paper desk
traderapp/desk_stocks.py    US stock paper desk
traderapp/desk_runner.py    headless loop with JSON and CSV persistence
templates/ static/          the UI (vanilla JS, no build step)
vendor/day-trader-skill/    upstream tools (MIT, commit in UPSTREAM_COMMIT; tests folder removed)
```

## Data and limits

Yahoo Finance's chart endpoint is free, unofficial, delayed and can rate-limit; a busy public
deployment will hit those limits. The scan is limited to ~100 names for speed. The time machine is
a simulation from the stock's last ~60 sessions, not a prediction, and ignores slippage and fees.

## Licence

App code: MIT. Vendored tools: MIT, © Jake Schincariol (see vendor/day-trader-skill/LICENSE).
