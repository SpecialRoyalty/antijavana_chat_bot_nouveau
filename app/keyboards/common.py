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
        [('👑 Grâce prés.','adm_pardon_ban'),('⚖️ Grâce min.','adm_pardon_mute')],
        [('📊 Rapports','adm_reports'),('⚙️ Paramètres','adm_settings')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t,callback_data=c) for t,c in r] for r in rows])
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
