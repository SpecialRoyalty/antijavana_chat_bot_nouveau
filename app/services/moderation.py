from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import ChatPermissions, Message
from sqlalchemy import select

from app.config import get_settings
from app.db.models import User, WordRule
from app.db.session import SessionLocal
from app.services import settings as st
from app.services.hashban import (
    MediaProbe,
    close_media_probe,
    find_banned_hash,
    find_banned_id,
    find_banned_perceptual,
    find_banned_sha,
    media_file_entries,
    open_media_probe,
    record_repost_verification,
    store_message_hashes,
)
from app.services.state import log_error, track
from app.services.users import display_name, protected, has_sent_media, increment_media_count
from app.services.anti_fast_join import enforce as enforce_fast_join
from app.services.anti_repost import (
    enabled as anti_repost_enabled,
    enforce_known_match as enforce_anti_repost_match,
    find_repost_by_id,
    find_repost_by_sha,
    find_repost_by_perceptual,
    remember_stored_keys,
)

_SETTINGS = get_settings()
_ADMIN_IDS = frozenset(_SETTINGS.admin_ids)
_TRUSTED_IDS = frozenset(_SETTINGS.trusted_ids)


def has_link(text: str) -> bool:
    return bool(re.search(r"(https?://|t\.me/|www\.|\.com\b|\.net\b|\.io\b)", text or "", re.I))


def has_mention(text: str) -> bool:
    return "@" in (text or "")


def has_command(text: str) -> bool:
    return (text or "").strip().startswith("/")


def is_media(msg: Message) -> bool:
    return bool(media_file_entries(msg))


def file_ids(msg: Message):
    """Compatibilité avec les autres modules existants."""
    return media_file_entries(msg)


_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_WORD_CACHE_TTL = 60.0
_WORD_CACHE: dict[str, tuple[float, list[str], list[tuple[str, ...]]]] = {}


def invalidate_word_cache(kind: str | None = None) -> None:
    if kind is None:
        _WORD_CACHE.clear()
    else:
        _WORD_CACHE.pop(kind, None)


async def _load_word_rules(kind: str) -> tuple[list[str], list[tuple[str, ...]]]:
    cached = _WORD_CACHE.get(kind)
    now = time.monotonic()
    if cached and now < cached[0]:
        return cached[1], cached[2]
    async with SessionLocal() as db:
        result = await db.execute(select(WordRule.word).where(WordRule.kind == kind))
        raw = [str(word).lower() for word in result.scalars().all()]
    pairs = [(rule, tuple(_word_tokens(rule))) for rule in raw]
    pairs = [(rule, tokens) for rule, tokens in pairs if tokens]
    raw = [rule for rule, _tokens in pairs]
    compiled = [tokens for _rule, tokens in pairs]
    _WORD_CACHE[kind] = (now + _WORD_CACHE_TTL, raw, compiled)
    return raw, compiled


async def words(kind: str) -> list[str]:
    raw, _compiled = await _load_word_rules(kind)
    return list(raw)


def _word_tokens(value: str) -> list[str]:
    """Normalise puis découpe un texte en mots complets.

    Les espaces, tirets, points, underscores et caractères spéciaux sont
    considérés comme des séparateurs. Ainsi, la règle ``cp`` correspond à
    ``je_cp_quoi`` mais pas à ``jecpquoi``.
    """
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return _TOKEN_RE.findall(normalized)


def _contains_complete_rule(rule: str, tokens: list[str]) -> bool:
    """Recherche une règle composée d'un ou plusieurs mots entiers consécutifs."""
    rule_tokens = _word_tokens(rule)
    if not rule_tokens or len(rule_tokens) > len(tokens):
        return False

    size = len(rule_tokens)
    return any(
        tokens[index:index + size] == rule_tokens
        for index in range(len(tokens) - size + 1)
    )


