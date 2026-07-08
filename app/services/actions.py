from sqlalchemy import select, update
from aiogram import Bot
from aiogram.types import Message

from app.config import get_settings
from app.db.models import MediaHash, TrackedMessage, TrustedAction
from app.db.session import SessionLocal
from app.services.hashban import ban_hash_from_message
from app.services.moderation import ban, delete, record_media, restrict


async def trusted_command(bot: Bot, msg: Message):
    """Trusted/admin moderation commands.

    Important hash-ban behavior:
    /pedo must ban the target media using both Telegram file_unique_id and SHA256,
    then mark every already-known media hash for that user as banned.
    """
    if not msg.from_user or msg.from_user.id not in get_settings().all_admin_ids:
        return False

    cmd = (msg.text or '').split()[0].lower().split('@')[0]
    if cmd not in ['/supprime', '/mineur', '/pasfr', '/pedo', '/clean', '/info']:
        return False

    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass

    target = msg.reply_to_message

    async with SessionLocal() as db:
        db.add(
            TrustedAction(
                trusted_user_id=msg.from_user.id,
                trusted_username=msg.from_user.username or msg.from_user.full_name or '',
                command=cmd,
                target_user_id=target.from_user.id if target and target.from_user else None,
            )
        )
        await db.commit()

    if cmd == '/clean':
        n = 50
        parts = (msg.text or '').split()
        if len(parts) > 1 and parts[1].isdigit():
            n = min(int(parts[1]), 300)

        for mid in range(msg.message_id - 1, max(msg.message_id - n, 0), -1):
            try:
                await bot.delete_message(msg.chat.id, mid)
            except Exception:
                pass
        return True

    if cmd == '/info' and target and target.from_user:
        await bot.send_message(
            msg.from_user.id,
            f'👤 {target.from_user.full_name}\n'
            f'@{target.from_user.username or "sans username"}\n'
            f'ID interne masqué dans le groupe.',
        )
        return True

    if not target or not target.from_user:
        return True

    if cmd == '/supprime':
        await delete(bot, target)

    elif cmd == '/mineur':
        await delete(bot, target)
        await restrict(bot, msg.chat.id, target.from_user.id, 1)

    elif cmd == '/pasfr':
        await delete(bot, target)
        await restrict(bot, msg.chat.id, target.from_user.id, 1)

    elif cmd == '/pedo':
        uid = target.from_user.id

        # 1) Ban the user first.
        await ban(bot, msg.chat.id, uid)

        # 2) Ban the replied media strongly: file_unique_id + SHA256.
        #    This was the missing part in the running project.
        await ban_hash_from_message(target, bot)

        # 3) Also record the replied media through the moderation media pipeline.
        #    This stores both file_unique_id and SHA256 in the corrected moderation.py.
        await record_media(target, banned=True, bot=bot)

        async with SessionLocal() as db:
            # 4) Ban every media already known for that user.
            await db.execute(
                update(MediaHash)
                .where(MediaHash.user_id == uid)
                .values(banned=True)
            )

            # 5) Delete every tracked message still visible from that user.
            res = await db.execute(
                select(TrackedMessage).where(
                    TrackedMessage.chat_id == msg.chat.id,
                    TrackedMessage.user_id == uid,
                    TrackedMessage.deleted == False,  # noqa: E712
                )
            )

            for tm in res.scalars().all():
                try:
                    await bot.delete_message(tm.chat_id, tm.message_id)
                    tm.deleted = True
                except Exception:
                    pass

            await db.commit()

    return True
