from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.services.permissions import is_admin
from app.bot.keyboards import admin_menu
from app.services.session_service import open_main_group, close_main_group, ensure_status_message
from app.services.health import health_report

router = Router()


@router.message(Command('start'))
async def start(message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        try:
            await message.delete()
        except Exception:
            pass
        return
    await message.answer('Panel admin', reply_markup=admin_menu())


@router.callback_query(F.data == 'admin:dashboard')
async def dashboard(cb: CallbackQuery):
    await cb.message.edit_text('📊 TABLEAU DE BORD\n\nV1 Python active.', reply_markup=admin_menu())
    await cb.answer()


@router.callback_query(F.data == 'admin:open')
async def open_cb(cb: CallbackQuery, bot: Bot):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await open_main_group(bot, manual=True)
    await cb.answer('Groupe ouvert')


@router.callback_query(F.data == 'admin:close')
async def close_cb(cb: CallbackQuery, bot: Bot):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await close_main_group(bot, reason='manual')
    await cb.answer('Groupe fermé')


@router.callback_query(F.data == 'admin:health')
async def health_cb(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await cb.message.edit_text(await health_report(), reply_markup=admin_menu())
    await cb.answer()


@router.callback_query(F.data.startswith('admin:'))
async def placeholder(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await cb.answer('Module présent dans architecture V1')
