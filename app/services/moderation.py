from __future__ import annotations
import re
from aiogram import Bot
from aiogram.types import Message
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import WordRule, TrackedMessage, User, TrustedAction
from app.services.messages import safe_delete
from app.services.state import register_user, get_group_state
from app.utils.text import display_user
from sqlalchemy import select

settings=get_settings()
URL_RE=re.compile(r'(https?://|t\.me/|www\.|\.com\b|\.net\b|\.io\b)', re.I)
MENTION_RE=re.compile(r'@[A-Za-z0-9_]{4,}')

def is_media(msg: Message) -> bool:
    return bool(msg.photo or msg.video or msg.document or msg.animation or msg.audio or msg.voice or msg.video_note)

def has_link(text:str|None)->bool:
    return bool(text and URL_RE.search(text))

def has_mention(text:str|None)->bool:
    return bool(text and MENTION_RE.search(text))

async def track_message(msg:Message, media:bool):
    async with SessionLocal() as db:
        st=await db.get(__import__('app.db.models', fromlist=['GroupState']).GroupState, msg.chat.id)
        tm=TrackedMessage(chat_id=msg.chat.id, message_id=msg.message_id, user_id=msg.from_user.id if msg.from_user else None, session_id=st.current_session_id if st else None, is_media=media)
        db.add(tm)
        if st and st.current_session_id:
            sess=await db.get(__import__('app.db.models', fromlist=['Session']).Session, st.current_session_id)
            if sess:
                sess.messages_seen += 1
                if media: sess.media_seen += 1
        await db.commit()

async def user_has_media(user_id:int)->bool:
    async with SessionLocal() as db:
        u=await db.get(User, user_id)
        return bool(u and u.sessions_with_media>0)

async def mark_user_media(user_id:int, session_id:int|None):
    async with SessionLocal() as db:
        u=await db.get(User, user_id)
        if u:
            u.sessions_with_media += 1
            u.last_media_session=session_id
            await db.commit()

async def check_word_rules(text:str|None):
    if not text: return None
    low=text.lower()
    async with SessionLocal() as db:
        rows=(await db.execute(select(WordRule))).scalars().all()
    hit_ban=None; hit_forbidden=None
    for r in rows:
        if r.word.lower() in low:
            if r.kind in ('ban','name_ban'): hit_ban=r
            if r.kind=='forbidden': hit_forbidden=r
    return hit_ban or hit_forbidden

async def moderate_message(bot:Bot, msg:Message):
    if not msg.from_user: return
    await register_user(msg.from_user)
    uid=msg.from_user.id
    st=await get_group_state(msg.chat.id)
    trusted = uid in settings.all_trusted
    text = msg.text or msg.caption or ''
    media=is_media(msg)

    # Always track during open session for cleanup/report.
    if st.is_open:
        await track_message(msg, media)

    # Group closed: delete everything except bot/admin/trusted commands.
    if not st.is_open:
        if not trusted:
            await safe_delete(bot, msg.chat.id, msg.message_id)
        return

    # Links forbidden even trusted, but trusted not sanctioned.
    if has_link(text):
        await safe_delete(bot,msg.chat.id,msg.message_id)
        if not trusted:
            try: await bot.ban_chat_member(msg.chat.id, uid)
            except Exception: pass
        return

    # Random slash commands forbidden.
    if msg.text and msg.text.startswith('/') and not trusted:
        await safe_delete(bot,msg.chat.id,msg.message_id)
        try: await bot.restrict_chat_member(msg.chat.id, uid, permissions={'can_send_messages': False})
        except Exception: pass
        return

    if trusted:
        return

    if has_mention(text) or msg.video_note:
        await safe_delete(bot,msg.chat.id,msg.message_id)
        return

    rule=await check_word_rules(text)
    if rule:
        await safe_delete(bot,msg.chat.id,msg.message_id)
        if rule.kind in ('ban','name_ban'):
            try: await bot.ban_chat_member(msg.chat.id, uid)
            except Exception: pass
        else:
            try: await bot.restrict_chat_member(msg.chat.id, uid, permissions={'can_send_messages': False})
            except Exception: pass
        return

    if media:
        await mark_user_media(uid, st.current_session_id)
    elif msg.text and not await user_has_media(uid):
        await safe_delete(bot,msg.chat.id,msg.message_id)
        warn=await bot.send_message(msg.chat.id, f'{display_user(msg.from_user)}, envoie d’abord un média avant d’écrire.')
        return

async def log_trusted_action(trusted_id:int, target_id:int|None, action:str, points:int):
    async with SessionLocal() as db:
        db.add(TrustedAction(trusted_user_id=trusted_id,target_user_id=target_id,action=action,points=points))
        await db.commit()
