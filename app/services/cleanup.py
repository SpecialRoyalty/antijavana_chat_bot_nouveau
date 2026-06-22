from __future__ import annotations
from aiogram import Bot
from sqlalchemy import select, delete, func
from app.config import get_settings
from app.db.models import TrackedMessage
from app.db.session import SessionLocal

settings = get_settings()


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in settings.admin_id_set:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def cleanup_session(bot: Bot) -> tuple[int, int]:
    deleted = 0
    failed = 0
    async with SessionLocal() as db:
        res = await db.execute(select(TrackedMessage).where(TrackedMessage.kind != 'status').order_by(TrackedMessage.id.desc()))
        rows = list(res.scalars().all())
        for row in rows:
            try:
                await bot.delete_message(row.chat_id, row.message_id)
                deleted += 1
                await db.delete(row)
            except Exception:
                failed += 1
        await db.commit()
    if failed:
        await notify_admins(bot, f'🚨 ERREUR NETTOYAGE\n\nMessages non supprimés : {failed}\nBouton admin : 🧹 Nettoyage pour relancer.')
    return deleted, failed
