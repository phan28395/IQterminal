from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from ..config import AppConfig
from ..data import dao
from ..data.models import Filing, Ticker
from .sec import FilingMeta, SecAdapter


class Poller:
    """
    Polls enabled sources for new filings and creates alerts.
    """

    def __init__(self, session: Session, config: AppConfig) -> None:
        self.session = session
        self.config = config
        self.sec = (
            SecAdapter(user_agent=config.sec_user_agent, throttle_seconds=config.sec_throttle_seconds)
            if config.sec_enabled
            else None
        )

    def run_once(self, symbols: Iterable[str] | None = None) -> list[Filing]:
        """
        One-shot poll across tickers. Returns new filings inserted.
        """
        new_filings: list[Filing] = []
        tickers = dao.list_watchlist(self.session)
        if symbols:
            wanted = {s.strip().upper() for s in symbols if str(s).strip()}
            tickers = [t for t in tickers if t.symbol in wanted]
        for ticker in tickers:
            if self.sec and ticker.cik:
                new_filings.extend(self._poll_sec(ticker))
        if new_filings:
            dao.add_alerts_for_filings(self.session, new_filings)
        return new_filings

    def _poll_sec(self, ticker: Ticker) -> list[Filing]:
        filings_meta: Iterable[FilingMeta] = self.sec.list_filings(
            ticker=ticker.symbol,
            cik=ticker.cik,
            limit=self.config.sec_filings_per_ticker,
        )
        filings: list[Filing] = []
        for meta in filings_meta:
            filing = Filing(
                filing_id=meta.filing_id,
                type=meta.type,
                title=meta.title,
                date=meta.date,
                url=meta.url,
                source=meta.source,
                hash=meta.hash,
            )
            filings.append(filing)
        return dao.upsert_filings(self.session, ticker, filings)
