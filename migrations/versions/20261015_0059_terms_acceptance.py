"""Принятие пользовательского соглашения (версия и время)."""
import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("terms_version", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
