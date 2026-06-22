from datetime import datetime, timedelta
from sqlalchemy import select, func
from aiogram import Bot
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import SessionLog, TrackedMessage, TrustedAction, User, ErrorLog
from app.services import settings as st
from app.services.state import ensure_status_message, log_error

OPEN_PERMS={'can_send_messages':True,'can_send_audios':True,'can_send_documents':True,'can_send_photos':True,'can_send_videos':True,'can_send_video_notes':False,'can_send_voice_notes':True,'can_send_polls':False,'can_send_other_messages':False,'can_add_web_page_previews':False}
CLOSED_PERMS={'can_send_messages':False}
async def set_group_open(bot:Bot, open_:bool, kind='auto'):
    s=get_settings()
    try: await bot.set_chat_permissions(s.main_group_id, permissions=OPEN_PERMS if open_ else CLOSED_PERMS)
    except Exception as e: await log_error('permissions',e)
    if open_:
        async with SessionLocal() as db:
            sess=SessionLog(chat_id=s.main_group_id,kind=kind,status='open'); db.add(sess); await db.flush()
            await st.set_value('active_session_id',str(sess.id)); await db.commit()
        await st.set_open(True)
    else:
        await st.set_open(False)
        await cleanup_session(bot)
        await close_active_session()
        await send_report(bot, kind)
    await ensure_status_message(bot,s.main_group_id)
async def close_active_session():
    async with SessionLocal() as db:
        sid=int(await st.get_value('active_session_id','0') or '0')
        if sid:
            sess=await db.get(SessionLog,sid)
            if sess: sess.status='closed'; sess.closed_at=datetime.utcnow()
        await st.set_value('active_session_id','0')
        await db.commit()
async def cleanup_session(bot:Bot):
    s=get_settings(); sid=int(await st.get_value('active_session_id','0') or '0')
    deleted=0
    async with SessionLocal() as db:
        q=select(TrackedMessage).where(TrackedMessage.chat_id==s.main_group_id,TrackedMessage.deleted==False)
        if sid: q=q.where(TrackedMessage.session_id==sid)
        res=await db.execute(q)
        for tm in res.scalars().all():
            try:
                await bot.delete_message(tm.chat_id,tm.message_id); tm.deleted=True; deleted+=1
            except Exception: pass
        if sid:
            sess=await db.get(SessionLog,sid)
            if sess: sess.messages_deleted+=deleted
        await db.commit()
    # double vérification sur messages suivis
    if sid:
        async with SessionLocal() as db:
            remain=(await db.execute(select(func.count(TrackedMessage.id)).where(TrackedMessage.session_id==sid,TrackedMessage.deleted==False))).scalar() or 0
            if remain: await notify_admins(bot,f'🚨 ERREUR NETTOYAGE\n\nMessages encore suivis non supprimés : {remain}\n\nUtilise 🧹 Nettoyage pour relancer.')
async def notify_admins(bot:Bot,text:str, reply_markup=None):
    for aid in get_settings().admin_ids:
        try: await bot.send_message(aid,text,reply_markup=reply_markup)
        except Exception: pass
async def send_report(bot:Bot, kind='auto'):
    sid=int(await st.get_value('active_session_id','0') or '0')
    async with SessionLocal() as db:
        # last session fallback
        sess=None
        res=await db.execute(select(SessionLog).order_by(SessionLog.id.desc()).limit(1)); sess=res.scalar_one_or_none()
        actions=await db.execute(select(TrustedAction.trusted_username,TrustedAction.command,func.count(TrustedAction.id)).group_by(TrustedAction.trusted_username,TrustedAction.command))
        action_lines=[]
        for name,cmd,c in actions.all(): action_lines.append(f'@{name or "trusted"} {cmd}: {c}')
        inactive=await db.execute(select(func.count(User.id)).where(User.media_count==0)); inactive_count=inactive.scalar() or 0
        errors=await db.execute(select(func.count(ErrorLog.id)).where(ErrorLog.created_at>=datetime.utcnow()-timedelta(hours=24))); err=errors.scalar() or 0
    text=f'📊 RAPPORT DE SESSION\n\nType : {kind}\nMessages vus : {sess.messages_seen if sess else 0}\nMédias vus : {sess.media_seen if sess else 0}\nMessages supprimés : {sess.messages_deleted if sess else 0}\n\nInactifs jamais média : {inactive_count}\n\nActions trusted :\n' + ('\n'.join(action_lines[-20:]) or 'Aucune') + f'\n\nErreurs 24h : {err}'
    await notify_admins(bot,text)
async def security_close_if_manual(bot:Bot):
    if not await st.is_open() or await st.auto_enabled(): return
    await notify_admins(bot,'⚠️ FERMETURE DE SÉCURITÉ\n\nLe groupe est ouvert manuellement depuis 2h. Sans réponse, fermeture exécutée.')
    await set_group_open(bot,False,'security')
