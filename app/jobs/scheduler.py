from __future__ import annotations
from datetime import timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from app.config import get_settings
from app.services.state import get_group_state, vote_count
from app.services.messages import ensure_status_message
from app.services.session_manager import open_group, close_group, notify_admins
from app.utils.time import in_slot, next_open_close, now_tz

settings=get_settings()
scheduler = AsyncIOScheduler(timezone=settings.timezone)

async def tick(bot:Bot):
    chat_id=settings.main_group_id
    if not chat_id: return
    st=await get_group_state(chat_id)
    # Always ensure one status message is updated.
    await ensure_status_message(bot, chat_id)
    inside=in_slot(st.time_slot, settings.timezone)
    if not st.auto_enabled:
        return
    votes=await vote_count(chat_id)
    if inside and not st.is_open and votes >= st.vote_goal:
        await open_group(bot, chat_id, kind='auto')
    if (not inside) and st.is_open and not st.manual_open:
        await close_group(bot, chat_id, reason='auto')
    if st.is_open and st.manual_open and st.auto_enabled:
        # Auto ON dominates official closure.
        _,end=next_open_close(st.time_slot, settings.timezone)
        if now_tz(settings.timezone) >= end:
            await close_group(bot, chat_id, reason='auto_after_manual')

async def safety_tick(bot:Bot):
    # Placeholder: manual Auto OFF 2h confirmation belongs in advanced job table.
    pass

def start_scheduler(bot:Bot):
    scheduler.add_job(tick, 'interval', minutes=1, args=[bot], id='main_tick', replace_existing=True)
    scheduler.add_job(lambda: None, 'interval', minutes=30, id='heartbeat', replace_existing=True)
    scheduler.start()
