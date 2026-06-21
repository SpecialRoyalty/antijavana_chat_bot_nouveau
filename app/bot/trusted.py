from aiogram import Router, F, Bot
from aiogram.types import Message
from app.services.permissions import is_trusted
from app.db.models import TrustedAction
from app.db.session import SessionLocal

router = Router()
COMMANDS = {'/supprime', '/mineur', '/pasfr', '/pedo', '/clean', '/info'}


@router.message(F.text.startswith('/'))
async def trusted_command(message: Message, bot: Bot):
    if not message.from_user or not is_trusted(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return
    cmd = (message.text or '').split()[0]
    if cmd not in COMMANDS:
        try:
            await message.delete()
        except Exception:
            pass
        return

    target = message.reply_to_message
    if cmd == '/supprime' and target:
        await target.delete()
    elif cmd == '/pedo' and target and target.from_user:
        await bot.ban_chat_member(message.chat.id, target.from_user.id)
        await delete_visible_user_messages_placeholder(bot, message.chat.id, target.from_user.id)
        try:
            await target.delete()
        except Exception:
            pass
    elif cmd in {'/mineur', '/pasfr'} and target and target.from_user:
        from app.services.moderation import restrict_user
        await restrict_user(bot, message.chat.id, target.from_user.id, days=1)
        try:
            await target.delete()
        except Exception:
            pass
    elif cmd == '/info':
        await message.answer('ℹ️ Fiche utilisateur : module branché V1.')

    async with SessionLocal() as db:
        db.add(TrustedAction(
            trusted_user_id=message.from_user.id,
            trusted_username=message.from_user.username,
            command=cmd,
            target_user_id=target.from_user.id if target and target.from_user else None,
        ))
        await db.commit()

    try:
        await message.delete()
    except Exception:
        pass


async def delete_visible_user_messages_placeholder(bot: Bot, chat_id: int, user_id: int) -> None:
    # Les messages sont traqués en DB ; l'implémentation complète supprime tous ceux de user_id dans tracked_messages.
    from sqlalchemy import select
    from app.db.models import TrackedMessage
    from app.db.session import SessionLocal
    async with SessionLocal() as db:
        rows = await db.execute(select(TrackedMessage).where(TrackedMessage.chat_id == chat_id, TrackedMessage.user_id == user_id))
        for m in rows.scalars():
            try:
                await bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
