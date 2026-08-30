from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update

from app.config import get_settings
from app.db.models import GlobalSanction, ManagedChat, User
from app.db.session import SessionLocal
from app.services import settings as st

ROLE_GROUP_A = 'group_a'
ROLE_GROUP_B = 'group_b'
ROLE_VIP_SOIREE = 'vip_soiree'
ROLE_VIP_TOTAL = 'vip_total'
ROLE_VIP_JAVANA = 'vip_javana'
ROLE_LOGS = 'logs'
ROLE_PENDING = 'pending'
ROLE_REFUSED = 'refused'
ROLE_UNASSIGNED = 'unassigned'

MAIN_ROLES = (ROLE_GROUP_A, ROLE_GROUP_B)
VIP_ROLES = (ROLE_VIP_SOIREE, ROLE_VIP_TOTAL, ROLE_VIP_JAVANA)
MANAGED_ROLES = MAIN_ROLES + VIP_ROLES + (ROLE_LOGS,)

CLOSED_PERMISSIONS = ChatPermissions(can_send_messages=False)
OPEN_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=False,
    can_send_voice_notes=True,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

# Empêche les événements ChatMember générés par notre propre synchronisation de repartir en boucle.
_SYNC_GUARD: dict[tuple[int, int, str], float] = {}
_GUARD_TTL = 30.0


def _member_status(value) -> str:
    """Retourne la valeur Telegram stable d'un ChatMemberStatus (enum ou str)."""
    status = getattr(value, 'value', value)
    return str(status or '').lower()


def _guard(chat_id: int, user_id: int, action: str) -> None:
    _SYNC_GUARD[(chat_id, user_id, action)] = time.monotonic() + _GUARD_TTL


def _guarded(chat_id: int, user_id: int, action: str) -> bool:
    now = time.monotonic()
    for key, expiry in list(_SYNC_GUARD.items()):
        if expiry <= now:
            _SYNC_GUARD.pop(key, None)
    key = (chat_id, user_id, action)
    expiry = _SYNC_GUARD.get(key)
    if expiry and expiry > now:
        _SYNC_GUARD.pop(key, None)
        return True
    return False


def validation_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    def b(text: str, role: str):
        return InlineKeyboardButton(text=text, callback_data=f'chat_role:{chat_id}:{role}')
    return InlineKeyboardMarkup(inline_keyboard=[
        [b('🅰️ Groupe A', ROLE_GROUP_A), b('🅱️ Groupe B', ROLE_GROUP_B)],
        [b('🌙 Pass soirée', ROLE_VIP_SOIREE), b('📦 Pass total', ROLE_VIP_TOTAL)],
        [b('💎 VIP JAVANA', ROLE_VIP_JAVANA), b('🧾 Logs', ROLE_LOGS)],
        [b('❌ Refuser', ROLE_REFUSED)],
    ])


def active_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🅰️ Groupe A', callback_data='active_group:group_a'),
         InlineKeyboardButton(text='🅱️ Groupe B', callback_data='active_group:group_b')],
        [InlineKeyboardButton(text='🌑 Aucune ouverture', callback_data='active_group:none')],
        [InlineKeyboardButton(text='⬅️ Retour', callback_data='adm_dashboard')],
    ])


def infra_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔄 Tester accès/droits', callback_data='infra_test')],
        [InlineKeyboardButton(text='🧪 Test réel VIP', callback_data='infra_vip_real')],
        [InlineKeyboardButton(text='⬅️ Retour', callback_data='adm_dashboard')],
    ])


