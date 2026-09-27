"""Круглая карта (патч 108): все по домам, любая деятельность оборвана.

Координаты старой квадратной карты на новой ничего не значат (половина из них
за краем круга), поэтому никого не переносим «примерно туда же»: каждый
персонаж с родным регионом встаёт в свой город с полным здоровьем, а всё, что
он делал - путь, поездка, снасть, добыча, бой, рейд, приглашение, - обрывается.
Идёт при остановленном боте (scripts/deploy-release.sh), так что гонок с
живыми событиями нет. Ресурсы не трогаются: инвентарь, руда в жилах, садок.

Живой мировой босс не пропадает - переезжает на свободную клетку своего
кольца на новой карте, чтобы вклад игроков в него не сгорел.
"""
import random

from alembic import op
from sqlalchemy import text

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

#: Копия world_config.CITY_COORDS на момент патча: миграция не должна
#: меняться, если города когда-нибудь переедут снова.
CITIES = {"ridge": (0, 30), "docks": (30, 0), "scorched": (0, -30), "woods": (-30, 0)}


def upgrade():
    bind = op.get_bind()
    # Добыча: начатые куски - обратно в жилы, как при обычном сбросе.
    bind.execute(text("""
        UPDATE mine_veins v SET ore_count = v.ore_count + c.n
        FROM (SELECT mining_mine_id AS mine_id, count(*) AS n FROM characters
              WHERE mining_mine_id IS NOT NULL AND mining_ends_at IS NOT NULL
              GROUP BY mining_mine_id) c
        WHERE v.mine_id = c.mine_id
    """))
    for region, (x, y) in CITIES.items():
        bind.execute(text("""
            UPDATE characters SET pos_x = :x, pos_y = :y
            WHERE region = :region
        """), {"x": x, "y": y, "region": region})
    bind.execute(text("""
        UPDATE characters SET
            travel_target_x = NULL, travel_target_y = NULL, travel_arrives_at = NULL,
            fishing_cast_at = NULL, fishing_bite_at = NULL,
            fishing_pending_fish = NULL, fishing_pending_grams = NULL,
            mining_ends_at = NULL, mining_mine_id = NULL,
            respawn_at = NULL, current_hp = NULL, screen = NULL
    """))
    bind.execute(text(
        "UPDATE mount_travels SET status = 'cancelled' WHERE status IN ('traveling', 'ambushed')"
    ))
    bind.execute(text("UPDATE pvp_battles SET finished_at = now() WHERE finished_at IS NULL"))
    bind.execute(text("UPDATE raid_runs SET status = 'interrupted' WHERE status = 'active'"))
    bind.execute(text("DELETE FROM raid_lobby_members"))
    bind.execute(text("UPDATE raid_lobbies SET status = 'finished' WHERE status IN ('waiting', 'started')"))
    bind.execute(text("UPDATE group_invites SET status = 'expired' WHERE status = 'pending'"))

    from game.world import world_boss

    rng = random.Random()
    for boss_id, ring in bind.execute(text("SELECT id, ring FROM world_bosses WHERE status = 'active'")).all():
        x, y = world_boss.pick_cell(ring, rng)
        bind.execute(text("UPDATE world_bosses SET x = :x, y = :y WHERE id = :id"), {"x": x, "y": y, "id": boss_id})


def downgrade():
    # Старые позиции не хранились - откатывать нечего, схема не менялась.
    pass
