"""Гильдии: состав, казна и склад, территория, постройки, осады, задания,
сезоны, гильдейский босс; гильдейские поля персонажа."""
import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "guilds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("tag", sa.String(8), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fame", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fame_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fame_month", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("treasury_gold", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("treasury_gems", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tree_nodes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tree_gold_spent", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("siege_hour", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("crown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("season_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_boss_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_guilds_name_lower", "guilds", [sa.text("lower(name)")], unique=True)
    op.create_index("uq_guilds_tag_lower", "guilds", [sa.text("lower(tag)")], unique=True)

    op.create_table(
        "guild_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.String(16), nullable=False, server_default="recruit"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("contribution_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("contribution_week", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("week_start", sa.Date(), nullable=True),
        sa.UniqueConstraint("character_id", name="uq_guild_members_character_id"),
    )
    op.create_index("ix_guild_members_guild_id", "guild_members", ["guild_id"])
    op.create_index("ix_guild_members_character_id", "guild_members", ["character_id"])

    op.create_table(
        "guild_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("guild_id", "character_id", "kind", name="uq_guild_invite"),
    )
    op.create_index("ix_guild_invites_guild_id", "guild_invites", ["guild_id"])
    op.create_index("ix_guild_invites_character_id", "guild_invites", ["character_id"])

    op.create_table(
        "guild_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_guild_log_guild_created", "guild_log", ["guild_id", "created_at"])

    op.create_table(
        "guild_ore",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ore_id", sa.String(32), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("guild_id", "ore_id", "grade", name="uq_guild_ore"),
    )
    op.create_index("ix_guild_ore_guild_id", "guild_ore", ["guild_id"])

    op.create_table(
        "guild_items",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deposited_by", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_guild_items_guild_id", "guild_items", ["guild_id"])

    op.create_table(
        "guild_cells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("mine_id", sa.String(48), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="claiming"),
        sa.Column("claim_progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_needed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("base_tier", sa.String(16), nullable=False, server_default="outpost"),
        sa.Column("upgrade_to", sa.String(16), nullable=True),
        sa.Column("upgrade_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shield_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shaft_progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("shaft_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tower_warned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("x", "y", name="uq_guild_cells_xy"),
    )
    op.create_index("ix_guild_cells_guild_id", "guild_cells", ["guild_id"])

    op.create_table(
        "guild_buildings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cell_id", sa.Integer(), sa.ForeignKey("guild_cells.id", ondelete="CASCADE"), nullable=False),
        sa.Column("building", sa.String(16), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upgrading_to", sa.Integer(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cell_id", "building", name="uq_guild_building"),
    )
    op.create_index("ix_guild_buildings_cell_id", "guild_buildings", ["cell_id"])

    op.create_table(
        "guild_sieges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attacker_guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("defender_guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cell_id", sa.Integer(), sa.ForeignKey("guild_cells.id", ondelete="SET NULL"), nullable=True),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("gather_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(300), nullable=True),
    )
    op.create_index("ix_guild_sieges_status", "guild_sieges", ["status"])
    op.create_index("ix_guild_sieges_attacker_guild_id", "guild_sieges", ["attacker_guild_id"])
    op.create_index("ix_guild_sieges_defender_guild_id", "guild_sieges", ["defender_guild_id"])

    op.create_table(
        "guild_dailies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("character_id", "date", "metric", name="uq_guild_daily"),
    )
    op.create_index("ix_guild_dailies_character_id", "guild_dailies", ["character_id"])

    op.create_table(
        "guild_weekly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("target", sa.BigInteger(), nullable=False),
        sa.Column("progress", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("contributors", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("guild_id", "week_start", "metric", name="uq_guild_weekly"),
    )
    op.create_index("ix_guild_weekly_guild_id", "guild_weekly", ["guild_id"])

    op.create_table(
        "guild_season_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season", sa.String(7), nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("points", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_snapshot", sa.Date(), nullable=True),
        sa.UniqueConstraint("season", "guild_id", name="uq_guild_season"),
    )
    op.create_index("ix_guild_season_scores_guild_id", "guild_season_scores", ["guild_id"])

    op.create_table(
        "guild_bosses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("max_hp", sa.BigInteger(), nullable=False),
        sa.Column("hp", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("spawned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_guild_bosses_guild_id", "guild_bosses", ["guild_id"])

    op.create_table(
        "guild_boss_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("boss_id", sa.Integer(), sa.ForeignKey("guild_bosses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("damage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("boss_id", "character_id", name="uq_guild_boss_contribution"),
    )
    op.create_index("ix_guild_boss_contributions_boss_id", "guild_boss_contributions", ["boss_id"])
    op.create_index(
        "ix_guild_boss_contributions_character_id", "guild_boss_contributions", ["character_id"]
    )

    op.add_column("characters", sa.Column(
        "guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_characters_guild_id", "characters", ["guild_id"])
    op.add_column("characters", sa.Column("guild_perks", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("characters", sa.Column("guild_left_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("prayer_stat", sa.String(3), nullable=True))
    op.add_column("characters", sa.Column("prayer_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column(
        "respawn_at_chapel", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.add_column("characters", sa.Column("gates_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for column in (
        "gates_used_at", "respawn_at_chapel", "prayer_until", "prayer_stat",
        "guild_left_at", "guild_perks",
    ):
        op.drop_column("characters", column)
    op.drop_index("ix_characters_guild_id", "characters")
    op.drop_column("characters", "guild_id")
    for table in (
        "guild_boss_contributions", "guild_bosses", "guild_season_scores", "guild_weekly",
        "guild_dailies", "guild_sieges", "guild_buildings", "guild_cells", "guild_items",
        "guild_ore", "guild_log", "guild_invites", "guild_members", "guilds",
    ):
        op.drop_table(table)
