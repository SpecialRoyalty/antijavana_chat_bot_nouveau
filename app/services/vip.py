from __future__ import annotations
import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import VipOrder, TrackedMessage, VipAccess
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

async def vip_cart_block_reason(user_id:int, items:set[str]) -> str|None:
    # Cohérence commerciale : quelqu'un qui possède déjà un accès supérieur
    # ne peut plus acheter le Pass soirée seul. On bloque aussi les doublons
    # d'accès déjà actifs/en attente.
    if not items:
        return 'Choisis au moins une offre.'
    async with SessionLocal() as db:
        existing = await db.execute(
            select(VipAccess).where(
                VipAccess.user_id == user_id,
                VipAccess.status.in_(['pending','active'])
            )
        )
        accesses=list(existing.scalars().all())
    have={a.offer for a in accesses}
    if 'soiree' in items and not ({'total','javana'} & items) and ({'total','javana'} & have):
        return 'Tu disposes déjà d’un accès supérieur. Le Pass Soirée n’est plus nécessaire.'
    if 'total' in items and 'total' in have:
        return 'Tu disposes déjà du Pass Total.'
    if 'javana' in items and 'javana' in have:
        return 'Tu disposes déjà du VIP JAVANA.'
    if 'soiree' in items and 'soiree' in have and not ({'total','javana'} & items):
        return 'Tu disposes déjà d’un Pass Soirée pour la session.'
    return None


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

