"""Custodial test-network wallets and durable external-operation journals."""
from sqlalchemy import String, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, uid, timestamp


class XRPLWallet(Base):
    __tablename__ = 'xrpl_wallets'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    squad_id: Mapped[str | None] = mapped_column(ForeignKey('squads.id'), nullable=True)
    role: Mapped[str] = mapped_column(String)
    network: Mapped[str] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    encrypted_seed: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default='creating')
    created_at: Mapped[str] = mapped_column(String, default=timestamp)


class XRPLSettlement(Base):
    __tablename__ = 'xrpl_settlements'
    squad_id: Mapped[str] = mapped_column(ForeignKey('squads.id'), primary_key=True)
    network: Mapped[str] = mapped_column(String)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey('xrpl_wallets.id'), nullable=True)
    status: Mapped[str] = mapped_column(String, default='gathering')
    cancel_after: Mapped[int] = mapped_column(Integer)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    batch_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)
    settled_at: Mapped[str | None] = mapped_column(String, nullable=True)


class XRPLEscrow(Base):
    __tablename__ = 'xrpl_escrows'
    __table_args__ = (UniqueConstraint('squad_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    squad_id: Mapped[str] = mapped_column(ForeignKey('squads.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey('xrpl_wallets.id'))
    amount_cents: Mapped[int] = mapped_column(Integer)
    cancel_after: Mapped[int] = mapped_column(Integer)
    owner: Mapped[str | None] = mapped_column(String, nullable=True)
    offer_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(String, nullable=True)
    encrypted_fulfillment: Mapped[str | None] = mapped_column(String, nullable=True)
    create_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    finish_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    cancel_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default='creating')
    created_at: Mapped[str] = mapped_column(String, default=timestamp)


class XRPLOperation(Base):
    __tablename__ = 'xrpl_operations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String, unique=True)
    squad_id: Mapped[str | None] = mapped_column(ForeignKey('squads.id'), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    operation: Mapped[str] = mapped_column(String)
    network: Mapped[str] = mapped_column(String)
    resource_keys: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default='pending')
    transactions: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)
    updated_at: Mapped[str] = mapped_column(String, default=timestamp)
