"""Пол выбирается один раз (2026-10-22, владелец): пусто - ещё не выбирал.

0082 ставил всем "m" по умолчанию, и выбравшего мужской силуэт не отличить
от не выбиравшего. Женский - точно выбор, его оставляем; остальным - пусто,
мини-апп спросит при первом заходе в профиль."""
import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("characters", "gender", existing_type=sa.String(1), nullable=True, server_default=None)
    op.execute("UPDATE characters SET gender = NULL WHERE gender <> 'f'")


def downgrade():
    op.execute("UPDATE characters SET gender = 'm' WHERE gender IS NULL")
    op.alter_column("characters", "gender", existing_type=sa.String(1), nullable=False, server_default="m")