async def send_vip_ad(bot:Bot, force:bool=False, target:str='active'):
    """Publie l'offre VIP.

    Automatique : groupe actif uniquement et seulement pendant l'ouverture.
    Manuel (force=True) : A, B ou A+B même si les groupes sont fermés.
    """
    if not force and not await st.is_open():
        return []
    from app.services.multigroup import resolve_main_targets
    targets=await resolve_main_targets(target, include_unavailable=False)
    if not targets:
        return []
    text=await st.get_value('vip_text','💎 ACCÈS VIP\n\nChoisissez une offre.')
    image=await st.get_value('vip_image_file_id','')
    kb=await vip_group_kb()
    sent=[]
    for chat_id in targets:
        try:
            if image:
                m=await bot.send_photo(chat_id,image,caption=text,reply_markup=kb)
            else:
                m=await bot.send_message(chat_id,text,reply_markup=kb)
            await track(chat_id,m.message_id,None,'vip_ad',bool(image))
            sent.append((chat_id,m.message_id))
        except Exception as e:
            await log_error(f'vip_ad:{chat_id}',e)
    if sent:
        await st.set_value('last_vip_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
        await st.set_value('last_vip_message_id', str(sent[-1][1]))
        await st.set_value('last_vip_chat_ids', ','.join(str(x[0]) for x in sent))
    return sent


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

def _proof_file_id(msg:Message):
    if msg.photo: return msg.photo[-1].file_id
    if msg.document: return msg.document.file_id
    return None

async def handle_vip_proof(bot:Bot,msg:Message):
    if not msg.from_user: return False
    fid=_proof_file_id(msg)
    if not fid: return False
    async with SessionLocal() as db:
        res=await db.execute(select(VipOrder).where(VipOrder.user_id==msg.from_user.id,VipOrder.status.in_(['selecting','pending'])).order_by(VipOrder.id.desc()).limit(1))
        order=res.scalar_one_or_none()
        if not order: return False
        order.screenshot_file_id=fid
        order.status='pending'
        if not order.proof_received_at:
            # Heure de réception de la preuve = meilleure référence disponible pour
            # déterminer le créneau d'achat du Pass soirée.
            order.proof_received_at=datetime.utcnow()
        await db.commit()
        await msg.answer('✅ Capture reçue. Validation admin en attente.')
        await notify_admins(bot,f'💰 Nouvelle demande VIP\n\nUtilisateur : @{msg.from_user.username or msg.from_user.full_name}\nOffres : {order.offers}\nMontant : {order.amount}€', admin_validate_kb('vip',order.id))
        return True

async def _group_for_offer(offer:str, *, include_unavailable:bool=True)->int|None:
    """Retourne le chat VIP configuré pour l'offre.

    Les émissions réelles essaient aussi un chat momentanément marqué unavailable :
    un ancien incident de health-check ne doit pas bloquer les paiements pour toujours.
    """
    from app.services.multigroup import chat_id_for_role, ROLE_VIP_SOIREE, ROLE_VIP_TOTAL, ROLE_VIP_JAVANA
    role={'soiree':ROLE_VIP_SOIREE,'total':ROLE_VIP_TOTAL,'javana':ROLE_VIP_JAVANA}.get(offer)
    if role:
        gid=await chat_id_for_role(role, include_unavailable=include_unavailable)
        if gid:
            return gid
    return None

def _now_local():
    return datetime.now(ZoneInfo(get_settings().timezone))

def _today_at(hour:int, minute:int=0):
    n=_now_local()
    return datetime.combine(n.date(), time(hour,minute), tzinfo=n.tzinfo)

def _soiree_send_now()->bool:
    n=_now_local()
    # de 23:00 à 04:59:59, le lien est envoyé immédiatement.
    return n.hour >= 23 or n.hour < 5

def _soiree_next_release_utc()->datetime:
    n=_now_local()
    release=_today_at(23,0)
    if n >= release:
        release = release + timedelta(days=1)
    return release.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

def _soiree_expire_utc_for_current_or_next()->datetime:
    n=_now_local()
    exp=_today_at(5,0)
    if n.hour >= 5:
        exp = exp + timedelta(days=1)
    return exp.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

def _utc_naive_to_local(value:datetime)->datetime:
    """Convertit un datetime DB UTC naive vers le fuseau du bot."""
    if value.tzinfo is None:
        value=value.replace(tzinfo=ZoneInfo('UTC'))
    else:
        value=value.astimezone(ZoneInfo('UTC'))
    return value.astimezone(ZoneInfo(get_settings().timezone))

def _local_to_utc_naive(value:datetime)->datetime:
    return value.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

def _next_six_local(moment:datetime)->datetime:
    six=datetime.combine(moment.date(), time(6,0), tzinfo=moment.tzinfo)
    if moment >= six:
        six += timedelta(days=1)
    return six

def _paid_soiree_schedule(payment_utc:datetime, *, now_local:datetime|None=None)->tuple[datetime,datetime,bool]:
    """Planning du Pass soirée payant.

    - preuve reçue entre 00:00 et 05:59 : libération à 12:00 le même jour,
      expiration à 06:00 le lendemain ;
    - preuve reçue entre 06:00 et 23:59 : éligible immédiatement après
      validation admin, expiration à 06:00 le lendemain ;
    - si l'admin valide tellement tard que l'expiration prévue est déjà passée,
      l'achat n'est jamais perdu : l'accès part immédiatement et expire au
      prochain 06:00.
    """
    pay=_utc_naive_to_local(payment_utc)
    now=now_local or _now_local()
    if pay.hour < 6:
        release=datetime.combine(pay.date(), time(12,0), tzinfo=pay.tzinfo)
        expiry=datetime.combine(pay.date()+timedelta(days=1), time(6,0), tzinfo=pay.tzinfo)
    else:
        release=pay
        expiry=datetime.combine(pay.date()+timedelta(days=1), time(6,0), tzinfo=pay.tzinfo)
    if expiry <= now:
        release=now
        expiry=_next_six_local(now)
    return _local_to_utc_naive(release), _local_to_utc_naive(expiry), now >= release

def _next_paid_soiree_expiry_utc()->datetime:
    return _local_to_utc_naive(_next_six_local(_now_local()))

async def _create_one_time_link(bot:Bot, group_id:int, offer:str, expires_at:datetime|None=None):
    kwargs={'member_limit':1}
    if expires_at:
        # Telegram accepte un datetime ou timestamp selon aiogram ; on passe datetime UTC naive/aware compatible.
        kwargs['expire_date']=expires_at
    link=await bot.create_chat_invite_link(group_id, **kwargs)
    return link.invite_link

async def _send_access_link_verbose(bot:Bot, access_id:int) -> tuple[bool,str]:
    """Crée puis livre réellement le lien.

    Un échec ne transforme plus l'accès en ``failed`` : il reste ``pending`` afin
    qu'un retry automatique puisse le reprendre. Un accès n'est marqué ``active``
    qu'après réception confirmée du message privé par Telegram.
    """
    async with SessionLocal() as db:
        a=await db.get(VipAccess, access_id)
        if not a or a.status not in ['pending','failed']:
            return False, 'accès introuvable ou déjà traité'
        offer=a.offer
        user_id=a.user_id
        expires_at=a.expires_at
        group_id=a.group_id

    # Toujours préférer le rôle VIP actuellement validé. Si un groupe VIP a été
    # remplacé depuis le paiement, on ne doit pas envoyer un lien vers l'ancien.
    resolved_group=await _group_for_offer(offer, include_unavailable=True)
    if resolved_group:
        group_id=resolved_group
    if offer=='soiree':
        # Pour le Pass soirée payant, ``expires_at`` est calculé à partir du
        # créneau de paiement. On le conserve tant qu'il est dans le futur.
        # Si un incident/retard a dépassé cette échéance, on ne fait jamais
        # payer un accès déjà expiré : il repart jusqu'au prochain 06:00.
        if not expires_at or expires_at <= datetime.utcnow():
            expires_at=_next_paid_soiree_expiry_utc()
    if group_id:
        async with SessionLocal() as db:
            a=await db.get(VipAccess, access_id)
            if a:
                a.group_id=group_id
                a.expires_at=expires_at
                a.status='pending'
                await db.commit()
    if not group_id:
        reason=f'groupe VIP {offer} non configuré'
        await st.set_value(f'vip_link_last_error:{offer}', reason)
        await log_error('vip_access', reason)
        return False, reason

    link=''
    try:
        link=await _create_one_time_link(bot, group_id, offer, expires_at)
    except Exception as exc:
        reason=f'création lien impossible: {type(exc).__name__}: {exc}'
        async with SessionLocal() as db:
            a=await db.get(VipAccess, access_id)
            if a:
                a.status='pending'
                await db.commit()
        await st.set_value(f'vip_link_last_error:{offer}', reason[:500])
        await log_error('vip_invite',exc)
        return False, reason

    msg = {
        'soiree': '✅ Paiement validé\n\nAccès accordé au Pass soirée.\n\nTon accès reste actif jusqu’à 06:00 selon le cycle indiqué lors de la validation.\n\nLien unique :',
        'total': '✅ Paiement validé\n\nAccès permanent accordé.\n\nLien unique utilisable une seule fois :',
        'javana': '✅ Paiement validé\n\nBienvenue dans COPIE 1:1 VIP JAVANA -50%.\n\nLien unique utilisable une seule fois :',
    }.get(offer,'✅ Paiement validé\n\nLien unique :')
    try:
        await bot.send_message(user_id, f'{msg}\n{link}')
    except Exception as exc:
        try:
            await bot.revoke_chat_invite_link(group_id, link)
        except Exception:
            pass
        reason=f'envoi privé impossible: {type(exc).__name__}: {exc}'
        async with SessionLocal() as db:
            a=await db.get(VipAccess, access_id)
            if a:
                a.status='pending'
                await db.commit()
        await st.set_value(f'vip_link_last_error:{offer}', reason[:500])
        await log_error('vip_send_link',exc)
        return False, reason

    async with SessionLocal() as db:
        a=await db.get(VipAccess, access_id)
        if a:
            a.group_id=group_id
            a.invite_link=link
            a.invite_sent_at=datetime.utcnow()
            a.status='active'
            await db.commit()
    await st.set_value(f'vip_link_last_error:{offer}', '')
    await st.set_value(f'vip_link_last_success:{offer}', datetime.utcnow().isoformat(timespec='seconds'))
    return True, 'lien envoyé'


async def _send_access_link(bot:Bot, access_id:int):
    ok,_reason=await _send_access_link_verbose(bot, access_id)
    return ok

async def validate_vip(bot:Bot, order_id:int, ok:bool):
    async with SessionLocal() as db:
        order=await db.get(VipOrder,order_id)
        if not order:
            return '❌ Commande introuvable.'
        if order.status in ('accepted','rejected'):
            return f'ℹ️ Commande déjà traitée : {order.status}.'
        order.status='accepted' if ok else 'rejected'
        accesses=[]
        if ok:
            payment_at=order.proof_received_at or order.created_at or datetime.utcnow()
            for offer in [x for x in order.offers.split(',') if x]:
                group=await _group_for_offer(offer, include_unavailable=True)
                access=VipAccess(order_id=order.id,user_id=order.user_id,username=order.username,offer=offer,group_id=group,status='pending')
                release_utc=None
                send_now=True
                if offer=='soiree':
                    release_utc, expiry_utc, send_now=_paid_soiree_schedule(payment_at)
                    access.expires_at=expiry_utc
                db.add(access)
                await db.flush()
                accesses.append((access.id,offer,bool(group),release_utc,send_now))
        await db.commit()
    if not ok:
        try:
            await bot.send_message(order.user_id,'❌ Paiement refusé.')
        except Exception:
            pass
        return '❌ Paiement refusé.'

    result_lines=['✅ Paiement validé.']
    waiting_soiree=[]
    for aid,offer,has_group,release_utc,send_now in accesses:
        if offer=='soiree' and not send_now:
            waiting_soiree.append((aid, release_utc, has_group))
            release_local=_utc_naive_to_local(release_utc)
            if has_group:
                result_lines.append(f'🎟 Pass soirée : en attente — lien prévu à {release_local:%H:%M} le {release_local:%d/%m}.')
            else:
                result_lines.append('🎟 Pass soirée : ⚠️ groupe VIP non configuré, accès conservé en attente.')
            continue
        sent,reason=await _send_access_link_verbose(bot, aid)
        if sent:
            result_lines.append(f'{OFFER_NAMES.get(offer,offer)} : ✅ lien envoyé.')
        else:
            result_lines.append(f'{OFFER_NAMES.get(offer,offer)} : ⚠️ lien non envoyé — {reason[:180]}')

    if waiting_soiree:
        _aid,release_utc,_has_group=waiting_soiree[0]
        release_local=_utc_naive_to_local(release_utc)
        try:
            await bot.send_message(
                order.user_id,
                '✅ Paiement validé\n\n'
                'Ton Pass soirée est enregistré.\n\n'
                f'Ton lien unique sera envoyé automatiquement à {release_local:%H:%M} le {release_local:%d/%m}.\n\n'
                'L’accès expirera à 06:00 le lendemain.'
            )
        except Exception as exc:
            await log_error('vip_soiree_wait_notice', exc)
        await notify_admins(
            bot,
            '🎟 Pass soirée mis en attente\n'
            f'Utilisateur : @{order.username or order.user_id}\n'
            f'Libération locale : {release_local:%d/%m/%Y %H:%M}'
        )

    await set_cart(order.user_id,set())
    return '\n'.join(result_lines)

async def send_due_pass_soiree_links(bot:Bot, force:bool=False):
    """Libère les Pass soirée PAYANTS devenus éligibles.

    Le scheduler appelle cette fonction régulièrement. Les Pass gratuits gardent
    leur propre mécanisme dans ``freepass.py`` (order_id=0).
    """
    now_local=_now_local()
    now_utc=datetime.utcnow()
    async with SessionLocal() as db:
        rows=list((await db.execute(
            select(VipAccess, VipOrder)
            .join(VipOrder, VipOrder.id==VipAccess.order_id)
            .where(
                VipAccess.offer=='soiree',
                VipAccess.order_id>0,
                VipAccess.status.in_(['pending','failed']),
            )
            .order_by(VipAccess.created_at.asc())
            .limit(100)
        )).all())
    sent=0
    due=0
    for access,order in rows:
        payment_at=order.proof_received_at or order.created_at or access.created_at or now_utc
        release_utc, expiry_utc, _send_now=_paid_soiree_schedule(payment_at, now_local=now_local)
        # Même ``force=True`` (appel lors d'une ouverture) ne doit jamais
        # contourner le créneau 00h-06h -> libération à 12h.
        if release_utc > now_utc:
            continue
        due += 1
        async with SessionLocal() as db:
            a=await db.get(VipAccess, access.id)
            if not a or a.status not in ['pending','failed']:
                continue
            # Si une validation/indisponibilité a dépassé l'ancien cycle, la
            # fonction de planning a déjà repoussé l'échéance au prochain 06:00.
            a.expires_at=expiry_utc
            a.status='pending'
            await db.commit()
        if await _send_access_link(bot, access.id):
            sent+=1
    if sent or due:
        await st.set_value('last_pass_soiree_release_at', datetime.utcnow().isoformat(timespec='seconds'))
    if sent:
        await notify_admins(bot, f'🎟 Pass soirée : {sent} lien(s) payé(s) envoyé(s).')
    return sent


async def retry_pending_permanent_vip_links(bot:Bot):
    """Retente automatiquement Total/JAVANA après une panne Telegram temporaire."""
    async with SessionLocal() as db:
        ids=list((await db.execute(
            select(VipAccess.id).where(
                VipAccess.offer.in_(['total','javana']),
                VipAccess.status.in_(['pending','failed']),
            ).order_by(VipAccess.created_at.asc()).limit(50)
        )).scalars().all())
    sent=0
    for aid in ids:
        if await _send_access_link(bot, int(aid)):
            sent += 1
    if sent:
        await notify_admins(bot, f'💎 Retry VIP : {sent} lien(s) permanent(s) finalement envoyé(s).')
    return sent

async def copy_media_to_vip(bot:Bot,msg:Message):
    """Copie les médias autorisés vers les trois VIP communs."""
    if (await st.get_value('vip_repost_enabled','true')) != 'true':
        return []
    if not (msg.photo or msg.video or msg.document or msg.animation):
        return []
    from app.services.multigroup import chat_id_for_role, ROLE_VIP_SOIREE, ROLE_VIP_TOTAL, ROLE_VIP_JAVANA
    targets=[
        (await chat_id_for_role(ROLE_VIP_SOIREE, include_unavailable=True),'soiree'),
        (await chat_id_for_role(ROLE_VIP_TOTAL, include_unavailable=True),'total'),
        (await chat_id_for_role(ROLE_VIP_JAVANA, include_unavailable=True),'javana'),
    ]
    sent=[]; failed=[]
    for gid,label in targets:
        if not gid:
            failed.append(f'{label}:non_configuré')
            continue
        try:
            copied=await bot.copy_message(gid,msg.chat.id,msg.message_id)
            await track(gid,copied.message_id,None,f'copy_{label}',True)
            sent.append((gid,label,copied.message_id))
        except Exception as e:
            failed.append(f'{label}:{type(e).__name__}')
            await log_error(f'copy_{label}',e)
    await st.set_value('vip_repost_last_at', datetime.utcnow().isoformat(timespec='seconds'))
    await st.set_value('vip_repost_last_result', f'ok={len(sent)};fail={"|".join(failed) if failed else "0"}')
    return sent

def _chat_member_status(member)->str:
    raw=getattr(member,'status','')
    return str(getattr(raw,'value',raw) or '').lower()

async def _user_has_active_total(user_id:int)->bool:
    async with SessionLocal() as db:
        row=await db.execute(
            select(VipAccess.id).where(
                VipAccess.user_id==user_id,
                VipAccess.offer=='total',
                VipAccess.status=='active',
            ).limit(1)
        )
        return row.scalar_one_or_none() is not None

async def _send_pass_soiree_expired_offer(bot:Bot, user_id:int):
    """Notification d'expiration + proposition Pass Total si pertinente."""
    if await _user_has_active_total(user_id):
        await bot.send_message(
            user_id,
            '⏳ Ton Pass Soirée est terminé.\n\n'
            'Ton accès Pass Total reste bien actif.'
        )
        return
    price=await offer_price('total')
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'📦 Prendre le Pass Total — {price}€', callback_data='vip_offer:total')]
    ])
    await bot.send_message(
        user_id,
        '⏳ Ton Pass Soirée est terminé.\n\n'
        'Ton accès au groupe Pass Soirée a été retiré.\n\n'
        'Tu veux garder un accès permanent ?\n'
        f'📦 Pass Total — {price}€',
        reply_markup=kb,
    )


