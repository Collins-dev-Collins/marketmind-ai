# Architecture — integrated phases 1–4

```text
Android / Mobile Browser
        |
        v
PWA frontend (HTML, CSS, JS; Capacitor wrapper)
        |
        v
FastAPI backend (CORS allowlist; validation)
   |          |             |              |
   v          v             v              v
SQLite     Provider       SEC EDGAR      RSS allowlist
watchlist  adapter        company facts  headline metadata
portfolio  Alpha Vantage  US filers      publisher URLs
journal    daily candles
reports
   |          |
   v          v
PDF parser  Deterministic indicator and risk calculations
+ exporter  Daily SMA long/cash backtest with configured costs
```

## Trust boundaries

- Market data and SEC facts are external inputs; preserve provider/source, retrieval time, period, filing date, form and unit metadata.
- RSS content is untrusted publisher content. It is rendered as a linked headline and never silently treated as corroborated fact or a confirmed rumor.
- PDF content is untrusted input. Enforce file type, byte-size and page-count limits; parse locally on the configured backend; do not transmit it to an AI provider.
- Numeric analysis is deterministic Python code. No language model can overwrite calculations or create missing numeric values.
- Portfolio positions and journal entries are hypothetical records only. No brokerage or execution integration exists.

## Current boundaries and known gaps

- SQLite is local development storage without encryption or multi-user isolation. Do not expose the backend publicly without authentication, rate limiting, secure deployment, backups and a privacy review.
- Alpha Vantage daily data requires a server-side API key. The free tier and symbol coverage are constrained; no live quote claim is made.
- SEC Company Facts supports US SEC filers only. Current extraction returns selected latest facts with period and unit metadata; no automated valuation or ratio blending across periods.
- RSS fetch is best-effort from a static publisher allowlist. No source graph, rumor verification or independent corroboration engine is implemented.
- PDF text extraction is not OCR and may misread tables, columns and footnotes. Exported PDF is a structured extraction report, not an accountant-reviewed financial opinion.
- Backtest is one daily SMA crossover model, long/cash only, with user-configured basis-point costs. It is not a full strategy builder and lacks dividend, tax, market impact, delisted-security and survivorship-bias treatment.
- AI explanations, calibrated probability models, alerts, FRED macro series, portfolio live marks and physical Android validation remain future work.

## Design principle

The UI may explain a typed result but may not fabricate prices, filing facts, sources, probabilities, backtest outputs or test outcomes. Provider errors and missing data are visible states.
