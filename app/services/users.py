from __future__ import annotations

import re
import time
from datetime import datetime

from aiogram.types import User as TgUser
from sqlalchemy import select, update

from app.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal

_SETTINGS = get_settings()
_ADMIN_IDS = frozenset(_SETTINGS.admin_ids)
_PROTECTED_IDS = frozenset(_SETTINGS.all_admin_ids)

# Évite une écriture PostgreSQL à chaque message d'un utilisateur actif.
_USER_TOUCH_TTL = 30.0
_USER_TOUCH_CACHE: dict[int, tuple[float, str | None, str]] = {}
_MEDIA_SENT_CACHE: dict[int, bool] = {}


def display_name(u):
    if getattr(u, 'username', None):
        return '@' + u.username
    return (getattr(u, 'full_name', '') or 'Utilisateur').strip()


def anon_name(username: str | None, full_name: str = ''):
    name = ('@' + username) if username else (full_name or 'membre')
    if len(name) <= 3:
        return name[0] + '*'
    return name[:3] + '****'


def is_gibberish(name: str):
    n = re.sub(r'[^A-Za-z]', '', name or '')
    if len(n) < 4:
        return False
    if re.search(r'(.)\1{3,}', n):
        return True
    vowels = sum(c.lower() in 'aeiouy' for c in n)
    ratio = vowels / len(n)
    return ratio < 0.18 or ratio > 0.82 or bool(
        re.match(r'^[A-Z]?[a-z]{1,2}[a-z]{1,2}\s+[A-Z]?[a-z]{1,4}$', name or '')
    )


async def upsert_user(tgu: TgUser):
    """Crée/met à jour un utilisateur sans écrire last_seen sur chaque message."""
    now_mono = time.monotonic()
    username = tgu.username
    full_name = tgu.full_name or ''
    cached = _USER_TOUCH_CACHE.get(tgu.id)

    if cached:
        last_touch, old_username, old_full_name = cached
        profile_unchanged = old_username == username and old_full_name == full_name
        if profile_unchanged and now_mono - last_touch < _USER_TOUCH_TTL:
            return None

    async with SessionLocal() as db:
        user = await db.get(User, tgu.id)
        if not user:
            score = 0
            if not username:
                score += 10
            if is_gibberish(full_name):
                score += 20
            user = User(
                id=tgu.id,
                username=username,
                full_name=full_name,
                suspect_score=score,
            )
            db.add(user)
        user.username = username
        user.full_name = full_name
        user.last_seen = datetime.utcnow()
        user.is_admin = tgu.id in _ADMIN_IDS
        user.is_trusted = tgu.id in _PROTECTED_IDS
        await db.commit()
        _MEDIA_SENT_CACHE[tgu.id] = bool(user.media_count > 0)

    _USER_TOUCH_CACHE[tgu.id] = (now_mono, username, full_name)
    return user


async def has_sent_media(user_id: int) -> bool:
    cached = _MEDIA_SENT_CACHE.get(user_id)
    if cached is not None:
        return cached
    async with SessionLocal() as db:
        media_count = (
            await db.execute(select(User.media_count).where(User.id == user_id))
        ).scalar_one_or_none()
    value = bool((media_count or 0) > 0)
    _MEDIA_SENT_CACHE[user_id] = value
    return value


def mark_media_sent(user_id: int) -> None:
    _MEDIA_SENT_CACHE[user_id] = True


async def increment_media_count(user_id: int, session_id: int) -> None:
    """Incrémente le compteur sans SELECT préalable."""
    async with SessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                media_count=User.media_count + 1,
                last_media_session=session_id,
            )
        )
        await db.commit()
    mark_media_sent(user_id)


async def protected(user_id: int):
    return user_id in _PROTECTED_IDS
