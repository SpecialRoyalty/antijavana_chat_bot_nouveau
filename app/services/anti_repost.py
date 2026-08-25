from __future__ import annotations

import asyncio
import time
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy import select

from app.config import get_settings
from app.db.models import MediaHash
from app.db.session import SessionLocal
from app.services import settings as st
from app.services.hashban import file_sha256, media_file_entries, related_media_messages
from app.services.state import log_error, track
from app.services.users import display_name, protected

_EXISTS_CACHE_TTL = 30.0
_EXISTS_CACHE: dict[str, tuple[bool, float]] = {}


async def enabled() -> bool:
    return (await st.get_value('anti_repost_enabled', 'false')) == 'true'


def _cache_set(key: str, value: bool) -> None:
    _EXISTS_CACHE[key] = (value, time.monotonic() + _EXISTS_CACHE_TTL)


async def _key_exists_non_banned(key: str | None) -> bool:
    if not key:
        return False
    cached = _EXISTS_CACHE.get(key)
    if cached and time.monotonic() < cached[1]:
        return cached[0]
    async with SessionLocal() as db:
        found = (
            await db.execute(
                select(MediaHash.id)
                .where(MediaHash.file_unique_id == key, MediaHash.banned.is_(False))
                .limit(1)
            )
        ).first()
    value = found is not None
    _cache_set(key, value)
    return value


def remember_stored_keys(msg: Message, sha256: str | None = None) -> None:
    """Met immédiatement à jour le cache après l'enregistrement d'un média autorisé."""
    for unique, _file_id, _media_type in media_file_entries(msg):
        _cache_set(unique, True)
    if sha256:
        _cache_set(sha256, True)


async def find_repost_by_id(msg: Message) -> tuple[bool, str]:
    for unique, _file_id, _media_type in media_file_entries(msg):
        if await _key_exists_non_banned(unique):
            return True, 'file_unique_id'
    return False, ''


async def find_repost_by_sha(sha256: str | None) -> tuple[bool, str]:
    if sha256 and await _key_exists_non_banned(sha256):
        return True, 'sha256'
    return False, ''


async def find_repost(bot: Bot, msg: Message) -> tuple[bool, str]:
    """Compatibilité : contrôle ID puis SHA exact."""
    matched = await find_repost_by_id(msg)
    if matched[0]:
        return matched
    entries = media_file_entries(msg)
    if not entries:
        return False, ''
    sha = await file_sha256(bot, entries[0][1])
    return await find_repost_by_sha(sha)


async def _delete_album_or_message(bot: Bot, msg: Message) -> tuple[int, int]:
    targets = related_media_messages(msg) if msg.media_group_id else [msg]
    seen: set[tuple[int, int]] = set()
    unique_targets = []
    for item in targets:
        key = (item.chat.id, item.message_id)
        if key not in seen:
            seen.add(key)
            unique_targets.append(item)

    semaphore = asyncio.Semaphore(4)

    async def remove(item: Message) -> bool:
        async with semaphore:
            try:
                await bot.delete_message(item.chat.id, item.message_id)
                return True
            except TelegramBadRequest as exc:
                low = str(exc).lower()
                if 'message to delete not found' in low or 'message identifier is not specified' in low:
                    return True
                await log_error('anti_repost_delete', exc)
                return False
            except Exception as exc:
                await log_error('anti_repost_delete', exc)
                return False

    results = await asyncio.gather(*(remove(item) for item in unique_targets)) if unique_targets else []
    deleted = sum(1 for ok in results if ok)
    return deleted, len(results) - deleted


async def enforce_known_match(bot: Bot, msg: Message, method: str) -> bool:
    """Applique la suppression quand la détection a déjà été faite par le pipeline."""
    deleted, failed = await _delete_album_or_message(bot, msg)

    try:
        warning = await bot.send_message(
            msg.chat.id,
            f'{display_name(msg.from_user)}, média déjà envoyé : repost interdit.',
        )
        await track(msg.chat.id, warning.message_id, None, 'temp', False)
    except Exception as exc:
        await log_error('anti_repost_warning', exc)

    now = datetime.utcnow().isoformat(timespec='seconds')
    await st.set_value('anti_repost_last_at', now)
    await st.set_value('anti_repost_last_method', method)
    await st.set_value('anti_repost_last_deleted', str(deleted))
    await st.set_value('anti_repost_last_failed', str(failed))
    await st.set_value('anti_repost_last_user_id', str(msg.from_user.id))
    total = int(await st.get_value('anti_repost_blocks', '0') or '0') + 1
    await st.set_value('anti_repost_blocks', str(total))
    return True


async def enforce(bot: Bot, msg: Message) -> bool:
    if not msg.from_user or msg.chat.id != get_settings().main_group_id:
        return False
    if await protected(msg.from_user.id) or not await enabled() or not media_file_entries(msg):
        return False

    matched, method = await find_repost(bot, msg)
    if not matched:
        return False
    return await enforce_known_match(bot, msg, method)


async def health_text() -> str:
    return (
        '♻️ Anti repost\n'
        f"Statut : {'✅ ON' if await enabled() else '⛔ OFF'}\n"
        f"Reposts bloqués : {await st.get_value('anti_repost_blocks','0')}\n"
        f"Dernier blocage : {await st.get_value('anti_repost_last_at','jamais')}\n"
        f"Méthode : {await st.get_value('anti_repost_last_method','-')}\n"
        f"Dernier nettoyage : {await st.get_value('anti_repost_last_deleted','0')} supprimé(s), "
        f"{await st.get_value('anti_repost_last_failed','0')} échec(s)"
    )
