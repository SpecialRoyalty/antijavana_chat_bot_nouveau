from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import func, select, update
from aiogram import Bot
from aiogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton

from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import User, InviteOwner, InviteCredit, InviteCompetition
from app.services.users import upsert_user, protected
from app.services.moderation import matched_word_rule
from app.services.state import log_error, track
from app.services import settings as st
from app.services.multigroup import active_group_id, is_main_group

VALID_MEMBER_STATUSES = {'member', 'administrator', 'creator', 'restricted'}


def _status_value(value) -> str:
    return str(getattr(value, 'value', value) or '').lower()


async def matches_nameban(username: str | None, full_name: str | None) -> tuple[bool, str | None]:
    rule = await matched_word_rule('nameban', f'{username or ""} {full_name or ""}')
    return rule is not None, rule


async def invite_text():
    return await st.get_value(
        'invite_text',
        '🎁 CLASSEMENT INVITATIONS\n\nInvite des membres avec ton lien personnel.\nChaque invitation validée augmente ton classement.\n\n🏆 Le TOP 3 remporte un accès VIP. Les gagnants seront contactés manuellement.'
    )


async def invite_kb(chat_id: int, button_text: str = '🎁 Obtenir mon lien'):
    username = get_settings().public_bot_username.strip().lstrip('@')
    if username:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=button_text, url=f'https://t.me/{username}?start=invite_{chat_id}')
        ]])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=button_text, callback_data=f'invite_private:{chat_id}')
    ]])


async def send_invite_ad(bot: Bot, force: bool = False, target: str = 'active'):
    if not force and not await st.is_open():
        return []
    from app.services.multigroup import resolve_main_targets
    targets=await resolve_main_targets(target, include_unavailable=False)
    if not targets:
        return []
    text = await invite_text()
    img = await st.get_value('invite_image_file_id', '')
    sent=[]
    for chat_id in targets:
        kb = await invite_kb(chat_id)
        try:
            if img:
                m = await bot.send_photo(chat_id, img, caption=text, reply_markup=kb)
                await track(chat_id, m.message_id, None, 'invite_ad', True)
            else:
                m = await bot.send_message(chat_id, text, reply_markup=kb)
                await track(chat_id, m.message_id, None, 'invite_ad', False)
            sent.append((chat_id,m.message_id))
        except Exception as e:
            await log_error(f'invite_ad:{chat_id}',e)
    if sent:
        await st.set_value('last_invite_sent_at', datetime.utcnow().isoformat(timespec='seconds'))
        await st.set_value('last_invite_message_id', str(sent[-1][1]))
        await st.set_value('last_invite_chat_ids', ','.join(str(x[0]) for x in sent))
    return sent


async def _owner(owner_id: int) -> InviteOwner | None:
    async with SessionLocal() as db:
        return await db.get(InviteOwner, owner_id)


async def _ensure_competition() -> None:
    async with SessionLocal() as db:
        current = (await db.execute(select(InviteCompetition).where(InviteCompetition.active.is_(True)).limit(1))).scalar_one_or_none()
        if not current:
            db.add(InviteCompetition(active=True, started_at=datetime.utcnow(), note='Classement invitations'))
            await db.commit()


async def get_or_create_link(bot: Bot, owner_id: int, requested_chat_id: int | None = None):
    await _ensure_competition()
    async with SessionLocal() as db:
        row = await db.get(InviteOwner, owner_id)
        if row and row.active and not row.released and row.invite_link:
            return row.invite_link, row.group_chat_id

    target = requested_chat_id if requested_chat_id and await is_main_group(requested_chat_id) else await active_group_id()
    if not target:
        raise RuntimeError('Aucun groupe principal actif/disponible pour créer le lien.')

    obj = await bot.create_chat_invite_link(target, name=f'invite_{owner_id}', creates_join_request=False)
    link = obj.invite_link
    async with SessionLocal() as db:
        row = await db.get(InviteOwner, owner_id)
        if not row:
            row = InviteOwner(owner_id=owner_id, score=0)
            db.add(row)
        row.group_chat_id = target
        row.invite_link = link
        row.active = True
        row.released = False
        row.updated_at = datetime.utcnow()
        await db.commit()
    return link, target


async def rank_for(owner_id: int) -> tuple[int | None, int]:
    async with SessionLocal() as db:
        me = await db.get(InviteOwner, owner_id)
        if not me:
            return None, 0
        higher = int((await db.execute(
            select(func.count(InviteOwner.owner_id)).where(InviteOwner.score > me.score)
        )).scalar() or 0)
        return higher + 1, me.score


