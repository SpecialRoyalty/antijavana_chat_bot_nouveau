from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text='📊 Tableau de bord', callback_data='admin:dashboard')],
        [InlineKeyboardButton(text='🔓 Ouvrir', callback_data='admin:open'), InlineKeyboardButton(text='🔒 Fermer', callback_data='admin:close')],
        [InlineKeyboardButton(text='⏰ Horaire auto', callback_data='admin:auto'), InlineKeyboardButton(text='🟢 Santé', callback_data='admin:health')],
        [InlineKeyboardButton(text='🛡️ Modération', callback_data='admin:moderation'), InlineKeyboardButton(text='⚖️ Justice', callback_data='admin:justice')],
        [InlineKeyboardButton(text='🕵️ Suspects', callback_data='admin:suspects'), InlineKeyboardButton(text='🎁 Récompenses', callback_data='admin:rewards')],
        [InlineKeyboardButton(text='💎 VIP', callback_data='admin:vip'), InlineKeyboardButton(text='💰 Crowdfunding', callback_data='admin:crowd')],
        [InlineKeyboardButton(text='👑 Grâce présidentielle', callback_data='admin:pardon_bans')],
        [InlineKeyboardButton(text='⚖️ Grâce ministérielle', callback_data='admin:pardon_restrict')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vote_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔓 Voter pour ouvrir le groupe', callback_data='vote:open')]])


def vip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎟 Pass soirée', callback_data='vip:soiree')],
        [InlineKeyboardButton(text='📦 Pass total', callback_data='vip:total')],
        [InlineKeyboardButton(text='💎 COPIE 1:1 VIP JAVANA -50%', callback_data='vip:javana')],
    ])
