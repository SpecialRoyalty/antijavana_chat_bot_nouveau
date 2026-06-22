import random
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Advertisement
from app.services import settings as st
from app.services.state import track

async def add_ad(text:str='', image_file_id:str|None=None):
    async with SessionLocal() as db:
        ad=Advertisement(title=f'Pub', text=text, image_file_id=image_file_id, active=True)
        db.add(ad); await db.commit(); return ad.id

async def list_ads_text():
    async with SessionLocal() as db:
        res=await db.execute(select(Advertisement).order_by(Advertisement.id.desc()).limit(20))
        ads=list(res.scalars().all())
    if not ads: return '📢 Aucune publicité configurée.'
    return '📢 Publicités configurées\n\n'+'\n'.join([f'#{a.id} — {"active" if a.active else "off"} — {(a.text or "[image]")[:60]}' for a in ads])

async def send_random_ad(bot:Bot, force:bool=False):
    if not force and not await st.is_open(): return None
    async with SessionLocal() as db:
        res=await db.execute(select(Advertisement).where(Advertisement.active==True))
        ads=list(res.scalars().all())
    if not ads: return None
    ad=random.choice(ads); s=get_settings()
    kb=None
    if ad.button_text and ad.button_url:
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=ad.button_text,url=ad.button_url)]])
    if ad.image_file_id:
        m=await bot.send_photo(s.main_group_id,ad.image_file_id,caption=ad.text or None,reply_markup=kb)
    else:
        m=await bot.send_message(s.main_group_id,ad.text or '📢 Publicité',reply_markup=kb)
    await track(s.main_group_id,m.message_id,None,'ad',bool(ad.image_file_id))
    from datetime import datetime
    await st.set_value('last_ad_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
    await st.set_value('last_ad_message_id', str(m.message_id))
    return m.message_id

async def ads_health_text():
    last=await st.get_value('last_ad_sent_at','jamais')
    mid=await st.get_value('last_ad_message_id','-')
    state='ouvert' if await st.is_open() else 'fermé'
    return f'📢 Publicités\n\nGroupe : {state}\nDernier envoi : {last}\nDernier message ID : {mid}\nProchain envoi automatique : pendant ouverture selon planning.\nVérification fermeture : le rapport de nettoyage confirme si la pub suivie a été supprimée.'
