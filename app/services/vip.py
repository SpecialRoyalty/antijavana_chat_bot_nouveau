from aiogram import Bot
from aiogram.types import Message
from app.config import get_settings
from app.bot.keyboards import vip_keyboard
from app.services.texts import vip_ad_text
from app.services.cleanup import notify_admins

settings = get_settings()


async def send_vip_ad(bot: Bot) -> None:
    if not settings.main_group_id:
        return
    if not (settings.pass_soiree_group_id or settings.pass_total_group_id or settings.vip_javana_group_id):
        return
    await bot.send_message(settings.main_group_id, vip_ad_text(), reply_markup=vip_keyboard())


async def copy_media_to_vip_groups(bot: Bot, message: Message) -> None:
    # Copie uniquement vers Pass soirée + Pass total. JAVANA est alimenté à part.
    targets = [settings.pass_soiree_group_id, settings.pass_total_group_id]
    for target in [x for x in targets if x]:
        try:
            await bot.copy_message(target, message.chat.id, message.message_id)
        except Exception as e:
            await notify_admins(bot, f"🚨 ERREUR REDIFFUSION\n\nGroupe cible : {target}\nErreur : {e}")
