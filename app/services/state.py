from __future__ import annotations
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import GroupState, Vote, User
from app.utils.time import day_key, next_open_close, human_delta

settings=get_settings()

async def get_group_state(chat_id:int|None=None) -> GroupState:
    chat_id = chat_id or settings.main_group_id
    if chat_id is None: raise RuntimeError('MAIN_GROUP_ID missing')
    async with SessionLocal() as db:
        st = await db.get(GroupState, chat_id)
        if not st:
            st=GroupState(chat_id=chat_id, auto_enabled=settings.auto_schedule_enabled, vote_goal=settings.default_vote_goal, time_slot=settings.default_time_slot)
            db.add(st); await db.commit(); await db.refresh(st)
        return st

async def save_status_message(chat_id:int, message_id:int, text:str):
    async with SessionLocal() as db:
        st=await db.get(GroupState, chat_id)
        if not st:
            st=GroupState(chat_id=chat_id)
            db.add(st)
        st.status_message_id=message_id; st.last_text=text; st.updated_at=datetime.utcnow()
        await db.commit()

async def mark_open(chat_id:int, open_:bool, manual:bool=False, session_id:int|None=None):
    async with SessionLocal() as db:
        st=await db.get(GroupState, chat_id) or GroupState(chat_id=chat_id)
        st.is_open=open_; st.manual_open=manual if open_ else False
        if session_id is not None: st.current_session_id=session_id
        if not open_: st.current_session_id=None
        st.updated_at=datetime.utcnow(); db.add(st); await db.commit()

async def register_user(tg_user):
    async with SessionLocal() as db:
        u=await db.get(User, tg_user.id)
        if not u:
            u=User(id=tg_user.id)
            db.add(u)
        u.username=getattr(tg_user,'username',None)
        u.first_name=getattr(tg_user,'first_name',None)
        u.last_name=getattr(tg_user,'last_name',None)
        u.is_admin=tg_user.id in settings.admin_ids
        u.is_trusted=tg_user.id in settings.all_trusted
        await db.commit()
        return u

async def add_vote(chat_id:int, user_id:int) -> bool:
    async with SessionLocal() as db:
        stmt=insert(Vote).values(chat_id=chat_id,user_id=user_id,day_key=day_key(settings.timezone)).on_conflict_do_nothing(index_elements=['chat_id','user_id','day_key'])
        res=await db.execute(stmt); await db.commit()
        return bool(res.rowcount)

async def vote_count(chat_id:int) -> int:
    async with SessionLocal() as db:
        res=await db.execute(select(func.count(Vote.id)).where(Vote.chat_id==chat_id, Vote.day_key==day_key(settings.timezone)))
        return int(res.scalar() or 0)

async def status_text(chat_id:int) -> str:
    st=await get_group_state(chat_id)
    votes=await vote_count(chat_id)
    if not st.auto_enabled and not st.is_open:
        return '🔴 MAINTENANCE\n\nLe système est en maintenance ce soir.\n\nAucune ouverture prévue.'
    if st.is_open:
        return '🟢 GROUPE OUVERT\n\nVous pouvez envoyer vos médias <3'
    start,_=next_open_close(st.time_slot, settings.timezone)
    missing=max(0, st.vote_goal-votes)
    return f'🔴 GROUPE FERMÉ\n\nOuverture prévue à {start.strftime("%Hh%M")}.\nTemps restant : {human_delta(start, settings.timezone)}\n\nObjectif :\n{votes} / {st.vote_goal} votes\n\nIl manque encore {missing} votes.'