async def bootstrap_managed_chats() -> None:
    """Importe les IDs historiques une seule fois sans écraser les choix admin.

    Une fois qu'un rôle a été remplacé depuis le panel, l'ancien ID d'environnement
    ne reprend jamais automatiquement ce rôle au redémarrage.
    """
    s = get_settings()
    bootstrap = [
        (s.bootstrap_group_a_id, ROLE_GROUP_A, 'Groupe A (bootstrap)'),
        (s.main_group_b_id, ROLE_GROUP_B, 'Groupe B (bootstrap)'),
        (s.pass_soiree_group_id, ROLE_VIP_SOIREE, 'Pass soirée (bootstrap)'),
        (s.pass_total_group_id, ROLE_VIP_TOTAL, 'Pass total (bootstrap)'),
        (s.vip_javana_group_id, ROLE_VIP_JAVANA, 'VIP JAVANA (bootstrap)'),
        (s.log_group_id, ROLE_LOGS, 'Logs (bootstrap)'),
    ]
    async with SessionLocal() as db:
        for chat_id, role, title in bootstrap:
            if not chat_id:
                continue
            chat_id = int(chat_id)
            # Si un autre chat détient déjà le rôle, le choix DB/admin gagne sur l'env.
            role_owner = (await db.execute(
                select(ManagedChat).where(ManagedChat.role == role).limit(1)
            )).scalar_one_or_none()
            if role_owner and int(role_owner.chat_id) != chat_id:
                continue
            row = await db.get(ManagedChat, chat_id)
            if not row:
                row = ManagedChat(
                    chat_id=chat_id, title=title, role=role, status='active',
                    validated_at=datetime.utcnow(), last_ok_at=datetime.utcnow(),
                )
                db.add(row)
            elif row.role == ROLE_PENDING:
                row.role = role
                row.status = 'active'
                row.validated_at = row.validated_at or datetime.utcnow()
            # ROLE_UNASSIGNED / REFUSED / DISABLED = décision admin persistante : ne pas écraser.
        await db.commit()

    selected = await st.get_value('selected_group_role', '')
    if not selected:
        a = await chat_id_for_role(ROLE_GROUP_A)
        await st.set_value('selected_group_role', ROLE_GROUP_A if a else 'none')
        await st.set_value('active_group_chat_id', str(a or ''))


async def register_detected_chat(event: ChatMemberUpdated, bot: Bot) -> None:
    """Enregistre un chat inconnu en PENDING et demande validation aux ADMIN_IDS."""
    if event.chat.type not in ('group', 'supergroup', 'channel'):
        return
    new_status = _member_status(getattr(event.new_chat_member, 'status', ''))
    if new_status not in ('member', 'administrator'):
        return

    async with SessionLocal() as db:
        row = await db.get(ManagedChat, event.chat.id)
        if row and row.role not in (ROLE_PENDING, ROLE_REFUSED, ROLE_UNASSIGNED):
            row.title = event.chat.title or row.title
            row.last_ok_at = datetime.utcnow()
            row.failure_count = 0
            if row.status != 'disabled':
                row.status = 'active'
            await db.commit()
            return
        if not row:
            row = ManagedChat(
                chat_id=event.chat.id,
                title=event.chat.title or '',
                role=ROLE_PENDING,
                status='pending',
            )
            db.add(row)
        else:
            row.title = event.chat.title or row.title
            row.role = ROLE_PENDING
            row.status = 'pending'
        await db.commit()

    text = (
        '🆕 NOUVEAU GROUPE DÉTECTÉ\n\n'
        f'Nom : {event.chat.title or "sans titre"}\n'
        f'Chat ID : {event.chat.id}\n\n'
        'Aucune automatisation ne sera exécutée avant validation.'
    )
    await notify_admins(bot, text, validation_keyboard(event.chat.id))


