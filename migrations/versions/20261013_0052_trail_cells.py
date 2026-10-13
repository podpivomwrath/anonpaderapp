"""След события помнит свою длину: награда финала растёт с расстоянием."""
import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("event_trails", sa.Column("cells", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("event_trails", "cells")
