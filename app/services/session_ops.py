from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, func, update
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.db.session import SessionLocal
from app.db.models import SessionLog, TrackedMessage, TrustedAction, User, ErrorLog
from app.services import settings as st
from app.services.state import ensure_status_message, log_error

OPEN_PERMS={
    'can_send_messages':True,'can_send_audios':True,'can_send_documents':True,'can_send_photos':True,
    'can_send_videos':True,'can_send_video_notes':False,'can_send_voice_notes':True,'can_send_polls':False,
    'can_send_other_messages':False,'can_add_web_page_previews':False,
}
CLOSED_PERMS={'can_send_messages':False}


async def set_group_open(bot: Bot, open_: bool, kind: str='auto'):
    from app.services.multigroup import active_group_id, main_group_ids, sync_redirections
    active = await active_group_id()
    groups = await main_group_ids()

    if open_ and not active:
        return False

    if open_:
        # Un seul groupe principal ouvert à la fois.
        for gid in groups:
            try:
                await bot.set_chat_permissions(gid, permissions=OPEN_PERMS if gid == active else CLOSED_PERMS)
            except Exception as exc:
                await log_error('permissions', f'{gid}: {exc}')

        if await st.is_open():
            await ensure_status_message(bot, active)
            await sync_redirections(bot)
            return True

        async with SessionLocal() as db:
            sess=SessionLog(chat_id=active,kind=kind,status='open')
            db.add(sess)
            await db.flush()
            sid=sess.id
            await db.execute(
                update(User)
                .where(User.is_admin==False, User.is_trusted==False, User.is_banned==False)
                .values(sessions_present=User.sessions_present+1)
            )
            await db.commit()
        await st.set_value('active_session_id',str(sid))
        await st.set_open(True)
        await st.set_value('session_suspended','false')
        await st.set_value('manual_opened_at', datetime.utcnow().isoformat() if kind=='manual' else '')
        await ensure_status_message(bot,active)
        await sync_redirections(bot)
        # Si la soirée ouvre après 23h (ou après une soirée précédemment annulée),
        # les accès Pass soirée restés en attente sont libérés à l'ouverture réelle.
        try:
            from app.services.vip import send_due_pass_soiree_links
            await send_due_pass_soiree_links(bot, force=True)
        except Exception as exc:
            await log_error('pass_soiree_release_on_open', exc)
        try:
            from app.services.freepass import send_due_free_pass_links
            await send_due_free_pass_links(bot, force=True)
        except Exception as exc:
            await log_error('free_pass_release_on_open', exc)
        return True

    # Fermeture.
    if not await st.is_open():
        for gid in groups:
            try:
                await bot.set_chat_permissions(gid, permissions=CLOSED_PERMS)
            except Exception:
                pass
        if active:
            await ensure_status_message(bot,active)
        await sync_redirections(bot)
        return True

    sid=int(await st.get_value('active_session_id','0') or '0')
    for gid in groups:
        try:
            await bot.set_chat_permissions(gid, permissions=CLOSED_PERMS)
        except Exception as exc:
            await log_error('permissions_close', f'{gid}: {exc}')
    await cleanup_session(bot, all_known=False)
    await close_active_session()
    await st.set_open(False)
    await st.set_value('session_suspended','false')
    await send_report(bot, kind, sid=sid)
    if active:
        await ensure_status_message(bot,active)
    await sync_redirections(bot)
    return True


async def close_active_session():
    sid=int(await st.get_value('active_session_id','0') or '0')
    async with SessionLocal() as db:
        if sid:
            sess=await db.get(SessionLog,sid)
            if sess:
                sess.status='closed'
                sess.closed_at=datetime.utcnow()
        await db.commit()
    await st.set_value('active_session_id','0')
    await st.set_value('manual_opened_at','')


