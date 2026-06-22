import logging
from sqlalchemy import select, func
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Vote, TrackedMessage, SessionLog, ErrorLog
from app.services import settings as st
from app.utils.time import day_key, next_open_text
from app.keyboards.common import vote_kb

async def log_error(area,msg):
    logging.exception('%s: %s',area,msg) if isinstance(msg,Exception) else logging.error('%s: %s',area,msg)
    try:
        async with SessionLocal() as db:
            db.add(ErrorLog(area=area,message=str(msg)[:2000])); await db.commit()
    except Exception: pass

async def vote_count(chat_id:int):
    s=get_settings()
    async with SessionLocal() as db:
        res=await db.execute(select(func.count(Vote.id)).where(Vote.chat_id==chat_id, Vote.day_key==day_key(s.timezone)))
        return int(res.scalar() or 0)
async def add_vote(chat_id:int,user_id:int):
    s=get_settings()
    async with SessionLocal() as db:
        exists=await db.execute(select(Vote).where(Vote.chat_id==chat_id,Vote.user_id==user_id,Vote.day_key==day_key(s.timezone)))
        if exists.scalar_one_or_none(): return False
        db.add(Vote(chat_id=chat_id,user_id=user_id,day_key=day_key(s.timezone))); await db.commit(); return True
async def status_text(chat_id:int):
    goal=await st.vote_goal(); votes=await vote_count(chat_id); slot=await st.time_slot()
    if not await st.auto_enabled():
        return '🔴 MAINTENANCE\n\nLe système est en maintenance ce soir.\n\nAucune ouverture prévue.'
    if await st.is_open():
        return '🟢 GROUPE OUVERT\n\nVous pouvez envoyer vos médias <3'
    missing=max(goal-votes,0)
    opening=slot.split('-')[0]
    return f'🔴 GROUPE FERMÉ\n\nOuverture prévue à {opening}.\nTemps restant : {next_open_text(slot,get_settings().timezone)}\n\nObjectif :\n{votes} / {goal} votes\n\nIl manque encore {missing} votes.'
async def track(chat_id:int,message_id:int,user_id:int|None,kind='message',is_media=False):
    async with SessionLocal() as db:
        sid=int(await st.get_value('active_session_id','0') or '0')
        if not await db.execute(select(TrackedMessage).where(TrackedMessage.chat_id==chat_id,TrackedMessage.message_id==message_id)):
            db.add(TrackedMessage(chat_id=chat_id,message_id=message_id,user_id=user_id,session_id=sid,kind=kind,is_media=is_media))
        if sid:
            sess=await db.get(SessionLog,sid)
            if sess:
                sess.messages_seen += 1
                if is_media: sess.media_seen += 1
        await db.commit()
async def ensure_status_message(bot:Bot, chat_id:int):
    text=await status_text(chat_id); mid=await st.get_value('status_message_id','')
    kb=None if await st.is_open() or not await st.auto_enabled() else vote_kb()
    if mid:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=int(mid), reply_markup=kb)
            return int(mid)
        except TelegramBadRequest as e:
            if 'message is not modified' in str(e).lower(): return int(mid)
            if 'message to edit not found' not in str(e).lower(): await log_error('edit_status',e)
        except Exception as e: await log_error('edit_status',e)
    m=await bot.send_message(chat_id,text,reply_markup=kb)
    await st.set_value('status_message_id',str(m.message_id)); await track(chat_id,m.message_id,None,'status',False)
    return m.message_id
async def cleanup_known_status_duplicates(bot:Bot, chat_id:int):
    # Telegram ne donne pas l'historique. On supprime seulement les anciens messages statut suivis.
    keep=int(await st.get_value('status_message_id','0') or '0')
    async with SessionLocal() as db:
        res=await db.execute(select(TrackedMessage).where(TrackedMessage.chat_id==chat_id,TrackedMessage.kind=='status',TrackedMessage.deleted==False))
        for tm in res.scalars().all():
            if tm.message_id!=keep:
                try: await bot.delete_message(chat_id,tm.message_id); tm.deleted=True
                except Exception: pass
        await db.commit()
