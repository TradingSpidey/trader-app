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
app.py                      Flask routes (/api/run, /api/bars, /api/scan, /api/analyst, /api/pelosi, /api/ptr, /healthz)
traderapp/pipeline.py       runs the vendored tools as subprocesses, validates input, caches
templates/ static/          the UI (vanilla JS, no build step)
vendor/day-trader-skill/    upstream tools (MIT, commit in UPSTREAM_COMMIT; tests folder removed)
```

## Data and limits

Yahoo Finance's chart endpoint is free, unofficial, delayed and can rate-limit; a busy public
deployment will hit those limits. The scan is limited to ~100 names for speed. The time machine is
a simulation from the stock's last ~60 sessions, not a prediction, and ignores slippage and fees.

## Licence

App code: MIT. Vendored tools: MIT, © Jake Schincariol (see vendor/day-trader-skill/LICENSE).
