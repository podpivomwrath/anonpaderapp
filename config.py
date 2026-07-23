"""Конфигурация приложения: Pydantic Settings, читает .env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- VK ---
    # Пустые значения по умолчанию, чтобы alembic/pytest работали без токена.
    # main.py проверяет заполненность перед запуском бота.
    vk_token: str = Field(default="", description="Токен сообщества VK")
    vk_group_id: int = Field(default=0, description="ID сообщества")
    vk_confirmation_code: str = Field(
        default="", description="Строка подтверждения сервера из настроек Callback API"
    )
    vk_secret: str = Field(
        default="", description="Секретный ключ Callback API (если задан — проверяется)"
    )

    # --- Режим получения событий ---
    # "polling" — LongPoll, публичный URL не нужен (локальная разработка);
    # "callback" — Callback API, нужен публичный URL (прод)
    bot_mode: str = "polling"

    # --- Веб-сервер (health-check; в режиме callback — ещё и вебхук) ---
    host: str = "0.0.0.0"
    port: int = 8080

    # --- Хранилища ---
    database_url: str = "postgresql+asyncpg://mmo:mmo@localhost:5432/mmo"
    redis_url: str = "redis://localhost:6379/0"

    # --- Бой ---
    # Окно хода группового PvP (п.3.1 дизайна: 1 минута). PvE — без таймера.
    combat_tick_window_seconds: float = 60.0

    # --- Респавн ---
    # Живой отсчёт до возрождения (edit сообщения). Если упрёмся в rate limit VK —
    # выключить: покажется статичное «Возрождение через ~N мин» без обновления.
    respawn_live_countdown: bool = True
    # Период фонового батч-сканера мёртвых игроков (один общий job, не на игрока)
    respawn_scan_seconds: float = 10.0

    # --- VK Mini App (хаб персонажа) ---
    # Секрет приложения из vk.com/editapp (не Callback-секрет!) — им проверяется
    # подпись launch-параметров на каждом запросе /api/miniapp/*.
    vk_miniapp_secret: str = Field(
        default="", description="Секретный ключ VK Mini App для проверки подписи launch-параметров"
    )
    # Ссылка на мини-апп для кнопки в боте (https://vk.com/app<APP_ID>); заполняется
    # после создания приложения в VK, пока — плейсхолдер.
    vk_miniapp_url: str = Field(default="", description="URL мини-аппа (vk.com/app<APP_ID>)")
    # Origin фронтенда мини-аппа для CORS (напр. https://xxxx.vk-apps.com в проде,
    # https://localhost:5173 или туннель — в разработке)
    vk_miniapp_origin: str = Field(default="*", description="Разрешённый CORS-origin мини-аппа")
    # Пока нигде не используется кодом — задел на будущие серверные вызовы VK API
    # от имени приложения (Service Token), сохранён про запас.
    vk_service_key: str = Field(default="", description="Сервисный ключ приложения VK (Service Token)")

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
