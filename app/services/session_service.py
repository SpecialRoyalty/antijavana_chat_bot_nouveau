from __future__ import annotations
from aiogram import Bot
from sqlalchemy import select, func
from app.config import get_settings
from app.db.models import Session, Vote, TrackedMessage
from app.db.session import SessionLocal
from app.bot.keyboards import vote_keyboard
from app.services.texts import closed_text, open_text, maintenance_text
from app.services.permissions import open_group, close_group

settings = get_settings()


async def get_or_create_session() -> Session:
    async with SessionLocal() as db:
        res = await db.execute(select(Session).order_by(Session.id.desc()).limit(1))
        s = res.scalar_one_or_none()
        if s:
            return s
        s = Session(vote_target=settings.default_vote_target)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s


async def count_votes(session_id: int) -> int:
    async with SessionLocal() as db:
        res = await db.execute(select(func.count(Vote.id)).where(Vote.session_id == session_id))
        return int(res.scalar() or 0)


async def register_vote(user_id: int) -> tuple[int, int]:
    s = await get_or_create_session()
    async with SessionLocal() as db:
        exists = await db.execute(select(Vote).where(Vote.session_id == s.id, Vote.user_id == user_id))
        if not exists.scalar_one_or_none():
            db.add(Vote(session_id=s.id, user_id=user_id))
            await db.commit()
    return await count_votes(s.id), s.vote_target


async def ensure_status_message(bot: Bot) -> None:
    if not settings.main_group_id:
        return
    s = await get_or_create_session()
    votes = await count_votes(s.id)
    text = closed_text(votes, s.vote_target)
    async with SessionLocal() as db:
        obj = await db.get(Session, s.id)
        if obj and obj.message_id:
            try:
                await bot.edit_message_text(text, chat_id=settings.main_group_id, message_id=obj.message_id, reply_markup=vote_keyboard())
                return
            except Exception:
                pass
        msg = await bot.send_message(settings.main_group_id, text, reply_markup=vote_keyboard())
        if obj:
            obj.message_id = msg.message_id
            await db.commit()


async def open_main_group(bot: Bot, manual: bool = False) -> None:
    if not settings.main_group_id:
        return
    await open_group(bot, settings.main_group_id)
    s = await get_or_create_session()
    async with SessionLocal() as db:
        obj = await db.get(Session, s.id)
        if obj:
            obj.status = 'open'
            obj.mode = 'manual' if manual else 'auto'
            await db.commit()
            if obj.message_id:
                try:
                    await bot.edit_message_text(open_text(), chat_id=settings.main_group_id, message_id=obj.message_id)
                    return
                except Exception:
                    pass
    await bot.send_message(settings.main_group_id, open_text())


async def close_main_group(bot: Bot, reason: str = 'auto') -> None:
    if not settings.main_group_id:
        return
    await close_group(bot, settings.main_group_id)
    from app.services.cleanup import cleanup_session
    await cleanup_session(bot)
    await ensure_status_message(bot)


async def track_message(chat_id: int, message_id: int, user_id: int | None, kind: str = 'message') -> None:
    s = await get_or_create_session()
    async with SessionLocal() as db:
        db.add(TrackedMessage(chat_id=chat_id, message_id=message_id, user_id=user_id, session_id=s.id, kind=kind))
        await db.commit()
