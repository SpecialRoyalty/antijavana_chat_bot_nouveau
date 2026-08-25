from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy import func, select, update

from app.config import get_settings
from app.db.models import RapidJoinGuard, TrackedMessage, User
from app.db.session import SessionLocal
from app.services import settings as st
from app.services.state import log_error
from app.services.users import protected

# Cache en mémoire des heures d'arrivée réellement observées.
# Il est alimenté immédiatement lors de chat_member et évite un SELECT à chaque média.
_JOIN_CACHE: dict[int, tuple[int, datetime]] = {}
_JOIN_CACHE_NEXT_CLEANUP = datetime.min
_DELETE_CONCURRENCY = 4


async def enabled() -> bool:
    return (await st.get_value('anti_fast_join_enabled', 'true')) == 'true'


async def window_minutes() -> int:
    raw = await st.get_value('anti_fast_join_minutes', '5')
    try:
        value = int(raw)
    except Exception:
        value = 5
    return max(1, min(value, 60))


async def register_join(event: ChatMemberUpdated) -> None:
    """Enregistre/réinitialise l'heure d'arrivée réelle d'un membre du groupe principal."""
    global _JOIN_CACHE_NEXT_CLEANUP
    if event.chat.id != get_settings().main_group_id:
        return
    member = getattr(event.new_chat_member, 'user', None) or event.from_user
    if not member or await protected(member.id):
        return
    if event.new_chat_member.status not in ('member', 'restricted'):
        return

    now = datetime.utcnow()
    if now >= _JOIN_CACHE_NEXT_CLEANUP:
        cutoff = now - timedelta(hours=2)
        for uid, (_chat_id, joined_at) in list(_JOIN_CACHE.items()):
            if joined_at < cutoff:
                _JOIN_CACHE.pop(uid, None)
        _JOIN_CACHE_NEXT_CLEANUP = now + timedelta(minutes=5)
    _JOIN_CACHE[member.id] = (event.chat.id, now)

    async with SessionLocal() as db:
        row = await db.get(RapidJoinGuard, member.id)
        if not row:
            row = RapidJoinGuard(
                user_id=member.id,
                chat_id=event.chat.id,
                joined_at=now,
                last_triggered_at=None,
                trigger_count=0,
            )
            db.add(row)
        else:
            row.chat_id = event.chat.id
            row.joined_at = now
        await db.commit()


async def _joined_at(user_id: int) -> tuple[int, datetime] | None:
    cached = _JOIN_CACHE.get(user_id)
    if cached is not None:
        return cached

    async with SessionLocal() as db:
        row = await db.get(RapidJoinGuard, user_id)
        if not row:
            return None
        cached = (row.chat_id, row.joined_at)
    _JOIN_CACHE[user_id] = cached
    return cached


async def remaining_seconds(user_id: int) -> int | None:
    if not await enabled():
        return None
    joined = await _joined_at(user_id)
    if not joined or joined[0] != get_settings().main_group_id:
        return None
    limit = timedelta(minutes=await window_minutes())
    remaining = (joined[1] + limit - datetime.utcnow()).total_seconds()
    return max(0, int(remaining))


async def should_ban_for_fast_media(msg: Message) -> bool:
    """True uniquement pour un média publié dans la fenêtre suivant une arrivée connue."""
    if not msg.from_user or msg.chat.id != get_settings().main_group_id:
        return False
    if await protected(msg.from_user.id) or not await enabled():
        return False

    from app.services.hashban import media_file_entries
    if not media_file_entries(msg):
        return False

    joined = await _joined_at(msg.from_user.id)
    if not joined or joined[0] != msg.chat.id:
        # Donnée absente = aucune sanction automatique.
        return False
    return datetime.utcnow() < joined[1] + timedelta(minutes=await window_minutes())