async def assign_chat_role(chat_id: int, role: str, admin_id: int, bot: Bot | None = None) -> bool:
    if role not in MANAGED_ROLES + (ROLE_REFUSED,):
        return False
    displaced_main_ids: list[int] = []
    async with SessionLocal() as db:
        row = await db.get(ManagedChat, chat_id)
        if not row:
            row = ManagedChat(chat_id=chat_id, title='', role=ROLE_PENDING, status='pending')
            db.add(row)
        if role != ROLE_REFUSED:
            # Un rôle structurel ne peut pointer que sur un chat.
            others = (await db.execute(
                select(ManagedChat).where(ManagedChat.role == role, ManagedChat.chat_id != chat_id)
            )).scalars().all()
            for other in others:
                if other.role in MAIN_ROLES:
                    displaced_main_ids.append(int(other.chat_id))
                other.role = ROLE_UNASSIGNED
                other.status = 'disabled'
        row.role = role
        row.status = 'disabled' if role == ROLE_REFUSED else 'active'
        row.validated_by = admin_id
        row.validated_at = datetime.utcnow()
        row.failure_count = 0
        row.last_ok_at = datetime.utcnow() if role != ROLE_REFUSED else row.last_ok_at
        await db.commit()

    if bot:
        # Si un groupe A/B est remplacé, les anciens liens personnels ne
        # doivent jamais continuer de recruter vers l'ancien chat. Les scores
        # restent intacts et les propriétaires pourront demander un nouveau lien.
        if displaced_main_ids:
            try:
                from app.services.invites import release_links_for_group
                for old_gid in displaced_main_ids:
                    await _set_permissions_safely(bot, old_gid, False)
                    await release_links_for_group(bot, old_gid)
            except Exception:
                pass
        # Remplacement du groupe actuellement sélectionné : la même session
        # continue sur le nouveau chat, sans rouvrir l'ancien.
        if role in MAIN_ROLES and await selected_group_role() == role:
            await st.set_value('active_group_chat_id', str(chat_id))
            if await st.is_open():
                await _set_permissions_safely(bot, chat_id, True)
        if role == ROLE_REFUSED:
            try:
                await bot.leave_chat(chat_id)
            except Exception:
                pass
        else:
            try:
                await sync_redirections(bot)
            except Exception:
                pass
    return True


async def managed_chat(chat_id: int) -> ManagedChat | None:
    async with SessionLocal() as db:
        return await db.get(ManagedChat, chat_id)


async def is_validated_chat(chat_id: int) -> bool:
    row = await managed_chat(chat_id)
    return bool(row and row.role in MANAGED_ROLES and row.status != 'disabled')


async def is_main_group(chat_id: int) -> bool:
    row = await managed_chat(chat_id)
    return bool(row and row.role in MAIN_ROLES and row.status != 'disabled')


async def chat_id_for_role(role: str, include_unavailable: bool = True) -> int | None:
    async with SessionLocal() as db:
        q = select(ManagedChat).where(ManagedChat.role == role)
        if not include_unavailable:
            q = q.where(ManagedChat.status.in_(['active', 'degraded']))
        row = (await db.execute(q.order_by(ManagedChat.validated_at.desc().nullslast()).limit(1))).scalar_one_or_none()
        return int(row.chat_id) if row else None


async def main_group_ids(include_unavailable: bool = True) -> list[int]:
    async with SessionLocal() as db:
        q = select(ManagedChat.chat_id).where(ManagedChat.role.in_(MAIN_ROLES))
        if not include_unavailable:
            q = q.where(ManagedChat.status.in_(['active', 'degraded']))
        return [int(x) for x in (await db.execute(q)).scalars().all()]


async def resolve_main_targets(target: str = 'active', include_unavailable: bool = False) -> list[int]:
    """Résout une cible de publication manuelle/automatique.

    target:
      - active : groupe principal sélectionné/actif
      - group_a / a : Groupe A
      - group_b / b : Groupe B
      - both / all : les deux groupes principaux validés

    Pour les publications manuelles, on peut cibler un groupe fermé : la fermeture
    bloque les membres, pas le bot. Un chat marqué unavailable reste exclu par défaut.
    """
    raw=(target or 'active').lower().strip()
    if raw == 'active':
        gid=await active_group_id()
        return [gid] if gid else []
    if raw in ('group_a','a'):
        gid=await chat_id_for_role(ROLE_GROUP_A, include_unavailable=include_unavailable)
        return [gid] if gid else []
    if raw in ('group_b','b'):
        gid=await chat_id_for_role(ROLE_GROUP_B, include_unavailable=include_unavailable)
        return [gid] if gid else []
    if raw in ('both','all','a+b'):
        return await main_group_ids(include_unavailable=include_unavailable)
    return []


async def vip_group_ids(include_unavailable: bool = True) -> list[int]:
    async with SessionLocal() as db:
        q = select(ManagedChat.chat_id).where(ManagedChat.role.in_(VIP_ROLES))
        if not include_unavailable:
            q = q.where(ManagedChat.status.in_(['active', 'degraded']))
        return [int(x) for x in (await db.execute(q)).scalars().all()]


