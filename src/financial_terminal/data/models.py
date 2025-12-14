from __future__ import annotations

import datetime as dt
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Ticker(Base):
    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, unique=True, nullable=False, index=True)
    cik = Column(String, unique=True, nullable=True, index=True)
    exchange = Column(String, nullable=True, index=True)
    name = Column(String, nullable=True)
    tags = Column(String, nullable=True)  # comma-separated tags
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    filings = relationship("Filing", back_populates="ticker", cascade="all, delete-orphan")
    watchlist_entry = relationship("Watchlist", back_populates="ticker", uselist=False, cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="ticker", cascade="all, delete-orphan")


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("ticker_id", name="uq_watchlist_ticker"),)

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    ticker = relationship("Ticker", back_populates="watchlist_entry")


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    content = Column(String, nullable=True)
    attachment = Column(String, nullable=True)  # file path or URL
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    ticker = relationship("Ticker", back_populates="notes")


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (UniqueConstraint("source", "filing_id", name="uq_source_filing"),)

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False, index=True)
    filing_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    url = Column(String, nullable=True)
    source = Column(String, nullable=False, default="sec")
    is_new = Column(Boolean, default=True, nullable=False)
    hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    ticker = relationship("Ticker", back_populates="filings")
    metrics = relationship("Metric", back_populates="filing", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="filing", cascade="all, delete-orphan")


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True)
    filing_id = Column(Integer, ForeignKey("filings.id"), nullable=False, index=True)
    var = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    currency = Column(String, nullable=True)

    filing = relationship("Filing", back_populates="metrics")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    filing_id = Column(Integer, ForeignKey("filings.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    read = Column(Boolean, default=False, nullable=False)

    filing = relationship("Filing", back_populates="alerts")
