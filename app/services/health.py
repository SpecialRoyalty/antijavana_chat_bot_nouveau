from __future__ import annotations
from aiogram import Bot
from sqlalchemy import text as sqltext
from app.config import get_settings
from app.db.session import SessionLocal
from app.services.state import get_group_state
from app.utils.time import next_open_close

settings=get_settings()

async def health_report(bot:Bot) -> str:
    db_ok=False; tg_ok=False
    try:
        async with SessionLocal() as db:
            await db.execute(sqltext('select 1'))
            db_ok=True
    except Exception: db_ok=False
    try:
        me=await bot.get_me(); tg_ok=bool(me.id)
    except Exception: tg_ok=False
    st = await get_group_state(settings.main_group_id) if settings.main_group_id else None
    groups = [
        ('Groupe principal', settings.main_group_id),
        ('Pass soirée', settings.pass_soiree_group_id),
        ('Pass total', settings.pass_total_group_id),
        ('VIP JAVANA', settings.vip_javana_group_id),
        ('Logs', settings.log_group_id),
    ]
    mode = '🟢 Fonctionnement total' if all(gid for _,gid in groups[:4]) else '🟡 Fonctionnement partiel'
    lines=[f'{mode}\n', f'Telegram API : {"OK" if tg_ok else "KO"}', f'PostgreSQL : {"OK" if db_ok else "KO"}']
    if st:
        start,end=next_open_close(st.time_slot, settings.timezone)
        lines += [f'Auto : {"ON" if st.auto_enabled else "OFF"}', f'Groupe ouvert : {"OUI" if st.is_open else "NON"}', f'Prochaine ouverture : {start.strftime("%H:%M")}', f'Prochaine fermeture : {end.strftime("%H:%M")}']
    lines += ['\nGroupes :']
    for name,gid in groups:
        lines.append(f'- {name} : {"OK" if gid else "non configuré"}')
    return '\n'.join(lines)