async def sanction_chat_ids() -> list[int]:
    """Bans/mutes globaux : A, B et VIP communs. Logs exclus."""
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(ManagedChat.chat_id).where(
                ManagedChat.role.in_(MAIN_ROLES + VIP_ROLES),
                ManagedChat.status != 'disabled',
            )
        )).scalars().all()
    return list(dict.fromkeys(int(x) for x in rows))


async def selected_group_role() -> str:
    role = await st.get_value('selected_group_role', 'none')
    return role if role in MAIN_ROLES else 'none'


async def active_group_id() -> int | None:
    if (await st.get_value('session_suspended', 'false')) == 'true':
        return None
    raw = await st.get_value('active_group_chat_id', '')
    try:
        chat_id = int(raw)
    except Exception:
        chat_id = None
    if chat_id and await is_main_group(chat_id):
        row = await managed_chat(chat_id)
        # Un groupe DEGRADED reste le groupe actif pendant les tentatives de
        # santé. Il ne devient indisponible qu'après plusieurs échecs.
        if row and row.status in ('active', 'degraded'):
            return chat_id
    role = await selected_group_role()
    if role == 'none':
        return None
    async with SessionLocal() as db:
        row = (await db.execute(
            select(ManagedChat).where(
                ManagedChat.role == role,
                ManagedChat.status.in_(['active', 'degraded']),
            ).order_by(ManagedChat.validated_at.desc().nullslast()).limit(1)
        )).scalar_one_or_none()
    chat_id = int(row.chat_id) if row else None
    if chat_id:
        await st.set_value('active_group_chat_id', str(chat_id))
    return chat_id


async def active_group_or_none_text() -> str:
    role = await selected_group_role()
    if role == ROLE_GROUP_A:
        return '🅰️ Groupe A'
    if role == ROLE_GROUP_B:
        return '🅱️ Groupe B'
    return '🌑 Aucune ouverture'


async def _set_permissions_safely(bot: Bot, chat_id: int, open_: bool) -> None:
    try:
        await bot.set_chat_permissions(chat_id, permissions=OPEN_PERMISSIONS if open_ else CLOSED_PERMISSIONS)
    except Exception:
        pass


async def select_active_group(bot: Bot, role: str) -> tuple[bool, str]:
    """Sélectionne A/B/NONE. Si une session est déjà ouverte/suspendue, la même session bascule."""
    if role not in MAIN_ROLES and role != 'none':
        return False, 'Choix invalide.'

    groups = await main_group_ids()
    was_open = await st.is_open()

    if role == 'none':
        for gid in groups:
            await _set_permissions_safely(bot, gid, False)
        await st.set_value('selected_group_role', 'none')
        await st.set_value('active_group_chat_id', '')
        await st.set_value('session_suspended', 'false')
        if was_open:
            # On ferme réellement la session si l'admin choisit explicitement AUCUN.
            from app.services.session_ops import set_group_open
            await set_group_open(bot, False, 'no_session')
        await sync_redirections(bot)
        try:
            from app.services.state import ensure_status_message
            for gid in groups:
                await ensure_status_message(bot,gid,recreate_on_change=True)
        except Exception:
            pass
        return True, '🌑 Aucune ouverture sélectionnée. Les deux groupes restent fermés.'

    target = await chat_id_for_role(role, include_unavailable=False)
    if not target:
        return False, 'Le groupe choisi n’est pas validé ou est indisponible.'

    old = await active_group_id()
    for gid in groups:
        await _set_permissions_safely(bot, gid, was_open and gid == target)

    await st.set_value('selected_group_role', role)
    await st.set_value('active_group_chat_id', str(target))
    await st.set_value('session_suspended', 'false')

    # Même SessionLog en cas de bascule pendant une session.
    if was_open and old and old != target:
        await st.set_value('last_failover_at', datetime.utcnow().isoformat(timespec='seconds'))
        await notify_admins(bot, f'🔁 Session basculée vers {"Groupe A" if role == ROLE_GROUP_A else "Groupe B"}. La même session reste active.')

    await sync_redirections(bot)
    return True, f'✅ {"Groupe A" if role == ROLE_GROUP_A else "Groupe B"} sélectionné pour la soirée.'


