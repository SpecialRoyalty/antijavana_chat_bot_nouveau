from __future__ import annotations

import time
from typing import Iterable

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Setting
from app.db.session import SessionLocal

# Petit cache local pour les réglages très consultés (groupe ouvert, anti-repost,
# session active, etc.). set_value() met toujours le cache à jour immédiatement.
# Le TTL garde un comportement correct même si une autre instance modifie la DB.
_CACHE_TTL_SECONDS = 10.0
_CACHE: dict[str, tuple[str, float]] = {}


def _cache_get(key: str) -> str | None:
    cached = _CACHE.get(key)
    if not cached:
        return None
    value, expires_at = cached
    if time.monotonic() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: str) -> None:
    _CACHE[key] = (value, time.monotonic() + _CACHE_TTL_SECONDS)


def invalidate_cache(key: str | None = None) -> None:
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)


async def get_value(key: str, default: str = '') -> str:
    cached = _cache_get(key)
    if cached is not None:
        return cached

    async with SessionLocal() as db:
        obj = await db.get(Setting, key)
        value = obj.value if obj else default
    _cache_set(key, value)
    return value


async def get_values(keys: Iterable[str]) -> dict[str, str]:
    """Lecture groupée pour les écrans de santé/admin qui utilisent plusieurs clés."""
    requested = list(dict.fromkeys(keys))
    result: dict[str, str] = {}
    missing: list[str] = []

    for key in requested:
        cached = _cache_get(key)
        if cached is None:
            missing.append(key)
        else:
            result[key] = cached

    if missing:
        async with SessionLocal() as db:
            rows = (
                await db.execute(select(Setting).where(Setting.key.in_(missing)))
            ).scalars().all()
        found = {row.key: row.value for row in rows}
        for key in missing:
            value = found.get(key, '')
            result[key] = value
            _cache_set(key, value)

    return result


async def set_value(key: str, value: str) -> None:
    value = str(value)
    async with SessionLocal() as db:
        obj = await db.get(Setting, key)
        if not obj:
            obj = Setting(key=key, value=value)
            db.add(obj)
        else:
            obj.value = value
        await db.commit()
    _cache_set(key, value)


async def init_defaults() -> None:
    s = get_settings()
    defaults = {
        'auto_enabled': str(s.auto_schedule_enabled).lower(),
        'time_slot': s.default_time_slot,
        'vote_goal': str(s.default_vote_goal),
        'group_open': 'false',
        'status_message_id': '',
        'active_session_id': '0',
        'rules_text': 'Respectez les règles. Pas de liens, pas de mentions, pas de commandes.',
        'vip_text': '💎 ACCÈS VIP\n\nChoisissez une offre pour obtenir plus d’informations.',
        'crowd_text': '🎯 FINANCEMENT COMMUNAUTAIRE',
        'ads_text': '📢 Publicité',
        'weekly_top_started': 'false',
        'weekly_top_start': '',
        'manual_security_warned_at': '',
        'manual_opened_at': '',
        'free_pass_enabled': 'false',
        'free_pass_places': '20',
        'free_pass_cooldown_days': '30',
        'free_pass_min_media': '3',
        'free_pass_min_invites': '0',
        'free_pass_message_id': '',
        'justice_limit': '20',
        'hashban_reposts_detected': '0',
        'hashban_reposts_blocked': '0',
        'hashban_reposts_failed': '0',
        'hashban_detected_file_unique_id': '0',
        'hashban_detected_sha256': '0',
        'anti_fast_join_enabled': 'true',
        'anti_fast_join_minutes': '5',
        'anti_fast_join_bans': '0',
        'anti_fast_join_last_at': '',
        'anti_fast_join_last_deleted': '0',
        'anti_fast_join_last_failed': '0',
        'anti_repost_enabled': 'false',
        'anti_repost_blocks': '0',
        'anti_repost_last_at': '',
        'anti_repost_last_method': '',
        'anti_repost_last_deleted': '0',
        'anti_repost_last_failed': '0',
    }

    # Un seul SELECT + un seul COMMIT au lieu d'un get/set pour chaque clé.
    async with SessionLocal() as db:
        rows = (
            await db.execute(select(Setting).where(Setting.key.in_(list(defaults))))
        ).scalars().all()
        by_key = {row.key: row for row in rows}
        existing = {row.key: row.value for row in rows}
        for key, value in defaults.items():
            if key not in by_key:
                db.add(Setting(key=key, value=value))
                existing[key] = value
            elif by_key[key].value == '':
                # Comportement historique : une valeur vide reçoit le défaut.
                by_key[key].value = value
                existing[key] = value
        await db.commit()

    for key, value in existing.items():
        if key in defaults:
            _cache_set(key, value)


async def is_open() -> bool:
    return (await get_value('group_open', 'false')) == 'true'


async def set_open(value: bool) -> None:
    await set_value('group_open', 'true' if value else 'false')


async def auto_enabled() -> bool:
    return (await get_value('auto_enabled', 'true')) == 'true'


async def time_slot() -> str:
    return await get_value('time_slot', get_settings().default_time_slot)


async def vote_goal() -> int:
    return int(await get_value('vote_goal', str(get_settings().default_vote_goal)))


async def justice_limit() -> int:
    raw = await get_value('justice_limit', '20')
    try:
        value = int(raw)
    except Exception:
        value = 20
    return max(1, min(value, 200))
