from __future__ import annotations
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from app.config import get_settings
from app.bot.keyboards import vip_keyboard

settings = get_settings()


async def send_vip_ad(bot: Bot) -> None:
    if not settings.main_group_id:
        return
    # Si groupes VIP non configurés: fonctionnement partiel, pas de pub VIP.
    if not (settings.pass_soiree_group_id or settings.pass_total_group_id or settings.vip_javana_group_id):
        return
    await bot.send_message(
        settings.main_group_id,
        '💎 ACCÈS VIP\n\nChoisissez une offre pour obtenir plus d’informations.',
        reply_markup=vip_keyboard(),
    )


async def handle_vip_callback(cb: CallbackQuery, bot: Bot) -> None:
    if not cb.from_user:
        return await cb.answer()
    offer = cb.data.split(':', 1)[1]
    texts = {
        'soiree': '🎟 PASS SOIRÉE\n\nAccès à la rediffusion de la session pendant 5h après fermeture.\n\nPaiement et validation en privé.',
        'total': '📦 PASS TOTAL\n\nAccès permanent aux archives alimentées depuis le groupe principal.\n\nPaiement et validation en privé.',
        'javana': '💎 COPIE 1:1 VIP JAVANA -50%\n\nAccès au groupe VIP associé.\n\nPaiement et validation en privé.',
    }
    try:
        await bot.send_message(cb.from_user.id, texts.get(offer, 'Offre VIP'), reply_markup=vip_keyboard())
        await cb.answer('Je t’ai envoyé les détails en privé')
    except Exception:
        await cb.answer('Ouvre le bot en privé puis reclique.', show_alert=True)


async def copy_media_to_vip_groups(bot: Bot, message: Message) -> None:
    targets = [settings.pass_soiree_group_id, settings.pass_total_group_id]
    for target in targets:
        if not target:
            continue
        try:
            await bot.copy_message(chat_id=target, from_chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
