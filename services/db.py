"""Подключение к БД: ленивая инициализация движка и фабрики сессий."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            connect_args={
                "server_settings": {
                    # Защита от "зависшей" транзакции (баг в коде — сессия
                    # открыта, но ничего не коммитит/не закрывает, например
                    # завис сетевой вызов ВНУТРИ async with db: до commit).
                    # Без этого Postgres ждёт commit/rollback БЕСКОНЕЧНО,
                    # держа лок на строку и блокируя всех остальных игроков,
                    # пока пул соединений не исчерпается целиком (два таких
                    # инцидента подряд — идентичная картина: idle in
                    # transaction на UPDATE characters.last_active_at,
                    # растущая очередь блокированных запросов, затем
                    # QueuePool timeout на новых подключениях). 5 минут —
                    # заведомо больше любого легитимного сценария (обычная
                    # транзакция — доли секунды), но НЕ бесконечность.
                    "idle_in_transaction_session_timeout": "300000",
                    # Аналогично для отдельного медленного/зависшего запроса
                    # (не между запросами, а конкретный SQL) — страховка от
                    # другого класса той же проблемы.
                    "statement_timeout": "60000",
                },
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
