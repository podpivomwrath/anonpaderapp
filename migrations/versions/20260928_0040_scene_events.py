"""События со сценами (патч 110): следы на карте и эффекты на N боёв."""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_trails",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "character_event_effects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("effect_id", sa.String(32), nullable=False),
        sa.Column("fights_left", sa.Integer(), nullable=False),
        sa.UniqueConstraint("character_id", "effect_id", name="uq_character_event_effects"),
    )
    op.create_index("ix_character_event_effects_character_id", "character_event_effects", ["character_id"])


def downgrade():
    op.drop_index("ix_character_event_effects_character_id", "character_event_effects")
    op.drop_table("character_event_effects")
    op.drop_table("event_trails")
