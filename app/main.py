from __future__ import annotations
import asyncio, logging
from aiogram import Bot, Dispatcher
from app.config import get_settings
from app.db.session import init_db
from app.handlers.admin import router as admin_router
from app.handlers.group import router as group_router
from app.jobs.scheduler import start_scheduler
from app.services.messages import ensure_status_message

logging.basicConfig(level=logging.INFO)
settings=get_settings()

async def main():
    await init_db()
    bot=Bot(settings.bot_token)
    dp=Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(group_router)
    start_scheduler(bot)
    if settings.main_group_id:
        try: await ensure_status_message(bot, settings.main_group_id)
        except Exception as e: logging.exception('status init failed: %s', e)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == '__main__':
    asyncio.run(main())
