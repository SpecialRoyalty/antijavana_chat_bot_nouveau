from datetime import datetime
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import VipOrder, TrackedMessage
from app.keyboards.common import admin_validate_kb
from app.services import settings as st
from app.services.session_ops import notify_admins
from app.services.state import track, log_error

OFFER_NAMES={'soiree':'🎟 Pass soirée','total':'📦 Pass total','javana':'💎 COPIE 1:1 VIP JAVANA -50%'}

async def offer_price(offer:str)->int:
    return int(await st.get_value(f'vip_price_{offer}', {'soiree':'10','total':'30','javana':'50'}.get(offer,'0')) or '0')

async def vip_group_kb():
    username=get_settings().public_bot_username.strip().lstrip('@')
    if username:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🎟 Pass soirée', url=f'https://t.me/{username}?start=vip_soiree')],
            [InlineKeyboardButton(text='📦 Pass total', url=f'https://t.me/{username}?start=vip_total')],
            [InlineKeyboardButton(text='💎 COPIE 1:1 VIP JAVANA -50%', url=f'https://t.me/{username}?start=vip_javana')],
        ])
    # fallback callback si username pas configuré
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎟 Pass soirée', callback_data='vip_offer:soiree')],
        [InlineKeyboardButton(text='📦 Pass total', callback_data='vip_offer:total')],
        [InlineKeyboardButton(text='💎 COPIE 1:1 VIP JAVANA -50%', callback_data='vip_offer:javana')],
    ])

async def user_cart(user_id:int)->set[str]:
    raw=await st.get_value(f'vip_cart:{user_id}','')
    return {x for x in raw.split(',') if x}
async def set_cart(user_id:int, items:set[str]):
    await st.set_value(f'vip_cart:{user_id}', ','.join(sorted(items)))
async def toggle_cart(user_id:int, offer:str):
    items=await user_cart(user_id)
    if offer in items: items.remove(offer)
    else: items.add(offer)
    await set_cart(user_id, items)
    return items
async def cart_total(items:set[str])->int:
    return sum([await offer_price(x) for x in items])

def vip_private_kb(items:set[str]):
    def mark(o): return '☑️' if o in items else '☐'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'{mark("soiree")} 🎟 Pass soirée', callback_data='vip_toggle:soiree')],
        [InlineKeyboardButton(text=f'{mark("total")} 📦 Pass total', callback_data='vip_toggle:total')],
        [InlineKeyboardButton(text=f'{mark("javana")} 💎 COPIE 1:1 VIP JAVANA -50%', callback_data='vip_toggle:javana')],
        [InlineKeyboardButton(text='💳 Continuer au paiement', callback_data='vip_checkout')],
    ])

def payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='PayPal', callback_data='vip_pay:paypal'), InlineKeyboardButton(text='Revolut', callback_data='vip_pay:revolut'), InlineKeyboardButton(text='Crypto', callback_data='vip_pay:crypto')],
        [InlineKeyboardButton(text='⬅️ Modifier offres', callback_data='vip_menu')]
    ])

async def vip_menu_text(user_id:int)->str:
    items=await user_cart(user_id)
    lines=['💎 MENU VIP\n']
    for o in ['soiree','total','javana']:
        desc=await st.get_value(f'vip_offer_{o}_text', OFFER_NAMES[o])
        lines.append(f'{OFFER_NAMES[o]} — {await offer_price(o)}€')
        if desc and desc != OFFER_NAMES[o]: lines.append(desc[:180])
        lines.append('')
    lines.append('Sélectionne une ou plusieurs offres.')
    if items:
        lines.append('\nVotre sélection : ' + ', '.join(OFFER_NAMES[x] for x in sorted(items)))
        lines.append(f'Total : {await cart_total(items)}€')
    return '\n'.join(lines)

async def send_vip_private(bot:Bot, user_id:int, preselect:str|None=None):
    if preselect:
        items=await user_cart(user_id); items.add(preselect); await set_cart(user_id,items)
    items=await user_cart(user_id)
    await bot.send_message(user_id, await vip_menu_text(user_id), reply_markup=vip_private_kb(items))

