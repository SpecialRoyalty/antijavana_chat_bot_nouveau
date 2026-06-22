from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from app.config import get_settings
from app.keyboards.inline import admin_main_keyboard
from app.services.session_manager import open_group, close_group, cleanup_session
from app.services.messages import ensure_status_message
from app.services.health import health_report
from app.services.state import get_group_state
from app.db.session import SessionLocal
from app.db.models import GroupState

router=Router(); settings=get_settings()

def is_admin(uid:int|None)->bool:
    return bool(uid and uid in settings.admin_ids)

@router.message(F.chat.type == 'private', F.text.in_({'/start','/admin'}))
async def admin_start(message:Message):
    if not is_admin(message.from_user.id):
        return await message.answer('Accès refusé.')
    await message.answer('Panel admin', reply_markup=admin_main_keyboard())

@router.callback_query(F.data.startswith('admin_'))
async def admin_callbacks(cb:CallbackQuery, bot:Bot):
    if not is_admin(cb.from_user.id):
        return await cb.answer('Accès refusé', show_alert=True)
    chat_id=settings.main_group_id
    if not chat_id:
        return await cb.message.answer('MAIN_GROUP_ID manquant.')
    data=cb.data
    if data=='admin_health':
        await cb.message.answer(await health_report(bot))
    elif data=='admin_dashboard':
        await cb.message.answer('📊 Tableau de bord\n\nUtilise Santé pour vérifier les branchements et erreurs.')
    elif data=='admin_open':
        await open_group(bot, chat_id, kind='manual')
        await cb.message.answer('Groupe ouvert manuellement.')
    elif data=='admin_close':
        await close_group(bot, chat_id, reason='manual')
        await cb.message.answer('Groupe fermé et nettoyage lancé.')
    elif data=='admin_cleanup':
        await cleanup_session(bot, chat_id)
        await cb.message.answer('Nettoyage relancé.')
    elif data=='admin_toggle_auto':
        async with SessionLocal() as db:
            st=await db.get(GroupState, chat_id) or GroupState(chat_id=chat_id)
            st.auto_enabled=not st.auto_enabled
            db.add(st); await db.commit()
        await ensure_status_message(bot, chat_id)
        st=await get_group_state(chat_id)
        await cb.message.answer(f'⏰ Horaire auto : {"ON" if st.auto_enabled else "OFF"}')
    else:
        await cb.message.answer('Module présent dans le cahier des charges. À configurer dans la V2 avancée.')
    await cb.answer()
