from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from app.config import get_settings
from app.services.session_service import register_vote, ensure_status_message, track_message, get_or_create_session
from app.services.moderation import moderate_message
from app.services.vip import copy_media_to_vip_groups, handle_vip_callback

router = Router()
settings = get_settings()


@router.callback_query(F.data == 'vote:open')
async def vote_open(cb: CallbackQuery, bot: Bot):
    if not cb.from_user:
        return await cb.answer()
    votes, target, created = await register_vote(cb.from_user.id)
    await ensure_status_message(bot)
    await cb.answer('Vote pris en compte' if created else 'Vote déjà compté')


@router.callback_query(F.data.startswith('vip:'))
async def vip_cb(cb: CallbackQuery, bot: Bot):
    await handle_vip_callback(cb, bot)


@router.message(F.chat.type.in_({'group', 'supergroup'}))
async def group_message(message: Message, bot: Bot):
    if settings.main_group_id and message.chat.id != settings.main_group_id:
        try:
            await message.answer('Tentative de raccordement pirate détectée. Rejoignez le groupe officiel.')
            await bot.leave_chat(message.chat.id)
        except Exception:
            pass
        return

    # Supprime les notifications entrée/sortie.
    if message.new_chat_members or message.left_chat_member:
        try:
            await message.delete()
        except Exception:
            pass
        return

    handled = await moderate_message(bot, message)
    if handled:
        return

    s = await get_or_create_session()
    # Groupe fermé: tout message utilisateur est supprimé silencieusement sauf statut/boutons.
    if s.status != 'open':
        try:
            await message.delete()
        except Exception:
            pass
        return

    kind = 'media' if (message.photo or message.video or message.document or message.animation) else 'message'
    await track_message(message.chat.id, message.message_id, message.from_user.id if message.from_user else None, kind)
    if kind == 'media':
        await copy_media_to_vip_groups(bot, message)
