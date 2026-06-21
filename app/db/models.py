from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_media_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sessions_present: Mapped[int] = mapped_column(Integer, default=0)
    sessions_with_media: Mapped[int] = mapped_column(Integer, default=0)
    suspicion_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = 'settings'
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default='closed')
    mode: Mapped[str] = mapped_column(String(32), default='auto')
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vote_target: Mapped[int] = mapped_column(Integer, default=120)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Vote(Base):
    __tablename__ = 'votes'
    __table_args__ = (UniqueConstraint('session_id', 'user_id'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackedMessage(Base):
    __tablename__ = 'tracked_messages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default='message')
    copied_to: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MediaHash(Base):
    __tablename__ = 'media_hashes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_type: Mapped[str] = mapped_column(String(32))
    hash_value: Mapped[str] = mapped_column(String(128), index=True)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    source_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrustedAction(Base):
    __tablename__ = 'trusted_actions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trusted_user_id: Mapped[int] = mapped_column(BigInteger)
    trusted_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    command: Mapped[str] = mapped_column(String(32))
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InviteLink(Base):
    __tablename__ = 'invite_links'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger)
    link: Mapped[str] = mapped_column(Text)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    reward_counter: Mapped[int] = mapped_column(Integer, default=0)
    suspect_count: Mapped[int] = mapped_column(Integer, default=0)
    banned_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
