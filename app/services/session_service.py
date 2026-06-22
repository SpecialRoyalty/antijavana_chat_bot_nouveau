from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, func, delete
from app.config import get_settings
from app.db.models import Session, Vote, TrackedMessage, Setting
from app.db.session import SessionLocal
from app.bot.keyboards import vote_keyboard
from app.services.texts import closed_text, open_text, maintenance_text
from app.services.permissions import open_group, close_group

settings = get_settings()


def _is_not_modified(exc: Exception) -> bool:
    return 'message is not modified' in str(exc).lower()


async def get_setting(key: str, default: dict | None = None) -> dict:
    async with SessionLocal() as db:
        obj = await db.get(Setting, key)
        return obj.value if obj else (default or {})


async def set_setting(key: str, value: dict) -> None:
    async with SessionLocal() as db:
        obj = await db.get(Setting, key)
        if obj:
            obj.value = value
        else:
            db.add(Setting(key=key, value=value))
        await db.commit()


async def get_runtime_settings() -> dict:
    data = await get_setting('runtime', {})
    data.setdefault('auto_enabled', True)
    data.setdefault('schedule', '22:30-00:45')
    data.setdefault('manual_opened_at', None)
    return data


async def get_or_create_session() -> Session:
    async with SessionLocal() as db:
        res = await db.execute(select(Session).order_by(Session.id.desc()).limit(1))
        s = res.scalar_one_or_none()
        if s and s.status != 'closed_archived':
            return s
        s = Session(vote_target=settings.default_vote_target, status='closed')
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s


async def count_votes(session_id: int) -> int:
    async with SessionLocal() as db:
        res = await db.execute(select(func.count(Vote.id)).where(Vote.session_id == session_id))
        return int(res.scalar() or 0)


async def register_vote(user_id: int) -> tuple[int, int, bool]:
    s = await get_or_create_session()
    created = False
    async with SessionLocal() as db:
        exists = await db.execute(select(Vote).where(Vote.session_id == s.id, Vote.user_id == user_id))
        if not exists.scalar_one_or_none():
            db.add(Vote(session_id=s.id, user_id=user_id))
            await db.commit()
            created = True
    return await count_votes(s.id), s.vote_target, created


async def delete_previous_status(bot: Bot, session_id: int, keep_message_id: int | None = None) -> None:
    async with SessionLocal() as db:
        res = await db.execute(select(TrackedMessage).where(TrackedMessage.session_id == session_id, TrackedMessage.kind == 'status'))
        rows = list(res.scalars().all())
        for row in rows:
            if keep_message_id and row.message_id == keep_message_id:
                continue
            try:
                await bot.delete_message(row.chat_id, row.message_id)
            except Exception:
                pass
            await db.delete(row)
        await db.commit()


async def upsert_status_message(bot: Bot, text: str, reply_markup=None) -> None:
    if not settings.main_group_id:
        return
    s = await get_or_create_session()
    async with SessionLocal() as db:
        obj = await db.get(Session, s.id)
        if obj and obj.message_id:
            try:
                await bot.edit_message_text(text, chat_id=settings.main_group_id, message_id=obj.message_id, reply_markup=reply_markup)
                await delete_previous_status(bot, s.id, keep_message_id=obj.message_id)
                return
            except TelegramBadRequest as e:
                if _is_not_modified(e):
                    await delete_previous_status(bot, s.id, keep_message_id=obj.message_id)
                    return
                # message supprimé/inaccessible: on en recrée un, mais on supprime l'ancien si possible
                try:
                    await bot.delete_message(settings.main_group_id, obj.message_id)
                except Exception:
                    pass
            except Exception:
                pass

        # Avant d'envoyer un nouveau message statut, supprimer tous les anciens statuts connus.
        await delete_previous_status(bot, s.id)
        msg = await bot.send_message(settings.main_group_id, text, reply_markup=reply_markup)
        if obj:
            obj.message_id = msg.message_id
            db.add(TrackedMessage(chat_id=settings.main_group_id, message_id=msg.message_id, user_id=None, session_id=s.id, kind='status'))
            await db.commit()


async def ensure_status_message(bot: Bot) -> None:
    runtime = await get_runtime_settings()
    s = await get_or_create_session()
    if not runtime.get('auto_enabled', True) and s.status != 'open':
        await upsert_status_message(bot, maintenance_text(), None)
        return
    if s.status == 'open':
        await upsert_status_message(bot, open_text(), None)
        return
    votes = await count_votes(s.id)
    await upsert_status_message(bot, closed_text(votes, s.vote_target), vote_keyboard())


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
            obj.opened_at = datetime.utcnow()
            await db.commit()
    if manual:
        runtime = await get_runtime_settings()
        runtime['manual_opened_at'] = datetime.utcnow().isoformat()
        await set_setting('runtime', runtime)
    await upsert_status_message(bot, open_text(), None)


async def close_main_group(bot: Bot, reason: str = 'auto') -> None:
    if not settings.main_group_id:
        return
    await close_group(bot, settings.main_group_id)
    from app.services.cleanup import cleanup_session
    await cleanup_session(bot)
    s = await get_or_create_session()
    async with SessionLocal() as db:
        obj = await db.get(Session, s.id)
        if obj:
            obj.status = 'closed'
            obj.closed_at = datetime.utcnow()
            await db.commit()
    runtime = await get_runtime_settings()
    runtime['manual_opened_at'] = None
    await set_setting('runtime', runtime)
    await ensure_status_message(bot)


async def toggle_auto() -> bool:
    runtime = await get_runtime_settings()
    runtime['auto_enabled'] = not bool(runtime.get('auto_enabled', True))
    await set_setting('runtime', runtime)
    return bool(runtime['auto_enabled'])


async def set_schedule(schedule: str) -> tuple[bool, str]:
    s = await get_or_create_session()
    if s.status == 'open':
        return False, 'Impossible de changer le créneau pendant une session ouverte.'
    if schedule not in {'22:30-00:45', '22:00-00:00', '23:00-01:00'}:
        return False, 'Créneau invalide.'
    runtime = await get_runtime_settings()
    runtime['schedule'] = schedule
    await set_setting('runtime', runtime)
    return True, f'Créneau actif : {schedule}'


async def track_message(chat_id: int, message_id: int, user_id: int | None, kind: str = 'message') -> None:
    # Ne jamais suivre le message statut comme message utilisateur.
    s = await get_or_create_session()
    async with SessionLocal() as db:
        db.add(TrackedMessage(chat_id=chat_id, message_id=message_id, user_id=user_id, session_id=s.id, kind=kind))
        await db.commit()
