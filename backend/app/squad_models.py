"""Persisted collaboration history. These rows do not represent placed orders."""
from sqlalchemy import String, Integer, Boolean, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, uid, timestamp


class Squad(Base):
    __tablename__ = 'squads'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    creator_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String)
    invite_code: Mapped[str] = mapped_column(String, unique=True, index=True)
    stake_cents: Mapped[int] = mapped_column(Integer)
    member_limit: Mapped[int] = mapped_column(Integer)
    lock_at: Mapped[str] = mapped_column(String)
    locked_at: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default='open')
    created_at: Mapped[str] = mapped_column(String, default=timestamp)


class SquadMember(Base):
    __tablename__ = 'squad_members'
    __table_args__ = (UniqueConstraint('squad_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    squad_id: Mapped[str] = mapped_column(ForeignKey('squads.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    joined_at: Mapped[str] = mapped_column(String, default=timestamp)


class SquadLeg(Base):
    __tablename__ = 'squad_legs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    squad_id: Mapped[str] = mapped_column(ForeignKey('squads.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    market_id: Mapped[str] = mapped_column(String)
    event_ticker: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)
    entry_price: Mapped[str] = mapped_column(String)
    closes_at: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default='open')
    created_at: Mapped[str] = mapped_column(String, default=timestamp)
    resolved_at: Mapped[str | None] = mapped_column(String, nullable=True)


class SquadVote(Base):
    __tablename__ = 'squad_votes'
    __table_args__ = (UniqueConstraint('leg_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    leg_id: Mapped[str] = mapped_column(ForeignKey('squad_legs.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    reaction: Mapped[str] = mapped_column(String)
    comment: Mapped[str] = mapped_column(String, default='')
    created_at: Mapped[str] = mapped_column(String, default=timestamp)
    updated_at: Mapped[str] = mapped_column(String, default=timestamp)


class SquadEvent(Base):
    __tablename__ = 'squad_events'
    __table_args__ = {'sqlite_autoincrement': True}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    squad_id: Mapped[str] = mapped_column(ForeignKey('squads.id'), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    type: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    leg_id: Mapped[str | None] = mapped_column(ForeignKey('squad_legs.id'), nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)
