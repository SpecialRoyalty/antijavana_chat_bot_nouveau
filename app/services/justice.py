from __future__ import annotations

import asyncio
import json
from sqlalchemy import select, func, and_, or_
from aiogram import Bot

from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import User
from app.services import settings as st
from app.services.session_ops import CLOSED_PERMS, OPEN_PERMS, notify_admins
from app.services.state import track, log_error

DEFAULT_JUSTICE_REMOVALS = 20


async def justice_limit() -> int:
    return await st.justice_limit()


async def _current_session_key() -> str:
    sid = await st.get_value('active_session_id','0')
    return sid if sid and sid != '0' else await st.get_value('current_day_key','manual')


async def justice_already_done() -> bool:
    key = await _current_session_key()
    return await st.get_value(f'justice_done_session:{key}','false') == 'true'


async def mark_justice_done():
    key = await _current_session_key()
    await st.set_value(f'justice_done_session:{key}','true')


def _candidate_filter(sid:int):
    return or_(
        and_(User.sessions_present >= 3, User.media_count == 0),
        and_(User.sessions_present >= 14, User.last_media_session < max(sid-14, 0))
    )


async def _protected_ids() -> set[int]:
    s=get_settings()
    bot_id = int(await st.get_value('bot_id','0') or '0')
    ids = set(s.admin_ids) | set(s.trusted_ids)
    if bot_id:
        ids.add(bot_id)
    return ids


def _base_query(protected_ids:set[int], sid:int):
    q = select(User).where(User.is_admin==False, User.is_trusted==False, User.is_banned==False)
    if protected_ids:
        q = q.where(User.id.not_in(list(protected_ids)))
    return q.where(_candidate_filter(sid))


def _display_name(u: User) -> str:
    if getattr(u, 'username', None):
        return '@' + u.username
    return ((getattr(u, 'full_name', None) or 'membre').strip()[:80] or 'membre')


async def _send_visible_justice_removal(bot: Bot, chat_id: int, user: User):
    try:
        m = await bot.send_message(chat_id, f'ANTIJAVANA CHAT removed {_display_name(user)}')
        await track(chat_id, m.message_id, getattr(user, 'id', None), 'justice_removed_notification', False)
    except Exception as exc:
        await log_error('justice_visible_remove_notice', exc)


async def candidate_count() -> int:
    sid = int(await st.get_value('active_session_id','0') or '0')
    protected_ids = await _protected_ids()
    async with SessionLocal() as db:
        q = select(func.count(User.id)).where(User.is_admin==False, User.is_trusted==False, User.is_banned==False)
        if protected_ids:
            q = q.where(User.id.not_in(list(protected_ids)))
        q = q.where(_candidate_filter(sid))
        return int((await db.execute(q)).scalar() or 0)


async def candidates(limit:int|None=None):
    limit = limit or await justice_limit()
    sid = int(await st.get_value('active_session_id','0') or '0')
    protected_ids = await _protected_ids()
    async with SessionLocal() as db:
        q = _base_query(protected_ids, sid).order_by(
            User.media_count.asc(), User.last_media_session.asc(),
            User.sessions_present.desc(), User.suspect_score.desc()
        ).limit(limit)
        return [u for u in (await db.execute(q)).scalars().all() if u.id not in protected_ids]


async def justice_preview_text():
    limit = await justice_limit()
    if await justice_already_done():
        return f'⚖️ Justice populaire\n\nJustice déjà exécutée pour cette session.\nLimite : {limit}.'
    total = await candidate_count()
    cs = await candidates(limit)
    if not cs:
        return f'⚖️ Justice populaire\n\nAucun membre justifiable.\nLimite : {limit}.'
    lines=[
        '⚖️ Justice populaire','',
        f'Membres justifiables : {total}',
        f'Limite : {limit}',
        f'Suppression prévue : {len(cs)}',
        f'Reportés : {max(total-len(cs),0)}','',
        'Aperçu :',
    ]
    for u in cs[:10]:
        name=('@'+u.username) if u.username else (u.full_name or 'membre')
        shown=name[:3]+'****' if len(name)>3 else name+'****'
        lines.append(f'- {shown} — médias: {u.media_count}, sessions: {u.sessions_present}')
    return '\n'.join(lines)


