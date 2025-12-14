from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

from sqlalchemy import MetaData, Table, column, func, select, text, inspect, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Alert, Filing, Metric, Note, Ticker, Watchlist


def init_db(session: Session) -> None:
    """
    Create all tables if they do not exist.
    """
    from .models import Base
    engine = session.get_bind()
    Base.metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine) -> None:
    """
    Ensure new columns exist when models evolve (minimal migration helper).
    """
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("tickers")}
    with engine.begin() as conn:
        if "cik" not in columns:
            conn.execute(text("ALTER TABLE tickers ADD COLUMN cik VARCHAR"))
        if "exchange" not in columns:
            conn.execute(text("ALTER TABLE tickers ADD COLUMN exchange VARCHAR"))


def add_ticker(
    session: Session,
    symbol: str,
    name: str | None = None,
    tags: str | None = None,
    cik: str | None = None,
    exchange: str | None = None,
) -> Ticker:
    ticker = Ticker(symbol=symbol.upper(), name=name, tags=tags, cik=cik, exchange=exchange)
    session.add(ticker)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        stmt = select(Ticker).where(Ticker.symbol == symbol.upper())
        ticker = session.scalar(stmt)
    return ticker


def upsert_tickers_bulk(
    session: Session,
    rows: Iterable[dict[str, str | None]],
) -> list[Ticker]:
    created_or_updated: list[Ticker] = []
    for row in rows:
        symbol = (row.get("symbol") or "").upper()
        if not symbol:
            continue
        name = row.get("name")
        cik = row.get("cik")
        exchange = row.get("exchange")
        stmt = select(Ticker).where(Ticker.symbol == symbol)
        existing = session.scalar(stmt)
        if existing:
            existing.name = name or existing.name
            existing.cik = cik or existing.cik
            existing.exchange = exchange or existing.exchange
            created_or_updated.append(existing)
            continue
        ticker = Ticker(symbol=symbol, name=name, cik=cik, exchange=exchange)
        session.add(ticker)
        created_or_updated.append(ticker)
    session.commit()
    return created_or_updated


def list_tickers(session: Session) -> list[Ticker]:
    stmt = select(Ticker).order_by(Ticker.symbol)
    return list(session.scalars(stmt))


def list_watchlist(session: Session) -> list[Ticker]:
    stmt = (
        select(Ticker)
        .join(Watchlist, Watchlist.ticker_id == Ticker.id)
        .order_by(Ticker.symbol)
    )
    return list(session.scalars(stmt))


def add_to_watchlist(session: Session, ticker: Ticker) -> None:
    exists_stmt = select(Watchlist).where(Watchlist.ticker_id == ticker.id)
    exists = session.scalar(exists_stmt)
    if exists:
        return
    entry = Watchlist(ticker=ticker)
    session.add(entry)
    session.commit()


def remove_from_watchlist(session: Session, ticker: Ticker) -> None:
    stmt = select(Watchlist).where(Watchlist.ticker_id == ticker.id)
    entry = session.scalar(stmt)
    if entry:
        session.delete(entry)
        session.commit()


def add_note(session: Session, ticker: Ticker, title: str, content: str | None = None, attachment: str | None = None) -> Note:
    note = Note(ticker=ticker, title=title, content=content, attachment=attachment)
    session.add(note)
    session.commit()
    return note


