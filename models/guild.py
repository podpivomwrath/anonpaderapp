"""Гильдии: состав, казна и склад, территория с базами и постройками, осады,
гильдейские задания, сезоны, гильдейский босс.

Числа - game/economy/guild_config.py, древо - game/guild/tree.py, логика -
services/guild_*.py.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Guild(Base):
    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32))
    tag: Mapped[str] = mapped_column(String(8))
    level: Mapped[int] = mapped_column(default=1)
    #: Слава в ТЕКУЩЕМ уровне (как опыт персонажа) и за всё время.
    fame: Mapped[int] = mapped_column(BigInteger, default=0)
    fame_total: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Слава в текущем месяце - идёт в сезонный зачёт.
    fame_month: Mapped[int] = mapped_column(BigInteger, default=0)
    treasury_gold: Mapped[int] = mapped_column(BigInteger, default=0)
    treasury_gems: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Взятые узлы древа (id из game/guild/tree.py).
    tree_nodes: Mapped[list] = mapped_column(JSON, default=list)
    tree_gold_spent: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Налог гильдии, %: доля любого золота, которое получают участники.
    gold_tax: Mapped[int] = mapped_column(default=0)
    tax_collected: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Час начала окна осад (МСК): осада на земли гильдии начинается только в него.
    siege_hour: Mapped[int] = mapped_column(default=20)
    #: Венец сезона: до какого момента гильдия носит его.
    crown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    season_wins: Mapped[int] = mapped_column(default=0)
    last_boss_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("uq_guilds_name_lower", func.lower(Guild.name), unique=True)
Index("uq_guilds_tag_lower", func.lower(Guild.tag), unique=True)


class GuildMember(Base):
    __tablename__ = "guild_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    rank: Mapped[str] = mapped_column(String(16), default="recruit")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    contribution_total: Mapped[int] = mapped_column(BigInteger, default=0)
    contribution_week: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Понедельник недели, к которой относится contribution_week.
    week_start: Mapped[date | None] = mapped_column(Date, nullable=True)


class GuildInvite(Base):
    """kind: invite (гильдия зовёт игрока) | apply (игрок просится сам)."""

    __tablename__ = "guild_invites"
    __table_args__ = (UniqueConstraint("guild_id", "character_id", "kind", name="uq_guild_invite"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    from_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GuildLog(Base):
    """Журнал гильдии: взносы, траты, стройка, осады. Видят все участники."""

    __tablename__ = "guild_log"
    __table_args__ = (Index("ix_guild_log_guild_created", "guild_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"))
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuildOre(Base):
    __tablename__ = "guild_ore"
    __table_args__ = (UniqueConstraint("guild_id", "ore_id", "grade", name="uq_guild_ore"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    ore_id: Mapped[str] = mapped_column(String(32))
    grade: Mapped[str] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(BigInteger, default=0)


class GuildItem(Base):
    """Снаряжение на складе. Сам предмет остаётся строкой items - со склада
    он уходит обратно в инвентарь тем же экземпляром."""

    __tablename__ = "guild_items"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    deposited_by: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )


class GuildCell(Base):
    """Клетка гильдии: сначала закладка знамени, потом база.

    status: claiming - знамя заложено, идёт закладка; held - своя земля.
    """

    __tablename__ = "guild_cells"
    __table_args__ = (UniqueConstraint("x", "y", name="uq_guild_cells_xy"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    mine_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="claiming")
    claim_progress: Mapped[int] = mapped_column(default=0)
    claim_needed: Mapped[int] = mapped_column(default=0)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    base_tier: Mapped[str] = mapped_column(String(16), default="outpost")
    #: Подъём базы до следующей ступени: куда и когда закончится.
    upgrade_to: Mapped[str | None] = mapped_column(String(16), nullable=True)
    upgrade_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shield_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Накопленная доля следующей руды у шахты (0..1).
    shaft_progress: Mapped[float] = mapped_column(Float, default=0.0)
    shaft_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tower_warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuildBuilding(Base):
    __tablename__ = "guild_buildings"
    __table_args__ = (UniqueConstraint("cell_id", "building", name="uq_guild_building"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cell_id: Mapped[int] = mapped_column(ForeignKey("guild_cells.id", ondelete="CASCADE"), index=True)
    building: Mapped[str] = mapped_column(String(16))
    #: Готовый уровень. 0 - строится первый.
    level: Mapped[int] = mapped_column(default=0)
    upgrading_to: Mapped[int | None] = mapped_column(nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuildSiege(Base):
    """status: scheduled | running | captured | repelled | failed | cancelled."""

    __tablename__ = "guild_sieges"
    __table_args__ = (Index("ix_guild_sieges_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attacker_guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    defender_guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    cell_id: Mapped[int | None] = mapped_column(
        ForeignKey("guild_cells.id", ondelete="SET NULL"), nullable=True
    )
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    gather_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(String(300), nullable=True)


class GuildDaily(Base):
    """Личная гильдейская ежедневка участника."""

    __tablename__ = "guild_dailies"
    __table_args__ = (
        UniqueConstraint("character_id", "date", "metric", name="uq_guild_daily"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    metric: Mapped[str] = mapped_column(String(16))
    target: Mapped[int] = mapped_column()
    progress: Mapped[int] = mapped_column(default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class GuildWeekly(Base):
    """Общее недельное задание гильдии."""

    __tablename__ = "guild_weekly"
    __table_args__ = (
        UniqueConstraint("guild_id", "week_start", "metric", name="uq_guild_weekly"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    metric: Mapped[str] = mapped_column(String(16))
    target: Mapped[int] = mapped_column(BigInteger)
    progress: Mapped[int] = mapped_column(BigInteger, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    #: {character_id: внесённый прогресс} - по нему делится вклад.
    contributors: Mapped[dict] = mapped_column(JSON, default=dict)


class GuildSeasonScore(Base):
    __tablename__ = "guild_season_scores"
    __table_args__ = (UniqueConstraint("season", "guild_id", name="uq_guild_season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: "YYYY-MM"
    season: Mapped[str] = mapped_column(String(7))
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    points: Mapped[int] = mapped_column(BigInteger, default=0)
    last_snapshot: Mapped[date | None] = mapped_column(Date, nullable=True)


class GuildBoss(Base):
    """Страж цитадели: призывается гильдией, бьют только свои."""

    __tablename__ = "guild_bosses"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    max_hp: Mapped[int] = mapped_column(BigInteger)
    hp: Mapped[int] = mapped_column(BigInteger)
    #: active | killed | escaped
    status: Mapped[str] = mapped_column(String(16), default="active")
    spawned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuildBossContribution(Base):
    __tablename__ = "guild_boss_contributions"
    __table_args__ = (
        UniqueConstraint("boss_id", "character_id", name="uq_guild_boss_contribution"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    boss_id: Mapped[int] = mapped_column(ForeignKey("guild_bosses.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    damage: Mapped[int] = mapped_column(BigInteger, default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
