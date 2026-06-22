from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy import select
from app.config import get_settings
from app.keyboards.common import admin_kb, goal_kb, settings_kb, justice_kb, cleanup_kb, mod_kb, crowd_admin_kb, ads_admin_kb, confirm_kb, back_kb, rules_admin_kb, hashban_kb, vip_admin_kb, top_admin_kb, invite_admin_kb
from app.services import settings as st
from app.services.session_ops import set_group_open, cleanup_session, count_known_bans_and_restrictions, presidential_pardon, ministerial_pardon
from app.services.state import ensure_status_message
from app.services.health import health_text
from app.services.vip import send_vip_ad, validate_vip, vip_health_text, send_vip_private, handle_vip_proof
from app.services.crowdfunding import send_crowd_ad, validate_crowd, set_campaign_text, set_campaign_target, set_campaign_image, stats_text, crowd_health_text, create_campaign, campaigns_text, set_active_campaign, start_crowd_private, campaigns_kb, campaign_detail, toggle_campaign, delete_campaign, handle_crowd_text, handle_crowd_proof, send_campaign_by_id
from app.services.invites import top_text, send_invite_ad, invite_health_text, tiers_text, set_tiers_from_text, send_invite_private
from app.services.ads import add_ad, send_random_ad, list_ads_text, ads_health_text, ads_list_kb, ad_detail, toggle_ad, delete_ad, set_ad_text, set_ad_image, send_ad_by_id
from app.db.session import SessionLocal
from app.db.models import WordRule
from app.services.justice import justice_preview_text, execute_justice
import asyncio
from aiogram.exceptions import TelegramBadRequest
from app.services.hashban import ban_hash_from_message, banned_hash_count
router=Router()

def is_admin(uid:int): return uid in get_settings().admin_ids
async def set_admin_state(uid:int,state:str): await st.set_value(f'admin_state:{uid}',state)
async def get_admin_state(uid:int): return await st.get_value(f'admin_state:{uid}','')
async def clear_admin_state(uid:int): await st.set_value(f'admin_state:{uid}','')

