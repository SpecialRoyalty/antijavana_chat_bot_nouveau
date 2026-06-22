from aiogram.types import Message
from app.db.session import SessionLocal
from app.db.models import MediaHash
from sqlalchemy import select, func


def media_file_entries(msg: Message):
    if msg.photo: return [(msg.photo[-1].file_unique_id, msg.photo[-1].file_id, 'photo')]
    if msg.video: return [(msg.video.file_unique_id, msg.video.file_id, 'video')]
    if msg.document: return [(msg.document.file_unique_id, msg.document.file_id, 'document')]
    if msg.animation: return [(msg.animation.file_unique_id, msg.animation.file_id, 'animation')]
    return []

async def ban_hash_from_message(msg: Message):
    entries = media_file_entries(msg)
    if not entries: return 0
    count=0
    async with SessionLocal() as db:
        for unique,file_id,typ in entries:
            res=await db.execute(select(MediaHash).where(MediaHash.file_unique_id==unique))
            mh=res.scalar_one_or_none()
            if not mh:
                mh=MediaHash(user_id=msg.from_user.id if msg.from_user else None,file_unique_id=unique,file_id=file_id,media_type=typ,banned=True)
                db.add(mh)
            else:
                mh.banned=True; mh.file_id=file_id; mh.media_type=typ
            count+=1
        await db.commit()
    return count

async def banned_hash_count():
    async with SessionLocal() as db:
        return int((await db.execute(select(func.count(MediaHash.id)).where(MediaHash.banned==True))).scalar() or 0)
