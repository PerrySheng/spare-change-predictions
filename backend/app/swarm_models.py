"""Prospective research runs and public event logs on the app's existing Base."""
from sqlalchemy import ForeignKey, Integer, JSON, String, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, uid, timestamp


class SwarmRun(Base):
    __tablename__ = 'swarm_runs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    market_id: Mapped[str] = mapped_column(String, index=True)
    outcome: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='queued', index=True)
    market: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=timestamp, index=True)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    brier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    side_edge: Mapped[float | None] = mapped_column(Float, nullable=True)
    scored_at: Mapped[str | None] = mapped_column(String, nullable=True)


class SwarmEvent(Base):
    __tablename__ = 'swarm_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('swarm_runs.id'), index=True)
    type: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)


class SwarmEstimate(Base):
    __tablename__ = 'swarm_estimates'
    __table_args__ = (UniqueConstraint('run_id', 'agent', 'round'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey('swarm_runs.id'), index=True)
    agent: Mapped[str] = mapped_column(String)
    round: Mapped[int] = mapped_column(Integer)
    probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String)
    reasons: Mapped[list] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    revision_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)


class MarketSnapshot(Base):
    __tablename__ = 'market_snapshots'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    market_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('swarm_runs.id'), unique=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)


class ResearchSource(Base):
    __tablename__ = 'research_sources'
    __table_args__ = (UniqueConstraint('market_id', 'url'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    market_id: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    snippet: Mapped[str] = mapped_column(String, default='')
    provider: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[str] = mapped_column(String, default=timestamp)
