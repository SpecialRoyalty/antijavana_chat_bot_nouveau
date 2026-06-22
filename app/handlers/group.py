from aiogram import Router, Bot, F
from aiogram.types import Message, ChatMemberUpdated
from app.config import get_settings
from app.services.users import upsert_user
from app.services.actions import trusted_command
from app.services.moderation import moderate_message, text_has_word, ban
from app.services.vip import copy_media_to_vip, handle_vip_proof
from app.services.crowdfunding import handle_crowd_text, handle_crowd_proof
from app.services.invites import on_join
from app.services.state import track
from app.services import settings as st
router=Router()
@router.my_chat_member()
async def bot_added(event:ChatMemberUpdated, bot:Bot):
    s=get_settings()
    if event.chat.id not in [s.main_group_id,s.pass_soiree_group_id,s.pass_total_group_id,s.vip_javana_group_id,s.log_group_id]:
        for aid in s.admin_ids:
            try: await bot.send_message(aid,f'🚨 Tentative de raccordement pirate\nGroupe: {event.chat.title} ({event.chat.id})')
            except Exception: pass
        try: await bot.send_message(event.chat.id,'Tentative de raccordement pirate détectée 😭')
        except Exception: pass
        try: await bot.leave_chat(event.chat.id)
        except Exception: pass
@router.chat_member()
async def member_update(event:ChatMemberUpdated, bot:Bot):
    await on_join(event, bot)
@router.message()
async def all_messages(msg:Message, bot:Bot):
    if msg.from_user: await upsert_user(msg.from_user)
    # Notifications entrée/sortie: supprimées toujours, sauf notifications de retrait pendant justice populaire.
    if msg.chat.id == get_settings().main_group_id and (msg.new_chat_members or msg.left_chat_member):
        keep_removed = bool(msg.left_chat_member and await st.get_value('justice_running','false') == 'true')
        if not keep_removed:
            try: await bot.delete_message(msg.chat.id, msg.message_id)
            except Exception: pass
        return
    if msg.chat.type=='private':
        if await handle_crowd_text(msg): return
        if await handle_crowd_proof(bot,msg): return
        if await handle_vip_proof(bot,msg): return
        return
    if msg.text and await trusted_command(bot,msg): return
    await moderate_message(bot,msg)
    if msg.chat.id==get_settings().main_group_id:
        await copy_media_to_vip(bot,msg)