def _revocation_error_means_already_closed(exc:Exception)->bool:
    msg=str(exc).lower()
    markers=(
        'invite hash expired', 'invite_hash_expired',
        'invite hash is invalid', 'invite_hash_invalid',
        'invite link expired',
    )
    return any(x in msg for x in markers)


async def expire_pass_soiree(bot:Bot):
    """Sécurise réellement les Pass soirée arrivés à échéance.

    Un accès ne passe à ``expired`` que lorsque :
    1) le lien d'invitation est révoqué (ou déjà inutilisable), et
    2) Telegram confirme que l'utilisateur n'est plus membre du groupe.

    En cas d'échec Telegram/droits, l'accès reste ``active`` et sera retenté au
    prochain passage du scheduler (toutes les 5 minutes).
    """
    now=datetime.utcnow()
    async with SessionLocal() as db:
        ids=list((await db.execute(
            select(VipAccess.id).where(
                VipAccess.offer=='soiree',
                VipAccess.status=='active',
                (VipAccess.expires_at.is_(None)) | (VipAccess.expires_at <= now),
            ).order_by(VipAccess.created_at.asc()).limit(200)
        )).scalars().all())

    removed=0
    already_absent=0
    expired=0
    failed=[]

    for aid in ids:
        async with SessionLocal() as db:
            a=await db.get(VipAccess, aid)
            if not a or a.status!='active':
                continue
            if a.expires_at and a.expires_at > datetime.utcnow():
                continue
            user_id=a.user_id
            gid=a.group_id
            invite_link=a.invite_link

        if not gid:
            gid=await _group_for_offer('soiree', include_unavailable=True)
        if not gid:
            failed.append(f'{user_id}: groupe Pass soirée introuvable')
            continue

        # 1) Le lien doit être neutralisé avant de finaliser l'expiration.
        link_secure=True
        if invite_link:
            try:
                await bot.revoke_chat_invite_link(gid, invite_link)
            except Exception as exc:
                if _revocation_error_means_already_closed(exc):
                    link_secure=True
                else:
                    link_secure=False
                    failed.append(f'{user_id}: révocation lien impossible ({type(exc).__name__})')
                    await log_error('pass_soiree_revoke',exc)

        # 2) Vérification réelle de présence + retrait si nécessaire.
        absent=False
        try:
            member=await bot.get_chat_member(gid, user_id)
            status=_chat_member_status(member)
            if status in ('left','kicked'):
                absent=True
                already_absent += 1
            else:
                try:
                    await bot.ban_chat_member(gid, user_id, revoke_messages=False)
                    await bot.unban_chat_member(gid, user_id, only_if_banned=True)
                    await asyncio.sleep(0.35)
                    check=await bot.get_chat_member(gid, user_id)
                    check_status=_chat_member_status(check)
                    absent=check_status in ('left','kicked')
                    if absent:
                        removed += 1
                    else:
                        failed.append(f'{user_id}: encore membre après retrait ({check_status or "inconnu"})')
                except Exception as exc:
                    failed.append(f'{user_id}: retrait impossible ({type(exc).__name__})')
                    await log_error('pass_soiree_kick',exc)
        except Exception as exc:
            failed.append(f'{user_id}: vérification membre impossible ({type(exc).__name__})')
            await log_error('pass_soiree_member_check',exc)

        if not (link_secure and absent):
            # Surtout ne pas passer expired : le scheduler doit retenter.
            continue

        async with SessionLocal() as db:
            a=await db.get(VipAccess, aid)
            if not a or a.status!='active':
                continue
            a.status='expired'
            await db.commit()
        expired += 1
        try:
            await _send_pass_soiree_expired_offer(bot, user_id)
        except Exception as exc:
            await log_error('pass_soiree_upsell',exc)

    await st.set_value('last_pass_soiree_expire_at', datetime.utcnow().isoformat(timespec='seconds'))
    await st.set_value(
        'last_pass_soiree_expire_result',
        f'due={len(ids)};expired={expired};removed={removed};already_absent={already_absent};failed={len(failed)}'
    )
    if ids or failed:
        lines=[
            '🎟 EXPIRATION PASS SOIRÉE',
            '',
            f'À traiter : {len(ids)}',
            f'✅ Accès sécurisés/expirés : {expired}',
            f'🚪 Membres réellement retirés : {removed}',
            f'ℹ️ Déjà absents : {already_absent}',
            f'🔴 Échecs à retenter : {len(failed)}',
            '',
            'Médias conservés.',
        ]
        if failed:
            lines += ['', 'Premiers échecs :'] + [f'• {x[:180]}' for x in failed[:8]]
        await notify_admins(bot, '\n'.join(lines))
    return {'due':len(ids),'expired':expired,'removed':removed,'already_absent':already_absent,'failed':len(failed)}

