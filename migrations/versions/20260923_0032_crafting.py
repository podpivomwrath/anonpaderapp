"""Crafting: rolled stats on items, bound flag, consumable upgrade tools."""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    # craft_base_stats - ролл на 100%; base_stats рядом с ним это он же,
    # умноженный на craft_efficiency. Два поля вместо одного нужны, чтобы
    # подъём по ступеням не был цепочкой округлений.
    op.add_column("items", sa.Column("craft_source_id", sa.String(64), nullable=True))
    op.add_column("items", sa.Column("craft_spec", sa.String(16), nullable=True))
    op.add_column("items", sa.Column("craft_efficiency", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("craft_base_stats", sa.JSON(), nullable=True))
    op.add_column(
        "items",
        sa.Column("craft_recrafts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "items",
        sa.Column("bound", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Инструмент - счётчик, а не предмет: он безымянный и отличается ровно
    # одним числом, строка в items на каждый штук засоряла бы инвентарь.
    op.create_table(
        "character_craft_tools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ceiling", sa.Integer(), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "ceiling", name="uq_craft_tool_char_ceiling"),
    )
    op.create_index(
        "ix_character_craft_tools_character_id", "character_craft_tools", ["character_id"]
    )


def downgrade():
    op.drop_index("ix_character_craft_tools_character_id", table_name="character_craft_tools")
    op.drop_table("character_craft_tools")
    for column in (
        "bound", "craft_recrafts", "craft_base_stats",
        "craft_efficiency", "craft_spec", "craft_source_id",
    ):
        op.drop_column("items", column)
