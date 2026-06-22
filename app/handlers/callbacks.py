from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from app.config import get_settings
from app.services.state import add_vote, ensure_status_message, vote_count
from app.services import settings as st
from app.services.session_ops import set_group_open
from app.utils.time import in_slot
from app.services.vip import create_order, payment_text
from app.keyboards.common import pay_kb
from app.services.crowdfunding import start_crowd_private
router=Router()

async def dm_or_alert(cb:CallbackQuery, bot:Bot, text:str, reply_markup=None):
    try:
        await bot.send_message(cb.from_user.id,text,reply_markup=reply_markup)
        await cb.answer('Je t’ai envoyé les détails en privé ✅')
    except (TelegramForbiddenError, TelegramBadRequest):
        await cb.answer('Ouvre le bot en privé puis reclique ici.',show_alert=True)

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
    await create_order(cb.from_user.id, cb.from_user.username or cb.from_user.full_name or '', offer)
    await dm_or_alert(cb,bot,await payment_text(offer),reply_markup=pay_kb('vip_pay'))

@router.callback_query(F.data=='crowd_join')
async def crowd(cb:CallbackQuery, bot:Bot):
    await start_crowd_private(bot, cb.from_user.id)
    await cb.answer('Je t’ai envoyé les infos en privé ✅')

@router.callback_query(F.data.startswith('vip_pay:') | F.data.startswith('crowd_pay:'))
async def paynoop(cb:CallbackQuery):
    await cb.answer('Envoie la capture ici après paiement.')
