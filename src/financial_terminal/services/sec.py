from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
import time
from typing import Iterable

import httpx


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
    Minimal SEC EDGAR adapter using the official submissions API.
    """

    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
    DEFAULT_USER_AGENT = "IQterminal/0.1 (contact: example@example.com)"

    def __init__(self, user_agent: str | None = None, throttle_seconds: float = 0.2) -> None:
        self.user_agent = (user_agent or self.DEFAULT_USER_AGENT).strip()
        self.throttle_seconds = max(0.0, float(throttle_seconds))

    def list_filings(self, ticker: str, cik: str | None, limit: int = 50) -> Iterable[FilingMeta]:
        """
        Fetch and parse the most recent SEC filings for the given ticker/CIK.
        """
        if not cik:
            return []
        cik_padded = str(cik).strip().zfill(10)
        payload = self._fetch_json(self.SUBMISSIONS_URL.format(cik=cik_padded))
        filings = _parse_recent_filings(payload, ticker=ticker, cik_padded=cik_padded, limit=limit)
        if self.throttle_seconds:
            time.sleep(self.throttle_seconds)
        return filings

    def fetch_document(self, filing_id: str) -> str:
        # TODO: retrieve document content.
        return ""

    def _fetch_json(self, url: str) -> dict:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()


def _parse_recent_filings(payload: dict, ticker: str, cik_padded: str, limit: int) -> list[FilingMeta]:
    recent = (payload.get("filings") or {}).get("recent") or {}

    accession_numbers: list[str] = list(recent.get("accessionNumber") or [])
    forms: list[str] = list(recent.get("form") or [])
    filing_dates: list[str] = list(recent.get("filingDate") or [])
    primary_docs: list[str] = list(recent.get("primaryDocument") or [])
    primary_desc: list[str] = list(recent.get("primaryDocDescription") or [])

    max_rows = min(len(accession_numbers), max(0, int(limit)))
    cik_int = int(cik_padded)

    filings: list[FilingMeta] = []
    for i in range(max_rows):
        accession = accession_numbers[i]
        form = forms[i] if i < len(forms) else ""
        filing_date_raw = filing_dates[i] if i < len(filing_dates) else ""
        if not accession or not filing_date_raw:
            continue
        try:
            filing_date = dt.date.fromisoformat(filing_date_raw)
        except ValueError:
            continue

        accession_no_dashes = accession.replace("-", "")
        primary_document = primary_docs[i] if i < len(primary_docs) else ""
        title = primary_desc[i] if i < len(primary_desc) else None

        # Link to the filing details page (more stable than a specific document).
        url = f"{SecAdapter.ARCHIVES_BASE}/{cik_int}/{accession_no_dashes}/{accession}-index.html"
        if not primary_document and title is None:
            title = form or None

        filings.append(
            FilingMeta(
                filing_id=accession,
                ticker=ticker,
                type=form or "UNKNOWN",
                title=title,
                date=filing_date,
                url=url,
            )
        )

    return filings