async def send_vip_ad(bot:Bot, force:bool=False):
    s=get_settings()
    if not force and not await st.is_open(): return None
    text=await st.get_value('vip_text','💎 ACCÈS VIP\n\nChoisissez une offre.')
    image=await st.get_value('vip_image_file_id','')
    kb=await vip_group_kb()
    if image:
        m=await bot.send_photo(s.main_group_id,image,caption=text,reply_markup=kb)
    else:
        m=await bot.send_message(s.main_group_id,text,reply_markup=kb)
    await track(s.main_group_id,m.message_id,None,'vip_ad',bool(image))
    await st.set_value('last_vip_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
    await st.set_value('last_vip_message_id', str(m.message_id))
    return m.message_id

async def create_order_from_cart(user_id:int, username:str):
    items=await user_cart(user_id)
    if not items: return None
    offers=','.join(sorted(items)); amount=str(await cart_total(items))
    async with SessionLocal() as db:
        order=VipOrder(user_id=user_id,username=username,offers=offers,amount=amount,status='selecting')
        db.add(order); await db.commit(); return order.id

async def payment_text_for_cart(user_id:int):
    s=get_settings(); items=await user_cart(user_id); total=await cart_total(items)
    selected='\n'.join(f'- {OFFER_NAMES.get(x,x)}' for x in sorted(items)) or 'Aucune'
    return f'💳 Paiement VIP\n\nSélection :\n{selected}\n\nTotal : {total}€\n\nPayPal : {s.paypal_text or "à configurer"}\nRevolut : {s.revolut_text or "à configurer"}\nCrypto : {s.crypto_text or "à configurer"}\n\nAprès paiement, envoie une capture ici.'

async def handle_vip_proof(bot:Bot,msg:Message):
    if not msg.photo: return False
    async with SessionLocal() as db:
        res=await db.execute(select(VipOrder).where(VipOrder.user_id==msg.from_user.id,VipOrder.status.in_(['selecting','pending'])).order_by(VipOrder.id.desc()).limit(1))
        order=res.scalar_one_or_none()
        if not order: return False
        order.screenshot_file_id=msg.photo[-1].file_id; order.status='pending'; await db.commit()
        await msg.answer('✅ Capture reçue. Validation admin en attente.')
        await notify_admins(bot,f'💰 Nouvelle demande VIP\n\nUtilisateur : @{msg.from_user.username or msg.from_user.full_name}\nOffres : {order.offers}\nMontant : {order.amount}€', admin_validate_kb('vip',order.id))
        return True

async def validate_vip(bot:Bot, order_id:int, ok:bool):
    s=get_settings()
    async with SessionLocal() as db:
        order=await db.get(VipOrder,order_id)
        if not order: return 'Commande introuvable.'
        order.status='accepted' if ok else 'rejected'; await db.commit()
    if ok:
        await bot.send_message(order.user_id,'✅ Paiement validé. Vos accès sont activés.')
        for offer in [x for x in order.offers.split(',') if x]:
            group={'soiree':s.pass_soiree_group_id,'total':s.pass_total_group_id,'javana':s.vip_javana_group_id}.get(offer)
            if group:
                try:
                    link=await bot.create_chat_invite_link(group, member_limit=1)
                    await bot.send_message(order.user_id,f'{OFFER_NAMES.get(offer,offer)}\nLien d’accès :\n{link.invite_link}')
                except Exception as e: await log_error('vip_invite',e)
    else:
        await bot.send_message(order.user_id,'❌ Paiement refusé.')
    return 'OK'

async def copy_media_to_vip(bot:Bot,msg:Message):
    s=get_settings()
    if not (msg.photo or msg.video or msg.document or msg.animation): return
    for gid,label in [(s.pass_soiree_group_id,'soiree'),(s.pass_total_group_id,'total')]:
        if not gid: continue
        try:
            copied=await bot.copy_message(gid,msg.chat.id,msg.message_id)
            await track(gid,copied.message_id,None,f'copy_{label}',True)
        except Exception as e: await log_error(f'copy_{label}',e)

async def expire_pass_soiree(bot:Bot):
    s=get_settings()
    if not s.pass_soiree_group_id: return
    async with SessionLocal() as db:
        res=await db.execute(select(TrackedMessage).where(TrackedMessage.chat_id==s.pass_soiree_group_id,TrackedMessage.deleted==False))
        for tm in res.scalars().all():
            try: await bot.delete_message(tm.chat_id,tm.message_id); tm.deleted=True
            except Exception: pass
        await db.commit()
    await notify_admins(bot,'🎟 Pass soirée expiré : nettoyage lancé. Retrait membres sur utilisateurs connus.')

async def vip_health_text():
    last=await st.get_value('last_vip_sent_at','jamais')
    mid=await st.get_value('last_vip_message_id','-')
    image='oui' if await st.get_value('vip_image_file_id','') else 'non'
    state='ouvert' if await st.is_open() else 'fermé'
    return f'💎 VIP\n\nGroupe : {state}\nImage principale configurée : {image}\nDernier envoi : {last}\nDernier message ID : {mid}\nPrix : soirée {await offer_price("soiree")}€ / total {await offer_price("total")}€ / JAVANA {await offer_price("javana")}€\nProchain envoi automatique : pendant ouverture selon planning.'
