"""Обзор админки: статистика по системам игры (2026-10-13).

Старый обзор (admin_service.overview_stats) знал только игроков, уровни,
экономику и смерти. С тех пор появились гильдии, рыбалка, добыча, рейды,
разломы, торговля, биржа, походы, Метка Хранителя, промокоды и репорты -
здесь их живое состояние и активность за сутки.

Каждый блок - заголовок и строки «подпись - значение», уже по-русски:
фронтенд рисует их как есть и ничего не переводит сам.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.economy.exchange import Exchange
from models import (
    BugReport,
    Character,
    CharacterCart,
    CharacterFish,
    CharacterLootbox,
    CharacterVoyage,
    ExchangeOrder,
    ExchangeState,
    Guild,
    GuildCell,
    GuildMember,
    GuildSiege,
    MiningEvent,
    MountTravel,
    PromoActivation,
    RaidRun,
    Rift,
    TradeCaravan,
    WorldBoss,
)


def _row(label: str, value) -> dict:
    return {"label": label, "value": value}


async def _count(db: AsyncSession, model, *where) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def systems_stats(db: AsyncSession) -> list[dict]:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    finished = Character.creation_state.is_(None)

    # --- Гильдии ---
    guilds = await _count(db, Guild)
    members = await _count(db, GuildMember)
    top_level = await db.scalar(select(func.max(Guild.level)))
    treasury = await db.scalar(select(func.coalesce(func.sum(Guild.treasury_gold), 0)))
    cells = await _count(db, GuildCell, GuildCell.status == "held")
    claiming = await _count(db, GuildCell, GuildCell.status == "claiming")
    sieges_open = await _count(db, GuildSiege, GuildSiege.status.in_(("scheduled", "running")))
    sieges_day = await _count(db, GuildSiege, GuildSiege.finished_at >= day_ago)
    guild_block = [
        _row("Гильдий / участников в них", f"{guilds} / {members}"),
        _row("Высший уровень гильдии", top_level or 0),
        _row("Золото во всех казнах", int(treasury or 0)),
        _row("Земель занято / закладывается", f"{cells} / {claiming}"),
        _row("Осад назначено или идёт / закончено за сутки", f"{sieges_open} / {sieges_day}"),
    ]

    # --- Рыбалка и добыча ---
    fishers = await _count(db, Character, finished, Character.fishing_level > 1)
    fishing_now = await _count(db, Character, Character.fishing_bite_at.is_not(None))
    top_fishing = await db.scalar(select(func.max(Character.fishing_level)))
    fish_kg = await db.scalar(select(func.coalesce(func.sum(CharacterFish.total_grams), 0)))
    miners = await _count(db, Character, finished, Character.mining_level > 1)
    digging_now = await _count(db, Character, Character.mining_ends_at.is_not(None))
    top_mining = await db.scalar(select(func.max(Character.mining_level)))
    digs_day = await _count(db, MiningEvent, MiningEvent.kind == "dig", MiningEvent.created_at >= day_ago)
    trades_block = [
        _row("Рыбачат сейчас / копают сейчас", f"{fishing_now} / {digging_now}"),
        _row("Рыбаков (2+ уровень) / лучший уровень", f"{fishers} / {top_fishing or 1}"),
        _row("Рыбы в садках у игроков, кг", round(int(fish_kg or 0) / 1000, 1)),
        _row("Горняков (2+ уровень) / лучший уровень", f"{miners} / {top_mining or 1}"),
        _row("Кусков руды добыто за сутки", digs_day),
    ]

    # --- Рейды, разломы, мировой босс ---
    raids_now = await _count(db, RaidRun, RaidRun.status == "active")
    raids_day = await _count(db, RaidRun, RaidRun.created_at >= day_ago)
    rifts_open = await _count(db, Rift, Rift.status == "active")
    rifts_busy = await _count(db, Rift, Rift.status == "active", Rift.state != "free")
    boss_alive = await _count(db, WorldBoss, WorldBoss.status == "active")
    bosses_day = await _count(db, WorldBoss, WorldBoss.ended_at >= day_ago)
    pve_block = [
        _row("Рейдов идёт сейчас / начато за сутки", f"{raids_now} / {raids_day}"),
        _row("Разломов открыто / из них заняты", f"{rifts_open} / {rifts_busy}"),
        _row("Мировой босс на карте / побеждён или ушёл за сутки", f"{'да' if boss_alive else 'нет'} / {bosses_day}"),
    ]

    # --- Торговля, походы, маунты ---
    carts = await _count(db, CharacterCart)
    trade_profit = await db.scalar(select(func.coalesce(func.sum(CharacterCart.profit_total), 0)))
    caravans = await _count(db, TradeCaravan, TradeCaravan.expires_at > now)
    voyages = await _count(db, CharacterVoyage, CharacterVoyage.status == "away")
    riding = await _count(db, MountTravel, MountTravel.status.in_(("traveling", "ambushed")))
    road_block = [
        _row("Повозок куплено / прибыль торговцев всего", f"{carts} / {int(trade_profit or 0)}"),
        _row("Караванов на карте", caravans),
        _row("В долгом походе сейчас", voyages),
        _row("В пути на маунте сейчас", riding),
    ]

    # --- Биржа и донат ---
    # Читаем без блокировки (в отличие от сделки): обзору хватит текущего числа.
    net_sold = int(await db.scalar(select(ExchangeState.net_sold).where(ExchangeState.id == 1)) or 0)
    lot = bc.EXCHANGE_BLOCK_SIZE
    deals_day = await _count(db, ExchangeOrder, ExchangeOrder.created_at >= day_ago)
    premium = await _count(db, Character, finished, Character.premium_until > now)
    promo_day = await _count(db, PromoActivation, PromoActivation.activated_at >= day_ago)
    chests_closed = await _count(db, CharacterLootbox, CharacterLootbox.status == "closed")
    money_block = [
        _row(f"Курс биржи: купить / продать лот {lot} 💎",
             f"{Exchange.buy_cost(net_sold, lot)} / {Exchange.sell_gain(net_sold, lot)}"),
        _row("Сделок на бирже за сутки", deals_day),
        _row("С Меткой Хранителя сейчас", premium),
        _row("Промокодов активировано за сутки", promo_day),
        _row("Неоткрытых Пепельных ларцов у игроков", chests_closed),
    ]

    # --- Репорты ---
    bugs_new = await _count(db, BugReport, BugReport.status == "new")
    bugs_day = await _count(db, BugReport, BugReport.created_at >= day_ago)
    bug_block = [
        _row("Новых, не разобранных", bugs_new),
        _row("Пришло за сутки", bugs_day),
    ]

    return [
        {"title": "🏰 Гильдии", "rows": guild_block},
        {"title": "🎣 Рыбалка и добыча", "rows": trades_block},
        {"title": "🌀 Рейды, разломы, босс", "rows": pve_block},
        {"title": "🐂 Торговля и дороги", "rows": road_block},
        {"title": "💎 Биржа и донат", "rows": money_block},
        {"title": "🐞 Баг-репорты", "rows": bug_block},
    ]
