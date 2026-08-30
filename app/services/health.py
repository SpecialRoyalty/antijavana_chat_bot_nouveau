from sqlalchemy import select, func
from aiogram import Bot

from app.db.session import SessionLocal
from app.db.models import (
    ErrorLog, TrackedMessage, User, VipOrder, ManagedChat, GlobalSanction,
    InviteOwner, InviteCredit,
)
from app.services import settings as st
from app.utils.time import mid_time, slot_times, next_open_text, next_status_update_text
from app.services.freepass import places as freepass_places, remaining_places, is_locked as freepass_locked, published_session_key
from app.services.justice import candidate_count
from app.services.hashban import hashban_health_text
from app.services.anti_fast_join import health_text as anti_fast_join_health_text
from app.services.anti_repost import health_text as anti_repost_health_text
from app.services.multigroup import active_group_or_none_text


async def health_text(bot:Bot):
    from app.config import get_settings
    s=get_settings(); slot=await st.time_slot(); _start,end=slot_times(slot,s.timezone)
    async with SessionLocal() as db:
        errors=int((await db.execute(select(func.count(ErrorLog.id)))).scalar() or 0)
        tracked=int((await db.execute(select(func.count(TrackedMessage.id)).where(TrackedMessage.deleted==False))).scalar() or 0)
        suspects=int((await db.execute(select(func.count(User.id)).where(User.suspect_score>=50))).scalar() or 0)
        vip_pending=int((await db.execute(select(func.count(VipOrder.id)).where(VipOrder.status=='pending'))).scalar() or 0)
        chats=list((await db.execute(select(ManagedChat).order_by(ManagedChat.role))).scalars().all())
        bans=int((await db.execute(select(func.count(GlobalSanction.id)).where(GlobalSanction.kind=='ban',GlobalSanction.active==True))).scalar() or 0)
        mutes=int((await db.execute(select(func.count(GlobalSanction.id)).where(GlobalSanction.kind=='mute',GlobalSanction.active==True))).scalar() or 0)
        invite_links=int((await db.execute(select(func.count(InviteOwner.owner_id)).where(InviteOwner.active==True))).scalar() or 0)
        invite_pending=int((await db.execute(select(func.count(InviteCredit.invited_user_id)).where(InviteCredit.status=='pending'))).scalar() or 0)

    labels={
        'group_a':'🅰️ Groupe A','group_b':'🅱️ Groupe B','vip_soiree':'🌙 Pass soirée',
        'vip_total':'📦 Pass total','vip_javana':'💎 VIP JAVANA','logs':'🧾 Logs','pending':'⏳ En attente',
    }
    group_lines=[]
    for row in chats:
        if row.role in ('refused','unassigned'):
            continue
        icon='🟢' if row.status=='active' else ('🟠' if row.status=='degraded' else ('🔴' if row.status=='unavailable' else '⚪'))
        group_lines.append(f'{labels.get(row.role,row.role)} : {icon} {row.status} — {row.chat_id}')
    if not group_lines:
        group_lines=['Aucun chat validé.']

    suspended=(await st.get_value('session_suspended','false'))=='true'
    return f'''❤️ SANTÉ GLOBALE

Bot: OK
PostgreSQL: OK
Scheduler: OK

🌙 Pilotage
Ce soir: {await active_group_or_none_text()}
Session ouverte: {'OUI' if await st.is_open() else 'NON'}
Session suspendue: {'OUI' if suspended else 'NON'}
Auto: {'ON' if await st.auto_enabled() else 'OFF'}
Créneau: {slot}
Prochaine ouverture: {next_open_text(slot,s.timezone)}
Prochaine justice: {mid_time(slot,s.timezone).strftime('%H:%M')}
Limite justice: {await st.justice_limit()}
Justifiables: {await candidate_count()}
Prochaine fermeture: {end.strftime('%H:%M')}

🧩 Groupes / VIP
{chr(10).join(group_lines)}

🌍 Sanctions globales
Bans actifs: {bans}
Mutes actifs: {mutes}

🎁 Invitations
Liens actifs: {invite_links}
Validations en attente: {invite_pending}
Dernier TOP: {await st.get_value('last_top_sent_at','jamais')}

Contrôles:
Messages suivis non supprimés: {tracked}
Comptes suspects: {suspects}
Paiements VIP en attente: {vip_pending}
Erreurs loggées: {errors}

{await hashban_health_text()}

{await anti_fast_join_health_text()}

{await anti_repost_health_text()}

Diffusions centrales:
Publicité — dernier envoi: {await st.get_value('last_ad_sent_at','jamais')}
Crowdfunding — dernier envoi: {await st.get_value('last_crowd_sent_at','jamais')}
VIP — dernier envoi: {await st.get_value('last_vip_sent_at','jamais')}
Règles — dernier envoi: {await st.get_value('last_rules_sent_at','jamais')}
Pass gratuit — campagne: {await published_session_key() or 'non publiée'} — verrou: {'OUI' if await freepass_locked() else 'NON'} — places restantes: {await remaining_places()} / {await freepass_places()}
'''
