import asyncio
import logging
import time
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramServerError
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Vote, TrackedMessage, ErrorLog
from app.services import settings as st
from app.utils.time import day_key, countdown_text, in_slot, slot_times
from app.keyboards.common import vote_kb

_STATUS_VERIFY_EVERY_SECONDS = 300.0
_STATUS_LAST_VERIFY: dict[int, float] = {}

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
    s=get_settings(); today=day_key(s.timezone)
    async with SessionLocal() as db:
        stmt=(
            pg_insert(Vote)
            .values(chat_id=chat_id,user_id=user_id,day_key=today)
            .on_conflict_do_nothing(constraint='uq_vote_day')
            .returning(Vote.id)
        )
        inserted=(await db.execute(stmt)).scalar_one_or_none()
        await db.commit()
        return inserted is not None

async def status_text(chat_id:int):
    from app.services.multigroup import active_group_id, is_main_group
    active = await active_group_id()
    if not await is_main_group(chat_id):
        return '⚫ Chat non principal.'
    if not active:
        return '🔴 GROUPE FERMÉ\n\nAucune ouverture n’est prévue ce soir.\n\nMerci de revenir demain.'
    auto_=await st.auto_enabled()
    open_=await st.is_open()
    # Auto OFF + groupe fermé = maintenance globale : A et B affichent le même
    # message et restent utilisables uniquement pour les annonces du bot.
    if not auto_ and not open_:
        return '🔴 GROUPE FERMÉ\n\nAucune ouverture n’est prévue ce soir.\n\nMerci de revenir demain.'
    if chat_id != active:
        return '🔒 GROUPE INACTIF\n\nLa session est gérée dans l’autre groupe principal.'
    goal=await st.vote_goal(); votes=await vote_count(chat_id); slot=await st.time_slot(); s=get_settings()
    opening=slot.split('-')[0]; closing=slot.split('-')[1]
    if not auto_:
        if open_:
            return '🟢 GROUPE OUVERT\n\nVous pouvez envoyer vos médias <3\n\nMode manuel : fermeture de sécurité active.'
        return '🔴 GROUPE FERMÉ\n\nAucune ouverture n’est prévue ce soir.\n\nMerci de revenir demain.'
    if await st.is_open():
        return f'🟢 GROUPE OUVERT\n\nObjectif atteint : {votes} / {goal} ✅\n\nVous pouvez envoyer vos médias <3\n\nFermeture prévue à {closing}.'
    missing=max(goal-votes,0)
    achieved=votes>=goal
    if achieved:
        if in_slot(slot,s.timezone):
            return f'🟢 OBJECTIF ATTEINT\n\nLe groupe est maintenant ouvert.\n\nFermeture prévue à {closing}.\n\nVous pouvez envoyer vos médias <3'
        remaining=countdown_text(slot,s.timezone,achieved=True)
        if remaining == 'maintenant':
            return '🟢 OBJECTIF ATTEINT\n\nOuverture en cours...'
        return f'🟡 OBJECTIF ATTEINT\n\nLe groupe ouvrira automatiquement à {opening}.\n\nOuverture dans : {remaining}\n\nObjectif :\n{votes} / {goal} votes ✅\n\nPréparez vos médias.'
    remaining=countdown_text(slot,s.timezone,achieved=False)
    return f'🔴 GROUPE FERMÉ\n\nOuverture prévue à {opening}.\nTemps restant : {remaining}\n\nObjectif :\n{votes} / {goal} votes\n\nIl manque encore {missing} votes.'

async def track(chat_id:int,message_id:int,user_id:int|None,kind='message',is_media=False):
    sid=int(await st.get_value('active_session_id','0') or '0')
    async with SessionLocal() as db:
        stmt=(
            pg_insert(TrackedMessage)
            .values(chat_id=chat_id,message_id=message_id,user_id=user_id,session_id=sid,kind=kind,is_media=is_media)
            .on_conflict_do_nothing(constraint='uq_tracked_message')
            .returning(TrackedMessage.id)
        )
        inserted=(await db.execute(stmt)).scalar_one_or_none()
        if inserted is not None and sid and kind!='status':
            from app.db.models import SessionLog
            values={'messages_seen': SessionLog.messages_seen + 1}
            if is_media:
                values['media_seen']=SessionLog.media_seen + 1
            await db.execute(update(SessionLog).where(SessionLog.id==sid).values(**values))
        await db.commit()

