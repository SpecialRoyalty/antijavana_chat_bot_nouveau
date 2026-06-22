from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from app.config import get_settings
from app.keyboards.common import admin_kb, goal_kb, settings_kb, justice_kb, cleanup_kb, mod_kb, crowd_admin_kb, ads_admin_kb, confirm_kb, back_kb
from app.services import settings as st
from app.services.session_ops import set_group_open, cleanup_session, count_known_bans_and_restrictions, presidential_pardon, ministerial_pardon
from app.services.state import ensure_status_message
from app.services.health import health_text
from app.services.vip import send_vip_ad, validate_vip
from app.services.crowdfunding import send_crowd_ad, validate_crowd, set_campaign_text, set_campaign_target, set_campaign_image, stats_text
from app.services.invites import top_text
from app.services.ads import add_ad, send_random_ad, list_ads_text
from app.db.session import SessionLocal
from app.db.models import WordRule
router=Router()

def is_admin(uid:int): return uid in get_settings().admin_ids
async def set_admin_state(uid:int,state:str): await st.set_value(f'admin_state:{uid}',state)
async def get_admin_state(uid:int): return await st.get_value(f'admin_state:{uid}','')
async def clear_admin_state(uid:int): await st.set_value(f'admin_state:{uid}','')

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
    if d=='adm_dashboard': await cb.message.answer('📊 Panel admin',reply_markup=admin_kb())
    elif d=='adm_health': await cb.message.answer(await health_text(bot))
    elif d=='adm_open': await set_group_open(bot,True,'manual'); await cb.message.answer('🟢 Groupe ouvert manuellement.')
    elif d=='adm_close': await set_group_open(bot,False,'manual'); await cb.message.answer('🔴 Groupe fermé manuellement.')
    elif d=='adm_auto':
        cur=await st.auto_enabled(); await st.set_value('auto_enabled','false' if cur else 'true'); await ensure_status_message(bot,get_settings().main_group_id); await cb.message.answer(f'⏰ Horaire auto : {"OFF" if cur else "ON"}',reply_markup=admin_kb())
    elif d=='adm_goal': await cb.message.answer(f'📦 Objectif actuel : {await st.vote_goal()}\nChoisis un objectif ou personnalisé.',reply_markup=goal_kb())
    elif d=='adm_justice': await cb.message.answer('⚖️ Justice populaire\n\nAutomatique : 50% de la session.\nTu peux aussi lancer un test manuel.',reply_markup=justice_kb())
    elif d=='adm_cleanup': await cb.message.answer('🧹 Nettoyage\n\nSi les médias ne se suppriment pas, vérifie que le bot est admin avec droit de suppression.',reply_markup=cleanup_kb())
    elif d=='adm_suspects': await cb.message.answer('🕵️ Comptes suspects\n\nScore 50+ visible admin\n80+ invitation en attente\n100+ rejetée\n\nBoutons de suppression par score à ajouter après volume réel.',reply_markup=back_kb())
    elif d=='adm_vip': await cb.message.answer('💎 VIP\n\nBoutons groupe : 🎟 Pass soirée / 📦 Pass total / 💎 JAVANA.\nClic = privé. Paiement + capture = validation admin.\n\nAction :',reply_markup=__import__('aiogram').types.InlineKeyboardMarkup(inline_keyboard=[[__import__('aiogram').types.InlineKeyboardButton(text='📤 Envoyer pub VIP',callback_data='vip_send')],[__import__('aiogram').types.InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]]))
    elif d=='adm_crowd': await cb.message.answer('💰 Crowdfunding',reply_markup=crowd_admin_kb())
    elif d=='adm_ads': await cb.message.answer('📢 Publicités',reply_markup=ads_admin_kb())
    elif d=='adm_invites': await cb.message.answer('🎁 Invitations\n\nValidation après 5 min, paliers GoFile, compteurs séparés total/récompense.\nConfiguration avancée à finaliser selon tes liens GoFile.',reply_markup=back_kb())
    elif d=='adm_top': await cb.message.answer(await top_text())
    elif d=='adm_mod': await cb.message.answer('🛡️ Modération\nAjoute les mots via boutons, sans commandes.',reply_markup=mod_kb())
    elif d=='adm_rules': await cb.message.answer('📜 Envoie maintenant le texte des règles.',reply_markup=back_kb()); await set_admin_state(cb.from_user.id,'rules_text')
    elif d=='adm_pardon_ban':
        b,r=await count_known_bans_and_restrictions(); await cb.message.answer(f'👑 Grâce présidentielle\n\nBannis connus concernés : {b}\n\nConfirmer le déban massif ?',reply_markup=confirm_kb('pardon_ban'))
    elif d=='adm_pardon_mute':
        b,r=await count_known_bans_and_restrictions(); await cb.message.answer(f'⚖️ Grâce ministérielle\n\nRestrictions connues concernées : {r}\n\nConfirmer la levée des restrictions ?',reply_markup=confirm_kb('pardon_mute'))
    elif d=='adm_reports': await cb.message.answer('📊 Les rapports sont envoyés automatiquement à chaque fermeture, avec actions trusted et inactifs.',reply_markup=back_kb())
    elif d=='adm_settings': await cb.message.answer('⚙️ Paramètres horaires\nChangement autorisé uniquement hors session active.',reply_markup=settings_kb())
    await cb.answer()

