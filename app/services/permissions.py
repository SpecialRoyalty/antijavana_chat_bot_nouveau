from aiogram import Bot
from app.config import get_settings

settings = get_settings()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in settings.admin_id_set)


def is_trusted(user_id: int | None) -> bool:
    return bool(user_id and user_id in settings.trusted_id_set)


async def close_group(bot: Bot, chat_id: int) -> None:
    await bot.set_chat_permissions(chat_id, permissions={
        'can_send_messages': False,
        'can_send_audios': False,
        'can_send_documents': False,
        'can_send_photos': False,
        'can_send_videos': False,
        'can_send_video_notes': False,
        'can_send_voice_notes': False,
        'can_send_polls': False,
        'can_send_other_messages': False,
        'can_add_web_page_previews': False,
    })


async def open_group(bot: Bot, chat_id: int) -> None:
    await bot.set_chat_permissions(chat_id, permissions={
        'can_send_messages': True,
        'can_send_audios': True,
        'can_send_documents': True,
        'can_send_photos': True,
        'can_send_videos': True,
        'can_send_video_notes': False,
        'can_send_voice_notes': True,
        'can_send_polls': False,
        'can_send_other_messages': True,
        'can_add_web_page_previews': False,
    })
