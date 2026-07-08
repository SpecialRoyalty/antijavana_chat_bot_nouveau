from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import select

from app.config import get_settings
from app.db.models import MediaHash, User, WordRule
from app.db.session import SessionLocal
from app.services import settings as st
from app.services.hashban import file_sha256
from app.services.state import log_error, track
from app.services.users import display_name, protected


def has_link(text: str) -> bool:
    return bool(re.search(r'(https?://|t\.me/|www\.|\.com\b|\.net\b|\.io\b)', text or '', re.I))


def has_mention(text: str) -> bool:
    return '@' in (text or '')


def has_command(text: str) -> bool:
    return (text or '').strip().startswith('/')


def is_media(msg: Message) -> bool:
    return bool(msg.photo or msg.video or msg.document or msg.animation or msg.audio or msg.voice or msg.video_note)


def file_ids(msg: Message) -> list[tuple[str, str, str]]:
    if msg.photo:
        return [(msg.photo[-1].file_unique_id, msg.photo[-1].file_id, 'photo')]
    if msg.video:
        return [(msg.video.file_unique_id, msg.video.file_id, 'video')]
    if msg.document:
        return [(msg.document.file_unique_id, msg.document.file_id, 'document')]
    if msg.animation:
        return [(msg.animation.file_unique_id, msg.animation.file_id, 'animation')]
    if msg.video_note:
        return [(msg.video_note.file_unique_id, msg.video_note.file_id, 'video_note')]
    return []


# Best-effort in-memory album tracking.
# Telegram sends album items as separate messages with the same media_group_id.
# The DB schema has no media_group_id column, so we keep a runtime cache to delete
# already-seen sibling messages and block future sibling messages in the same album.
_MEDIA_GROUP_MESSAGES: Dict[Tuple[int, str], List[int]] = {}
_BLOCKED_MEDIA_GROUPS: Set[Tuple[int, str]] = set()


def _album_key(msg: Message) -> tuple[int, str] | None:
    if not getattr(msg, 'media_group_id', None):
        return None
    return (msg.chat.id, str(msg.media_group_id))


def _remember_album_message(msg: Message) -> None:
    key = _album_key(msg)
    if not key:
        return
    ids = _MEDIA_GROUP_MESSAGES.setdefault(key, [])
    if msg.message_id not in ids:
        ids.append(msg.message_id)
    # Prevent unbounded growth in long-running processes.
    if len(_MEDIA_GROUP_MESSAGES) > 1000:
        _MEDIA_GROUP_MESSAGES.clear()
        _BLOCKED_MEDIA_GROUPS.clear()


async def _delete_album_messages(bot: Bot, msg: Message) -> None:
    key = _album_key(msg)
    if not key:
        await delete(bot, msg)
        return

    _BLOCKED_MEDIA_GROUPS.add(key)
    ids = list(dict.fromkeys(_MEDIA_GROUP_MESSAGES.get(key, []) + [msg.message_id]))
    for mid in ids:
        try:
            await bot.delete_message(msg.chat.id, mid)
        except Exception:
            pass


async def words(kind: str) -> list[str]:
    async with SessionLocal() as db:
        res = await db.execute(select(WordRule).where(WordRule.kind == kind))
        return [x.word.lower() for x in res.scalars().all()]


async def text_has_word(kind: str, text: str) -> bool:
    t = (text or '').lower()
    return any(w and w in t for w in await words(kind))


async def restrict(bot: Bot, chat_id: int, user_id: int, days: int):
    if await protected(user_id):
        return
    until = datetime.utcnow() + timedelta(days=days)
    try:
        await bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions={'can_send_messages': False},
            until_date=until,
        )
        async with SessionLocal() as db:
            u = await db.get(User, user_id)
            if u:
                u.is_restricted = True
            await db.commit()
    except Exception as e:
        await log_error('restrict', e)


async def ban(bot: Bot, chat_id: int, user_id: int):
    if await protected(user_id):
        return
    try:
        await bot.ban_chat_member(chat_id, user_id)
        async with SessionLocal() as db:
            u = await db.get(User, user_id)
            if u:
                u.is_banned = True
            await db.commit()
    except Exception as e:
        await log_error('ban', e)


async def delete(bot: Bot, msg: Message):
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass


