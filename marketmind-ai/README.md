# MarketMind AI — Integrated research release (Phases 1–4)

A mobile-first, local-first financial research and education application. This release combines the original PWA and technical indicators with source-linked RSS headlines, SEC issuer facts, a transparent daily moving-average backtest, PDF text extraction and export, a virtual-only portfolio, and a trading journal.

> **Risk notice:** This is an educational research tool, not personalized financial advice. It does not execute trades, promise returns, or produce calibrated directional probabilities. Missing market data is shown as unavailable. Historical backtests are not evidence of future performance.

## What is implemented

- **Phase 1:** responsive PWA, local watchlists, theme, symbol helper, optional Alpha Vantage daily history, deterministic SMA/EMA/RSI/MACD/Bollinger/ATR, forex risk sizing, education.
- **Phase 2:** public RSS headline collection with original links and publisher labels; SEC EDGAR Company Facts lookup for US SEC filers. Headlines are not rumor verification. SEC facts include their filing period/date/unit metadata and are not silently combined into ratios.
- **Phase 3:** daily long/cash SMA crossover backtest with fees and slippage assumptions, equity curve, maximum drawdown, daily annualized Sharpe where computable, trade events and explicit limitations. It requires actual provider history and is not run on fabricated data.
- **Phase 4:** PDF text extraction (8 MB / 100 pages), page references for selected financial topics, SQLite report metadata, PDF export, virtual positions and a trading journal. Uploaded files are processed by the configured backend; no external AI provider receives them.

## Environment and run

Requirements: Python 3.10+.

```bash
cd marketmind-ai
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r backend/requirements.txt
cp .env.example .env
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`; API docs: `http://localhost:8000/docs`.

### Test from an Android phone on the same Wi-Fi

1. Connect the phone and computer to the same Wi-Fi network.
2. Find the computer's local IPv4 address.
3. Start the server with `--host 0.0.0.0` as above.
4. Allow inbound TCP port 8000 through the computer firewall on the private network.
5. Open `http://COMPUTER-IP:8000` on the phone.
6. For PWA installation outside localhost, deploy over HTTPS. The local Wi-Fi HTTP address is for immediate testing only.

### Static PWA route

A GitHub Pages workflow is included. Push the project to a GitHub repository on `main`, select **Settings → Pages → GitHub Actions**, then run **Deploy MarketMind AI PWA** from the Actions tab. Open the deployment URL on Android Chrome and use **Add to Home screen** / **Install app** if offered.

The static PWA does not host the Python API. For API features, deploy the backend separately over HTTPS, set `window.MARKETMIND_API_BASE` in `frontend/config.js`, and configure `CORS_ORIGINS` to the exact frontend origin.

## Optional data configuration

- `ALPHA_VANTAGE_API_KEY`: enables daily history for supported symbols. Provider limits and exchange coverage apply. This release does not claim live US stock quotes or complete global coverage.
- `SEC_USER_AGENT`: set an identifiable application/contact user agent in accordance with SEC fair-access guidance. The default is a placeholder and should be replaced before external use.
- `MARKETMIND_DB`: optional SQLite path; default is project-root `marketmind.sqlite3`.
- `CORS_ORIGINS`: comma-separated exact frontend origins.

No secrets belong in the frontend bundle or APK. `.env.example` contains no credentials.

## New API endpoints

- `GET /api/news?limit=20` — fetch allowlisted RSS headlines; includes publisher, URL, timestamp when present, feed errors and a verification disclaimer.
- `GET /api/fundamentals/{ticker}` — SEC Company Facts for supported US SEC filers; missing facts remain null.
- `POST /api/backtest/{symbol}` — daily SMA crossover. JSON fields: `fast_period`, `slow_period`, `initial_balance`, `fee_bps`, `slippage_bps`.
- `POST /api/reports/analyze` — multipart PDF extraction; returns page text and topic/page references.
- `GET /api/reports` and `GET /api/reports/{id}/export` — saved report metadata and readable PDF export.
- `GET/POST /api/portfolio`, `DELETE /api/portfolio/{id}` — virtual positions only.
- `GET/POST /api/journal` — local research/trade notes.

Existing `/api/market`, `/api/watchlist`, `/api/forex/position-size`, `/api/education` endpoints remain available.

## Important limitations

- RSS headlines are source-linked publisher content, not independent corroboration or an automated misinformation verdict. No rumors are fabricated or classified as confirmed.
- SEC data is US-filer focused. Company facts can have different units, periods and reporting dates; compare those fields before ratios or valuation conclusions. No global issuer coverage is implied.
- FRED macro integration, broad global fundamentals, licensed analyst estimates, calibrated models, multi-regime out-of-sample validation, advanced strategy builder, and real-time/intraday feeds remain incomplete.
- Backtest is a basic long/cash SMA crossover on available daily history. It does not currently adjust for dividends, taxes, short borrow, market impact, survivorship bias or delisted securities. It models configured turnover costs and uses next-bar application of close-derived signals.
- PDF module extracts embedded text only. Scanned PDFs need OCR (not enabled); complex tables, footnotes and multi-column layouts may parse incorrectly. It does not perform complete accounting reconciliation or AI valuation. Review cited page references and source document.
- Virtual portfolio records entry details but does not fetch marks, calculate current unrealized P/L, or connect to a broker.
- No authentication, production rate limiting, encrypted database, public deployment hardening, AI provider, or alert delivery is included. Do not expose an unprotected backend to the public internet.

## Android APK

The environment used for the original MVP did not contain Android SDK/Gradle/adb. `.github/workflows/android-apk.yml` builds a debug APK on a GitHub-hosted Android runner. Push the source to `main`, open **Actions → Build MarketMind AI Android APK → Run workflow**, then download the `marketmind-ai-debug-apk` artifact from a successful run. That workflow is a build path, not proof an APK has already been built or installed. Backend-dependent functionality needs a reachable HTTPS API URL configured before rebuilding the app.

## Automated tests

```bash
pip install -r backend/requirements.txt
PYTHONPATH=backend pytest -q backend/tests
node --check frontend/app.js
```

See `docs/TEST_REPORT.md` for the observed run and blocked checks.