async def _delete_one(bot: Bot, chat_id: int, message_id: int, semaphore: asyncio.Semaphore) -> tuple[int, bool]:
    async with semaphore:
        try:
            await bot.delete_message(chat_id, message_id)
            return message_id, True
        except TelegramBadRequest as exc:
            low = str(exc).lower()
            # Déjà absent = considéré comme nettoyé, inutile de le retenter plus tard.
            if 'message to delete not found' in low or 'message identifier is not specified' in low:
                return message_id, True
            await log_error('anti_fast_join_delete', exc)
            return message_id, False
        except Exception as exc:
            await log_error('anti_fast_join_delete', exc)
            return message_id, False


async def delete_all_tracked_user_content(bot: Bot, chat_id: int, user_id: int) -> tuple[int, int]:
    """Supprime les messages suivis sans garder une transaction DB ouverte pendant Telegram."""
    async with SessionLocal() as db:
        rows = list((await db.execute(
            select(TrackedMessage.id, TrackedMessage.message_id).where(
                TrackedMessage.chat_id == chat_id,
                TrackedMessage.user_id == user_id,
                TrackedMessage.deleted.is_(False),
            )
        )).all())

    if not rows:
        return 0, 0

    semaphore = asyncio.Semaphore(_DELETE_CONCURRENCY)
    results = await asyncio.gather(*[
        _delete_one(bot, chat_id, message_id, semaphore)
        for _row_id, message_id in rows
    ])
    success_message_ids = [message_id for message_id, ok in results if ok]
    deleted = len(success_message_ids)
    failed = len(results) - deleted

    if success_message_ids:
        async with SessionLocal() as db:
            await db.execute(
                update(TrackedMessage)
                .where(
                    TrackedMessage.chat_id == chat_id,
                    TrackedMessage.message_id.in_(success_message_ids),
                )
                .values(deleted=True)
            )
            await db.commit()
    return deleted, failed


async def enforce(bot: Bot, msg: Message) -> bool:
    if not await should_ban_for_fast_media(msg):
        return False

    uid = msg.from_user.id
    deleted, failed = await delete_all_tracked_user_content(bot, msg.chat.id, uid)

    # Le message courant est déjà tracké ; tentative défensive supplémentaire.
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass

    banned = False
    try:
        await bot.ban_chat_member(msg.chat.id, uid)
        banned = True
    except Exception as exc:
        await log_error('anti_fast_join_ban', exc)

    now = datetime.utcnow()
    async with SessionLocal() as db:
        row = await db.get(RapidJoinGuard, uid)
        if row:
            row.last_triggered_at = now
            row.trigger_count += 1
        if banned:
            await db.execute(update(User).where(User.id == uid).values(is_banned=True))
        await db.commit()

    await st.set_value('anti_fast_join_last_user_id', str(uid))
    await st.set_value('anti_fast_join_last_at', now.isoformat(timespec='seconds'))
    await st.set_value('anti_fast_join_last_deleted', str(deleted))
    await st.set_value('anti_fast_join_last_failed', str(failed))
    total = int(await st.get_value('anti_fast_join_bans', '0') or '0') + (1 if banned else 0)
    await st.set_value('anti_fast_join_bans', str(total))
    return True


async def health_text() -> str:
    async with SessionLocal() as db:
        known = int((await db.execute(select(func.count(RapidJoinGuard.user_id)))).scalar() or 0)
    return (
        '🛡️ Anti publication immédiate\n'
        f"Statut : {'✅ ON' if await enabled() else '⛔ OFF'}\n"
        f'Délai : {await window_minutes()} min\n'
        f'Arrivées connues : {known}\n'
        f"Bans déclenchés : {await st.get_value('anti_fast_join_bans','0')}\n"
        f"Dernier déclenchement : {await st.get_value('anti_fast_join_last_at','jamais')}\n"
        f"Dernier nettoyage : {await st.get_value('anti_fast_join_last_deleted','0')} supprimé(s), {await st.get_value('anti_fast_join_last_failed','0')} échec(s)"
    )
