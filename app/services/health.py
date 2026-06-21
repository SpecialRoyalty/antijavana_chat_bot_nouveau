from sqlalchemy import text
from app.config import get_settings
from app.db.session import SessionLocal

settings = get_settings()


async def health_report() -> str:
    db_ok = False
    try:
        async with SessionLocal() as db:
            await db.execute(text('select 1'))
            db_ok = True
    except Exception:
        db_ok = False

    groups = {
        'Groupe principal': settings.main_group_id,
        'Pass soirée': settings.pass_soiree_group_id,
        'Pass total': settings.pass_total_group_id,
        'VIP JAVANA': settings.vip_javana_group_id,
        'Logs': settings.log_group_id,
    }
    total = all(groups.values())
    mode = '🟢 FONCTIONNEMENT TOTAL' if total and db_ok else '🟡 FONCTIONNEMENT PARTIEL'
    lines = [mode, '', f"PostgreSQL : {'OK' if db_ok else 'ERREUR'}", '']
    for name, gid in groups.items():
        lines.append(f"{name} : {'OK' if gid else 'manquant'}")
    lines += ['', 'Modules VIP : ' + ('actifs' if settings.pass_soiree_group_id and settings.pass_total_group_id else 'désactivés/partiels')]
    return '\n'.join(lines)
