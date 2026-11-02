"""«Упрямый лоб» (2026-11-02, владелец): 8% -> 4%, но в PvP в полную силу,
а не вполсилы (стат работает только в PvP). Копия эффекта на персонаже
(rune_effects) делится пополам - значение руны линейно от базы."""
from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

KEY = "rune:stubborn_brow"


def _scale(factor: float) -> None:
    op.execute(
        f"""
        UPDATE characters
        SET rune_effects = jsonb_set(
            rune_effects::jsonb, '{{{KEY}}}',
            to_jsonb(round(((rune_effects::jsonb ->> '{KEY}')::numeric * {factor}), 6))
        )::json
        WHERE rune_effects::jsonb ? '{KEY}'
        """
    )


def upgrade():
    _scale(0.5)


def downgrade():
    _scale(2)
