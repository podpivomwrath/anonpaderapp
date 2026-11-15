"""Бесплатный сброс характеристик на 60 уровне (2026-11-15, владелец):
отметка, что он уже потрачен."""

import sqlalchemy as sa
from alembic import op

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("cap_respec_used", sa.Boolean, nullable=False, server_default="false"))


def downgrade():
    op.drop_column("characters", "cap_respec_used")