async def send_invite_private(bot: Bot, user_id: int, requested_chat_id: int | None = None):
    try:
        link, group_id = await get_or_create_link(bot, user_id, requested_chat_id)
    except RuntimeError:
        await bot.send_message(user_id, '🌑 Aucun groupe disponible pour créer un lien pour le moment. Ton classement reste conservé.')
        return
    rank, score = await rank_for(user_id)
    await bot.send_message(
        user_id,
        '🎁 TON LIEN D’INVITATION\n\n'
        f'{link}\n\n'
        f'Invitations validées : {score}\n'
        f'Classement actuel : #{rank or "-"}\n\n'
        '🏆 Le TOP 3 remporte un accès VIP.\n'
        'Les gagnants seront contactés manuellement.\n\n'
        'Tu gardes un seul lien actif. S’il est rattaché à un groupe indisponible, il sera libéré sans perdre ton score.'
    )


async def on_join(event: ChatMemberUpdated, bot: Bot | None = None):
    member = getattr(event.new_chat_member, 'user', None)
    if not member or getattr(member, 'is_bot', False) or _status_value(event.new_chat_member.status) not in ('member', 'restricted'):
        return
    await upsert_user(member)

    name_banned, matched_rule = await matches_nameban(member.username, member.full_name)
    if bot and name_banned and not await protected(member.id):
        try:
            from app.services.multigroup import global_ban
            await global_ban(bot, member.id, source_chat_id=event.chat.id, source='nameban', reason=matched_rule or '')
        except Exception as e:
            await log_error(f'nameban_join:{matched_rule or "unknown"}', e)
        return

    inv = getattr(event, 'invite_link', None)
    link = getattr(inv, 'invite_link', None) if inv else None
    if not link:
        return

    async with SessionLocal() as db:
        owner = (await db.execute(
            select(InviteOwner).where(InviteOwner.invite_link == link, InviteOwner.active.is_(True)).limit(1)
        )).scalar_one_or_none()
        if not owner or owner.owner_id == member.id:
            return
        existing = await db.get(InviteCredit, member.id)
        if existing:
            # Une personne ne peut donner qu'un seul point globalement, même après leave/rejoin/A→B.
            return
        db.add(InviteCredit(
            invited_user_id=member.id,
            owner_id=owner.owner_id,
            group_chat_id=event.chat.id,
            invite_link=link,
            status='pending',
            joined_at=datetime.utcnow(),
        ))
        await db.commit()


async def validate_invites(bot: Bot):
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    async with SessionLocal() as db:
        pending = list((await db.execute(
            select(InviteCredit).where(InviteCredit.status == 'pending', InviteCredit.joined_at <= cutoff)
        )).scalars().all())

    for credit in pending:
        valid = False
        reason = ''
        try:
            member = await bot.get_chat_member(credit.group_chat_id, credit.invited_user_id)
            valid = _status_value(member.status) in VALID_MEMBER_STATUSES
            if not valid:
                reason = 'membre parti avant validation'
        except Exception:
            # On ne valide pas à l'aveugle en cas d'erreur Telegram : prochain tick réessaiera.
            continue

        if valid:
            async with SessionLocal() as db:
                fresh = await db.get(InviteCredit, credit.invited_user_id)
                if not fresh or fresh.status != 'pending':
                    continue
                fresh.status = 'valid'
                fresh.validated_at = datetime.utcnow()
                owner = await db.get(InviteOwner, fresh.owner_id)
                if owner:
                    owner.score += 1
                    owner.updated_at = datetime.utcnow()
                user = await db.get(User, fresh.owner_id)
                if user:
                    user.total_invites += 1
                    user.weekly_invites += 1
                await db.commit()
            rank, score = await rank_for(credit.owner_id)
            try:
                await bot.send_message(
                    credit.owner_id,
                    '🎉 NOUVELLE INVITATION VALIDÉE\n\n'
                    f'Invitations : {score}\n'
                    f'Classement actuel : #{rank or "-"}\n\n'
                    '🏆 Le TOP 3 remporte un accès VIP. Les gagnants seront contactés manuellement.'
                )
            except Exception:
                pass
        else:
            async with SessionLocal() as db:
                fresh = await db.get(InviteCredit, credit.invited_user_id)
                if fresh and fresh.status == 'pending':
                    fresh.status = 'rejected'
                    fresh.reject_reason = reason
                    await db.commit()


