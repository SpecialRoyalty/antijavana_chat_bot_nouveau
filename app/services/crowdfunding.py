from sqlalchemy import select, func
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
    active_id=int(await st.get_value('active_crowd_id','0') or '0')
    async with SessionLocal() as db:
        c=None
        if active_id:
            c=await db.get(Crowdfunding, active_id)
        if not c:
            res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.asc()).limit(1))
            c=res.scalar_one_or_none()
        if not c:
            c=Crowdfunding(text='🎯 FINANCEMENT COMMUNAUTAIRE'); db.add(c); await db.flush(); await st.set_value('active_crowd_id', str(c.id)); await db.commit()
        return c

async def create_campaign():
    async with SessionLocal() as db:
        count=int((await db.execute(select(func.count(Crowdfunding.id)))).scalar() or 0)
        if count>=2: return False, 'Maximum 2 campagnes crowdfunding à la fois.'
        c=Crowdfunding(text='🎯 FINANCEMENT COMMUNAUTAIRE', target_amount=1000, active=True); db.add(c); await db.flush(); cid=c.id; await db.commit()
    await st.set_value('active_crowd_id', str(cid))
    return True, f'✅ Campagne créée et activée : #{cid}'

async def set_active_campaign(cid:int):
    await st.set_value('active_crowd_id', str(cid))

async def campaigns_text():
    active_id=await st.get_value('active_crowd_id','0')
    async with SessionLocal() as db:
        res=await db.execute(select(Crowdfunding).order_by(Crowdfunding.id.asc()))
        rows=list(res.scalars().all())
    if not rows: return 'Aucune campagne.'
    lines=['💰 Campagnes crowdfunding']
    for c in rows:
        mark='✅ active' if str(c.id)==str(active_id) else 'inactive'
        lines.append(f'#{c.id} — {mark} — {c.current_amount}€/{c.target_amount}€ — image: {"OK" if c.image_file_id else "non"}')
    lines.append('\nPour changer active: bouton à venir / ou crée une nouvelle campagne.')
    return '\n'.join(lines)
async def send_crowd_ad(bot:Bot, force:bool=False):
    if not force and not await st.is_open(): return None
    c=await get_campaign(); s=get_settings()
    text=f'{c.text or c.title}\n\nObjectif :\n{c.current_amount}€ / {c.target_amount}€\n\n{bar(c.current_amount,c.target_amount)}'
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💰 Je participe',callback_data='crowd_join')]])
    
    if c.image_file_id:
        m=await bot.send_photo(s.main_group_id,c.image_file_id,caption=text,reply_markup=kb)
        await track(s.main_group_id,m.message_id,None,'crowdfunding',True)
    else:
        m=await bot.send_message(s.main_group_id,text,reply_markup=kb)
        await track(s.main_group_id,m.message_id,None,'crowdfunding',False)
    from datetime import datetime
    await st.set_value('last_crowd_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
    await st.set_value('last_crowd_message_id', str(m.message_id))
    return m.message_id
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

async def crowd_health_text():
    c=await get_campaign()
    last=await st.get_value('last_crowd_sent_at','jamais')
    mid=await st.get_value('last_crowd_message_id','-')
    state='ouvert' if await st.is_open() else 'fermé'
    return f'💰 Crowdfunding\n\nGroupe : {state}\nDernier envoi : {last}\nDernier message ID : {mid}\nProgression : {c.current_amount}€ / {c.target_amount}€\n{bar(c.current_amount,c.target_amount)}\nProchain envoi automatique : pendant ouverture selon planning.'