@router.callback_query(F.data.startswith('goal_set:'))
async def cb_goal_set(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    n=int(cb.data.split(':')[1]); await st.set_value('vote_goal',str(n)); await ensure_status_message(bot,get_settings().main_group_id)
    await cb.message.answer(f'✅ Objectif défini : {n}',reply_markup=admin_kb()); await cb.answer()

@router.callback_query(F.data.startswith('slot_set:'))
async def cb_slot(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    if await st.is_open(): await cb.answer('Impossible pendant session active',show_alert=True); return
    slot=cb.data.split(':',1)[1]
    await st.set_value('time_slot',slot); await ensure_status_message(bot,get_settings().main_group_id)
    await cb.message.answer(f'✅ Horaire défini : {slot}',reply_markup=admin_kb()); await cb.answer()

@router.callback_query(F.data.startswith('await:'))
async def await_input(cb:CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    state=cb.data.split(':',1)[1]; await set_admin_state(cb.from_user.id,state)
    prompts={
        'goal':'Envoie le nouvel objectif en nombre.',
        'forbidden':'Envoie le mot interdit à ajouter.',
        'banword':'Envoie le mot BAN à ajouter.',
        'nameban':'Envoie le mot interdit dans les noms.',
        'crowd_text':'Envoie le texte crowdfunding.',
        'crowd_target':'Envoie le montant objectif crowdfunding.',
        'crowd_image':'Envoie l’image crowdfunding.',
        'ad_text':'Envoie le texte de la publicité.',
        'ad_image':'Envoie l’image de la publicité avec texte en légende si besoin.',
    }
    await cb.message.answer('✍️ '+prompts.get(state,'Envoie la valeur.'))
    await cb.answer()

@router.callback_query(F.data=='cleanup_active')
async def cb_cleanup_active(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    d,f=await cleanup_session(bot,all_known=False); await cb.message.answer(f'🧹 Nettoyage session terminé.\nSupprimés : {d}\nÉchecs : {f}'); await cb.answer()
@router.callback_query(F.data=='cleanup_all')
async def cb_cleanup_all(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    d,f=await cleanup_session(bot,all_known=True); await cb.message.answer(f'🧹 Nettoyage global suivi terminé.\nSupprimés : {d}\nÉchecs : {f}'); await cb.answer()
@router.callback_query(F.data=='vip_send')
async def cb_vip_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id): await send_vip_ad(bot); await cb.message.answer('💎 Pub VIP envoyée si groupe ouvert.'); await cb.answer()
@router.callback_query(F.data=='crowd_send')
async def cb_crowd_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id): await send_crowd_ad(bot); await cb.message.answer('💰 Crowdfunding envoyé si groupe ouvert.'); await cb.answer()
@router.callback_query(F.data=='crowd_stats')
async def cb_crowd_stats(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await stats_text()); await cb.answer()
@router.callback_query(F.data=='ad_send')
async def cb_ad_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        mid=await send_random_ad(bot); await cb.message.answer('📢 Pub envoyée.' if mid else 'Aucune pub active ou groupe fermé.'); await cb.answer()
@router.callback_query(F.data=='ad_list')
async def cb_ad_list(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await list_ads_text()); await cb.answer()
@router.callback_query(F.data=='mod_lists')
async def cb_mod_lists(cb:CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    async with SessionLocal() as db:
        res=await db.execute(select(WordRule)); rows=list(res.scalars().all())
    text='🛡️ Listes modération\n\n'+'\n'.join([f'{r.kind}: {r.word}' for r in rows[-80:]]) if rows else 'Aucun mot configuré.'
    await cb.message.answer(text); await cb.answer()
@router.callback_query(F.data.startswith('confirm:'))
async def cb_confirm(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    action=cb.data.split(':',1)[1]
    if action=='pardon_ban': n=await presidential_pardon(bot); await cb.message.answer(f'👑 Grâce présidentielle exécutée.\nBannis débannis : {n}')
    elif action=='pardon_mute': n=await ministerial_pardon(bot); await cb.message.answer(f'⚖️ Grâce ministérielle exécutée.\nRestrictions levées : {n}')
    await cb.answer()

@router.message(F.chat.type=='private')
async def admin_text_state(msg:Message, bot:Bot):
    if not msg.from_user or not is_admin(msg.from_user.id): return
    state=await get_admin_state(msg.from_user.id)
    if not state: return
    if state=='goal':
        n=int(''.join(x for x in (msg.text or '') if x.isdigit()) or '0')
        if n>0: await st.set_value('vote_goal',str(n)); await ensure_status_message(bot,get_settings().main_group_id); await msg.answer(f'✅ Objectif défini : {n}',reply_markup=admin_kb())
    elif state in ['forbidden','banword','nameban']:
        kind={'forbidden':'forbidden','banword':'ban','nameban':'nameban'}[state]
        word=(msg.text or '').strip().lower()
        if word:
            async with SessionLocal() as db: db.add(WordRule(kind=kind,word=word)); await db.commit()
            await msg.answer(f'✅ Ajouté dans {kind}: {word}',reply_markup=mod_kb())
    elif state=='rules_text':
        await st.set_value('rules_text',msg.text or ''); await msg.answer('✅ Règles sauvegardées.',reply_markup=admin_kb())
    elif state=='crowd_text':
        await set_campaign_text(msg.text or ''); await msg.answer('✅ Texte crowdfunding sauvegardé.',reply_markup=crowd_admin_kb())
    elif state=='crowd_target':
        n=int(''.join(x for x in (msg.text or '') if x.isdigit()) or '0'); await set_campaign_target(n); await msg.answer(f'✅ Objectif crowdfunding : {n}€',reply_markup=crowd_admin_kb())
    elif state=='crowd_image':
        if msg.photo: await set_campaign_image(msg.photo[-1].file_id); await msg.answer('✅ Image crowdfunding sauvegardée.',reply_markup=crowd_admin_kb())
        else: await msg.answer('Envoie une image.') ; return
    elif state=='ad_text':
        await add_ad(text=msg.text or ''); await msg.answer('✅ Publicité texte ajoutée.',reply_markup=ads_admin_kb())
    elif state=='ad_image':
        if msg.photo: await add_ad(text=msg.caption or '',image_file_id=msg.photo[-1].file_id); await msg.answer('✅ Publicité image ajoutée.',reply_markup=ads_admin_kb())
        else: await msg.answer('Envoie une image.') ; return
    await clear_admin_state(msg.from_user.id)


@router.callback_query(F.data=='manual_keep_open')
async def cb_manual_keep(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        from datetime import datetime
        await st.set_value('manual_opened_at',datetime.utcnow().isoformat())
        await st.set_value('manual_security_warned_at','')
        await cb.message.answer('✅ Le groupe reste ouvert. Nouveau contrôle dans 2h.')
        await cb.answer()

@router.callback_query(F.data=='manual_security_close')
async def cb_manual_security_close(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        await set_group_open(bot,False,'security')
        await cb.message.answer('🔒 Fermeture de sécurité exécutée.')
        await cb.answer()

@router.callback_query(F.data=='justice_status')
async def cb_justice_status(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        await cb.message.answer('⚖️ Justice automatique : active à 50% de la session.\nSuppression max : 20 inactifs connus.\nLes inactifs sont calculés par sessions accessibles.')
        await cb.answer()

@router.callback_query(F.data=='justice_run')
async def cb_justice_run(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        from app.scheduler import run_justice_now
        await run_justice_now(bot)
        await cb.message.answer('⚖️ Justice lancée manuellement.')
        await cb.answer()

@router.callback_query(F.data.startswith('validate:') | F.data.startswith('reject:'))
async def validate(cb:CallbackQuery,bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    action,kind,id_s=cb.data.split(':'); ok=action=='validate'; oid=int(id_s)
    if kind=='vip': await validate_vip(bot,oid,ok)
    if kind=='crowd': await validate_crowd(bot,oid,ok)
    await cb.message.answer('Action exécutée.'); await cb.answer()
