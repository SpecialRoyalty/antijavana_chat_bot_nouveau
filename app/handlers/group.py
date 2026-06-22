from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from app.config import get_settings
from app.services.state import add_vote, vote_count, get_group_state, register_user
from app.services.messages import ensure_status_message, safe_delete
from app.services.moderation import moderate_message, log_trusted_action
from app.services.session_manager import open_group

router=Router(); settings=get_settings()

@router.callback_query(F.data=='vote_open')
async def vote_open(cb:CallbackQuery, bot:Bot):
    if cb.message is None: return await cb.answer()
    chat_id=cb.message.chat.id
    await register_user(cb.from_user)
    added=await add_vote(chat_id, cb.from_user.id)
    st=await get_group_state(chat_id)
    votes=await vote_count(chat_id)
    if votes >= st.vote_goal and not st.is_open:
        # if inside slot handled by scheduler; this is safe but opens immediately when clicked during slot in simple core
        pass
    await ensure_status_message(bot, chat_id)
    await cb.answer('Vote pris en compte.' if added else 'Vote déjà compté.')

@router.message(F.chat.type.in_({'group','supergroup'}))
async def group_all(message:Message, bot:Bot):
    # anti-pirate: if not configured group, warn and leave
    if settings.main_group_id and message.chat.id != settings.main_group_id and message.from_user and message.from_user.id not in settings.admin_ids:
        try: await message.answer('Tentative de raccordement pirate détectée 😭')
        except Exception: pass
        try: await bot.leave_chat(message.chat.id)
        except Exception: pass
        return

    # trusted commands
    if message.text and message.text.startswith('/') and message.from_user and message.from_user.id in settings.all_trusted:
        cmd=message.text.split()[0].lower()
        if cmd in ['/supprime','/mineur','/pasfr','/pedo'] and message.reply_to_message:
            target=message.reply_to_message
            await safe_delete(bot, message.chat.id, target.message_id)
            await safe_delete(bot, message.chat.id, message.message_id)
            points={'/supprime':1,'/mineur':2,'/pasfr':2,'/pedo':5}[cmd]
            await log_trusted_action(message.from_user.id, target.from_user.id if target.from_user else None, cmd, points)
            if cmd=='/pedo' and target.from_user:
                try: await bot.ban_chat_member(message.chat.id, target.from_user.id)
                except Exception: pass
            return
    await moderate_message(bot, message)
