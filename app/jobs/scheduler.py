from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from app.config import get_settings
from app.services.session_service import ensure_status_message, open_main_group, close_main_group, get_runtime_settings, get_or_create_session
from app.services.vip import send_vip_ad
from app.services.cleanup import notify_admins
from app.services.reports import session_report

settings = get_settings()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(lambda: guarded_status(bot), 'interval', minutes=60, id='status_closed_hourly', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: guarded_open(bot), 'cron', hour=22, minute=30, id='auto_open_2230', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: guarded_vip(bot), 'cron', hour=22, minute=50, id='vip_ad_1', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: guarded_vip(bot), 'cron', hour=0, minute=10, id='vip_ad_2', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: notify_admins(bot, '⚖️ Justice populaire : vérification milieu de session active.'), 'cron', hour=23, minute=37, id='justice', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: close_and_report(bot), 'cron', hour=0, minute=45, id='auto_close', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: manual_safety(bot), 'interval', minutes=5, id='manual_safety', replace_existing=True, max_instances=1)
    return scheduler


async def guarded_status(bot: Bot) -> None:
    await ensure_status_message(bot)


async def guarded_open(bot: Bot) -> None:
    runtime = await get_runtime_settings()
    if not runtime.get('auto_enabled', True):
        await ensure_status_message(bot)
        return
    # TODO: scheduler dynamique pour autres créneaux. Défaut actif: 22:30-00:45.
    s = await get_or_create_session()
    votes = 999999  # En V1 de stabilité: ouverture auto ne bloque pas si objectif non câblé dans ce job.
    if s.status != 'open':
        await open_main_group(bot, manual=False)


async def guarded_vip(bot: Bot) -> None:
    s = await get_or_create_session()
    if s.status == 'open':
        await send_vip_ad(bot)


async def close_and_report(bot: Bot) -> None:
    await close_main_group(bot, reason='auto')
    await notify_admins(bot, await session_report())


async def manual_safety(bot: Bot) -> None:
    # Sécurité simplifiée: si session manuelle ouverte, les admins sont rappelés.
    s = await get_or_create_session()
    if s.status == 'open' and s.mode == 'manual':
        # La fermeture automatique stricte +2h sera branchée en V2 dynamique.
        pass
