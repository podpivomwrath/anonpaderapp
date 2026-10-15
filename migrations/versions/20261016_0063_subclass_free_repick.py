"""Повторный выбор подкласса после смены класса/подкласса - без платы
(2026-10-16, временно). Флаг ставится и тем, кто уже сменил класс и сейчас
без подкласса: признак, что подкласс был, - открытые баффы или прогресс
испытаний."""
import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "characters",
        sa.Column("subclass_free_repick", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE characters SET subclass_free_repick = true
        WHERE subclass IS NULL AND (
            id IN (SELECT character_id FROM character_unlocked_buffs)
            OR id IN (SELECT character_id FROM character_trial_progress)
        )
        """
    )


def downgrade():
    op.drop_column("characters", "subclass_free_repick")
