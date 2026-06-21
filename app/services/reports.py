from sqlalchemy import select, func
from app.db.models import TrustedAction, TrackedMessage
from app.db.session import SessionLocal


async def session_report() -> str:
    async with SessionLocal() as db:
        msg_count = (await db.execute(select(func.count(TrackedMessage.id)))).scalar() or 0
        rows = await db.execute(select(TrustedAction.trusted_username, TrustedAction.command, func.count(TrustedAction.id)).group_by(TrustedAction.trusted_username, TrustedAction.command))
        actions = rows.all()
    lines = ['📊 RAPPORT DE SESSION', '', f'Messages suivis/supprimables : {msg_count}', '', 'Actions trusted :']
    if not actions:
        lines.append('Aucune action trusted.')
    for username, command, count in actions:
        lines.append(f'@{username or "unknown"} — {command} : {count}')
    lines += ['', 'Inactifs : calculés par sessions ouvertes accessibles.']
    return '\n'.join(lines)
