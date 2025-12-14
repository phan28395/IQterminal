from __future__ import annotations

import httpx
from pydantic import BaseModel
import json
from pathlib import Path
from typing import Iterable

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


class SecTicker(BaseModel):
    cik_str: int
    ticker: str
    title: str
    exchange: str | None = None

    @property
    def cik_padded(self) -> str:
        return f"{self.cik_str:010d}"


def fetch_sec_tickers(with_exchange: bool = True) -> list[SecTicker]:
    """
    Download SEC ticker list. If with_exchange is True, enrich using the exchange file.
    """
    primary = _fetch_json(SEC_TICKERS_URL)
    exchange_map = {}
    if with_exchange:
        exchange_map = {int(v["cik_str"]): v.get("exchange") for v in _fetch_json(SEC_TICKERS_EXCHANGE_URL).values()}

    tickers: list[SecTicker] = []
    for item in primary.values():
        cik_str = int(item["cik_str"])
        ticker = item["ticker"]
        title = item.get("title", "")
        exchange = exchange_map.get(cik_str)
        tickers.append(SecTicker(cik_str=cik_str, ticker=ticker, title=title, exchange=exchange))
    return tickers


def load_sec_tickers_from_file(path: Path, exchange_path: Path | None = None) -> list[SecTicker]:
    """
    Load SEC tickers from local JSON files matching the SEC structure.
    """
    primary = _load_json_file(path)
    exchange_map = {}
    if exchange_path and exchange_path.exists():
        exchange_map = _load_exchange_map(exchange_path)

    tickers: list[SecTicker] = []
    for item in primary.values():
        cik_str = int(item["cik_str"])
        ticker = item["ticker"]
        title = item.get("title", "")
        exchange = exchange_map.get(cik_str)
        tickers.append(SecTicker(cik_str=cik_str, ticker=ticker, title=title, exchange=exchange))
    return tickers


def _fetch_json(url: str) -> dict:
    headers = {"User-Agent": "FinancialTerminal/0.1 (contact: example@example.com)"}
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _load_json_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_exchange_map(path: Path) -> dict[int, str | None]:
    """
    Handle both SEC exchange JSON formats:
    - dict of id -> {cik_str, exchange}
    - dict with keys "fields" and "data" (rows)
    """
    data = _load_json_file(path)
    if isinstance(data, dict) and "fields" in data and "data" in data:
        fields = data.get("fields", [])
        rows = data.get("data", [])
        try:
            cik_idx = fields.index("cik")
            exch_idx = fields.index("exchange")
        except ValueError:
            return {}
        return {int(row[cik_idx]): row[exch_idx] for row in rows}
    # Fallback to dict of cik_str
    return {int(v["cik_str"]): v.get("exchange") for v in data.values()}
