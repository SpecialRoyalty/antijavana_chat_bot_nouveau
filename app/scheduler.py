from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from aiogram import Bot

from app.config import get_settings
from app.services import settings as st
from app.services.state import ensure_status_message, vote_count
from app.services.session_ops import set_group_open, security_close_if_manual
from app.services.vip import send_vip_ad, expire_pass_soiree, send_due_pass_soiree_links
from app.services.crowdfunding import send_crowd_ad
from app.services.ads import send_random_ad
from app.services.invites import validate_invites, top_text, send_invite_ad
from app.services.freepass import send_due_free_pass_links
from app.services.multigroup import active_group_id, health_monitor_tick, selected_group_role, main_group_ids
from app.services.justice import justice_already_done, process_pending_justice_removals
from app.utils.time import in_slot, mid_time, now_tz, slot_times


async def tick(bot:Bot):
    chat=await active_group_id()
    auto_=await st.auto_enabled()
    open_=await st.is_open()
    if not chat or (not auto_ and not open_):
        # Aucune ouverture / maintenance : A et B restent fermés mais gardent
        # un message public avec le bouton « Partager le groupe ».
        for gid in await main_group_ids(include_unavailable=False):
            try:
                await ensure_status_message(bot,gid,recreate_on_change=True)
            except Exception:
                pass
        return
    await ensure_status_message(bot,chat,recreate_on_change=True)
    if not auto_:
        return
    s=get_settings()
    ins=in_slot(await st.time_slot(),s.timezone)
    open_=await st.is_open()
    goal=await st.vote_goal(); votes=await vote_count(chat)
    if ins and not open_ and votes>=goal:
        await set_group_open(bot,True,'auto')
    if not ins and open_:
        await set_group_open(bot,False,'auto')


async def run_justice_now(bot:Bot):
    if not await st.is_open():
        return
    from app.services.justice import execute_justice
    await execute_justice(bot, manual=False)


async def justice_tick(bot:Bot):
    if not await st.is_open() or not await active_group_id():
        return
    if await justice_already_done():
        return
    s=get_settings(); mt=mid_time(await st.time_slot(),s.timezone); n=now_tz(s.timezone)
    if abs((n-mt).total_seconds())<70:
        # execute_justice pose lui-même le flag seulement au vrai démarrage.
        await run_justice_now(bot)


async def rules_tick(bot:Bot, force:bool=False, target:str='active'):
    if not force and not await st.is_open():
        return []
    from app.services.multigroup import resolve_main_targets
    targets=await resolve_main_targets(target, include_unavailable=False)
    if not targets:
        return []
    text=await st.get_value('rules_text','Règles')
    sent=[]
    for chat in targets:
        old_key=f'rules_message_id:{chat}'
        old=await st.get_value(old_key,'')
        try:
            if old:
                await bot.delete_message(chat,int(old))
        except Exception:
            pass
        try:
            m=await bot.send_message(chat,text)
            await st.set_value(old_key,str(m.message_id))
            sent.append((chat,m.message_id))
        except Exception:
            continue
    if sent:
        await st.set_value('last_rules_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
        await st.set_value('rules_message_id',str(sent[-1][1]))
        await st.set_value('rules_chat_id',str(sent[-1][0]))
        await st.set_value('last_rules_chat_ids', ','.join(str(x[0]) for x in sent))
    return sent


async def _publish_invite_top(bot: Bot, marker_key: str):
    sid=await st.get_value('active_session_id','0')
    if sid != '0' and await st.get_value(marker_key,'') == sid:
        return None
    txt=await top_text()
    if 'Aucune statistique' in txt:
        return None
    chat=await active_group_id()
    if not chat:
        return None
    m=await bot.send_message(chat,txt)
    await st.set_value('last_top_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
    if sid != '0':
        await st.set_value(marker_key,sid)
    return m.message_id


async def top_after_justice_tick(bot:Bot, force:bool=False):
    """Premier TOP 10 : juste après la justice populaire."""
    if not force and (not await st.is_open() or not await active_group_id()):
        return None
    if not force:
        if not await justice_already_done():
            return None
        if await st.get_value('justice_running','false') == 'true':
            return None
    return await _publish_invite_top(bot, 'invite_top1_last_session')


async def top_late_session_tick(bot: Bot, force: bool=False):
    """Deuxième TOP 10 : à environ 75 % de la fenêtre d'ouverture.

    Le marqueur par session empêche un doublon après redémarrage du scheduler.
    """
    if not force and (not await st.is_open() or not await active_group_id()):
        return None
    if not force:
        slot=await st.time_slot()
        tz=get_settings().timezone
        start,end=slot_times(slot,tz)
        n=now_tz(tz)
        # slot_times peut retourner la prochaine fenêtre lorsqu'on est après minuit ;
        # on ramène à la fenêtre courante si nécessaire.
        if n < start and (start-n) > timedelta(hours=12):
            start-=timedelta(days=1); end-=timedelta(days=1)
        threshold=start+(end-start)*0.75
        if n < threshold:
            return None
    return await _publish_invite_top(bot, 'invite_top2_last_session')


async def infrastructure_tick(bot: Bot):
    await health_monitor_tick(bot)
    await process_pending_justice_removals(bot)


def start_scheduler(bot:Bot):
    sch=AsyncIOScheduler(
        timezone=get_settings().timezone,
        job_defaults={'coalesce':True,'max_instances':1,'misfire_grace_time':120},
    )
    now=datetime.now(sch.timezone)
    # Jobs décalés pour éviter un burst API Telegram au démarrage.
    sch.add_job(tick,'interval',minutes=1,args=[bot],id='tick',next_run_time=now+timedelta(seconds=5))
    sch.add_job(justice_tick,'interval',minutes=1,args=[bot],id='justice',next_run_time=now+timedelta(seconds=20))
    sch.add_job(validate_invites,'interval',minutes=1,args=[bot],id='invite_validate',next_run_time=now+timedelta(seconds=35))
    sch.add_job(top_after_justice_tick,'interval',minutes=1,args=[bot],id='top_after_justice',next_run_time=now+timedelta(seconds=50))
    sch.add_job(top_late_session_tick,'interval',minutes=1,args=[bot],id='top_late_session',next_run_time=now+timedelta(seconds=57))
    sch.add_job(infrastructure_tick,'interval',minutes=2,args=[bot],id='infra_health',next_run_time=now+timedelta(seconds=65))
    sch.add_job(security_close_if_manual,'interval',minutes=5,args=[bot],id='security_close',next_run_time=now+timedelta(seconds=80))

    sch.add_job(rules_tick,'interval',minutes=30,args=[bot],id='rules',next_run_time=now+timedelta(seconds=95))
    sch.add_job(send_vip_ad,'cron',hour='22,0',minute='50,10',second=5,args=[bot],id='vip_ads')
    sch.add_job(send_crowd_ad,'cron',hour='22,0',minute='55,15',second=15,args=[bot],id='crowd_ads')
    sch.add_job(send_random_ad,'cron',hour='22,0',minute='45,5',second=25,args=[bot],id='random_ads')
    sch.add_job(send_invite_ad,'cron',hour='23',minute='25',second=45,args=[bot],id='invite_ad')
    sch.add_job(send_due_pass_soiree_links,'cron',hour='23',minute='0',second=5,args=[bot],id='pass_soiree_release')
    sch.add_job(send_due_free_pass_links,'cron',hour='23',minute='0',second=25,args=[bot],id='free_pass_release')
    sch.add_job(expire_pass_soiree,'cron',hour='5',minute='0',second=10,args=[bot],id='expire_pass')
    sch.start()
    return sch