async def _redirect_link(bot: Bot, target_chat_id: int) -> str | None:
    key = f'redirect_link:{target_chat_id}'
    cached = await st.get_value(key, '')
    if cached:
        return cached
    try:
        obj = await bot.create_chat_invite_link(target_chat_id, name='redirection_centrale')
        await st.set_value(key, obj.invite_link)
        return obj.invite_link
    except Exception:
        return None


async def sync_redirections(bot: Bot) -> None:
    """Ferme le groupe inactif et y maintient un message de redirection vers le groupe actif."""
    active = await active_group_id()
    # En maintenance (Auto OFF, session fermée), aucun groupe ne redirige vers
    # l'autre : les deux restent fermés et peuvent afficher leurs annonces.
    redirect_active = active if (await st.is_open() or await st.auto_enabled()) else None
    groups = await main_group_ids()
    link = await _redirect_link(bot, redirect_active) if redirect_active else None

    for gid in groups:
        key = f'redirect_message_id:{gid}'
        old = await st.get_value(key, '')
        if gid == redirect_active or not redirect_active:
            if old:
                try:
                    await bot.delete_message(gid, int(old))
                except Exception:
                    pass
                await st.set_value(key, '')
            if not redirect_active:
                await _set_permissions_safely(bot, gid, False)
            continue

        await _set_permissions_safely(bot, gid, False)
        if old:
            try:
                await bot.delete_message(gid, int(old))
            except Exception:
                pass
        text = ('🔒 Ce groupe est fermé ce soir.\n\n🔥 La session est ouverte dans notre autre groupe.'
                if await st.is_open()
                else '🔒 Ce groupe est fermé ce soir.\n\n🌙 L’ouverture de ce soir aura lieu dans notre autre groupe.')
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='👉 REJOINDRE LA SESSION', url=link)]
        ]) if link else None
        try:
            msg = await bot.send_message(gid, text, reply_markup=kb)
            await st.set_value(key, str(msg.message_id))
        except Exception:
            pass


async def notify_admins(bot: Bot, text: str, reply_markup=None) -> None:
    async def one(uid: int):
        try:
            await bot.send_message(uid, text, reply_markup=reply_markup)
        except Exception:
            pass
    await asyncio.gather(*(one(uid) for uid in get_settings().admin_ids))


async def _upsert_sanction(user_id: int, kind: str, *, active: bool, expires_at: datetime | None,
                           source_chat_id: int | None, source: str, reason: str = '', created_by: int | None = None) -> None:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(GlobalSanction).where(GlobalSanction.user_id == user_id, GlobalSanction.kind == kind, GlobalSanction.active.is_(True))
        )).scalars().all()
        if active:
            if rows:
                row = rows[-1]
                row.expires_at = expires_at
                row.source_chat_id = source_chat_id
                row.source = source
                row.reason = reason
                row.created_by = created_by
                row.updated_at = datetime.utcnow()
                for extra in rows[:-1]:
                    extra.active = False
            else:
                db.add(GlobalSanction(
                    user_id=user_id, kind=kind, active=True, expires_at=expires_at,
                    source_chat_id=source_chat_id, source=source, reason=reason, created_by=created_by,
                ))
        else:
            for row in rows:
                row.active = False
                row.updated_at = datetime.utcnow()
        user = await db.get(User, user_id)
        if user:
            if kind == 'ban':
                user.is_banned = active
            elif kind == 'mute':
                user.is_restricted = active
        await db.commit()


async def global_ban(bot: Bot, user_id: int, *, source_chat_id: int | None = None,
                     source: str = 'automatic', reason: str = '', created_by: int | None = None) -> bool:
    if user_id in get_settings().all_admin_ids:
        return False
    await _upsert_sanction(user_id, 'ban', active=True, expires_at=None, source_chat_id=source_chat_id,
                           source=source, reason=reason, created_by=created_by)
    # Un membre globalement banni ne garde pas un lien d'invitation actif.
    try:
        from app.services.invites import release_link_for_owner
        await release_link_for_owner(bot, user_id, reason='global_ban')
    except Exception:
        pass
    ok_any = False
    for gid in await sanction_chat_ids():
        _guard(gid, user_id, 'ban')
        try:
            await bot.ban_chat_member(gid, user_id)
            ok_any = True
        except TelegramBadRequest as exc:
            low = str(exc).lower()
            if 'user not found' in low or 'participant_id_invalid' in low or 'user is not a member' in low:
                continue
        except Exception:
            continue
    return ok_any