def list_notes_for_ticker(session: Session, ticker: Ticker, limit: int = 100) -> list[Note]:
    stmt = (
        select(Note)
        .where(Note.ticker_id == ticker.id)
        .order_by(Note.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def delete_note(session: Session, note_id: int) -> None:
    note = session.get(Note, note_id)
    if note:
        session.delete(note)
        session.commit()


def search_tickers(session: Session, query: str, limit: int = 20) -> list[Ticker]:
    """
    Search by symbol, cik, or name (case-insensitive) with prioritization:
    1) exact symbol match
    2) symbol startswith query
    3) symbol contains query
    4) name contains query
    5) cik contains query
    """
    q = query.strip().lower()
    if not q:
        return []
    like_q = f"%{q}%"
    starts_q = f"{q}%"

    stmt = (
        select(Ticker)
        .where(
            func.lower(Ticker.symbol).like(like_q)
            | func.lower(Ticker.name).like(like_q)
            | func.lower(Ticker.cik).like(like_q)
        )
        .order_by(
            # Priority ordering
            (func.lower(Ticker.symbol) != q),  # exact matches first
            (func.lower(Ticker.symbol).notlike(starts_q)),  # startswith next
            (func.lower(Ticker.symbol).notlike(like_q)),  # other symbol contains
            (func.lower(Ticker.name).notlike(like_q)),  # name contains
            Ticker.symbol,
        )
        .limit(limit)
    )
    return list(session.scalars(stmt))


def upsert_filings(session: Session, ticker: Ticker, filings: Iterable[Filing]) -> list[Filing]:
    """
    Insert filings if new; mark is_new True when not seen before.
    """
    created: list[Filing] = []
    for filing in filings:
        stmt = select(Filing).where(Filing.source == filing.source, Filing.filing_id == filing.filing_id)
        existing = session.scalar(stmt)
        if existing:
            existing.is_new = False
            continue
        filing.ticker = ticker
        filing.is_new = True
        session.add(filing)
        created.append(filing)
    session.commit()
    return created


def add_alerts_for_filings(session: Session, filings: Iterable[Filing]) -> list[Alert]:
    alerts: list[Alert] = []
    now = dt.datetime.utcnow()
    for filing in filings:
        alert = Alert(filing=filing, created_at=now, read=False)
        session.add(alert)
        alerts.append(alert)
    session.commit()
    return alerts


def unread_alerts(session: Session) -> list[Alert]:
    stmt = select(Alert).where(Alert.read.is_(False)).order_by(Alert.created_at.desc())
    return list(session.scalars(stmt))


def unread_alert_counts(session: Session) -> dict[int, int]:
    """
    Return a mapping of ticker_id -> unread alert count.
    """
    stmt = (
        select(Filing.ticker_id, func.count(Alert.id))
        .join(Alert, Alert.filing_id == Filing.id)
        .where(Alert.read.is_(False))
        .group_by(Filing.ticker_id)
    )
    return {row[0]: row[1] for row in session.execute(stmt)}


def mark_alerts_read(session: Session, alerts: Iterable[Alert]) -> None:
    for alert in alerts:
        alert.read = True
    session.commit()


def latest_filings(session: Session, ticker: Ticker, limit: int = 20) -> list[Filing]:
    stmt = (
        select(Filing)
        .where(Filing.ticker_id == ticker.id)
        .order_by(Filing.date.desc(), Filing.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def _non_mock_clause():
    """
    Exclude obvious mock/demo filings.
    """
    return or_(
        Filing.hash.is_(None),
        ~Filing.hash.like("mock%"),
    )


def list_filings(session: Session, limit: int = 100):
    """
    Return filings joined with ticker for display, excluding mock/demo rows.
    """
    from .models import Ticker

    stmt = (
        select(Filing, Ticker)
        .join(Ticker, Filing.ticker_id == Ticker.id)
        .where(_non_mock_clause())
        .order_by(Filing.date.desc(), Filing.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).all())


def list_filings_for_symbols(session: Session, symbols: list[str], limit: int = 100):
    """
    Return filings joined with ticker limited to given symbols, excluding mock/demo rows.
    """
    if not symbols:
        return []
    from .models import Ticker

    stmt = (
        select(Filing, Ticker)
        .join(Ticker, Filing.ticker_id == Ticker.id)
        .where(Ticker.symbol.in_(symbols))
        .where(_non_mock_clause())
        .order_by(Filing.date.desc(), Filing.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).all())


def upsert_metrics(
    session: Session,
    filing: Filing,
    metrics: Iterable[dict[str, Optional[float]]],
) -> list[Metric]:
    """
    Insert metrics for a filing; duplicates by var are replaced.
    """
    inserted: list[Metric] = []
    for row in metrics:
        existing_stmt = select(Metric).where(Metric.filing_id == filing.id, Metric.var == row["var"])
        existing = session.scalar(existing_stmt)
        if existing:
            existing.value = row["value"]
            existing.period_start = row.get("period_start")
            existing.period_end = row.get("period_end")
            existing.currency = row.get("currency")
            inserted.append(existing)
            continue
        metric = Metric(
            filing=filing,
            var=row["var"],
            value=row["value"] or 0.0,
            period_start=row.get("period_start"),
            period_end=row.get("period_end"),
            currency=row.get("currency"),
        )
        session.add(metric)
        inserted.append(metric)
    session.commit()
    return inserted
