from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.db.models import TrackedMessage, TrustedAction, User


async def session_report() -> str:
    async with SessionLocal() as db:
        msg_count = int((await db.execute(select(func.count(TrackedMessage.id)))).scalar() or 0)
        actions = await db.execute(select(TrustedAction.trusted_username, TrustedAction.command, func.count(TrustedAction.id)).group_by(TrustedAction.trusted_username, TrustedAction.command))
        users = await db.execute(select(func.count(User.id)))
        user_count = int(users.scalar() or 0)
    lines = ['📊 RAPPORT DE SESSION', '', f'Messages encore suivis : {msg_count}', f'Utilisateurs connus : {user_count}', '', 'Actions trusted :']
    any_action = False
    for username, command, count in actions.all():
        any_action = True
        lines.append(f'@{username or "unknown"} — {command} : {count}')
    if not any_action:
        lines.append('Aucune action trusted enregistrée.')
    lines += ['', 'Inactifs : calcul par sessions accessibles prévu dans le module Justice.']
    return '\n'.join(lines)