async def ensure_status_message(bot:Bot, chat_id:int, recreate_on_change:bool=False):
    """Maintient le message principal sans créer de doublon en cas de panne API.

    Une erreur réseau pendant une édition ne signifie pas que le message a
    disparu. Dans ce cas on laisse le scheduler réessayer plus tard au lieu de
    publier immédiatement un nouveau message d'état.
    """
    text=await status_text(chat_id)
    mid_key=f'status_message_id:{chat_id}'
    text_key=f'status_last_text:{chat_id}'
    mid=await st.get_value(mid_key,'')
    last_text=await st.get_value(text_key,'')
    from app.services.multigroup import active_group_id
    active=await active_group_id()
    open_=await st.is_open()
    auto_=await st.auto_enabled()
    if open_:
        kb=None
    elif not active or not auto_:
        # Même fermé / sans ouverture, le groupe reste un point d'acquisition :
        # le bouton ouvre le bot en privé et attribue un lien unique à ce groupe.
        from app.services.invites import invite_kb
        kb=await invite_kb(chat_id, button_text='🎁 Partager le groupe')
    elif chat_id == active:
        kb=vote_kb()
    else:
        kb=None

    if mid and recreate_on_change and last_text and text != last_text:
        try:
            await bot.delete_message(chat_id,int(mid))
            async with SessionLocal() as db:
                res=await db.execute(select(TrackedMessage).where(TrackedMessage.chat_id==chat_id,TrackedMessage.message_id==int(mid)))
                tm=res.scalar_one_or_none()
                if tm: tm.deleted=True
                await db.commit()
            mid=''
        except TelegramBadRequest as e:
            low=str(e).lower()
            if 'message to delete not found' in low or 'message identifier is not specified' in low:
                mid=''
            else:
                await log_error('delete_old_status',e)
                raise
        except (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError) as e:
            await log_error('delete_old_status_temporary',e)
            raise
        except Exception as e:
            await log_error('delete_old_status',e)
            raise

    if mid:
        # Si le texte n'a pas changé, évite un edit Telegram inutile à chaque tick.
        # On force tout de même une vérification périodique pour recréer le message
        # s'il a été supprimé manuellement hors du bot.
        now_mono=time.monotonic()
        last_verify=_STATUS_LAST_VERIFY.get(chat_id,0.0)
        if last_text == text and now_mono-last_verify < _STATUS_VERIFY_EVERY_SECONDS:
            return int(mid)
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=int(mid), reply_markup=kb)
            _STATUS_LAST_VERIFY[chat_id]=now_mono
            from datetime import datetime
            await st.set_value('last_status_update_at', datetime.utcnow().isoformat(timespec='seconds'))
            await st.set_value(text_key, text)
            return int(mid)
        except TelegramBadRequest as e:
            low=str(e).lower()
            if 'message is not modified' in low:
                _STATUS_LAST_VERIFY[chat_id]=time.monotonic()
                return int(mid)
            if 'message to edit not found' in low:
                mid=''
            else:
                await log_error('edit_status',e)
                raise
        except (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError) as e:
            await log_error('edit_status_temporary',e)
            raise
        except Exception as e:
            await log_error('edit_status',e)
            raise

    m=await bot.send_message(chat_id,text,reply_markup=kb)
    await st.set_value(mid_key,str(m.message_id))
    await st.set_value(text_key, text)
    from datetime import datetime
    await st.set_value('last_status_update_at', datetime.utcnow().isoformat(timespec='seconds'))
    await track(chat_id,m.message_id,None,'status',False)
    _STATUS_LAST_VERIFY[chat_id]=time.monotonic()
    await cleanup_known_status_duplicates(bot, chat_id)
    return m.message_id

async def cleanup_known_status_duplicates(bot:Bot, chat_id:int):
    keep=int(await st.get_value(f'status_message_id:{chat_id}','0') or '0')
    async with SessionLocal() as db:
        rows=list((await db.execute(
            select(TrackedMessage.id,TrackedMessage.message_id).where(
                TrackedMessage.chat_id==chat_id,
                TrackedMessage.kind=='status',
                TrackedMessage.deleted.is_(False),
                TrackedMessage.message_id!=keep,
            )
        )).all())
    if not rows:
        return
    semaphore=asyncio.Semaphore(4)
    async def remove(row):
        row_id,message_id=row
        async with semaphore:
            try:
                await bot.delete_message(chat_id,message_id)
                return row_id
            except TelegramBadRequest as e:
                low=str(e).lower()
                if 'message to delete not found' in low or 'message identifier is not specified' in low:
                    return row_id
                return None
            except Exception:
                return None
    removed=[rid for rid in await asyncio.gather(*(remove(row) for row in rows)) if rid is not None]
    if removed:
        async with SessionLocal() as db:
            await db.execute(update(TrackedMessage).where(TrackedMessage.id.in_(removed)).values(deleted=True))
            await db.commit()
