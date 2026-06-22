from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔓 Voter pour ouvrir le groupe", callback_data="vote_open")]])

def admin_main_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [("📊 Tableau de bord", "admin_dashboard"), ("🟢 Santé", "admin_health")],
        [("🔓 Ouvrir", "admin_open"), ("🔒 Fermer", "admin_close")],
        [("⏰ Auto ON/OFF", "admin_toggle_auto"), ("🗳 Objectif", "admin_vote_goal")],
        [("⚖️ Justice", "admin_justice"), ("🧹 Nettoyage", "admin_cleanup")],
        [("🕵️ Suspects", "admin_suspects"), ("💎 VIP", "admin_vip")],
        [("📊 Rapports", "admin_reports"), ("⚙️ Paramètres", "admin_settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t,d in r] for r in rows])

def security_close_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Maintenir ouvert", callback_data="security_keep_open"),
        InlineKeyboardButton(text="🔒 Fermer", callback_data="admin_close"),
    ]])
