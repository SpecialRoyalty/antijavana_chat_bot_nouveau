from datetime import datetime, timedelta
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import Message
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import VipOrder, PaymentProof, TrackedMessage
from app.keyboards.common import vip_kb, pay_kb, admin_validate_kb
from app.services import settings as st
from app.services.session_ops import notify_admins
from app.services.state import track, log_error

OFFER_NAMES={'soiree':'🎟 Pass soirée','total':'📦 Pass total','javana':'💎 COPIE 1:1 VIP JAVANA -50%'}
async def send_vip_ad(bot:Bot):
    s=get_settings()
    if not await st.is_open(): return
    text=await st.get_value('vip_text','💎 ACCÈS VIP\n\nChoisissez une offre.')
    m=await bot.send_message(s.main_group_id,text,reply_markup=vip_kb())
    await track(s.main_group_id,m.message_id,None,'vip_ad',False)
async def create_order(user_id:int, username:str, offer:str):
    async with SessionLocal() as db:
        order=VipOrder(user_id=user_id,username=username,offers=offer,status='selecting'); db.add(order); await db.commit(); return order.id
async def payment_text(offer:str):
    s=get_settings()
    return f'{OFFER_NAMES.get(offer,offer)}\n\nChoisissez le moyen de paiement.\n\nPayPal: {s.paypal_text or "à configurer"}\nRevolut: {s.revolut_text or "à configurer"}\nCrypto: {s.crypto_text or "à configurer"}\n\nAprès paiement, envoyez la capture ici.'
async def handle_vip_proof(bot:Bot,msg:Message):
    if not msg.photo: return False
    async with SessionLocal() as db:
        res=await db.execute(select(VipOrder).where(VipOrder.user_id==msg.from_user.id,VipOrder.status.in_(['selecting','pending'])).order_by(VipOrder.id.desc()).limit(1))
        order=res.scalar_one_or_none()
        if not order: return False
        order.screenshot_file_id=msg.photo[-1].file_id; order.status='pending'; await db.commit()
        await msg.answer('✅ Capture reçue. Validation admin en attente.')
        await notify_admins(bot,f'💰 Nouvelle demande VIP\n\nUtilisateur : @{msg.from_user.username or msg.from_user.full_name}\nOffre : {OFFER_NAMES.get(order.offers,order.offers)}', admin_validate_kb('vip',order.id))
        return True
async def validate_vip(bot:Bot, order_id:int, ok:bool):
    s=get_settings()
    async with SessionLocal() as db:
        order=await db.get(VipOrder,order_id)
        if not order: return 'Commande introuvable.'
        order.status='accepted' if ok else 'rejected'; await db.commit()
    if ok:
        await bot.send_message(order.user_id,'✅ Paiement validé. Votre accès est activé.')
        group={'soiree':s.pass_soiree_group_id,'total':s.pass_total_group_id,'javana':s.vip_javana_group_id}.get(order.offers)
        if group:
            try:
                link=await bot.create_chat_invite_link(group, member_limit=1)
                await bot.send_message(order.user_id,f'Lien d’accès :\n{link.invite_link}')
            except Exception as e: await log_error('vip_invite',e)
    else:
        await bot.send_message(order.user_id,'❌ Paiement refusé.')
    return 'OK'
async def copy_media_to_vip(bot:Bot,msg:Message):
    s=get_settings()
    if not (msg.photo or msg.video or msg.document or msg.animation): return
    for gid,label in [(s.pass_soiree_group_id,'soiree'),(s.pass_total_group_id,'total')]:
        if not gid: continue
        try: await bot.copy_message(gid,msg.chat.id,msg.message_id)
        except Exception as e: await log_error(f'copy_{label}',e)
async def expire_pass_soiree(bot:Bot):
    s=get_settings()
    if not s.pass_soiree_group_id: return
    # Supprime les médias suivis dans ce groupe et relance les admins; Telegram ne permet pas de lister tous les membres non vus.
    async with SessionLocal() as db:
        res=await db.execute(select(TrackedMessage).where(TrackedMessage.chat_id==s.pass_soiree_group_id,TrackedMessage.deleted==False))
        for tm in res.scalars().all():
            try: await bot.delete_message(tm.chat_id,tm.message_id); tm.deleted=True
            except Exception: pass
        await db.commit()
    await notify_admins(bot,'🎟 Pass soirée expiré : nettoyage lancé. Retrait membres à faire sur membres connus/commandes validées.')