async def matched_word_rule(kind: str, text: str) -> str | None:
    """Retourne la première règle complète trouvée, avec règles pré-tokenisées."""
    tokens = _word_tokens(text)
    if not tokens:
        return None
    raw_rules, compiled_rules = await _load_word_rules(kind)
    for raw_rule, rule_tokens in zip(raw_rules, compiled_rules):
        size = len(rule_tokens)
        if size <= len(tokens) and any(
            tuple(tokens[index:index + size]) == rule_tokens
            for index in range(len(tokens) - size + 1)
        ):
            return raw_rule
    return None


async def text_has_word(kind: str, text: str) -> bool:
    """Vérifie les règles par mots complets."""
    return await matched_word_rule(kind, text) is not None


async def restrict(bot: Bot, chat_id: int, user_id: int, days: int) -> bool:
    if await protected(user_id):
        return False
    until = datetime.utcnow() + timedelta(days=days)
    try:
        from app.services.multigroup import global_mute
        return await global_mute(
            bot, user_id, until,
            source_chat_id=chat_id,
            source='moderation',
            reason=f'restriction {days} jour(s)',
        )
    except Exception as exc:
        await log_error('restrict_global', exc)
        return False


async def ban(bot: Bot, chat_id: int, user_id: int) -> bool:
    if await protected(user_id):
        return False
    try:
        from app.services.multigroup import global_ban
        return await global_ban(
            bot, user_id,
            source_chat_id=chat_id,
            source='moderation',
        )
    except Exception as exc:
        await log_error('ban_global', exc)
        return False


async def delete(bot: Bot, msg: Message) -> bool:
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
        return True
    except Exception as exc:
        await log_error("delete_message", exc)
        return False


async def record_media(
    msg: Message, bot: Bot | None = None, banned: bool = False, probe: MediaProbe | None = None
) -> int:
    """Enregistre le média. Avec bot, l'ID Telegram et le SHA256 sont stockés."""
    if bot is None:
        # Compatibilité prudente : sans Bot, impossible de calculer le SHA256.
        from app.db.models import MediaHash

        entries = media_file_entries(msg)
        async with SessionLocal() as db:
            for unique, file_id, media_type in entries:
                result = await db.execute(select(MediaHash).where(MediaHash.file_unique_id == unique))
                rows = list(result.scalars().all())
                if not rows:
                    db.add(MediaHash(
                        user_id=msg.from_user.id if msg.from_user else None,
                        file_unique_id=unique,
                        file_id=file_id,
                        media_type=media_type,
                        banned=banned,
                    ))
                else:
                    for row in rows:
                        row.file_id = file_id
                        row.media_type = media_type
                        if banned:
                            row.banned = True
            await db.commit()
        stored = len(entries)
    else:
        stored = await store_message_hashes(msg, bot, banned=banned, probe=probe)

    if msg.from_user and not banned and media_file_entries(msg):
        session_id = int(await st.get_value("active_session_id", "0") or "0")
        await increment_media_count(msg.from_user.id, session_id)
    return stored


async def contains_banned_hash(bot: Bot, msg: Message) -> bool:
    """Compatibilité : retourne seulement un booléen."""
    return (await find_banned_hash(bot, msg)).matched