async def cleanup_session(bot:Bot, all_known:bool=False):
    from app.services.multigroup import main_group_ids
    sid=int(await st.get_value('active_session_id','0') or '0')
    groups=await main_group_ids()
    async with SessionLocal() as db:
        q=select(
            TrackedMessage.id,TrackedMessage.chat_id,TrackedMessage.message_id,TrackedMessage.is_media
        ).where(TrackedMessage.deleted.is_(False),TrackedMessage.kind!='status')
        if all_known:
            if groups:
                q=q.where(TrackedMessage.chat_id.in_(groups))
        elif sid:
            q=q.where(TrackedMessage.session_id==sid)
        elif groups:
            q=q.where(TrackedMessage.chat_id.in_(groups))
        items=list((await db.execute(q)).all())

    semaphore=asyncio.Semaphore(4)
    async def remove(item):
        _row_id,chat_id,message_id,is_media=item
        async with semaphore:
            try:
                await bot.delete_message(chat_id,message_id)
                return _row_id,True,bool(is_media)
            except TelegramBadRequest as exc:
                low=str(exc).lower()
                if 'message to delete not found' in low or 'message identifier is not specified' in low:
                    return _row_id,True,bool(is_media)
                await log_error('cleanup_delete',f'{chat_id}/{message_id}: {exc}')
                return _row_id,False,bool(is_media)
            except Exception as exc:
                await log_error('cleanup_delete',f'{chat_id}/{message_id}: {exc}')
                return _row_id,False,bool(is_media)

    results=await asyncio.gather(*(remove(item) for item in items)) if items else []
    successful=[rid for rid,ok,_media in results if ok]
    deleted=len(successful)
    failed=len(results)-deleted
    media_failed=sum(1 for _rid,ok,is_media in results if not ok and is_media)

    async with SessionLocal() as db:
        if successful:
            await db.execute(update(TrackedMessage).where(TrackedMessage.id.in_(successful)).values(deleted=True))
        if sid and deleted:
            await db.execute(
                update(SessionLog).where(SessionLog.id==sid)
                .values(messages_deleted=SessionLog.messages_deleted+deleted)
            )
        await db.commit()

    if failed:
        await notify_admins(
            bot,
            f'🚨 ERREUR NETTOYAGE\n\nMessages non supprimés : {failed}\nMédias non supprimés : {media_failed}\n\nVérifie les droits de suppression dans A et B puis relance le nettoyage.'
        )
    return deleted, failed


async def notify_admins(bot:Bot,text:str, reply_markup=None):
    from app.config import get_settings
    async def send_one(aid:int):
        try:
            await bot.send_message(aid,text,reply_markup=reply_markup)
        except Exception:
            pass
    await asyncio.gather(*(send_one(aid) for aid in get_settings().admin_ids))


async def send_report(bot:Bot, kind='auto', sid:int|None=None):
    async with SessionLocal() as db:
        sess=None
        if sid:
            sess=await db.get(SessionLog,sid)
        if not sess:
            sess=(await db.execute(select(SessionLog).order_by(SessionLog.id.desc()).limit(1))).scalar_one_or_none()
        actions=await db.execute(
            select(TrustedAction.trusted_username,TrustedAction.command,func.count(TrustedAction.id))
            .group_by(TrustedAction.trusted_username,TrustedAction.command)
        )
        action_lines=[f'@{name or "trusted"} {cmd}: {c}' for name,cmd,c in actions.all()]
        inactive_count=(await db.execute(select(func.count(User.id)).where(User.media_count==0))).scalar() or 0
        trusted_inactive=await db.execute(select(User).where(User.is_trusted==True).limit(20))
        trusted_lines=[]
        for u in trusted_inactive.scalars().all():
            last=(u.last_seen.strftime('%d/%m %H:%M') if u.last_seen else 'jamais')
            trusted_lines.append(f'@{u.username or u.full_name or "trusted"} — dernière activité {last}')
        err=(await db.execute(
            select(func.count(ErrorLog.id)).where(ErrorLog.created_at>=datetime.utcnow()-timedelta(hours=24))
        )).scalar() or 0
        remain=0
        if sid:
            remain=(await db.execute(
                select(func.count(TrackedMessage.id)).where(
                    TrackedMessage.session_id==sid,
                    TrackedMessage.deleted==False,
                    TrackedMessage.kind!='status',
                )
            )).scalar() or 0
    text=(f'📊 RAPPORT DE SESSION\n\nType : {kind}\n'
          f'Groupe de départ : {sess.chat_id if sess else "-"}\n'
          f'Messages vus : {sess.messages_seen if sess else 0}\nMédias vus : {sess.media_seen if sess else 0}\n'
          f'Messages supprimés : {sess.messages_deleted if sess else 0}\nMessages restants suivis : {remain}\n\n'
          f'Inactifs jamais média : {inactive_count}\n\nActions trusted :\n' + ('\n'.join(action_lines[-20:]) or 'Aucune') +
          '\n\nTrusted inactifs / peu actifs :\n' + ('\n'.join(trusted_lines[:10]) or 'Aucun') + f'\n\nErreurs 24h : {err}')
    await notify_admins(bot,text)


