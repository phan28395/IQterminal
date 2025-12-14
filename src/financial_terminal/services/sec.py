from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class FilingMeta:
    filing_id: str
    ticker: str
    type: str
    title: str | None
    date: dt.date
    url: str | None
    source: str = "sec"
    hash: str | None = None


class SecAdapter:
    """
    SEC adapter placeholder for future EDGAR fetch/parse.
    """

    def list_filings(self, ticker: str) -> Iterable[FilingMeta]:
        """
        TODO: fetch and parse SEC filings for the ticker.
        """
        return []

    def fetch_document(self, filing_id: str) -> str:
        # TODO: retrieve document content.
        return ""
