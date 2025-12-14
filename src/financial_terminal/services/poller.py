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
        self.sec = SecAdapter() if config.sec_enabled else None

    def run_once(self) -> list[Filing]:
        """
        One-shot poll across tickers. Returns new filings inserted.
        """
        new_filings: list[Filing] = []
        tickers = dao.list_tickers(self.session)
        for ticker in tickers:
            if self.sec:
                new_filings.extend(self._poll_sec(ticker))
        if new_filings:
            dao.add_alerts_for_filings(self.session, new_filings)
        return new_filings

    def _poll_sec(self, ticker: Ticker) -> list[Filing]:
        filings_meta: Iterable[FilingMeta] = self.sec.list_filings(ticker.symbol)
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