async def security_close_if_manual(bot:Bot):
    if not await st.is_open() or await st.auto_enabled():
        return
    opened=await st.get_value('manual_opened_at','')
    if not opened:
        return
    try:
        dt=datetime.fromisoformat(opened)
    except Exception:
        return
    if datetime.utcnow()-dt < timedelta(hours=2):
        return
    warned=await st.get_value('manual_security_warned_at','')
    if not warned:
        kb=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='✅ Maintenir ouvert',callback_data='manual_keep_open'),
            InlineKeyboardButton(text='🔒 Fermer',callback_data='manual_security_close'),
        ]])
        await st.set_value('manual_security_warned_at',datetime.utcnow().isoformat())
        await notify_admins(bot,'⚠️ FERMETURE DE SÉCURITÉ\n\nLa session est ouverte manuellement depuis 2h. Sans réponse sous 5 minutes : fermeture.',kb)
        return
    try:
        wdt=datetime.fromisoformat(warned)
    except Exception:
        wdt=datetime.utcnow()-timedelta(minutes=10)
    if datetime.utcnow()-wdt >= timedelta(minutes=5):
        await set_group_open(bot,False,'security')


async def count_known_bans_and_restrictions():
    async with SessionLocal() as db:
        banned=(await db.execute(select(func.count(User.id)).where(User.is_banned==True))).scalar() or 0
        restricted=(await db.execute(select(func.count(User.id)).where(User.is_restricted==True))).scalar() or 0
        return int(banned), int(restricted)


async def presidential_pardon(bot:Bot):
    from app.services.multigroup import global_unban, active_group_id
    async with SessionLocal() as db:
        users=list((await db.execute(select(User.id).where(User.is_banned==True))).scalars().all())
    for uid in users:
        await global_unban(bot, uid, source='presidential_pardon')
    chat=await active_group_id()
    if chat and await st.is_open():
        await bot.send_message(chat,f'👑 GRÂCE PRÉSIDENTIELLE\n\n{len(users)} bannissement(s) globaux levé(s).\n\nNe confondez pas pardon et oubli.')
    return len(users)


async def ministerial_pardon(bot:Bot):
    from app.services.multigroup import global_unmute, active_group_id
    async with SessionLocal() as db:
        users=list((await db.execute(select(User.id).where(User.is_restricted==True))).scalars().all())
    for uid in users:
        await global_unmute(bot, uid, source='ministerial_pardon')
    chat=await active_group_id()
    if chat and await st.is_open():
        await bot.send_message(chat,f'⚖️ GRÂCE MINISTÉRIELLE\n\n{len(users)} restriction(s) globales levée(s).\n\nLa prochaine faute comptera double.')
    return len(users)
