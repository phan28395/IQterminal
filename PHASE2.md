# Phase 2 — Watchlist-Only SEC Filings Ingestion

## Goal
Automatically fetch and store SEC filings **only** for tickers in the watchlist (not the full SEC ticker universe), and surface those filings in the **Filings** tab.

## What changed
- Implemented a minimal SEC adapter that pulls recent filings from the official submissions endpoint:
  - `https://data.sec.gov/submissions/CIK##########.json`
- Updated the poller so it only refreshes filings for **watchlist** tickers, and skips tickers without a CIK.
- Added an automatic, periodic background refresh (so the UI stays responsive) and also refreshes right after adding a ticker.
- Updated the Filings table behavior:
  - If a ticker is selected in the watchlist, show filings for that ticker.
  - If no ticker is selected, show filings across the whole watchlist.

## Config additions
Edit `config.default.toml` (or your own config) under `[sources]`:
- `sec_user_agent` — required by SEC (include a contact)
- `sec_filings_per_ticker` — how many recent filings to ingest per ticker
- `sec_throttle_seconds` — simple per-request throttle

## Files touched
- `src/financial_terminal/services/sec.py`
- `src/financial_terminal/services/poller.py`
- `src/financial_terminal/app.py`
- `src/financial_terminal/config.py`
- `config.default.toml`

