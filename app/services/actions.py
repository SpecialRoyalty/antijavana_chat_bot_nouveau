import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy import select

from app.config import get_settings
from app.db.models import TrackedMessage, TrustedAction
from app.db.session import SessionLocal
from app.services.hashban import (
    audit_hashes,
    ensure_hashes_banned,
    format_hash_audit,
    split_telegram_text,
)
from app.services.moderation import ban, delete, restrict
from app.services.state import log_error


async def trusted_command(bot: Bot, msg: Message) -> bool:
    if not msg.from_user or msg.from_user.id not in get_settings().all_admin_ids:
        return False

    cmd = (msg.text or "").split()[0].lower()
    if cmd not in ["/supprime", "/mineur", "/pasfr", "/pedo", "/hashdemande", "/clean", "/info"]:
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
                trusted_username=msg.from_user.username or msg.from_user.full_name or "",
                command=cmd,
                target_user_id=target.from_user.id if target and target.from_user else None,
            )
        )
        await db.commit()

    if cmd == "/clean":
        count = 50
        parts = (msg.text or "").split()
        if len(parts) > 1 and parts[1].isdigit():
            count = min(int(parts[1]), 300)
        semaphore = asyncio.Semaphore(4)
        async def remove(message_id: int):
            async with semaphore:
                try:
                    await bot.delete_message(msg.chat.id, message_id)
                except Exception:
                    pass
        await asyncio.gather(*(
            remove(message_id)
            for message_id in range(msg.message_id - 1, max(msg.message_id - count, 0), -1)
        ))
        return True

    if cmd == "/info" and target and target.from_user:
        await bot.send_message(
            msg.from_user.id,
            f"👤 {target.from_user.full_name}\n"
            f"@{target.from_user.username or 'sans username'}\n"
            "ID interne masqué dans le groupe.",
        )
        return True

    if cmd == "/hashdemande":
        if not target:
            await bot.send_message(msg.from_user.id, "Réponds à un média ou à un élément d’album avec /hashdemande.")
            return True
        entries = await audit_hashes(bot, target)
        report = format_hash_audit(entries, title="🔍 DEMANDE DE VÉRIFICATION HASH")
        async def send_report_to_admin(admin_id: int):
            for chunk in split_telegram_text(report):
                try:
                    await bot.send_message(admin_id, chunk)
                except Exception as exc:
                    await log_error("hashdemande_send", exc)
        await asyncio.gather(*(send_report_to_admin(admin_id) for admin_id in get_settings().admin_ids))
        return True

    if not target:
        return True

    if cmd == "/supprime":
        await delete(bot, target)
    elif cmd == "/mineur":
        await delete(bot, target)
        if target.from_user:
            await restrict(bot, msg.chat.id, target.from_user.id, 1)
    elif cmd == "/pasfr":
        await delete(bot, target)
        if target.from_user:
            await restrict(bot, msg.chat.id, target.from_user.id, 1)
    elif cmd == "/pedo":
        uid = target.from_user.id if target.from_user else None
        if uid:
            # Le média ciblé est blacklisté AVANT sa suppression : ID Telegram + SHA256.
            try:
                fingerprints, audits = await ensure_hashes_banned(bot, target)
                report = format_hash_audit(
                    audits,
                    title=f"🚫 /PEDO — BLACKLIST CONFIRMÉE ({fingerprints} empreinte(s))",
                )
                for chunk in split_telegram_text(report):
                    try:
                        await bot.send_message(msg.from_user.id, chunk)
                    except Exception as send_exc:
                        await log_error("pedo_hash_report", send_exc)
            except Exception as exc:
                await log_error("pedo_hashban", exc)
                try:
                    await bot.send_message(
                        msg.from_user.id,
                        "🔴 /pedo : le bannissement utilisateur continue, mais la mise en blacklist du média a échoué. Consulte les logs avant de considérer le hash comme protégé.",
                    )
                except Exception:
                    pass

            from app.services.multigroup import global_ban, main_group_ids
            await global_ban(bot, uid, source_chat_id=msg.chat.id, source='pedo', reason='/pedo', created_by=msg.from_user.id)

            group_ids=await main_group_ids()
            async with SessionLocal() as db:
                tracked_rows = list((await db.execute(
                    select(TrackedMessage.id, TrackedMessage.chat_id, TrackedMessage.message_id).where(
                        TrackedMessage.chat_id.in_(group_ids) if group_ids else TrackedMessage.chat_id == msg.chat.id,
                        TrackedMessage.user_id == uid,
                        TrackedMessage.deleted.is_(False),
                    )
                )).all())

            semaphore = asyncio.Semaphore(4)
            async def remove_tracked(row):
                row_id, chat_id, message_id = row
                async with semaphore:
                    try:
                        await bot.delete_message(chat_id, message_id)
                        return row_id
                    except TelegramBadRequest as exc:
                        low = str(exc).lower()
                        if 'message to delete not found' in low or 'message identifier is not specified' in low:
                            return row_id
                        return None
                    except Exception:
                        return None
            removed_ids = [rid for rid in await asyncio.gather(*(remove_tracked(row) for row in tracked_rows)) if rid is not None]
            if removed_ids:
                from sqlalchemy import update
                async with SessionLocal() as db:
                    await db.execute(update(TrackedMessage).where(TrackedMessage.id.in_(removed_ids)).values(deleted=True))
                    await db.commit()

    return True