async def _test_one_vip_invite_link(bot:Bot, offer:str) -> tuple[bool,str]:
    """Test réel : accès + création + révocation d'un lien d'invitation."""
    gid=await _group_for_offer(offer, include_unavailable=True)
    if not gid:
        return False, 'groupe non configuré'
    link=''
    try:
        me=await bot.get_me()
        member=await bot.get_chat_member(gid, me.id)
        status=str(getattr(getattr(member,'status',''),'value',getattr(member,'status','')) or '').lower()
        if status not in ('administrator','creator'):
            return False, 'bot non administrateur'
        if status=='administrator' and not bool(getattr(member,'can_invite_users',False)):
            return False, 'droit Inviter des utilisateurs manquant'
        if offer=='soiree' and status=='administrator' and not bool(getattr(member,'can_restrict_members',False)):
            return False, 'droit Bannir/retirer des membres manquant'
        created=await bot.create_chat_invite_link(gid, member_limit=1, name='healthcheck-auto')
        link=created.invite_link
        await bot.revoke_chat_invite_link(gid, link)
        detail='création + révocation OK'
        if offer=='soiree':
            detail += ' + droit retrait OK'
        return True, detail
    except Exception as exc:
        if link:
            try:
                await bot.revoke_chat_invite_link(gid, link)
            except Exception:
                pass
        return False, f'{type(exc).__name__}: {exc}'


