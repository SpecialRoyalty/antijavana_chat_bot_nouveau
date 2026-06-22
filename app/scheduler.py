from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from app.config import get_settings
from app.services import settings as st
from app.services.state import ensure_status_message, vote_count
from app.services.session_ops import set_group_open, security_close_if_manual
from app.services.vip import send_vip_ad, expire_pass_soiree
from app.services.crowdfunding import send_crowd_ad
from app.services.invites import validate_invites, top_text
from app.utils.time import in_slot, mid_time, now_tz

async def tick(bot:Bot):
    s=get_settings(); chat=s.main_group_id
    await ensure_status_message(bot,chat)
    if not await st.auto_enabled():
        return
    ins=in_slot(await st.time_slot(),s.timezone)
    open_=await st.is_open()
    goal=await st.vote_goal(); votes=await vote_count(chat)
    if ins and not open_ and votes>=goal:
        await set_group_open(bot,True,'auto')
    if not ins and open_:
        await set_group_open(bot,False,'auto')
async def justice_tick(bot:Bot):
    if not await st.is_open(): return
    s=get_settings(); mt=mid_time(await st.time_slot(),s.timezone); n=now_tz(s.timezone)
    done=await st.get_value('justice_done_'+n.strftime('%Y%m%d'),'false')
    if done=='true': return
    if abs((n-mt).total_seconds())<70:
        await st.set_value('justice_done_'+n.strftime('%Y%m%d'),'true')
        m=await bot.send_message(s.main_group_id,'⚖️ JUSTICE POPULAIRE\n\nLe groupe est bloqué pendant 5 minutes.\n\nDes membres profitent du groupe sans participer.\nLes plus inactifs sont supprimés.')
        # suppression réelle d'inactifs limitée/sécurisée : à gérer avec membres connus seulement
        await bot.send_message(s.main_group_id,'🟢 JUSTICE TERMINÉE\n\nLe groupe est de nouveau ouvert.')
async def rules_tick(bot:Bot):
    if not await st.is_open(): return
    s=get_settings(); old=await st.get_value('rules_message_id','')
    try:
        if old: await bot.delete_message(s.main_group_id,int(old))
    except Exception: pass
    m=await bot.send_message(s.main_group_id, await st.get_value('rules_text','Règles'))
    await st.set_value('rules_message_id',str(m.message_id))
async def top_tick(bot:Bot):
    if not await st.is_open(): return
    s=get_settings(); await bot.send_message(s.main_group_id, await top_text())
def start_scheduler(bot:Bot):
    sch=AsyncIOScheduler(timezone=get_settings().timezone)
    sch.add_job(lambda: tick(bot),'interval',minutes=1, id='tick')
    sch.add_job(lambda: justice_tick(bot),'interval',minutes=1, id='justice')
    sch.add_job(lambda: validate_invites(bot),'interval',minutes=1, id='invite_validate')
    sch.add_job(lambda: rules_tick(bot),'interval',minutes=30, id='rules')
    sch.add_job(lambda: send_vip_ad(bot),'cron',hour='22,0',minute='50,10', id='vip_ads')
    sch.add_job(lambda: send_crowd_ad(bot),'cron',hour='22,0',minute='55,15', id='crowd_ads')
    sch.add_job(lambda: top_tick(bot),'cron',hour='0',minute='40', id='top')
    sch.add_job(lambda: security_close_if_manual(bot),'interval',hours=2, id='security_close')
    sch.add_job(lambda: expire_pass_soiree(bot),'cron',hour='5',minute='45', id='expire_pass')
    sch.start(); return sch
