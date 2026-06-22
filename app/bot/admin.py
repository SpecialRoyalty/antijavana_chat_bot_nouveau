from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.services.permissions import is_admin
from app.bot.keyboards import admin_menu, schedules_menu, back_menu
from app.services.session_service import open_main_group, close_main_group, ensure_status_message, toggle_auto, get_runtime_settings, set_schedule
from app.services.health import health_report
from app.services.reports import session_report
from app.services.cleanup import cleanup_session

router = Router()


async def _safe_edit(cb: CallbackQuery, text: str, markup=None):
    if cb.message:
        try:
            await cb.message.edit_text(text, reply_markup=markup or admin_menu())
        except Exception:
            await cb.message.answer(text, reply_markup=markup or admin_menu())


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
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    runtime = await get_runtime_settings()
    mode = 'ON' if runtime.get('auto_enabled', True) else 'OFF'
    await _safe_edit(cb, f'📊 TABLEAU DE BORD\n\nHoraire auto : {mode}\nCréneau : {runtime.get("schedule", "22:30-00:45")}\n\nSélectionne un module.', admin_menu())
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


@router.callback_query(F.data == 'admin:auto')
async def auto_cb(cb: CallbackQuery, bot: Bot):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    enabled = await toggle_auto()
    await ensure_status_message(bot)
    await _safe_edit(cb, f'⏰ Horaire auto : {"ON" if enabled else "OFF"}\n\nOFF = maintenance, mais ouverture manuelle possible avec fermeture de sécurité.', admin_menu())
    await cb.answer('Mis à jour')


@router.callback_query(F.data == 'admin:schedules')
async def schedules_cb(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await _safe_edit(cb, '🕒 Choisis le créneau.\n\nModification refusée si une session est déjà ouverte.', schedules_menu())
    await cb.answer()


@router.callback_query(F.data.startswith('admin:set_schedule:'))
async def set_schedule_cb(cb: CallbackQuery, bot: Bot):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    schedule = cb.data.split(':', 2)[2]
    ok, msg = await set_schedule(schedule)
    await ensure_status_message(bot)
    await _safe_edit(cb, ('✅ ' if ok else '⚠️ ') + msg, admin_menu())
    await cb.answer()


@router.callback_query(F.data == 'admin:health')
async def health_cb(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await _safe_edit(cb, await health_report(), admin_menu())
    await cb.answer()


@router.callback_query(F.data == 'admin:report')
async def report_cb(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await _safe_edit(cb, await session_report(), admin_menu())
    await cb.answer()


@router.callback_query(F.data == 'admin:cleanup')
async def cleanup_cb(cb: CallbackQuery, bot: Bot):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    await cleanup_session(bot)
    await ensure_status_message(bot)
    await cb.answer('Nettoyage relancé')


@router.callback_query(F.data.in_({'admin:moderation','admin:justice','admin:suspects','admin:rewards','admin:vip','admin:crowd','admin:ads','admin:pardon_bans','admin:pardon_restrict'}))
async def module_pages(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        return await cb.answer('Non autorisé', show_alert=True)
    titles = {
        'admin:moderation':'🛡️ MODÉRATION\n\nMots interdits, mots ban, noms bannis, liens, mentions, hashes. Configuration complète à brancher ici.',
        'admin:justice':'⚖️ JUSTICE\n\nDéclenchement à 50% de session. Inactifs calculés sur sessions réellement ouvertes.',
        'admin:suspects':'🕵️ COMPTES SUSPECTS\n\nScore 50+ visible, 80+ invitation en attente, 100+ rejet. Bouton nettoyage prévu.',
        'admin:rewards':'🎁 RÉCOMPENSES\n\nPaliers GoFile configurables, compteur récompense remis à 0 après palier.',
        'admin:vip':'💎 VIP\n\nPass soirée, Pass total, COPIE 1:1 VIP JAVANA -50%. Textes/images/prix configurables.',
        'admin:crowd':'💰 CROWDFUNDING\n\nImage + texte + bouton + validation admin.',
        'admin:ads':'📢 PUBLICITÉS\n\nPubs texte/image envoyées pendant session puis supprimées.',
        'admin:pardon_bans':'👑 GRÂCE PRÉSIDENTIELLE\n\nDéban global à connecter à la base Telegram.',
        'admin:pardon_restrict':'⚖️ GRÂCE MINISTÉRIELLE\n\nSuppression globale restrictions à connecter.',
    }
    await _safe_edit(cb, titles.get(cb.data, 'Module'), admin_menu())
    await cb.answer()
