from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from app.config import get_settings
from app.services.state import add_vote, ensure_status_message, vote_count
from app.services import settings as st
from app.services.session_ops import set_group_open
from app.utils.time import in_slot
from app.services.vip import send_vip_private, toggle_cart, user_cart, vip_menu_text, vip_private_kb, create_order_from_cart, payment_text_for_cart, payment_kb
from app.services.crowdfunding import start_crowd_private
router=Router()

async def dm_or_deeplink(cb:CallbackQuery, bot:Bot, offer:str):
    try:
        await send_vip_private(bot, cb.from_user.id, offer)
        await cb.answer('Menu VIP ouvert en privé ✅')
    except (TelegramForbiddenError, TelegramBadRequest):
        username=get_settings().public_bot_username.strip().lstrip('@')
        if username:
            await cb.answer(url=f'https://t.me/{username}?start=vip_{offer}')
        else:
            await cb.answer('Démarre le bot en privé puis reclique.', show_alert=True)

@router.callback_query(F.data=='vote_open')
async def vote(cb:CallbackQuery,bot:Bot):
    added=await add_vote(cb.message.chat.id,cb.from_user.id)
    goal=await st.vote_goal(); votes=await vote_count(cb.message.chat.id)
    if votes>=goal and in_slot(await st.time_slot(), get_settings().timezone) and not await st.is_open():
        await set_group_open(bot,True,'auto_vote')
    else:
        await ensure_status_message(bot,cb.message.chat.id)
    await cb.answer('Vote pris en compte ✅' if added else 'Vote déjà compté ✅')

@router.callback_query(F.data.startswith('vip_offer:'))
async def vip_offer(cb:CallbackQuery, bot:Bot):
    offer=cb.data.split(':')[1]
    await dm_or_deeplink(cb, bot, offer)

@router.callback_query(F.data=='vip_menu')
async def vip_menu(cb:CallbackQuery, bot:Bot):
    items=await user_cart(cb.from_user.id)
    try:
        await cb.message.edit_text(await vip_menu_text(cb.from_user.id), reply_markup=vip_private_kb(items))
    except Exception:
        await bot.send_message(cb.from_user.id, await vip_menu_text(cb.from_user.id), reply_markup=vip_private_kb(items))
    await cb.answer()

@router.callback_query(F.data.startswith('vip_toggle:'))
async def vip_toggle(cb:CallbackQuery):
    offer=cb.data.split(':')[1]
    items=await toggle_cart(cb.from_user.id, offer)
    await cb.message.edit_text(await vip_menu_text(cb.from_user.id), reply_markup=vip_private_kb(items))
    await cb.answer('Sélection mise à jour')

@router.callback_query(F.data=='vip_checkout')
async def vip_checkout(cb:CallbackQuery):
    items=await user_cart(cb.from_user.id)
    if not items:
        await cb.answer('Choisis au moins une offre.', show_alert=True); return
    await create_order_from_cart(cb.from_user.id, cb.from_user.username or cb.from_user.full_name or '')
    await cb.message.edit_text(await payment_text_for_cart(cb.from_user.id), reply_markup=payment_kb())
    await cb.answer()

@router.callback_query(F.data=='crowd_join')
async def crowd(cb:CallbackQuery, bot:Bot):
    try:
        await start_crowd_private(bot, cb.from_user.id)
        await cb.answer('Je t’ai envoyé les infos en privé ✅')
    except (TelegramForbiddenError, TelegramBadRequest):
        username=get_settings().public_bot_username.strip().lstrip('@')
        if username: await cb.answer(url=f'https://t.me/{username}?start=crowd')
        else: await cb.answer('Démarre le bot en privé puis reclique.', show_alert=True)

@router.callback_query(F.data.startswith('vip_pay:') | F.data.startswith('crowd_pay:'))
async def paynoop(cb:CallbackQuery):
    await cb.answer('Envoie la capture ici après paiement.')
