"""Fusionne les données de sécurité d'une seconde base historique dans la DB centrale.

Usage Railway/local :
  DATABASE_URL=<db_centrale> LEGACY_DATABASE_URL_B=<ancienne_db_B> \
      python scripts/merge_legacy_database.py

La DB centrale peut être l'ancienne DB du Groupe A. Le script ne supprime rien :
- MediaHash : déduplication par file_unique_id, banned = A OR B.
- VideoFingerprint : déduplication par fingerprint + métadonnées, banned = A OR B.
- Users : fusion conservatrice des drapeaux/scores.
- WordRule : union des règles.
- PrivateSubscriber : union des personnes ayant /start.
- Ban/mute historiques de B : convertis en GlobalSanction active.

Les historiques transactionnels (commandes VIP/paiements/sessions) ne sont pas
fusionnés automatiquement pour éviter des collisions d'identifiants. Conserver
l'ancienne DB B en lecture seule comme archive après migration.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.session import SessionLocal, init_db
from app.db.models import (
    GlobalSanction,
    MediaHash,
    PrivateSubscriber,
    User,
    VideoFingerprint,
    WordRule,
)


def normalize_url(url: str) -> str:
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if url.startswith('postgresql://'):
        url = 'postgresql+asyncpg://' + url[len('postgresql://'):]
    return url


async def table_exists(conn, name: str) -> bool:
    q = text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name=:name
        )
    """)
    return bool((await conn.execute(q, {'name': name})).scalar())


async def source_rows(conn, table: str):
    if not await table_exists(conn, table):
        return []
    return list((await conn.execute(text(f'SELECT * FROM "{table}"'))).mappings().all())


async def merge_media_hashes(rows) -> tuple[int, int]:
    inserted = updated = 0
    async with SessionLocal() as db:
        for r in rows:
            key = (r.get('file_unique_id') or '').strip()
            if not key:
                continue
            existing = list((await db.execute(
                select(MediaHash).where(MediaHash.file_unique_id == key)
            )).scalars().all())
            banned = bool(r.get('banned', False))
            if existing:
                for item in existing:
                    item.banned = bool(item.banned or banned)
                    if not item.file_id and r.get('file_id'):
                        item.file_id = str(r.get('file_id'))
                    if item.media_type in ('', 'unknown') and r.get('media_type'):
                        item.media_type = str(r.get('media_type'))
                updated += 1
            else:
                db.add(MediaHash(
                    user_id=r.get('user_id'),
                    file_unique_id=key,
                    file_id=str(r.get('file_id') or ''),
                    media_type=str(r.get('media_type') or 'unknown'),
                    banned=banned,
                    created_at=r.get('created_at') or datetime.utcnow(),
                ))
                inserted += 1
        await db.commit()
    return inserted, updated


async def merge_fingerprints(rows) -> tuple[int, int]:
    inserted = updated = 0
    async with SessionLocal() as db:
        for r in rows:
            fp = (r.get('fingerprint') or '').strip()
            if not fp:
                continue
            duration = r.get('duration')
            width = r.get('width')
            height = r.get('height')
            existing = list((await db.execute(
                select(VideoFingerprint).where(
                    VideoFingerprint.fingerprint == fp,
                    VideoFingerprint.duration == duration,
                    VideoFingerprint.width == width,
                    VideoFingerprint.height == height,
                )
            )).scalars().all())
            banned = bool(r.get('banned', False))
            if existing:
                for item in existing:
                    item.banned = bool(item.banned or banned)
                    if not item.file_id and r.get('file_id'):
                        item.file_id = str(r.get('file_id'))
                updated += 1
            else:
                db.add(VideoFingerprint(
                    user_id=r.get('user_id'),
                    file_id=str(r.get('file_id') or ''),
                    fingerprint=fp,
                    duration=duration,
                    width=width,
                    height=height,
                    banned=banned,
                    created_at=r.get('created_at') or datetime.utcnow(),
                ))
                inserted += 1
        await db.commit()
    return inserted, updated


async def _ensure_global_sanction(db, user_id: int, kind: str, source: str) -> None:
    exists = (await db.execute(select(GlobalSanction.id).where(
        GlobalSanction.user_id == user_id,
        GlobalSanction.kind == kind,
        GlobalSanction.active.is_(True),
    ).limit(1))).scalar_one_or_none()
    if exists is None:
        db.add(GlobalSanction(
            user_id=user_id,
            kind=kind,
            active=True,
            source=source,
            reason='Import ancienne base',
        ))


