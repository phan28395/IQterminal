# Financial Terminal (Textual)

Terminal-based financial filings dashboard built with Textual.

## Quick start
1. Ensure Python 3.10+ is installed.
2. Install dependencies globally: `python -m pip install textual rich sqlalchemy httpx pydantic lxml`.
3. Register the package (from repo root): `python -m pip install -e .` (or set `PYTHONPATH=%CD%\\src` for a one-off run).
4. Run the app: `python -m financial_terminal.app` or `financial-terminal`.

## Config
- Defaults live in `config.default.toml`. Adjust poll interval, cache path, and source toggles there.

## Status
Skeleton layout only; wiring for data, polling, and widgets comes next.
