from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated, Message

from app.config import get_settings
from app.services import settings as st
from app.services.actions import trusted_command
from app.services.crowdfunding import handle_crowd_proof, handle_crowd_text
from app.services.invites import on_join
from app.services.moderation import moderate_message
from app.services.state import track
from app.services.users import upsert_user
from app.services.vip import copy_media_to_vip, handle_vip_proof

router = Router()


@router.my_chat_member()
async def bot_added(event: ChatMemberUpdated, bot: Bot):
    s = get_settings()
    allowed_groups = [
        s.main_group_id,
        s.pass_soiree_group_id,
        s.pass_total_group_id,
        s.vip_javana_group_id,
        s.log_group_id,
    ]

    if event.chat.id not in allowed_groups:
        for aid in s.admin_ids:
            try:
                await bot.send_message(
                    aid,
                    f'🚨 Tentative de raccordement pirate\n'
                    f'Groupe: {event.chat.title} ({event.chat.id})',
                )
            except Exception:
                pass
        try:
            await bot.send_message(event.chat.id, 'Tentative de raccordement pirate détectée 😭')
        except Exception:
            pass
        try:
            await bot.leave_chat(event.chat.id)
        except Exception:
            pass


@router.chat_member()
async def member_update(event: ChatMemberUpdated, bot: Bot):
    await on_join(event, bot)


@router.message()
async def all_messages(msg: Message, bot: Bot):
    if msg.from_user:
        await upsert_user(msg.from_user)

    # Notifications entrée/sortie: supprimées toujours, sauf notifications de retrait pendant justice populaire.
    if msg.chat.id == get_settings().main_group_id and (msg.new_chat_members or msg.left_chat_member):
        keep_removed = bool(
            msg.left_chat_member
            and await st.get_value('justice_running', 'false') == 'true'
        )
        if keep_removed:
            # Pendant la justice populaire, les notifications de retrait restent visibles
            # pour l'effet public. Elles sont suivies afin d'être supprimées
            # automatiquement à la fermeture/nettoyage de session.
            await track(
                msg.chat.id,
                msg.message_id,
                getattr(msg.left_chat_member, 'id', None),
                'justice_removed_notification',
                False,
            )
        else:
            try:
                await bot.delete_message(msg.chat.id, msg.message_id)
            except Exception:
                pass
        return

    if msg.chat.type == 'private':
        if await handle_crowd_text(msg):
            return
        if await handle_crowd_proof(bot, msg):
            return
        if await handle_vip_proof(bot, msg):
            return
        return

    if msg.text and await trusted_command(bot, msg):
        return

    allowed = await moderate_message(bot, msg)
    if not allowed:
        return

    if msg.chat.id == get_settings().main_group_id:
        await copy_media_to_vip(bot, msg)