async def top_text(limit: int = 10):
    async with SessionLocal() as db:
        rows = list((await db.execute(
            select(InviteOwner, User)
            .outerjoin(User, User.id == InviteOwner.owner_id)
            .where(InviteOwner.score > 0)
            .order_by(InviteOwner.score.desc(), InviteOwner.owner_id.asc())
            .limit(limit)
        )).all())
    if not rows:
        return '🏆 TOP 10 INVITATIONS\n\nAucune statistique pour le moment.'
    medals = {1: '🥇', 2: '🥈', 3: '🥉'}
    lines = ['🏆 TOP 10 INVITATIONS', '']
    for index, (owner, user) in enumerate(rows, 1):
        if user and user.username:
            name = '@' + user.username
        elif user and user.full_name:
            name = user.full_name[:24]
        else:
            name = 'membre'
        lines.append(f'{medals.get(index, str(index)+".")} {name} — {owner.score}')
    lines += ['', '🎁 Le TOP 3 remporte un accès VIP.', 'Les gagnants seront contactés manuellement.']
    return '\n'.join(lines)


async def release_link_for_owner(bot: Bot, owner_id: int, reason: str = 'sanction') -> bool:
    """Révoque le lien personnel d'un propriétaire sans toucher à son score."""
    async with SessionLocal() as db:
        owner = await db.get(InviteOwner, owner_id)
        if not owner or not owner.active or not owner.invite_link or not owner.group_chat_id:
            return False
        group_id = int(owner.group_chat_id)
        link = owner.invite_link
    try:
        await bot.revoke_chat_invite_link(group_id, link)
    except Exception:
        pass
    async with SessionLocal() as db:
        owner = await db.get(InviteOwner, owner_id)
        if owner:
            owner.active = False
            owner.released = True
            owner.group_chat_id = None
            owner.invite_link = None
            owner.updated_at = datetime.utcnow()
            await db.commit()
    return True


async def release_links_for_group(bot: Bot, group_chat_id: int) -> int:
    async with SessionLocal() as db:
        owners = list((await db.execute(
            select(InviteOwner).where(
                InviteOwner.group_chat_id == group_chat_id,
                InviteOwner.active.is_(True),
                InviteOwner.invite_link.is_not(None),
            )
        )).scalars().all())
    released = 0
    for owner in owners:
        if owner.invite_link:
            try:
                await bot.revoke_chat_invite_link(group_chat_id, owner.invite_link)
            except Exception:
                pass
        async with SessionLocal() as db:
            row = await db.get(InviteOwner, owner.owner_id)
            if row and row.group_chat_id == group_chat_id:
                row.active = False
                row.released = True
                row.group_chat_id = None
                row.invite_link = None
                row.updated_at = datetime.utcnow()
                await db.commit()
        released += 1
        try:
            await bot.send_message(
                owner.owner_id,
                '⚠️ Ton groupe d’invitation est indisponible. Ton ancien lien a été libéré.\n\n'
                f'Ton score ({owner.score}) est conservé. Reclique sur “Obtenir mon lien” lorsqu’un groupe est disponible.'
            )
        except Exception:
            pass
    return released


async def archive_and_reset_competition() -> int:
    async with SessionLocal() as db:
        active = (await db.execute(select(InviteCompetition).where(InviteCompetition.active.is_(True)))).scalars().all()
        now = datetime.utcnow()
        for comp in active:
            comp.active = False
            comp.ended_at = now
        count = int((await db.execute(select(func.count(InviteOwner.owner_id)).where(InviteOwner.score > 0))).scalar() or 0)
        await db.execute(update(InviteOwner).values(score=0, updated_at=now))
        await db.execute(update(User).values(weekly_invites=0))
        db.add(InviteCompetition(active=True, started_at=now, note='Classement invitations'))
        await db.commit()
    await st.set_value('invite_competition_started_at', datetime.utcnow().isoformat(timespec='seconds'))
    return count


async def invite_health_text():
    async with SessionLocal() as db:
        owners = int((await db.execute(select(func.count(InviteOwner.owner_id)).where(InviteOwner.active.is_(True)))).scalar() or 0)
        pending = int((await db.execute(select(func.count(InviteCredit.invited_user_id)).where(InviteCredit.status == 'pending'))).scalar() or 0)
        valid = int((await db.execute(select(func.count(InviteCredit.invited_user_id)).where(InviteCredit.status == 'valid'))).scalar() or 0)
    return (
        '🎁 Invitations\n\n'
        f'Liens actifs : {owners}\n'
        f'Validations en attente : {pending}\n'
        f'Invitations validées : {valid}\n'
        f'Dernière publication : {await st.get_value("last_invite_sent_at", "jamais")}\n\n'
        'TOP 3 : VIP, contact manuel.'
    )