async def merge_users(rows) -> tuple[int, int]:
    inserted = updated = 0
    async with SessionLocal() as db:
        for r in rows:
            uid = r.get('id')
            if uid is None:
                continue
            uid = int(uid)
            user = await db.get(User, uid)
            if not user:
                user = User(
                    id=uid,
                    username=r.get('username'),
                    full_name=str(r.get('full_name') or ''),
                    is_admin=bool(r.get('is_admin', False)),
                    is_trusted=bool(r.get('is_trusted', False)),
                    is_banned=bool(r.get('is_banned', False)),
                    is_restricted=bool(r.get('is_restricted', False)),
                    media_count=int(r.get('media_count') or 0),
                    last_media_session=int(r.get('last_media_session') or 0),
                    sessions_present=int(r.get('sessions_present') or 0),
                    sessions_with_media=int(r.get('sessions_with_media') or 0),
                    suspect_score=int(r.get('suspect_score') or 0),
                    reward_counter=int(r.get('reward_counter') or 0),
                    total_invites=int(r.get('total_invites') or 0),
                    weekly_invites=int(r.get('weekly_invites') or 0),
                    created_at=r.get('created_at') or datetime.utcnow(),
                    last_seen=r.get('last_seen') or datetime.utcnow(),
                )
                db.add(user)
                inserted += 1
            else:
                if r.get('username'):
                    user.username = r.get('username')
                if r.get('full_name'):
                    user.full_name = str(r.get('full_name'))
                user.is_admin = bool(user.is_admin or r.get('is_admin', False))
                user.is_trusted = bool(user.is_trusted or r.get('is_trusted', False))
                user.is_banned = bool(user.is_banned or r.get('is_banned', False))
                user.is_restricted = bool(user.is_restricted or r.get('is_restricted', False))
                # Max évite de doubler artificiellement les compteurs issus des deux installations.
                for name in ('media_count', 'last_media_session', 'sessions_present', 'sessions_with_media',
                             'suspect_score', 'reward_counter', 'total_invites', 'weekly_invites'):
                    setattr(user, name, max(int(getattr(user, name) or 0), int(r.get(name) or 0)))
                if r.get('last_seen') and (not user.last_seen or r.get('last_seen') > user.last_seen):
                    user.last_seen = r.get('last_seen')
                updated += 1
            if bool(r.get('is_banned', False)):
                await _ensure_global_sanction(db, uid, 'ban', 'legacy_import')
            if bool(r.get('is_restricted', False)):
                await _ensure_global_sanction(db, uid, 'mute', 'legacy_import')
        await db.commit()
    return inserted, updated


async def merge_word_rules(rows) -> int:
    added = 0
    async with SessionLocal() as db:
        for r in rows:
            kind = str(r.get('kind') or '').strip().lower()
            word = str(r.get('word') or '').strip()
            if not kind or not word:
                continue
            exists = (await db.execute(select(WordRule.id).where(
                WordRule.kind == kind, WordRule.word == word
            ).limit(1))).scalar_one_or_none()
            if exists is None:
                db.add(WordRule(kind=kind, word=word))
                added += 1
        await db.commit()
    return added


async def merge_private_subscribers(rows) -> int:
    added = 0
    async with SessionLocal() as db:
        for r in rows:
            uid = r.get('user_id')
            if uid is None:
                continue
            uid = int(uid)
            row = await db.get(PrivateSubscriber, uid)
            if not row:
                db.add(PrivateSubscriber(
                    user_id=uid,
                    username=r.get('username'),
                    full_name=str(r.get('full_name') or ''),
                    active=bool(r.get('active', True)),
                    started_at=r.get('started_at') or datetime.utcnow(),
                    last_start_at=r.get('last_start_at') or datetime.utcnow(),
                    last_broadcast_at=r.get('last_broadcast_at'),
                ))
                added += 1
            else:
                row.active = bool(row.active or r.get('active', True))
                if r.get('username'):
                    row.username = r.get('username')
                if r.get('full_name'):
                    row.full_name = str(r.get('full_name'))
                if r.get('last_start_at') and r.get('last_start_at') > row.last_start_at:
                    row.last_start_at = r.get('last_start_at')
        await db.commit()
    return added


async def main() -> None:
    source_url = os.getenv('LEGACY_DATABASE_URL_B', '').strip()
    if not source_url:
        raise SystemExit('LEGACY_DATABASE_URL_B manquant.')

    await init_db()
    source_engine = create_async_engine(normalize_url(source_url), pool_pre_ping=True)
    try:
        async with source_engine.connect() as conn:
            media = await source_rows(conn, 'media_hashes')
            fps = await source_rows(conn, 'video_fingerprints')
            users = await source_rows(conn, 'users')
            rules = await source_rows(conn, 'word_rules')
            subs = await source_rows(conn, 'private_subscribers')

        mh_i, mh_u = await merge_media_hashes(media)
        fp_i, fp_u = await merge_fingerprints(fps)
        us_i, us_u = await merge_users(users)
        wr_i = await merge_word_rules(rules)
        ps_i = await merge_private_subscribers(subs)

        print('Migration terminée sans suppression :')
        print(f'  media_hashes       : +{mh_i}, fusionnés {mh_u}')
        print(f'  video_fingerprints : +{fp_i}, fusionnés {fp_u}')
        print(f'  users              : +{us_i}, fusionnés {us_u}')
        print(f'  word_rules         : +{wr_i}')
        print(f'  private_subscribers: +{ps_i}')
        print('Les sanctions historiques is_banned/is_restricted ont été converties en sanctions globales.')
    finally:
        await source_engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
