import asyncio
import structlog
from aiogram import Bot, Dispatcher
from app.config import get_settings
from app.db.session import init_db
from app.bot import admin, trusted, group
from app.jobs.scheduler import setup_scheduler

log = structlog.get_logger()


async def main() -> None:
    settings = get_settings()
    await init_db()
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(trusted.router)
    dp.include_router(group.router)
    scheduler = setup_scheduler(bot)
    scheduler.start()
    log.info('bot_started')
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
