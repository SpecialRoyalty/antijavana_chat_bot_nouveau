import re
from aiogram import Bot
from aiogram.types import Message
from app.services.permissions import is_admin, is_trusted

LINK_RE = re.compile(r'(https?://|t\.me/|www\.)', re.I)
MENTION_RE = re.compile(r'@\w+', re.I)
BOT_MENTION_RE = re.compile(r'@\w*bot\b', re.I)

FORBIDDEN_WORDS: set[str] = set()
BAN_WORDS: set[str] = set()
BANNED_NAME_WORDS: set[str] = set()


def contains_casefold(text: str, words: set[str]) -> bool:
    t = text.casefold()
    return any(w.casefold() in t for w in words)


async def moderate_message(bot: Bot, message: Message) -> bool:
    user = message.from_user
    user_id = user.id if user else None
    if is_admin(user_id):
        return False

    text = message.text or message.caption or ''

    # Trusted protégés, mais liens interdits pour tout le monde.
    if LINK_RE.search(text):
        await safe_delete(message)
        if not is_trusted(user_id):
            await restrict_user(bot, message.chat.id, user_id, days=1)
        return True

    if is_trusted(user_id):
        return False

    if BOT_MENTION_RE.search(text):
        await ban_user(bot, message.chat.id, user_id)
        await safe_delete(message)
        return True

    if MENTION_RE.search(text):
        await safe_delete(message)
        await restrict_user(bot, message.chat.id, user_id, days=2)
        return True

    if contains_casefold(text, BAN_WORDS):
        await ban_user(bot, message.chat.id, user_id)
        await safe_delete(message)
        return True

    if contains_casefold(text, FORBIDDEN_WORDS):
        await safe_delete(message)
        await restrict_user(bot, message.chat.id, user_id, days=1)
        return True

    if message.text and message.text.startswith('/'):
        await safe_delete(message)
        await restrict_user(bot, message.chat.id, user_id, days=1)
        return True

    if message.video_note:
        await safe_delete(message)
        await restrict_user(bot, message.chat.id, user_id, days=1)
        return True

    return False


async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def restrict_user(bot: Bot, chat_id: int, user_id: int | None, days: int = 1) -> None:
    if not user_id:
        return
    from datetime import datetime, timedelta
    until = datetime.utcnow() + timedelta(days=days)
    await bot.restrict_chat_member(chat_id, user_id, permissions={'can_send_messages': False}, until_date=until)


async def ban_user(bot: Bot, chat_id: int, user_id: int | None) -> None:
    if not user_id:
        return
    await bot.ban_chat_member(chat_id, user_id)