async def global_unban(bot: Bot, user_id: int, *, source: str = 'manual_unban') -> bool:
    await _upsert_sanction(user_id, 'ban', active=False, expires_at=None, source_chat_id=None, source=source)
    ok_any = False
    for gid in await sanction_chat_ids():
        _guard(gid, user_id, 'unban')
        try:
            await bot.unban_chat_member(gid, user_id, only_if_banned=True)
            ok_any = True
        except Exception:
            pass
    return ok_any


async def global_mute(bot: Bot, user_id: int, until: datetime | None, *, source_chat_id: int | None = None,
                      source: str = 'automatic', reason: str = '', created_by: int | None = None) -> bool:
    if user_id in get_settings().all_admin_ids:
        return False
    await _upsert_sanction(user_id, 'mute', active=True, expires_at=until, source_chat_id=source_chat_id,
                           source=source, reason=reason, created_by=created_by)
    ok_any = False
    for gid in await sanction_chat_ids():
        _guard(gid, user_id, 'mute')
        try:
            await bot.restrict_chat_member(gid, user_id, permissions=CLOSED_PERMISSIONS, until_date=until)
            ok_any = True
        except Exception:
            pass
    return ok_any


async def global_unmute(bot: Bot, user_id: int, *, source: str = 'manual_unmute') -> bool:
    await _upsert_sanction(user_id, 'mute', active=False, expires_at=None, source_chat_id=None, source=source)
    ok_any = False
    for gid in await sanction_chat_ids():
        _guard(gid, user_id, 'unmute')
        try:
            await bot.restrict_chat_member(gid, user_id, permissions=OPEN_PERMISSIONS)
            ok_any = True
        except Exception:
            pass
    return ok_any


async def active_sanctions(user_id: int) -> list[GlobalSanction]:
    now = datetime.utcnow()
    async with SessionLocal() as db:
        rows = (await db.execute(select(GlobalSanction).where(
            GlobalSanction.user_id == user_id, GlobalSanction.active.is_(True)
        ))).scalars().all()
        changed = False
        active: list[GlobalSanction] = []
        for row in rows:
            if row.kind == 'mute' and row.expires_at and row.expires_at <= now:
                row.active = False
                changed = True
            else:
                active.append(row)
        if changed:
            await db.commit()
        return active