@router.message(CommandStart())
async def start(msg:Message, bot:Bot):
    arg=''
    if msg.text and len(msg.text.split(maxsplit=1))>1:
        arg=msg.text.split(maxsplit=1)[1].strip()
    if msg.chat.type=='private' and msg.from_user:
        if arg.startswith('vip_'):
            offer=arg.split('_',1)[1]
            await send_vip_private(bot, msg.from_user.id, offer if offer in ['soiree','total','javana'] else None)
            return
        if arg=='crowd':
            await start_crowd_private(bot, msg.from_user.id)
            return
        if arg=='invite':
            await send_invite_private(bot, msg.from_user.id)
            return
        if is_admin(msg.from_user.id):
            await msg.answer('Panel admin',reply_markup=admin_kb())
        else:
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
    elif d=='adm_justice': await cb.message.answer('⚖️ Justice populaire\n\nAutomatique : 50% de la session.\nTest manuel disponible avec prévisualisation.',reply_markup=justice_kb())
    elif d=='adm_cleanup': await cb.message.answer('🧹 Nettoyage\n\nSi les médias ne se suppriment pas, vérifie que le bot est admin avec droit de suppression.',reply_markup=cleanup_kb())
    elif d=='adm_suspects': await cb.message.answer('🕵️ Comptes suspects\n\nScore 50+ visible admin\n80+ invitation en attente\n100+ rejetée\n\nBoutons de suppression par score à ajouter après volume réel.',reply_markup=back_kb())
    elif d=='adm_vip': await cb.message.answer('💎 VIP\n\nPublication manuelle pour test + suivi santé.',reply_markup=vip_admin_kb())
    elif d=='adm_crowd': await cb.message.answer('💰 Crowdfunding',reply_markup=crowd_admin_kb())
    elif d=='adm_ads': await cb.message.answer('📢 Publicités',reply_markup=ads_admin_kb())
    elif d=='adm_invites': await cb.message.answer('🎁 Invitations\n\nTexte + image + bouton Recevoir vidéos. Validation après 5 min, paliers GoFile, compteurs total/récompense.',reply_markup=invite_admin_kb())
    elif d=='adm_top': await cb.message.answer(await top_text(), reply_markup=top_admin_kb())
    elif d=='adm_mod': await cb.message.answer('🛡️ Modération\nAjoute les mots via boutons, sans commandes.',reply_markup=mod_kb())
    elif d=='adm_rules': await cb.message.answer('📜 Règles\n\nTu peux publier maintenant ou modifier le texte.',reply_markup=rules_admin_kb())
    elif d=='adm_pardon_ban':
        b,r=await count_known_bans_and_restrictions(); await cb.message.answer(f'👑 Grâce présidentielle\n\nBannis connus concernés : {b}\n\nConfirmer le déban massif ?',reply_markup=confirm_kb('pardon_ban'))
    elif d=='adm_pardon_mute':
        b,r=await count_known_bans_and_restrictions(); await cb.message.answer(f'⚖️ Grâce ministérielle\n\nRestrictions connues concernées : {r}\n\nConfirmer la levée des restrictions ?',reply_markup=confirm_kb('pardon_mute'))
    elif d=='adm_reports': await cb.message.answer('📊 Les rapports sont envoyés automatiquement à chaque fermeture, avec actions trusted et inactifs.',reply_markup=back_kb())
    elif d=='adm_hashban': await cb.message.answer('🚫 Hash ban\n\nEnvoie un média en privé pour l’ajouter aux hashes bannis.',reply_markup=hashban_kb())
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
        'vip_text':'Envoie le texte principal du message VIP.',
        'vip_image':'Envoie l’image principale du message VIP.',
        'vip_offer_text:soiree':'Envoie le texte détaillé du Pass soirée.',
        'vip_offer_text:total':'Envoie le texte détaillé du Pass total.',
        'vip_offer_text:javana':'Envoie le texte détaillé de COPIE 1:1 VIP JAVANA -50%.',
        'vip_price:soiree':'Envoie le prix du Pass soirée en nombre.',
        'vip_price:total':'Envoie le prix du Pass total en nombre.',
        'vip_price:javana':'Envoie le prix de COPIE 1:1 VIP JAVANA -50% en nombre.',
        'hash_ban_media':'Envoie le média à bannir par hash. Le bot l’ajoutera en amont.',
        'invite_text':'Envoie le texte du message invitations.',
        'invite_image':'Envoie l’image du message invitations.',
        'invite_tiers':'Envoie les paliers, une ligne par palier : 1|Label|Lien GoFile',
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
    if cb.from_user and is_admin(cb.from_user.id):
        mid=await send_vip_ad(bot, force=True)
        await cb.message.answer('💎 Pub VIP publiée maintenant.' if mid else '💎 VIP non publié : groupe fermé ou erreur.')
        await cb.answer()

@router.callback_query(F.data=='vip_health')
async def cb_vip_health(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await vip_health_text()); await cb.answer()
@router.callback_query(F.data=='crowd_send')
async def cb_crowd_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        mid=await send_crowd_ad(bot, force=True)
        await cb.message.answer('💰 Crowdfunding publié maintenant.' if mid else '💰 Crowdfunding non publié : groupe fermé ou erreur.')
        await cb.answer()

@router.callback_query(F.data=='crowd_health')
async def cb_crowd_health(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await crowd_health_text()); await cb.answer()