async def _remember_pending(chat_id: int, user_ids: list[int]) -> None:
    if not user_ids:
        return
    key=f'justice_pending:{chat_id}'
    try:
        old=json.loads(await st.get_value(key,'[]') or '[]')
    except Exception:
        old=[]
    merged=list(dict.fromkeys([int(x) for x in old] + [int(x) for x in user_ids]))
    await st.set_value(key, json.dumps(merged))


async def process_pending_justice_removals(bot: Bot) -> int:
    from app.services.multigroup import main_group_ids
    done=0
    for gid in await main_group_ids():
        key=f'justice_pending:{gid}'
        try:
            ids=[int(x) for x in json.loads(await st.get_value(key,'[]') or '[]')]
        except Exception:
            ids=[]
        if not ids:
            continue
        remaining=[]
        for uid in ids:
            try:
                await bot.ban_chat_member(gid, uid, revoke_messages=False)
                await bot.unban_chat_member(gid, uid, only_if_banned=True)
                done += 1
            except Exception:
                remaining.append(uid)
        await st.set_value(key, json.dumps(remaining))
    return done


async def execute_justice(bot:Bot, manual:bool=False):
    from app.services.multigroup import active_group_id, main_group_ids
    active=await active_group_id()
    if not active:
        return 0, 'Aucun groupe actif.'
    limit=await justice_limit()
    if await justice_already_done():
        return 0, 'Justice déjà exécutée pour cette session.'
    total=await candidate_count()
    cs=await candidates(limit)
    if not cs:
        return 0, 'Aucun membre justifiable détecté.'

    # Le flag n'est posé qu'une fois que l'exécution va réellement commencer.
    await mark_justice_done()
    await st.set_value('justice_running','true')
    try:
        await bot.set_chat_permissions(active, permissions=CLOSED_PERMS)
    except Exception as exc:
        await log_error('justice_permissions_close',exc)

    try:
        m=await bot.send_message(
            active,
            f'⚖️ JUSTICE POPULAIRE\n\nLe groupe est bloqué pendant 5 minutes.\n\n'
            f'Membres justifiables : {total}\nLimite session : {limit}\nSuppression prévue : {len(cs)}'
        )
        await track(active,m.message_id,None,'justice',False)
    except Exception as exc:
        await log_error('justice_message',exc)

    groups=await main_group_ids()
    removed_users=0
    for u in cs:
        successes=0
        for gid in groups:
            try:
                # Kick technique uniquement : jamais transformé en GlobalSanction/User.is_banned.
                await bot.ban_chat_member(gid,u.id,revoke_messages=False)
                await bot.unban_chat_member(gid,u.id,only_if_banned=True)
                successes += 1
            except Exception as exc:
                await log_error('justice_remove',f'{gid}/{u.id}: {exc}')
                await _remember_pending(gid,[u.id])
        if successes:
            removed_users += 1
            await _send_visible_justice_removal(bot,active,u)

    await asyncio.sleep(300)
    # Si la session a été basculée pendant les 5 minutes, on rouvre le groupe actuellement actif.
    current=await active_group_id()
    if current and await st.is_open():
        try:
            await bot.set_chat_permissions(current, permissions=OPEN_PERMS)
        except Exception as exc:
            await log_error('justice_permissions_open',exc)

    postponed=max(total-removed_users,0)
    if current:
        try:
            m2=await bot.send_message(
                current,
                f'🟢 JUSTICE TERMINÉE\n\nMembres supprimés : {removed_users}\nReportés : {postponed}\nLe groupe est de nouveau ouvert.'
            )
            await track(current,m2.message_id,None,'justice',False)
        except Exception as exc:
            await log_error('justice_end_message',exc)
    await st.set_value('justice_running','false')
    await notify_admins(bot,f'⚖️ Justice terminée. Éligibles : {total} — Supprimés : {removed_users} — Reportés : {postponed} — Limite : {limit}')
    return removed_users, f'Justice terminée. Membres supprimés : {removed_users}'
