from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from app.config import get_settings
from app.services.session_service import ensure_status_message, open_main_group, close_main_group
from app.services.vip import send_vip_ad
from app.services.cleanup import notify_admins
from app.services.reports import session_report

settings = get_settings()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # Créneau par défaut 22h30 -> 00h45. Les autres créneaux seront lus depuis settings DB.
    scheduler.add_job(lambda: ensure_status_message(bot), 'interval', minutes=60, id='status_closed', replace_existing=True)
    scheduler.add_job(lambda: open_main_group(bot, manual=False), 'cron', hour=22, minute=30, id='auto_open', replace_existing=True)
    scheduler.add_job(lambda: send_vip_ad(bot), 'cron', hour=22, minute=50, id='vip_ad_1', replace_existing=True)
    scheduler.add_job(lambda: send_vip_ad(bot), 'cron', hour=0, minute=10, id='vip_ad_2', replace_existing=True)
    scheduler.add_job(lambda: notify_admins(bot, '⚖️ Justice populaire : job V1 à implémenter selon inactivité sessions.'), 'cron', hour=23, minute=37, id='justice', replace_existing=True)
    scheduler.add_job(lambda: close_and_report(bot), 'cron', hour=0, minute=45, id='auto_close', replace_existing=True)
    return scheduler


async def close_and_report(bot: Bot) -> None:
    await close_main_group(bot, reason='auto')
    await notify_admins(bot, await session_report())
