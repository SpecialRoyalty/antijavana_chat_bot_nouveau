from sqlalchemy import select
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Crowdfunding, PaymentProof
from app.services import settings as st
from app.services.state import track
from app.services.session_ops import notify_admins
from app.keyboards.common import pay_kb, admin_validate_kb

def bar(cur:int,target:int):
    pct=0 if target<=0 else min(cur/target,1)
    full=int(pct*10)
    return '█'*full+'░'*(10-full)+f' {int(pct*100)}%'
async def get_campaign():
    async with SessionLocal() as db:
        res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.desc()).limit(1))
        c=res.scalar_one_or_none()
        if not c:
            c=Crowdfunding(text='🎯 FINANCEMENT COMMUNAUTAIRE'); db.add(c); await db.commit()
        return c
async def send_crowd_ad(bot:Bot):
    if not await st.is_open(): return
    c=await get_campaign(); s=get_settings()
    text=f'{c.text or c.title}\n\nObjectif :\n{c.current_amount}€ / {c.target_amount}€\n\n{bar(c.current_amount,c.target_amount)}'
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💰 Je participe',callback_data='crowd_join')]])
    
    if c.image_file_id:
        m=await bot.send_photo(s.main_group_id,c.image_file_id,caption=text,reply_markup=kb)
        await track(s.main_group_id,m.message_id,None,'crowdfunding',True)
    else:
        m=await bot.send_message(s.main_group_id,text,reply_markup=kb)
        await track(s.main_group_id,m.message_id,None,'crowdfunding',False)
async def start_crowd_private(bot:Bot, user_id:int):
    c=await get_campaign()
    await bot.send_message(user_id, f'💰 Participation\n\nObjectif actuel : {c.current_amount}€ / {c.target_amount}€\n\nRéponds avec le montant que tu veux envoyer.')
    await st.set_value(f'crowd_state:{user_id}','amount')
async def handle_crowd_text(msg:Message):
    state=await st.get_value(f'crowd_state:{msg.from_user.id}','')
    if state!='amount': return False
    amount=int(''.join(x for x in (msg.text or '') if x.isdigit()) or '0')
    await st.set_value(f'crowd_amount:{msg.from_user.id}',str(amount))
    await st.set_value(f'crowd_state:{msg.from_user.id}','proof')
    await msg.answer(f'Montant : {amount}€\n\nChoisis un moyen de paiement puis envoie ta capture.',reply_markup=pay_kb('crowd_pay'))
    return True
async def handle_crowd_proof(bot:Bot,msg:Message):
    state=await st.get_value(f'crowd_state:{msg.from_user.id}','')
    if state!='proof' or not msg.photo: return False
    amount=int(await st.get_value(f'crowd_amount:{msg.from_user.id}','0') or '0')
    async with SessionLocal() as db:
        p=PaymentProof(user_id=msg.from_user.id,kind='crowdfunding',amount=amount,screenshot_file_id=msg.photo[-1].file_id,status='pending'); db.add(p); await db.commit(); pid=p.id
    await msg.answer('✅ Capture reçue. Validation admin en attente.')
    await notify_admins(bot,f'💰 Crowdfunding à valider\n\nUtilisateur : @{msg.from_user.username or msg.from_user.full_name}\nMontant : {amount}€',admin_validate_kb('crowd',pid))
    return True
async def validate_crowd(bot:Bot,pid:int,ok:bool):
    async with SessionLocal() as db:
        p=await db.get(PaymentProof,pid)
        if not p: return 'Introuvable'
        p.status='accepted' if ok else 'rejected'
        if ok:
            res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.desc()).limit(1)); c=res.scalar_one_or_none()
            if c: c.current_amount+=p.amount
        await db.commit()
    await bot.send_message(p.user_id,'✅ Participation validée.' if ok else '❌ Participation refusée.')
    return 'OK'


async def set_campaign_text(text:str):
    async with SessionLocal() as db:
        res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.desc()).limit(1)); c=res.scalar_one_or_none()
        if not c: c=Crowdfunding(); db.add(c)
        c.text=text; await db.commit()

async def set_campaign_target(amount:int):
    async with SessionLocal() as db:
        res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.desc()).limit(1)); c=res.scalar_one_or_none()
        if not c: c=Crowdfunding(); db.add(c)
        c.target_amount=max(amount,1); await db.commit()

async def set_campaign_image(file_id:str):
    async with SessionLocal() as db:
        res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.desc()).limit(1)); c=res.scalar_one_or_none()
        if not c: c=Crowdfunding(); db.add(c)
        c.image_file_id=file_id; await db.commit()

async def stats_text():
    c=await get_campaign()
    return f'💰 Crowdfunding\n\nMontant : {c.current_amount}€ / {c.target_amount}€\n\n{bar(c.current_amount,c.target_amount)}\nImage : {"OK" if c.image_file_id else "non configurée"}'
