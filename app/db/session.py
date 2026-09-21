from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import get_settings
from app.db.models import Base

settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration légère compatible avec les bases Railway déjà existantes.
        # ``create_all`` ne rajoute pas de colonne sur une table existante.
        # On mémorise l'heure de réception de la preuve de paiement pour calculer
        # équitablement le cycle du Pass soirée.
        await conn.execute(text(
            'ALTER TABLE vip_orders ADD COLUMN IF NOT EXISTS proof_received_at TIMESTAMP NULL'
        ))
        # Index complémentaires sur les chemins les plus fréquents. IF NOT EXISTS
        # rend la mise à jour compatible avec une base Railway déjà existante.
        await conn.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_video_fingerprints_fingerprint '
            'ON video_fingerprints (fingerprint)'
        ))
        await conn.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_tracked_chat_user_deleted '
            'ON tracked_messages (chat_id, user_id, deleted)'
        ))
        await conn.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_tracked_chat_session_deleted '
            'ON tracked_messages (chat_id, session_id, deleted)'
        ))