@router.callback_query(F.data=='crowd_new')
async def cb_crowd_new(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        ok,msg=await create_campaign()
        await cb.message.answer(msg, reply_markup=crowd_admin_kb())
        await cb.answer()

@router.callback_query(F.data=='crowd_list')
async def cb_crowd_list(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        await cb.message.answer(await campaigns_text(), reply_markup=await campaigns_kb())
        await cb.answer()

@router.callback_query(F.data.startswith('crowd_active:'))
async def cb_crowd_active(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        cid=int(cb.data.split(':')[1]); await set_active_campaign(cid)
        await cb.message.answer('✅ Campagne active changée.', reply_markup=crowd_admin_kb())
        await cb.answer()


@router.callback_query(F.data.startswith('crowd_manage:'))
async def cb_crowd_manage(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        cid=int(cb.data.split(':')[1]); txt,kb=await campaign_detail(cid)
        await cb.message.answer(txt, reply_markup=kb); await cb.answer()

@router.callback_query(F.data.startswith('crowd_toggle:'))
async def cb_crowd_toggle(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        cid=int(cb.data.split(':')[1]); await toggle_campaign(cid)
        txt,kb=await campaign_detail(cid)
        await cb.message.answer(txt, reply_markup=kb); await cb.answer()

@router.callback_query(F.data.startswith('crowd_delete:'))
async def cb_crowd_delete(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        cid=int(cb.data.split(':')[1]); ok=await delete_campaign(cid)
        await cb.message.answer('🗑 Campagne supprimée.' if ok else 'Campagne introuvable.', reply_markup=await campaigns_kb())
        await cb.answer()


@router.callback_query(F.data.startswith('crowd_send_one:'))
async def cb_crowd_send_one(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        cid=int(cb.data.split(':')[1])
        mid=await send_campaign_by_id(bot,cid,force=True)
        await cb.message.answer('💰 Campagne publiée maintenant.' if mid else 'Campagne introuvable ou erreur.')
        await cb.answer()

@router.callback_query(F.data=='crowd_stats')
async def cb_crowd_stats(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await stats_text()); await cb.answer()
@router.callback_query(F.data=='ad_send')
async def cb_ad_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        mid=await send_random_ad(bot); await cb.message.answer('📢 Pub envoyée.' if mid else 'Aucune pub active ou groupe fermé.'); await cb.answer()
@router.callback_query(F.data=='ad_health')
async def cb_ad_health(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await ads_health_text()); await cb.answer()

@router.callback_query(F.data=='ad_list')
async def cb_ad_list(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(await list_ads_text(), reply_markup=await ads_list_kb()); await cb.answer()

@router.callback_query(F.data.startswith('ad_manage:'))
async def cb_ad_manage(cb:CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    ad_id=int(cb.data.split(':')[1])
    txt,kb=await ad_detail(ad_id)
    await cb.message.answer(txt, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith('ad_send_one:'))
async def cb_ad_send_one(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    ad_id=int(cb.data.split(':')[1])
    mid=await send_ad_by_id(bot, ad_id, force=True)
    await cb.message.answer('📢 Pub publiée maintenant.' if mid else 'Pub introuvable ou erreur.')
    await cb.answer()

@router.callback_query(F.data.startswith('ad_toggle:'))
async def cb_ad_toggle(cb:CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    ad_id=int(cb.data.split(':')[1])
    ok=await toggle_ad(ad_id)
    txt,kb=await ad_detail(ad_id)
    await cb.message.answer(txt if ok else 'Pub introuvable.', reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith('ad_delete:'))
async def cb_ad_delete(cb:CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    ad_id=int(cb.data.split(':')[1])
    ok=await delete_ad(ad_id)
    await cb.message.answer('🗑 Pub supprimée.' if ok else 'Pub introuvable.', reply_markup=await ads_list_kb())
    await cb.answer()
@router.callback_query(F.data=='mod_lists')
async def cb_mod_lists(cb:CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    async with SessionLocal() as db:
        res=await db.execute(select(WordRule)); rows=list(res.scalars().all())
    text='🛡️ Listes modération\n\n'+'\n'.join([f'{r.kind}: {r.word}' for r in rows[-80:]]) if rows else 'Aucun mot configuré.'
    await cb.message.answer(text); await cb.answer()
@router.callback_query(F.data=='rules_send')
async def cb_rules_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        from app.scheduler import rules_tick
        await rules_tick(bot, force=True)
        await cb.message.answer('📜 Règles publiées maintenant.')
        await cb.answer()

@router.callback_query(F.data=='rules_health')
async def cb_rules_health(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        last=await st.get_value('last_rules_sent_at','jamais')
        await cb.message.answer(f'📜 Règles\n\nDernier envoi : {last}\nProchain envoi automatique : toutes les 30 min pendant ouverture.')
        await cb.answer()

@router.callback_query(F.data=='top_send')
async def cb_top_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        txt=await top_text()
        if 'Aucune statistique' in txt:
            await cb.message.answer('🏆 Top inviteurs vide. Rien publié dans le groupe.')
        else:
            m=await bot.send_message(get_settings().main_group_id, txt)
            await st.set_value('last_top_sent_at', __import__('datetime').datetime.utcnow().isoformat(timespec='seconds'))
            await cb.message.answer('🏆 Classement publié maintenant.')
        await cb.answer()

@router.callback_query(F.data=='top_health')
async def cb_top_health(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        await cb.message.answer('🏆 Top inviteurs\n\n' + await top_text() + '\n\nDernier envoi : ' + await st.get_value('last_top_sent_at','jamais'))
        await cb.answer()

@router.callback_query(F.data=='hashban_stats')
async def cb_hashban_stats(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id): await cb.message.answer(f'🚫 Hash bannis : {await banned_hash_count()}'); await cb.answer()

@router.callback_query(F.data.startswith('confirm:'))
async def cb_confirm(cb:CallbackQuery, bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    action=cb.data.split(':',1)[1]
    if action=='pardon_ban': n=await presidential_pardon(bot); await cb.message.answer(f'👑 Grâce présidentielle exécutée.\nBannis débannis : {n}')
    elif action=='pardon_mute': n=await ministerial_pardon(bot); await cb.message.answer(f'⚖️ Grâce ministérielle exécutée.\nRestrictions levées : {n}')
    elif action=='justice_run':
        try:
            await cb.answer('Justice lancée ✅')
        except TelegramBadRequest:
            pass
        await cb.message.answer('⚖️ Justice lancée. Le groupe sera bloqué 5 minutes.')
        asyncio.create_task(execute_justice(bot, manual=True))
        return
    try:
        await cb.answer()
    except TelegramBadRequest:
        pass

@router.message(F.chat.type=='private')
async def admin_text_state(msg:Message, bot:Bot):
    if not msg.from_user or not is_admin(msg.from_user.id): return
    # Priorité aux parcours utilisateur en cours, même si l'utilisateur est admin.
    # Sinon un ancien état admin peut bloquer crowdfunding/VIP.
    if await handle_crowd_text(msg): return
    if await handle_crowd_proof(bot,msg): return
    if await handle_vip_proof(bot,msg): return
    state=await get_admin_state(msg.from_user.id)
    if not state:
        return
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
    elif state.startswith('crowd_text'):
        cid=int(state.split(':')[1]) if ':' in state else None
        await set_campaign_text(msg.text or '', cid); await msg.answer('✅ Texte crowdfunding sauvegardé.',reply_markup=crowd_admin_kb())
    elif state.startswith('crowd_target'):
        cid=int(state.split(':')[1]) if ':' in state else None
        n=int(''.join(x for x in (msg.text or '') if x.isdigit()) or '0'); await set_campaign_target(n, cid); await msg.answer(f'✅ Objectif crowdfunding : {n}€',reply_markup=crowd_admin_kb())
    elif state.startswith('crowd_image'):
        cid=int(state.split(':')[1]) if ':' in state else None
        if msg.photo: await set_campaign_image(msg.photo[-1].file_id, cid); await msg.answer('✅ Image crowdfunding sauvegardée.',reply_markup=crowd_admin_kb())
        else: await msg.answer('Envoie une image.') ; return
    elif state.startswith('ad_edit_text:'):
        adid=int(state.split(':')[1])
        ok=await set_ad_text(adid, msg.text or '')
        await msg.answer('✅ Texte de la pub modifié.' if ok else 'Pub introuvable.', reply_markup=ads_admin_kb())
    elif state=='ad_text':
        adid=await add_ad(text=msg.text or '')
        await msg.answer('✅ Publicité texte ajoutée.' if adid!=-1 else 'Maximum 2 publicités configurées. Supprime une pub avant d’en ajouter une autre.',reply_markup=ads_admin_kb())
    elif state.startswith('ad_edit_image:'):
        adid=int(state.split(':')[1])
        if msg.photo:
            ok=await set_ad_image(adid, msg.photo[-1].file_id)
            await msg.answer('✅ Image de la pub modifiée.' if ok else 'Pub introuvable.', reply_markup=ads_admin_kb())
        else:
            await msg.answer('Envoie une image.') ; return
    elif state=='ad_image':
        if msg.photo:
            adid=await add_ad(text=msg.caption or '',image_file_id=msg.photo[-1].file_id)
            await msg.answer('✅ Publicité image ajoutée.' if adid!=-1 else 'Maximum 2 publicités configurées. Supprime une pub avant d’en ajouter une autre.',reply_markup=ads_admin_kb())
        else: await msg.answer('Envoie une image.') ; return
    elif state=='vip_text':
        await st.set_value('vip_text', msg.text or '')
        await msg.answer('✅ Texte VIP principal sauvegardé.', reply_markup=vip_admin_kb())
    elif state=='vip_image':
        if msg.photo:
            await st.set_value('vip_image_file_id', msg.photo[-1].file_id)
            await msg.answer('✅ Image VIP principale sauvegardée.', reply_markup=vip_admin_kb())
        else:
            await msg.answer('Envoie une image.') ; return
    elif state.startswith('vip_offer_text:'):
        offer=state.split(':',1)[1]
        await st.set_value(f'vip_offer_{offer}_text', msg.text or '')
        await msg.answer('✅ Texte de l’offre VIP sauvegardé.', reply_markup=vip_admin_kb())
    elif state.startswith('vip_price:'):
        offer=state.split(':',1)[1]
        n=int(''.join(x for x in (msg.text or '') if x.isdigit()) or '0')
        await st.set_value(f'vip_price_{offer}', str(n))
        await msg.answer(f'✅ Prix VIP sauvegardé : {n}€', reply_markup=vip_admin_kb())
    elif state=='invite_text':
        await st.set_value('invite_text', msg.text or '')
        await msg.answer('✅ Texte invitations sauvegardé.', reply_markup=invite_admin_kb())
    elif state=='invite_image':
        if msg.photo:
            await st.set_value('invite_image_file_id', msg.photo[-1].file_id)
            await msg.answer('✅ Image invitations sauvegardée.', reply_markup=invite_admin_kb())
        else:
            await msg.answer('Envoie une image.') ; return
    elif state=='invite_tiers':
        ok=await set_tiers_from_text(msg.text or '')
        await msg.answer('✅ Paliers sauvegardés.' if ok else 'Format invalide. Exemple : 1|1 vidéo|https://gofile...', reply_markup=invite_admin_kb())
    elif state=='hash_ban_media':
        n=await ban_hash_from_message(msg, bot)
        if n: await msg.answer(f'✅ Hash ban ajouté : {n} média(s).', reply_markup=hashban_kb())
        else:
            await msg.answer('Envoie une photo/vidéo/document à bannir par hash.')
            return
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
        await cb.message.answer(await justice_preview_text())
        await cb.answer()

@router.callback_query(F.data=='justice_preview')
async def cb_justice_preview(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        txt=await justice_preview_text()
        if 'Aucun membre' in txt:
            await cb.message.answer(txt)
        else:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Valider justice', callback_data='confirm:justice_run')],[InlineKeyboardButton(text='❌ Annuler', callback_data='adm_dashboard')]])
            await cb.message.answer(txt, reply_markup=kb)
        await cb.answer()

@router.callback_query(F.data=='justice_run')
async def cb_justice_run(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        txt=await justice_preview_text()
        if 'Aucun membre' in txt:
            await cb.message.answer(txt)
        else:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Valider justice', callback_data='confirm:justice_run')],[InlineKeyboardButton(text='❌ Annuler', callback_data='adm_dashboard')]])
            await cb.message.answer(txt, reply_markup=kb)
        await cb.answer()


@router.callback_query(F.data=='invite_send')
async def cb_invite_send(cb:CallbackQuery, bot:Bot):
    if cb.from_user and is_admin(cb.from_user.id):
        mid=await send_invite_ad(bot, force=True)
        await cb.message.answer('🎁 Message invitations publié maintenant.' if mid else 'Erreur publication invitations.')
        await cb.answer()

@router.callback_query(F.data=='invite_health')
async def cb_invite_health(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        await cb.message.answer(await invite_health_text())
        await cb.answer()

@router.callback_query(F.data=='invite_tiers')
async def cb_invite_tiers(cb:CallbackQuery):
    if cb.from_user and is_admin(cb.from_user.id):
        await cb.message.answer(await tiers_text(), reply_markup=invite_admin_kb())
        await cb.answer()

@router.callback_query(F.data.startswith('validate:') | F.data.startswith('reject:'))
async def validate(cb:CallbackQuery,bot:Bot):
    if not cb.from_user or not is_admin(cb.from_user.id): return
    action,kind,id_s=cb.data.split(':'); ok=action=='validate'; oid=int(id_s)
    if kind=='vip': await validate_vip(bot,oid,ok)
    if kind=='crowd': await validate_crowd(bot,oid,ok)
    await cb.message.answer('Action exécutée.'); await cb.answer()
