"""Двор гильдии (2026-10-17): постройки без клетки на карте и Страж из Двора.

Постройка Двора - строка guild_buildings с cell_id = NULL и guild_id гильдии.
Постройки баз на карте - как раньше, с cell_id (guild_id у них пустой).
"""
import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("guild_buildings", "cell_id", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "guild_buildings",
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_guild_buildings_guild_id", "guild_buildings", ["guild_id"])
    op.create_unique_constraint("uq_guild_court_building", "guild_buildings", ["guild_id", "building"])
    op.add_column(
        "guild_bosses",
        sa.Column("court", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("guild_bosses", "court")
    op.drop_constraint("uq_guild_court_building", "guild_buildings", type_="unique")
    op.drop_index("ix_guild_buildings_guild_id", table_name="guild_buildings")
    op.drop_column("guild_buildings", "guild_id")
    op.execute("DELETE FROM guild_buildings WHERE cell_id IS NULL")
    op.alter_column("guild_buildings", "cell_id", existing_type=sa.Integer(), nullable=False)