async def vip_link_test_report(bot:Bot, *, notify:bool=False) -> str:
    labels={'soiree':'🌙 Pass soirée','total':'📦 Pass total','javana':'💎 VIP JAVANA'}
    lines=['🔗 TEST LIENS VIP','']
    all_ok=True
    for offer in ('soiree','total','javana'):
        ok,detail=await _test_one_vip_invite_link(bot, offer)
        all_ok = all_ok and ok
        await st.set_value(f'vip_link_test:{offer}:ok','true' if ok else 'false')
        await st.set_value(f'vip_link_test:{offer}:detail',detail[:500])
        lines.append(f'{labels[offer]} : {"✅" if ok else "❌"} {detail}')
    now=datetime.utcnow().isoformat(timespec='seconds')
    await st.set_value('vip_link_test_last_at', now)
    lines += ['', '🟢 Tous les liens sont créables.' if all_ok else '🔴 Au moins un VIP ne peut pas créer de lien.']
    report='\n'.join(lines)
    if notify:
        await notify_admins(bot, report)
    return report


async def daily_vip_link_test(bot:Bot):
    return await vip_link_test_report(bot, notify=True)


async def vip_health_text():
    last=await st.get_value('last_vip_sent_at','jamais')
    mid=await st.get_value('last_vip_message_id','-')
    image='oui' if await st.get_value('vip_image_file_id','') else 'non'
    release=await st.get_value('last_pass_soiree_release_at','jamais')
    expire=await st.get_value('last_pass_soiree_expire_at','jamais')
    state='ouvert' if await st.is_open() else 'fermé'
    repost=(await st.get_value('vip_repost_enabled','true'))=='true'
    async with SessionLocal() as db:
        pending=(await db.execute(select(VipAccess).where(VipAccess.offer=='soiree', VipAccess.status=='pending'))).scalars().all()
        active=(await db.execute(select(VipAccess).where(VipAccess.offer=='soiree', VipAccess.status=='active'))).scalars().all()
        pc=len(list(pending)); ac=len(list(active))
    link_lines=[]
    for offer,label in [('soiree','Pass soirée'),('total','Pass total'),('javana','VIP JAVANA')]:
        raw=await st.get_value(f'vip_link_test:{offer}:ok','')
        symbol='✅' if raw=='true' else ('❌' if raw=='false' else '⚪')
        link_lines.append(f'{label} lien : {symbol}')
    return (
        f'💎 VIP\n\nGroupe principal : {state}\n'
        f'Repost médias vers VIP : {"✅ ON" if repost else "⛔ OFF"}\n'
        f'Dernier repost VIP : {await st.get_value("vip_repost_last_at","jamais")}\n'
        f'Résultat : {await st.get_value("vip_repost_last_result","-")}\n\n'
        f'Image principale configurée : {image}\nDernier envoi pub VIP : {last}\nDernier message ID : {mid}\n'
        f'Prix : soirée {await offer_price("soiree")}€ / total {await offer_price("total")}€ / JAVANA {await offer_price("javana")}€\n\n'
        f'Pass soirée :\nEn attente : {pc}\nActifs : {ac}\nCycle payant : expiration à 06h00\nDernier envoi liens : {release}\nDernière expiration : {expire}\nRésultat expiration : {await st.get_value("last_pass_soiree_expire_result","-")}\n\n'
        f'Test liens (dernier : {await st.get_value("vip_link_test_last_at","jamais")})\n' + '\n'.join(link_lines)
    )
