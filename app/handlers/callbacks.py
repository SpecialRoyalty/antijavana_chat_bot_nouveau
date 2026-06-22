from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message
from app.config import get_settings
from app.services.state import add_vote, ensure_status_message, vote_count
from app.services import settings as st
from app.services.session_ops import set_group_open
from app.utils.time import in_slot
from app.services.vip import create_order, payment_text
from app.keyboards.common import pay_kb
from app.services.crowdfunding import start_crowd_private
router=Router()
@router.callback_query(F.data=='vote_open')
async def vote(cb:CallbackQuery,bot:Bot):
    await add_vote(cb.message.chat.id,cb.from_user.id)
    goal=await st.vote_goal(); votes=await vote_count(cb.message.chat.id)
    await ensure_status_message(bot,cb.message.chat.id)
    if votes>=goal and in_slot(await st.time_slot(), get_settings().timezone) and not await st.is_open():
        await set_group_open(bot,True,'auto_vote')
    await cb.answer('Vote pris en compte ✅')
@router.callback_query(F.data.startswith('vip_offer:'))
async def vip_offer(cb:CallbackQuery):
    offer=cb.data.split(':')[1]
    oid=await create_order(cb.from_user.id, cb.from_user.username or cb.from_user.full_name or '', offer)
    await cb.message.answer(await payment_text(offer),reply_markup=pay_kb('vip_pay'))
    await cb.answer()
@router.callback_query(F.data=='crowd_join')
async def crowd(cb:CallbackQuery):
    await start_crowd_private(cb.message)
    await cb.answer()
@router.callback_query(F.data.startswith('vip_pay:') | F.data.startswith('crowd_pay:'))
async def paynoop(cb:CallbackQuery):
    await cb.answer('Envoie la capture ici après paiement.')
