from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from app.config import get_settings
from app.keyboards.common import admin_kb, pay_kb
from app.services import settings as st
from app.services.session_ops import set_group_open, cleanup_session, notify_admins
from app.services.state import ensure_status_message
from app.services.health import health_text
from app.services.vip import send_vip_ad
from app.services.crowdfunding import send_crowd_ad, validate_crowd
from app.services.invites import top_text
from app.services.vip import validate_vip
router=Router()

def is_admin(uid:int): return uid in get_settings().admin_ids
@router.message(CommandStart())
async def start(msg:Message):
    if msg.chat.type=='private' and msg.from_user and is_admin(msg.from_user.id):
        await msg.answer('Panel admin',reply_markup=admin_kb())
    elif msg.chat.type=='private':
        await msg.answer('Bot actif.')
@router.callback_query(F.data.startswith('adm_'))
async def admin_cb(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): await cb.answer('Accès refusé',show_alert=True); return
    d=cb.data
    if d=='adm_dashboard': await cb.message.answer('📊 Tableau de bord',reply_markup=admin_kb())
    elif d=='adm_health': await cb.message.answer(await health_text(bot))
    elif d=='adm_open': await set_group_open(bot,True,'manual'); await cb.message.answer('Groupe ouvert manuellement.')
    elif d=='adm_close': await set_group_open(bot,False,'manual'); await cb.message.answer('Groupe fermé manuellement.')
    elif d=='adm_auto':
        cur=await st.auto_enabled(); await st.set_value('auto_enabled','false' if cur else 'true'); await ensure_status_message(bot,get_settings().main_group_id); await cb.message.answer(f'Auto: {"OFF" if cur else "ON"}')
    elif d=='adm_goal': await cb.message.answer(f'Objectif actuel: {await st.vote_goal()}\nPour modifier: /objectif 150')
    elif d=='adm_justice': await cb.message.answer('⚖️ Justice populaire: déclenchement à 50% de session. Bouton manuel: /justice')
    elif d=='adm_cleanup': await cleanup_session(bot); await cb.message.answer('Nettoyage relancé.')
    elif d=='adm_suspects': await cb.message.answer('🕵️ Suspects\n/supprimer_suspects80\n/supprimer_suspects100\nLes admins/trusted sont protégés.')
    elif d=='adm_vip': await cb.message.answer('💎 VIP\n/envoyer_vip pour envoyer la pub VIP dans le groupe.\nLes paiements sont gérés en PV.')
    elif d=='adm_crowd': await cb.message.answer('💰 Crowdfunding\n/envoyer_crowdfunding pour envoyer le message.\nLes paiements + captures sont validés par admin.')
    elif d=='adm_ads': await cb.message.answer('📢 Publicités\n/pub Texte pour définir. /envoyer_pub pour envoyer.')
    elif d=='adm_invites': await cb.message.answer('🎁 Invitations: validation après 5 min, paliers GoFile configurables à ajouter via /palier.')
    elif d=='adm_top': await cb.message.answer(await top_text())
    elif d=='adm_mod': await cb.message.answer('🛡️ Modération\n/motinterdit mot\n/motban mot\n/nomban mot')
    elif d=='adm_rules': await cb.message.answer('📜 Règles\n/regles votre texte')
    elif d=='adm_pardon_ban': await cb.message.answer('👑 Grâce présidentielle enregistrée. Déban massif dépend des utilisateurs bannis connus.')
    elif d=='adm_pardon_mute': await cb.message.answer('⚖️ Grâce ministérielle enregistrée. Restrictions connues levées au prochain passage.')
    elif d=='adm_reports': await cb.message.answer('📊 Les rapports sont envoyés automatiquement à chaque fermeture.')
    elif d=='adm_settings': await cb.message.answer('⚙️ Paramètres\n/horaire 22:30-00:45\n/objectif 120')
    await cb.answer()
@router.message(F.text.startswith('/objectif'))
async def set_goal(msg:Message):
    if not msg.from_user or not is_admin(msg.from_user.id): return
    n=''.join(x for x in msg.text if x.isdigit())
    if n: await st.set_value('vote_goal',n); await msg.answer(f'Objectif défini: {n}')
@router.message(F.text.startswith('/horaire'))
async def set_slot(msg:Message):
    if not msg.from_user or not is_admin(msg.from_user.id): return
    if await st.is_open(): await msg.answer('Impossible pendant session active. Ancien paramètre conservé.'); return
    parts=msg.text.split(maxsplit=1)
    if len(parts)>1 and parts[1] in ['22:30-00:45','22:00-00:00','23:00-01:00']:
        await st.set_value('time_slot',parts[1]); await msg.answer('Horaire modifié.')
    else: await msg.answer('Créneaux: 22:30-00:45, 22:00-00:00, 23:00-01:00')
@router.message(F.text.startswith('/envoyer_vip'))
async def manual_vip(msg:Message,bot:Bot):
    if msg.from_user and is_admin(msg.from_user.id): await send_vip_ad(bot); await msg.answer('VIP envoyé.')
@router.message(F.text.startswith('/envoyer_crowdfunding'))
async def manual_crowd(msg:Message,bot:Bot):
    if msg.from_user and is_admin(msg.from_user.id): await send_crowd_ad(bot); await msg.answer('Crowdfunding envoyé.')
@router.message(F.text.startswith('/pub'))
async def set_pub(msg:Message,bot:Bot):
    if not msg.from_user or not is_admin(msg.from_user.id): return
    txt=msg.text.replace('/pub','',1).strip()
    if txt: await st.set_value('ads_text',txt); await msg.answer('Pub sauvegardée.')
@router.message(F.text.startswith('/envoyer_pub'))
async def send_pub(msg:Message,bot:Bot):
    if msg.from_user and is_admin(msg.from_user.id):
        m=await bot.send_message(get_settings().main_group_id, await st.get_value('ads_text','📢 Publicité'))
        await msg.answer('Pub envoyée.')
@router.message(F.text.startswith('/regles'))
async def set_rules(msg:Message):
    if msg.from_user and is_admin(msg.from_user.id): await st.set_value('rules_text',msg.text.replace('/regles','',1).strip()); await msg.answer('Règles sauvegardées.')
@router.callback_query(F.data.startswith('validate:') | F.data.startswith('reject:'))
async def validate(cb:CallbackQuery,bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    action,kind,id_s=cb.data.split(':'); ok=action=='validate'; oid=int(id_s)
    if kind=='vip': await validate_vip(bot,oid,ok)
    if kind=='crowd': await validate_crowd(bot,oid,ok)
    await cb.message.answer('Action exécutée.'); await cb.answer()
