from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app.models import chat_message, thread, user  # noqa: F401

    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            try:
                await conn.run_sync(table.create, checkfirst=True)
            except SQLAlchemyError:
                continue

        # Keep existing databases compatible when new columns are introduced.
        try:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255)")
            )
            await conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_id ON users (google_id)")
            )
            await conn.execute(
                text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS thread_id INTEGER")
            )
            await conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'chat_messages_thread_id_fkey'
                        ) THEN
                            ALTER TABLE chat_messages
                            ADD CONSTRAINT chat_messages_thread_id_fkey
                            FOREIGN KEY (thread_id) REFERENCES threads(id);
                        END IF;
                    END
                    $$;
                    """
                )
            )
        except SQLAlchemyError:
            pass