async def moderate_message(bot: Bot, msg: Message) -> bool:
    """Modère les DEUX groupes principaux, même lorsque l'un est inactif.

    Les règles de sécurité (liens, hash-ban, anti-repost, mots interdits) sont
    globales A+B. Seul l'enregistrement d'un nouveau média et la copie VIP sont
    réservés au groupe actif réellement ouvert.
    """
    if not msg.from_user:
        return False

    await track(msg.chat.id, msg.message_id, msg.from_user.id, "message", is_media(msg))
    from app.services.multigroup import is_main_group, active_group_id
    if not await is_main_group(msg.chat.id):
        return True

    uid = msg.from_user.id
    text = msg.text or msg.caption or ""
    trusted = uid in _TRUSTED_IDS
    admin = uid in _ADMIN_IDS
    active = await active_group_id()
    open_ = await st.is_open()
    active_here = bool(active and msg.chat.id == active)
    media = is_media(msg)
    may_store_new_media = bool(active_here and (open_ or trusted or admin))

    # Anti-retour : actif dans A comme dans B. Si quelqu'un rejoint puis publie
    # immédiatement dans le groupe fermé, la même politique globale s'applique.
    if media and not (trusted or admin):
        if await enforce_fast_join(bot, msg):
            return False

    if media:
        # 1) Hash-ban et anti-repost exacts par ID, communs à A+B.
        match = await find_banned_id(msg)
        if match.matched:
            deleted = await delete(bot, msg)
            user_banned = await ban(bot, msg.chat.id, uid)
            await record_repost_verification(
                match=match, deleted=deleted, user_banned=user_banned,
                pipeline_stopped=True, user_id=uid, chat_id=msg.chat.id,
                message_id=msg.message_id,
            )
            return False

        anti_repost_on = not (trusted or admin) and await anti_repost_enabled()
        if anti_repost_on:
            repost, method = await find_repost_by_id(msg)
            if repost:
                await enforce_anti_repost_match(bot, msg, method)
                return False

        # 2) Un seul téléchargement pour SHA + perceptuel.
        probe = await open_media_probe(bot, msg)
        if probe is None:
            # On n'enregistre un nouveau média que s'il appartient à la vraie
            # session active. Un média envoyé dans le groupe fermé est supprimé
            # plus bas et ne devient pas une référence anti-repost.
            if may_store_new_media:
                await record_media(msg, bot=None)
                remember_stored_keys(msg, None)
        else:
            try:
                match = await find_banned_sha(probe)
                if match.matched:
                    deleted = await delete(bot, msg)
                    user_banned = await ban(bot, msg.chat.id, uid)
                    await record_repost_verification(
                        match=match, deleted=deleted, user_banned=user_banned,
                        pipeline_stopped=True, user_id=uid, chat_id=msg.chat.id,
                        message_id=msg.message_id,
                    )
                    return False

                if anti_repost_on:
                    repost, method = await find_repost_by_sha(probe.sha256)
                    if repost:
                        await enforce_anti_repost_match(bot, msg, method)
                        return False

                match = await find_banned_perceptual(probe, msg)
                if match.matched:
                    deleted = await delete(bot, msg)
                    user_banned = await ban(bot, msg.chat.id, uid)
                    await record_repost_verification(
                        match=match, deleted=deleted, user_banned=user_banned,
                        pipeline_stopped=True, user_id=uid, chat_id=msg.chat.id,
                        message_id=msg.message_id,
                    )
                    return False

                if anti_repost_on:
                    repost, method = await find_repost_by_perceptual(probe, msg)
                    if repost:
                        await enforce_anti_repost_match(bot, msg, method)
                        return False

                if may_store_new_media:
                    await record_media(msg, bot=bot, probe=probe)
                    remember_stored_keys(msg, probe.sha256)
            finally:
                close_media_probe(probe)

    # Le contrôle anti-lien est volontairement AVANT le rejet du groupe inactif.
    # Avant cette correction, B court-circuitait toute la modération quand A était actif.
    if has_link(text):
        await delete(bot, msg)
        if not (trusted or admin):
            await ban(bot, msg.chat.id, uid)
        return False

    # Admin/trusted gardent leur immunité historique pour les autres règles.
    if trusted or admin:
        return True

    if has_command(text):
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 1)
        return False

    if msg.video_note:
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 1)
        return False

    if has_mention(text):
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 2)
        return False

    if await text_has_word("ban", text):
        await delete(bot, msg)
        await ban(bot, msg.chat.id, uid)
        return False

    if await text_has_word("forbidden", text):
        await delete(bot, msg)
        await restrict(bot, msg.chat.id, uid, 1)
        return False

    # Le groupe non sélectionné et un groupe fermé restent interdits à la
    # publication membre, mais seulement APRÈS les contrôles de sécurité globaux.
    if not active_here or not open_:
        await delete(bot, msg)
        return False

    if text and not media:
        if not await has_sent_media(uid):
            await delete(bot, msg)
            warning = await bot.send_message(
                msg.chat.id,
                f"{display_name(msg.from_user)}, envoie d’abord un média avant d’écrire.",
            )
            await track(msg.chat.id, warning.message_id, None, "temp", False)
            return False

    return True
