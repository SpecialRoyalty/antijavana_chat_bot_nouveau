from __future__ import annotations
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    suspect_score: Mapped[int] = mapped_column(Integer, default=0)
    sessions_present: Mapped[int] = mapped_column(Integer, default=0)
    sessions_with_media: Mapped[int] = mapped_column(Integer, default=0)
    last_media_session: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reward_counter: Mapped[int] = mapped_column(Integer, default=0)
    total_invites: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GroupState(Base):
    __tablename__ = "group_state"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    status_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rules_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_open: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    time_slot: Mapped[str] = mapped_column(String(32), default="22:30-00:45")
    vote_goal: Mapped[int] = mapped_column(Integer, default=120)
    current_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="auto")
    messages_seen: Mapped[int] = mapped_column(Integer, default=0)
    media_seen: Mapped[int] = mapped_column(Integer, default=0)
    messages_deleted: Mapped[int] = mapped_column(Integer, default=0)
    media_deleted: Mapped[int] = mapped_column(Integer, default=0)

class Vote(Base):
    __tablename__ = "votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    day_key: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("chat_id", "user_id", "day_key", name="uq_vote_day"),)

class TrackedMessage(Base):
    __tablename__ = "tracked_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_media: Mapped[bool] = mapped_column(Boolean, default=False)
    copied_soiree_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    copied_total_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class WordRule(Base):
    __tablename__ = "word_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20)) # forbidden, ban, name_ban
    word: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MediaHash(Base):
    __tablename__ = "media_hashes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_type: Mapped[str] = mapped_column(String(20))
    hash_value: Mapped[str] = mapped_column(String(128), index=True)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    source_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TrustedAction(Base):
    __tablename__ = "trusted_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trusted_user_id: Mapped[int] = mapped_column(BigInteger)
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    points: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