async def _upsert_media_hash(
    *,
    user_id: int | None,
    key: str,
    file_id: str,
    media_type: str,
    banned: bool,
) -> None:
    async with SessionLocal() as db:
        old = await db.execute(select(MediaHash).where(MediaHash.file_unique_id == key))
        mh = old.scalar_one_or_none()
        if not mh:
            mh = MediaHash(
                user_id=user_id,
                file_unique_id=key,
                file_id=file_id,
                media_type=media_type,
                banned=banned,
            )
            db.add(mh)
        else:
            # Keep the latest file_id/type for operational reuse.
            mh.file_id = file_id
            mh.media_type = media_type
            if user_id is not None and mh.user_id is None:
                mh.user_id = user_id
            if banned:
                mh.banned = True
        await db.commit()


async def record_media(msg: Message, banned: bool = False, bot: Bot | None = None):
    """Record all media keys for a message.

    Previous bug: only file_unique_id was stored here. Now we also store SHA256
    whenever a bot instance is provided. /pedo and normal media intake should pass bot.
    """
    entries = file_ids(msg)
    if not entries:
        return

    user_id = msg.from_user.id if msg.from_user else None

    for unique, file_id, typ in entries:
        await _upsert_media_hash(
            user_id=user_id,
            key=unique,
            file_id=file_id,
            media_type=typ,
            banned=banned,
        )

        if bot:
            sha = await file_sha256(bot, file_id)
            if sha:
                await _upsert_media_hash(
                    user_id=user_id,
                    key=sha,
                    file_id=file_id,
                    media_type=typ,
                    banned=banned,
                )

    # Count one media message only once, not once per hash key.
    if user_id and not banned:
        async with SessionLocal() as db:
            u = await db.get(User, user_id)
            if u:
                u.media_count += 1
                u.last_media_session = int(await st.get_value('active_session_id', '0') or '0')
            await db.commit()


async def contains_banned_hash(bot: Bot, msg: Message) -> bool:
    entries = file_ids(msg)
    ids = [x[0] for x in entries]
    for _unique, file_id, _typ in entries:
        sha = await file_sha256(bot, file_id)
        if sha:
            ids.append(sha)

    if not ids:
        return False

    async with SessionLocal() as db:
        res = await db.execute(
            select(MediaHash).where(
                MediaHash.file_unique_id.in_(ids),
                MediaHash.banned == True,  # noqa: E712
            )
        )
        return res.scalar_one_or_none() is not None


async def moderate_message(bot: Bot, msg: Message) -> bool:
    """Moderate a group message.

    Returns True if later handlers may continue processing/copying the message.
    Returns False if the message was deleted, restricted, banned, or otherwise blocked.
    """
    if not msg.from_user:
        return True

    await track(msg.chat.id, msg.message_id, msg.from_user.id, 'message', is_media(msg))

    if msg.chat.id != get_settings().main_group_id:
        return True

    uid = msg.from_user.id
    text = msg.text or msg.caption or ''
    trusted = uid in get_settings().trusted_ids
    admin = uid in get_settings().admin_ids

    if not await st.is_open() and not (trusted or admin):
        await delete(bot, msg)
        return False

    if is_media(msg):
        _remember_album_message(msg)
        key = _album_key(msg)
        if key and key in _BLOCKED_MEDIA_GROUPS:
            await delete(bot, msg)
            await ban(bot, msg.chat.id, uid)
            return False

        if await contains_banned_hash(bot, msg):
            await _delete_album_messages(bot, msg)
            await ban(bot, msg.chat.id, uid)
            return False

        # Record normal media with both file_unique_id and SHA256 before any later logic.
        await record_media(msg, bot=bot)

    # Links are forbidden for everyone except admins; trusted message is deleted without sanction.
    if has_link(text):
        await delete(bot, msg)
        if not (trusted or admin):
            await ban(bot, msg.chat.id, uid)
        return False

    if trusted or admin:
        return True

    if has_command(text):
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 1)
        return False

    if msg.video_note:
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 1)
        return False

    if has_mention(text):
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 2)
        return False

    if await text_has_word('ban', text):
        await delete(bot, msg)
        await ban(bot, msg.chat.id, uid)
        return False

    if await text_has_word('forbidden', text):
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 1)
        return False

    if text and not is_media(msg):
        async with SessionLocal() as db:
            u = await db.get(User, uid)
            if u and u.media_count <= 0:
                await delete(bot, msg)
                warn = await bot.send_message(
                    msg.chat.id,
                    f'{display_name(msg.from_user)}, envoie d’abord un média avant d’écrire.',
                )
                await track(msg.chat.id, warn.message_id, None, 'temp', False)
                return False

    return True
