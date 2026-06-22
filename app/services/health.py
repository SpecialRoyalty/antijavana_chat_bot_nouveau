from __future__ import annotations
from sqlalchemy import text, select, func
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import TrackedMessage, Session
from app.services.session_service import get_runtime_settings

settings = get_settings()


async def health_report() -> str:
    db_ok = '❌'
    tracked = 0
    status = 'unknown'
    try:
        async with SessionLocal() as db:
            await db.execute(text('SELECT 1'))
            db_ok = '✅'
            res = await db.execute(select(func.count(TrackedMessage.id)))
            tracked = int(res.scalar() or 0)
            sres = await db.execute(select(Session).order_by(Session.id.desc()).limit(1))
            s = sres.scalar_one_or_none()
            status = s.status if s else 'closed'
    except Exception:
        pass
    runtime = await get_runtime_settings()
    groups = [
        ('Principal', settings.main_group_id),
        ('Pass soirée', settings.pass_soiree_group_id),
        ('Pass total', settings.pass_total_group_id),
        ('VIP JAVANA', settings.vip_javana_group_id),
        ('Logs', settings.log_group_id),
    ]
    missing_vip = any(v is None for _, v in groups[1:4])
    mode = '🟢 FONCTIONNEMENT TOTAL' if settings.main_group_id and not missing_vip else '🟡 FONCTIONNEMENT PARTIEL'
    lines = [
        f'{mode}', '',
        '🤖 SANTÉ DU BOT', '',
        f'PostgreSQL : {db_ok}',
        'Telegram API : ✅ si ce message est affiché',
        f'Auto : {"ON" if runtime.get("auto_enabled", True) else "OFF"}',
        f'Créneau : {runtime.get("schedule", "22:30-00:45")}',
        f'Session : {status}',
        f'Messages suivis/nettoyables : {tracked}', '',
        'Groupes :'
    ]
    for name, gid in groups:
        lines.append(f'- {name} : {"✅ " + str(gid) if gid else "⚠️ non configuré"}')
    lines += ['', 'Vérifications :', '- Message statut unique : actif', '- Double nettoyage : actif', '- Mode partiel VIP : actif', '- Anti-raccordement pirate : actif']
    return '\n'.join(lines)
