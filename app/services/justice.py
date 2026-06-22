from sqlalchemy import select
from aiogram import Bot
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import User
from app.services import settings as st
from app.services.session_ops import CLOSED_PERMS, OPEN_PERMS, notify_admins
from app.services.state import track, log_error

MAX_JUSTICE_REMOVALS = 20

async def _current_session_key() -> str:
    sid = await st.get_value('active_session_id','0')
    return sid if sid and sid != '0' else await st.get_value('current_day_key','manual')

async def justice_already_done() -> bool:
    key = await _current_session_key()
    return await st.get_value(f'justice_done_session:{key}','false') == 'true'

async def mark_justice_done():
    key = await _current_session_key()
    await st.set_value(f'justice_done_session:{key}','true')

async def candidates(limit:int=MAX_JUSTICE_REMOVALS):
    s=get_settings()
    bot_id = int(await st.get_value('bot_id','0') or '0')
    sid = int(await st.get_value('active_session_id','0') or '0')
    protected_ids = set(s.admin_ids) | set(s.trusted_ids)
    if bot_id:
        protected_ids.add(bot_id)
    async with SessionLocal() as db:
        q = select(User).where(User.is_admin==False, User.is_trusted==False, User.is_banned==False)
        if protected_ids:
            q = q.where(User.id.not_in(list(protected_ids)))
        q = q.where((User.media_count==0) | (User.last_media_session < max(sid-14, 0)))
        q = q.order_by(User.media_count.asc(), User.last_media_session.asc(), User.suspect_score.desc()).limit(limit)
        res = await db.execute(q)
        return [u for u in res.scalars().all() if u.id not in protected_ids]

async def justice_preview_text():
    if await justice_already_done():
        return '⚖️ Justice populaire\n\nJustice déjà exécutée pour cette session.\n\nMaximum : 1 fois par session, manuel ou auto.'
    cs = await candidates(MAX_JUSTICE_REMOVALS)
    if not cs:
        return '⚖️ Justice populaire\n\nAucun membre justifiable détecté pour le moment.\n\nRien ne sera envoyé dans le groupe.'
    lines = [f'⚖️ Justice populaire\n\nMembres justifiables détectés : {len(cs)}\nSuppression max : {MAX_JUSTICE_REMOVALS}\n', 'Aperçu :']
    for u in cs[:10]:
        name = ('@'+u.username) if u.username else (u.full_name or 'membre')
        shown = name[:3] + '****' if len(name)>3 else name+'****'
        lines.append(f'- {shown} — médias: {u.media_count}, score: {u.suspect_score}')
    lines.append('\nValider le lancement ?')
    return '\n'.join(lines)

async def execute_justice(bot:Bot, manual:bool=False):
    s=get_settings()
    if await justice_already_done():
        return 0, 'Justice déjà exécutée pour cette session.'
    cs=await candidates(MAX_JUSTICE_REMOVALS)
    if not cs:
        return 0, 'Aucun membre justifiable détecté.'
    await mark_justice_done()
    await st.set_value('justice_running','true')
    try: await bot.set_chat_permissions(s.main_group_id, permissions=CLOSED_PERMS)
    except Exception as e: await log_error('justice_permissions_close',e)
    try:
        m = await bot.send_message(s.main_group_id, f'⚖️ JUSTICE POPULAIRE\n\nLe groupe est bloqué pendant 5 minutes.\n\nMembres inactifs détectés : {len(cs)}\nLes plus inactifs sont supprimés.')
        await track(s.main_group_id, m.message_id, None, 'justice', False)
    except Exception as e:
        await log_error('justice_message', e)
    removed=0
    async with SessionLocal() as db:
        for u in cs:
            if u.id == int(await st.get_value('bot_id','0') or '0'):
                continue
            try:
                await bot.ban_chat_member(s.main_group_id, u.id)
                await bot.unban_chat_member(s.main_group_id, u.id, only_if_banned=True)
                u2=await db.get(User,u.id)
                if u2: u2.is_banned=True
                removed+=1
            except Exception as e:
                await log_error('justice_remove',f'{u.id}: {e}')
        await db.commit()
    import asyncio
    await asyncio.sleep(300)
    try: await bot.set_chat_permissions(s.main_group_id, permissions=OPEN_PERMS)
    except Exception as e: await log_error('justice_permissions_open',e)
    try:
        m2=await bot.send_message(s.main_group_id, f'🟢 JUSTICE TERMINÉE\n\nMembres supprimés : {removed}\nLe groupe est de nouveau ouvert.')
        await track(s.main_group_id, m2.message_id, None, 'justice', False)
    except Exception as e:
        await log_error('justice_end_message', e)
    await st.set_value('justice_running','false')
    await notify_admins(bot, f'⚖️ Justice terminée. Membres supprimés : {removed}')
    return removed, f'Justice lancée. Membres supprimés : {removed}'
