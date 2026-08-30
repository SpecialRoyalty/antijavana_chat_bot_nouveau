from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated, Message

from app.services import settings as st
from app.services.actions import trusted_command
from app.services.crowdfunding import handle_crowd_proof, handle_crowd_text
from app.services.invites import on_join
from app.services.moderation import moderate_message
from app.services.hashban import remember_media_message
from app.services.state import track
from app.services.users import upsert_user
from app.services.vip import copy_media_to_vip, handle_vip_proof
from app.services.anti_fast_join import register_join
from app.services.multigroup import (
    active_group_id,
    apply_existing_sanctions_on_join,
    handle_manual_member_change,
    is_main_group,
    is_validated_chat,
    register_detected_chat,
)

router = Router()


@router.my_chat_member()
async def bot_added(event: ChatMemberUpdated, bot: Bot):
    # Un chat inconnu reste silencieux/PENDING jusqu'à validation par ADMIN_ID.
    await register_detected_chat(event, bot)


@router.chat_member()
async def member_update(event: ChatMemberUpdated, bot: Bot):
    if not await is_validated_chat(event.chat.id):
        return

    member = getattr(event.new_chat_member, 'user', None)
    raw_status = getattr(event.new_chat_member, 'status', '')
    new_status = str(getattr(raw_status, 'value', raw_status) or '').lower()

    # Les bans/mutes faits manuellement par un admin Telegram deviennent globaux.
    await handle_manual_member_change(event, bot)

    if member and new_status in ('member', 'restricted'):
        # Une sanction persistée gagne toujours sur un retour/rejoin.
        if await apply_existing_sanctions_on_join(bot, event.chat.id, member.id):
            return
        if await is_main_group(event.chat.id):
            await register_join(event)
            await on_join(event, bot)


@router.message()
async def all_messages(msg: Message, bot: Bot):
    remember_media_message(msg)

    if msg.from_user:
        await upsert_user(msg.from_user)

    if msg.chat.type == 'private':
        if await handle_crowd_text(msg):
            return
        if await handle_crowd_proof(bot, msg):
            return
        if await handle_vip_proof(bot, msg):
            return
        return

    # Aucun chat non validé n'est modéré/automatisé.
    if not await is_validated_chat(msg.chat.id):
        return

    main = await is_main_group(msg.chat.id)

    # Notifications entrée/sortie : supprimées dans les deux groupes principaux,
    # sauf les notifications visibles de justice.
    if main and (msg.new_chat_members or msg.left_chat_member):
        keep_removed = bool(
            msg.left_chat_member and await st.get_value('justice_running', 'false') == 'true'
        )
        if keep_removed:
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

    # Les VIP communs ne passent pas dans le pipeline de publication principal.
    if not main:
        return

    if msg.text and await trusted_command(bot, msg):
        return

    # Le groupe inactif ne doit jamais injecter des médias dans les VIP.
    active = await active_group_id()
    if not active or msg.chat.id != active:
        if not msg.from_user or msg.from_user.id not in __import__('app.config', fromlist=['get_settings']).get_settings().all_admin_ids:
            try:
                await bot.delete_message(msg.chat.id, msg.message_id)
            except Exception:
                pass
            return

    allowed = await moderate_message(bot, msg)
    if not allowed:
        return

    if msg.chat.id == active:
        await copy_media_to_vip(bot, msg)
