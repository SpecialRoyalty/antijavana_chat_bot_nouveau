from aiogram import Bot
from sqlalchemy import select
from app.config import get_settings
from app.db.models import TrackedMessage
from app.db.session import SessionLocal

settings = get_settings()


async def cleanup_session(bot: Bot) -> dict:
    deleted = 0
    failed = []
    async with SessionLocal() as db:
        res = await db.execute(select(TrackedMessage).order_by(TrackedMessage.id.desc()).limit(5000))
        messages = list(res.scalars())
        for m in messages:
            try:
                await bot.delete_message(m.chat_id, m.message_id)
                deleted += 1
            except Exception:
                failed.append({'chat_id': m.chat_id, 'message_id': m.message_id})
    if failed:
        await notify_admins(bot, f"🚨 ERREUR NETTOYAGE\n\nMessages non supprimés : {len(failed)}")
    return {'deleted': deleted, 'failed': len(failed)}


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in settings.admin_id_set:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass
