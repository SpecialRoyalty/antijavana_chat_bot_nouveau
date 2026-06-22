from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def vote_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔓 Voter pour ouvrir le groupe', callback_data='vote_open')]])

def admin_kb():
    rows=[
        [('📊 Tableau de bord','adm_dashboard'),('🟢 Santé','adm_health')],
        [('🔓 Ouvrir','adm_open'),('🔒 Fermer','adm_close')],
        [('⏰ Auto ON/OFF','adm_auto'),('📦 Objectif','adm_goal')],
        [('⚖️ Justice','adm_justice'),('🧹 Nettoyage','adm_cleanup')],
        [('🕵️ Suspects','adm_suspects'),('💎 VIP','adm_vip')],
        [('💰 Crowdfunding','adm_crowd'),('📢 Publicités','adm_ads')],
        [('🎁 Invitations','adm_invites'),('🏆 Top inviteurs','adm_top')],
        [('🛡️ Modération','adm_mod'),('📜 Règles','adm_rules')],
        [('🚫 Hash ban','adm_hashban')],
        [('👑 Grâce prés.','adm_pardon_ban'),('⚖️ Grâce min.','adm_pardon_mute')],
        [('📊 Rapports','adm_reports'),('⚙️ Paramètres','adm_settings')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t,callback_data=c) for t,c in r] for r in rows])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Retour panel', callback_data='adm_dashboard')]])

def goal_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='1',callback_data='goal_set:1'),InlineKeyboardButton(text='10',callback_data='goal_set:10'),InlineKeyboardButton(text='50',callback_data='goal_set:50'),InlineKeyboardButton(text='120',callback_data='goal_set:120')],
        [InlineKeyboardButton(text='✍️ Objectif personnalisé',callback_data='await:goal')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='22h30 → 00h45',callback_data='slot_set:22:30-00:45')],
        [InlineKeyboardButton(text='22h00 → 00h00',callback_data='slot_set:22:00-00:00')],
        [InlineKeyboardButton(text='23h00 → 01h00',callback_data='slot_set:23:00-01:00')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def justice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⚖️ Lancer justice maintenant',callback_data='justice_run')],
        [InlineKeyboardButton(text='📊 Statut justice',callback_data='justice_status')],
        [InlineKeyboardButton(text='🔍 Prévisualiser justice',callback_data='justice_preview')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def cleanup_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🧹 Nettoyer session active',callback_data='cleanup_active')],
        [InlineKeyboardButton(text='🧹 Nettoyer tous messages suivis',callback_data='cleanup_all')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def mod_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Mot interdit',callback_data='await:forbidden'),InlineKeyboardButton(text='➕ Mot ban',callback_data='await:banword')],
        [InlineKeyboardButton(text='➕ Nom ban',callback_data='await:nameban'),InlineKeyboardButton(text='📋 Voir listes',callback_data='mod_lists')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def crowd_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📤 Publier maintenant',callback_data='crowd_send'), InlineKeyboardButton(text='🩺 Vérifier diffusion',callback_data='crowd_health')],
        [InlineKeyboardButton(text='📝 Modifier texte',callback_data='await:crowd_text'),InlineKeyboardButton(text='🎯 Modifier objectif',callback_data='await:crowd_target')],
        [InlineKeyboardButton(text='🖼 Modifier image',callback_data='await:crowd_image'),InlineKeyboardButton(text='📊 Stats',callback_data='crowd_stats')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def ads_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Ajouter pub texte',callback_data='await:ad_text'),InlineKeyboardButton(text='🖼 Ajouter pub image',callback_data='await:ad_image')],
        [InlineKeyboardButton(text='📤 Publier maintenant',callback_data='ad_send'),InlineKeyboardButton(text='📋 Liste pubs',callback_data='ad_list')],
        [InlineKeyboardButton(text='🩺 Vérifier diffusion',callback_data='ad_health')],
        [InlineKeyboardButton(text='⬅️ Retour',callback_data='adm_dashboard')]
    ])

def vip_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎟 Pass soirée', callback_data='vip_offer:soiree')],
        [InlineKeyboardButton(text='📦 Pass total', callback_data='vip_offer:total')],
        [InlineKeyboardButton(text='💎 COPIE 1:1 VIP JAVANA -50%', callback_data='vip_offer:javana')],
    ])

def pay_kb(prefix='pay'):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='PayPal',callback_data=f'{prefix}:paypal'),InlineKeyboardButton(text='Revolut',callback_data=f'{prefix}:revolut'),InlineKeyboardButton(text='Crypto',callback_data=f'{prefix}:crypto')],
        [InlineKeyboardButton(text='✅ Envoyer capture ensuite',callback_data=f'{prefix}:proof')]
    ])

def admin_validate_kb(kind:str, id:int):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Valider', callback_data=f'validate:{kind}:{id}'),InlineKeyboardButton(text='❌ Refuser', callback_data=f'reject:{kind}:{id}')]])

def rules_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📤 Publier règles maintenant', callback_data='rules_send')],
        [InlineKeyboardButton(text='🩺 Vérifier diffusion', callback_data='rules_health')],
        [InlineKeyboardButton(text='✍️ Modifier texte', callback_data='await:rules_text')],
        [InlineKeyboardButton(text='⬅️ Retour', callback_data='adm_dashboard')]
    ])

def hashban_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Ajouter hash ban', callback_data='await:hash_ban_media')],
        [InlineKeyboardButton(text='📊 Stats hash ban', callback_data='hashban_stats')],
        [InlineKeyboardButton(text='⬅️ Retour', callback_data='adm_dashboard')]
    ])

def vip_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📤 Publier VIP maintenant', callback_data='vip_send')],
        [InlineKeyboardButton(text='🩺 Vérifier diffusion', callback_data='vip_health')],
        [InlineKeyboardButton(text='⬅️ Retour', callback_data='adm_dashboard')]
    ])

def top_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📤 Publier classement maintenant', callback_data='top_send')],
        [InlineKeyboardButton(text='🩺 Vérifier top inviteurs', callback_data='top_health')],
        [InlineKeyboardButton(text='⬅️ Retour', callback_data='adm_dashboard')]
    ])

def confirm_kb(action:str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Confirmer', callback_data=f'confirm:{action}'), InlineKeyboardButton(text='❌ Annuler', callback_data='adm_dashboard')]
    ])