async def apply_existing_sanctions_on_join(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Applique la DB globale lorsqu'un membre revient. True si un ban a été appliqué."""
    if user_id in get_settings().all_admin_ids:
        return False
    rows = await active_sanctions(user_id)
    for row in rows:
        if row.kind == 'ban':
            _guard(chat_id, user_id, 'ban')
            try:
                await bot.ban_chat_member(chat_id, user_id)
            except Exception:
                pass
            return True
        if row.kind == 'mute':
            _guard(chat_id, user_id, 'mute')
            try:
                await bot.restrict_chat_member(chat_id, user_id, permissions=CLOSED_PERMISSIONS, until_date=row.expires_at)
            except Exception:
                pass
    return False


async def handle_manual_member_change(event: ChatMemberUpdated, bot: Bot) -> None:
    """Transforme les sanctions Telegram manuelles en sanctions globales, sans boucle."""
    if not await is_validated_chat(event.chat.id):
        return
    member = getattr(event.new_chat_member, 'user', None)
    if not member or member.id in get_settings().all_admin_ids:
        return
    try:
        me = await bot.get_me()
        actor_is_bot = bool(event.from_user and event.from_user.id == me.id)
    except Exception:
        actor_is_bot = False

    old = _member_status(getattr(event.old_chat_member, 'status', ''))
    new = _member_status(getattr(event.new_chat_member, 'status', ''))

    if new == 'kicked':
        if _guarded(event.chat.id, member.id, 'ban') or actor_is_bot:
            return
        await global_ban(bot, member.id, source_chat_id=event.chat.id, source='manual', created_by=getattr(event.from_user, 'id', None))
        return
    if old == 'kicked' and new != 'kicked':
        if _guarded(event.chat.id, member.id, 'unban') or actor_is_bot:
            return
        await global_unban(bot, member.id, source='manual_unban')
        return
    if new == 'restricted':
        if _guarded(event.chat.id, member.id, 'mute') or actor_is_bot:
            return
        until = getattr(event.new_chat_member, 'until_date', None)
        if isinstance(until, int):
            until = datetime.utcfromtimestamp(until) if until > 0 else None
        await global_mute(bot, member.id, until, source_chat_id=event.chat.id, source='manual', created_by=getattr(event.from_user, 'id', None))
        return
    if old == 'restricted' and new == 'member':
        if _guarded(event.chat.id, member.id, 'unmute') or actor_is_bot:
            return
        await global_unmute(bot, member.id, source='manual_unmute')


async def probe_chat(bot: Bot, row: ManagedChat, *, real_vip_test: bool = False) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    try:
        me = await bot.get_me()
        await bot.get_chat(row.chat_id)
        member = await bot.get_chat_member(row.chat_id, me.id)
        admin = _member_status(member.status) in ('administrator', 'creator')
        lines.append(f'Accès : ✅')
        lines.append(f'Admin : {"✅" if admin else "❌"}')
        if not admin:
            ok = False
        if row.role in MAIN_ROLES:
            can_delete = bool(getattr(member, 'can_delete_messages', False))
            can_restrict = bool(getattr(member, 'can_restrict_members', False))
            can_invite = bool(getattr(member, 'can_invite_users', False))
            lines += [
                f'Supprimer : {"✅" if can_delete else "❌"}',
                f'Bannir/restreindre : {"✅" if can_restrict else "❌"}',
                f'Invitations : {"✅" if can_invite else "❌"}',
            ]
            ok = ok and can_delete and can_restrict and can_invite
        elif row.role in VIP_ROLES:
            can_delete = bool(getattr(member, 'can_delete_messages', False))
            can_invite = bool(getattr(member, 'can_invite_users', False))
            lines += [f'Supprimer : {"✅" if can_delete else "❌"}', f'Invitations : {"✅" if can_invite else "❌"}']
            ok = ok and can_invite
            if real_vip_test:
                try:
                    m = await bot.send_message(row.chat_id, '🧪 Test de connexion VIP — suppression automatique.')
                    lines.append('Envoi réel : ✅')
                    try:
                        await bot.delete_message(row.chat_id, m.message_id)
                        lines.append('Suppression réelle : ✅')
                    except Exception:
                        lines.append('Suppression réelle : ❌')
                        ok = False
                except Exception:
                    lines.append('Envoi réel : ❌')
                    ok = False
    except Exception as exc:
        ok = False
        lines.append(f'Accès : ❌ ({type(exc).__name__})')

    async with SessionLocal() as db:
        stored = await db.get(ManagedChat, row.chat_id)
        if stored:
            if ok:
                stored.failure_count = 0
                stored.status = 'active'
                stored.last_ok_at = datetime.utcnow()
            else:
                stored.failure_count += 1
                stored.last_error_at = datetime.utcnow()
                if stored.failure_count >= 3:
                    stored.status = 'unavailable'
                elif stored.status == 'active':
                    stored.status = 'degraded'
            await db.commit()
    return ok, lines


async def infrastructure_report(bot: Bot, *, real_vip_test: bool = False) -> str:
    async with SessionLocal() as db:
        rows = list((await db.execute(
            select(ManagedChat).where(ManagedChat.role.in_(MANAGED_ROLES)).order_by(ManagedChat.role)
        )).scalars().all())
    if not rows:
        return '🧪 INFRASTRUCTURE\n\nAucun groupe validé.'
    labels = {
        ROLE_GROUP_A: '🅰️ Groupe A', ROLE_GROUP_B: '🅱️ Groupe B',
        ROLE_VIP_SOIREE: '🌙 Pass soirée', ROLE_VIP_TOTAL: '📦 Pass total',
        ROLE_VIP_JAVANA: '💎 VIP JAVANA', ROLE_LOGS: '🧾 Logs',
    }
    blocks = ['🧪 TEST INFRASTRUCTURE', '']
    all_ok = True
    for row in rows:
        if real_vip_test and row.role not in VIP_ROLES:
            continue
        ok, lines = await probe_chat(bot, row, real_vip_test=real_vip_test)
        all_ok = all_ok and ok
        blocks.append(labels.get(row.role, row.role))
        blocks.extend(lines)
        blocks.append('')
    blocks.append('🟢 INFRASTRUCTURE PRÊTE' if all_ok else '🔴 PROBLÈME(S) DÉTECTÉ(S)')
    return '\n'.join(blocks)


async def health_monitor_tick(bot: Bot) -> None:
    """Contrôle doux : 3 échecs consécutifs avant de suspendre une session.

    Un premier échec passe le chat en DEGRADED sans perdre son rôle actif. Cela
    évite qu'un 502/timeout Telegram isolé provoque un faux failover.
    """
    async with SessionLocal() as db:
        rows = list((await db.execute(select(ManagedChat).where(ManagedChat.role.in_(MANAGED_ROLES)))).scalars().all())

    selected = await selected_group_role()
    selected_chat = None
    if selected in MAIN_ROLES:
        for row in rows:
            if row.role == selected and row.status != 'disabled':
                selected_chat = int(row.chat_id)
                break

    suspended_now = False
    for row in rows:
        ok, _ = await probe_chat(bot, row)
        if ok:
            continue
        fresh = await managed_chat(row.chat_id)
        if selected_chat == row.chat_id and fresh and fresh.status == 'unavailable':
            if (await st.get_value('session_suspended', 'false')) != 'true':
                await st.set_value('session_suspended', 'true')
                await st.set_value('active_group_chat_id', '')
                suspended_now = True
                try:
                    from app.services.invites import release_links_for_group
                    await release_links_for_group(bot, row.chat_id)
                except Exception:
                    pass
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='➡️ Basculer vers A', callback_data='active_group:group_a'),
                     InlineKeyboardButton(text='➡️ Basculer vers B', callback_data='active_group:group_b')],
                    [InlineKeyboardButton(text='🌑 Terminer / aucune ouverture', callback_data='active_group:none')],
                ])
                await notify_admins(
                    bot,
                    f'🚨 Groupe actif indisponible après {fresh.failure_count} contrôles.\n\n'
                    'La session est SUSPENDUE : pubs/crowdfunding/règles ne seront pas consommés.\n'
                    'Choisis une bascule ou termine la soirée.',
                    kb,
                )
    if suspended_now:
        # Supprime les redirections qui pointeraient encore vers le chat tombé.
        await sync_redirections(bot)


async def managed_chats_text() -> str:
    async with SessionLocal() as db:
        rows = list((await db.execute(select(ManagedChat).order_by(ManagedChat.role, ManagedChat.chat_id))).scalars().all())
    labels = {
        ROLE_GROUP_A: '🅰️ Groupe A', ROLE_GROUP_B: '🅱️ Groupe B', ROLE_VIP_SOIREE: '🌙 Pass soirée',
        ROLE_VIP_TOTAL: '📦 Pass total', ROLE_VIP_JAVANA: '💎 VIP JAVANA', ROLE_LOGS: '🧾 Logs',
        ROLE_PENDING: '⏳ En attente', ROLE_UNASSIGNED: '⚫ Non assigné', ROLE_REFUSED: '❌ Refusé',
    }
    if not rows:
        return '🧩 Groupes / VIP\n\nAucun chat détecté.'
    lines = ['🧩 Groupes / VIP', '']
    for row in rows:
        lines.append(f'{labels.get(row.role, row.role)} — {row.title or row.chat_id}\nID: {row.chat_id}\nÉtat: {row.status}')
    lines += ['', f'Ce soir : {await active_group_or_none_text()}']
    return '\n\n'.join(lines)
