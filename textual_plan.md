# Textual Financial Terminal Plan

## Scope
Minimal slice: watchlist, SEC polling, alerts, filings table/detail, metrics extraction stub, simple charts.

## Steps
1) Environment
- Python 3.10+, global install (no venv), `pip install textual rich sqlalchemy httpx pydantic lxml` (pin versions).
- Create config file for defaults (poll interval, cache paths).

2) Project layout
- `src/`: `app.py`, `ui/` (widgets), `services/` (poller, adapters), `data/` (db models, dao), `domain/` (entities), `config.py`.
- `tests/`: unit and snapshot tests.
- `pyproject.toml` with entrypoint `financial-terminal`.

3) Data layer (SQLite)
- Use `sqlalchemy`/`sqlmodel`: tables for `tickers`, `filings`, `metrics`, `alerts`, `settings`.
- DAO helpers: `add_ticker`, `latest_filings(ticker)`, `upsert_filing`, `mark_alert_read`.

4) Source adapter (SEC to start)
- `SecAdapter.list_filings(ticker)` returns metadata (id, type, title, date, url, hash).
- `SecAdapter.fetch_document(filing_id)` returns text (cache locally).
- Dedup by `filing_id/hash`; log rate limits.

5) Poller
- Async task running on interval; per ticker: fetch list, diff vs DB, store new, enqueue alerts.
- Configurable interval; manual `refresh` command triggers once.

6) Textual app skeleton
- Layout: `Header`, `Footer`, `Sidebar` (watchlist + badges), `Main` (Tabs), `StatusBar`.
- Tabs: Dashboard, Filings, Metrics, Formulas, Widgets.
- Wire command palette (`:`) for actions (add ticker, refresh, open settings).

7) Watchlist UI
- Sidebar list with tags; add/remove via modal; store in DB.
- Badge shows count of unread alerts per ticker.

8) Filings tab
- Table with columns: date, type, ticker, title, `NEW` badge.
- Selecting row opens detail view (split pane): metadata + notes + key numbers table placeholder.
- Actions: mark read, open link in browser (optional), copy URL.

9) Alerts drawer
- Hotkey `a` to open; shows recent alerts (ticker/type/date); mark all read.
- Status bar shows next poll time and pending alerts count.

10) Metrics extraction stub
- Basic parser for 10-K/10-Q: regex for Revenue/Net Income; store as metrics tied to filing.
- Metrics tab shows variables per ticker with sparkline (use Rich text + braille blocks).

11) Formulas (MVP)
- Simple expressions using `numexpr` or custom eval sandbox: variables map to metrics (latest/TTM placeholder).
- Formulas list view with status (ok/error); run to produce table + sparkline.

12) Widgets (MVP)
- Schema: {id, name, type: chart/table/text, inputs, options} stored in DB.
- Widgets tab renders each widget; chart widget uses series from formulas/metrics; table widget uses filings list.

13) Commands & hotkeys
- `r` refresh, `a` alerts drawer, `/` search in current table, `:` command palette, `Enter` open detail.
- Provide help modal.

14) Config & profiles
- Settings modal: poll interval, sources enabled, cache dir.
- Support multiple profiles stored in DB or JSON; load profile on startup flag.

15) Testing
- Unit: adapters (parsing/dedup), poller scheduling, formula evaluator safety, metrics parser.
- Snapshot: table rendering variants; sparkline rendering.
- Integration: poller inserts new filings -> alerts visible.

16) Packaging & run
- CLI entry `financial-terminal` runs Textual app.
- Add `Makefile`/`invoke` tasks: `fmt`, `lint`, `test`, `run`.
