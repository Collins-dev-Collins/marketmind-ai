# MarketMind AI — Integrated phases 1–4 test report

Test date: 2026-11-14 (execution environment date).

## Automated checks

- Backend pytest: **25 passed** in the final post-change run.
- Frontend JavaScript syntax: `node --check frontend/app.js` — passed.
- Python bytecode compilation: `python -m compileall -q backend/app` — passed.
- FastAPI smoke checks: `/api/health`, `/api/portfolio`, `/api/journal`, `/api/reports`, `/api/news`, `/docs`, and `/` returned HTTP 200 in TestClient smoke test. The news endpoint returned feed connection errors in this environment, correctly reporting no headlines rather than fabricating them.
- PDF upload and export: automated test creates a text PDF, extracts page text, and verifies exported bytes begin with `%PDF-`.
- Backtest: synthetic test fixture checks endpoint structure and chronology; provider-unavailable path is separately tested. Synthetic fixture is test-only and is never exposed as live market data.
- SEC facts: mocked provider test verifies filing date, form, period and units metadata are retained.
- Virtual portfolio and journal: create/list persistence tests passed.

## Feature acceptance status

| Feature | Status | Evidence / limitation |
|---|---|---|
| PWA shell and mobile navigation | Passed (code-level) | Existing responsive interface and service worker; physical phone not tested. |
| Technical indicator functions | Passed | Unit tests for SMA, EMA, RSI, MACD, Bollinger and ATR. |
| Real historical market data | Blocked | No Alpha Vantage API key configured; no live prices asserted. |
| Source-linked news | Partially passed | RSS parser tested with fixture; actual feeds unreachable in test environment. |
| Rumor corroboration | Not implemented | No automated truth verdict; user-facing disclosure explains limitation. |
| SEC fundamentals | Partially passed | SEC endpoint structure and metadata tested with mocked HTTP responses; live SEC request not verified. US filers only. |
| Forex position sizing | Passed (calculator tests) | User-supplied pip size/value; broker conversion assumptions remain user responsibility. |
| Historical backtest | Partially passed | Strategy logic/chronology tested on synthetic fixture; real-data run blocked without provider key. Basic SMA long/cash only. |
| PDF extraction | Passed (text PDF fixture) | Scanned PDF OCR and robust table extraction not implemented. |
| PDF export | Passed (generated PDF signature) | Readability is tested at file level, not on every mobile PDF viewer. |
| Virtual portfolio | Passed | SQLite create/list and virtual-only mode tested; live valuation not implemented. |
| Trading journal | Passed | SQLite create/list tested. |
| External AI explanations | Not implemented | No AI provider configured or required; deterministic rules and extraction only. |
| APK build | Blocked | Android SDK/Gradle/adb unavailable in this environment; CI workflow is provided. |
| Physical Android installation | Not tested | Requires APK build and actual device verification. |
| Public production security | Not ready | No authentication, production rate limiting, encrypted database, or hardened hosting. |

## Known warnings

FastAPI currently emits a deprecation warning for startup event registration. It does not fail tests; migrate to a lifespan handler in a future cleanup. External RSS and SEC requests need a network-enabled deployment environment and a proper SEC user-agent/contact value.
