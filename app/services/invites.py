from datetime import datetime, timedelta
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import ChatMemberUpdated
from app.db.session import SessionLocal
from app.db.models import User, InviteLink
from app.services.users import upsert_user
from app.config import get_settings
from app.services.moderation import text_has_word
from app.services.state import log_error

JOIN_CACHE: dict[int, tuple[int|None, datetime]] = {}
async def on_join(event:ChatMemberUpdated, bot:Bot|None=None):
    if not event.new_chat_member or event.new_chat_member.status not in ('member','restricted'): return
    u=await upsert_user(event.from_user)
    name=((event.from_user.username or '')+' '+(event.from_user.full_name or '')).strip()
    if bot and await text_has_word('nameban', name):
        try:
            await bot.ban_chat_member(event.chat.id, event.from_user.id)
            u.is_banned=True
        except Exception as e: await log_error('nameban_join', e)
        return
    owner=None
    JOIN_CACHE[event.from_user.id]=(owner, datetime.utcnow())
async def validate_invites(bot:Bot):
    now=datetime.utcnow()
    for uid,(owner,t) in list(JOIN_CACHE.items()):
        if now-t >= timedelta(minutes=5):
            if owner:
                async with SessionLocal() as db:
                    user=await db.get(User,owner)
                    if user:
                        user.total_invites+=1; user.reward_counter+=1; user.weekly_invites+=1
                        await db.commit()
                        try: await bot.send_message(owner,f'✅ +1 invité validé\n\nProgression : {user.reward_counter}')
                        except Exception: pass
            JOIN_CACHE.pop(uid,None)
async def top_text():
    async with SessionLocal() as db:
        res=await db.execute(select(User).where(User.weekly_invites>0).order_by(User.weekly_invites.desc()).limit(10))
        users=res.scalars().all()
    if not users: return '🏆 TOP INVITEURS\n\nAucune statistique pour le moment.'
    lines=['🏆 TOP INVITEURS — J-7','']
    for i,u in enumerate(users,1):
        name=('@'+u.username[:2]+'****') if u.username else (u.full_name[:2]+'****')
        lines.append(f'{i}. {name} — {u.weekly_invites} invités')
    lines.append('\nLe TOP 3 débloque tous les avantages.\nFin du classement dans : 7 jours')
    return '\n'.join(lines)
