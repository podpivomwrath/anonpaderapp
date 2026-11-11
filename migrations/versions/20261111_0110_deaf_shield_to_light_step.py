"""«Глухой щит» сливается с «Лёгким шагом» (2026-11-11, владелец): шанс
заблокировать обычную атаку заменён шансом увернуться, а руна на уклонение
уже есть. Всё, что было у игроков от «Глухого щита», переходит в «Лёгкий шаг»:

- мастерство (впитанные копии) - складывается с мастерством «Лёгкого шага»;
- копии в сумке - становятся «Лёгким шагом»;
- вставленный «Глухой щит» - заменяется «Лёгким шагом» в том же слоте; если
  «Лёгкий шаг» уже вставлен в другой вещи, руна уходит в сумку (в экипировке
  одна руна вида);
- пресеты, мешки забегов в руинах, заявки рынка - тоже;
- копия эффектов на персонаже (rune_effects) пересчитывается.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None

OLD, NEW = "deaf_shield", "light_step"


def _add(conn, table: str, column: str, character_id: int, amount: int) -> None:
    row = conn.execute(sa.text(f"SELECT id FROM {table} WHERE character_id=:c AND rune_id=:r"),
                       {"c": character_id, "r": NEW}).first()
    if row:
        conn.execute(sa.text(f"UPDATE {table} SET {column} = {column} + :n WHERE id=:id"),
                     {"n": amount, "id": row.id})
    else:
        conn.execute(sa.text(f"INSERT INTO {table} (character_id, rune_id, {column}) VALUES (:c, :r, :n)"),
                     {"c": character_id, "r": NEW, "n": amount})


def _move_counts(conn, table: str, column: str) -> set[int]:
    moved = set()
    for row in conn.execute(sa.text(f"SELECT id, character_id, {column} AS n FROM {table} WHERE rune_id=:r"),
                            {"r": OLD}).all():
        if row.n > 0:
            _add(conn, table, column, row.character_id, row.n)
        conn.execute(sa.text(f"DELETE FROM {table} WHERE id=:id"), {"id": row.id})
        moved.add(row.character_id)
    return moved


def upgrade():
    migrate(op.get_bind())


def migrate(conn) -> None:
    """Сама перекладка - отдельно, чтобы прогнать её на копии в транзакции."""
    from game.economy import runes
    from game.economy import runes_config as rc

    # мастерство сложилось - сила вставленного «Лёгкого шага» пересчитывается
    touched: set[int] = _move_counts(conn, "character_rune_mastery", "absorbed")
    _move_counts(conn, "character_runes", "count")

    for row in conn.execute(sa.text("SELECT id, character_id, kind FROM character_rune_slots WHERE rune_id=:r"),
                            {"r": OLD}).all():
        touched.add(row.character_id)
        has_new = conn.execute(sa.text(
            "SELECT 1 FROM character_rune_slots WHERE character_id=:c AND kind=:k AND rune_id=:r"),
            {"c": row.character_id, "k": row.kind, "r": NEW}).first()
        if has_new:
            conn.execute(sa.text("DELETE FROM character_rune_slots WHERE id=:id"), {"id": row.id})
            _add(conn, "character_runes", "count", row.character_id, 1)
        else:
            conn.execute(sa.text("UPDATE character_rune_slots SET rune_id=:r WHERE id=:id"), {"r": NEW, "id": row.id})

    # Пресеты: раскладка рун - список {"kind", "slot", "rune_id"}.
    for row in conn.execute(sa.text(
            "SELECT id, runes FROM character_buff_presets WHERE runes::text LIKE :p"), {"p": f"%{OLD}%"}).all():
        layout = row.runes if isinstance(row.runes, list) else json.loads(row.runes)
        kinds_with_new = {e.get("kind") for e in layout if e.get("rune_id") == NEW}
        fixed = []
        for e in layout:
            if e.get("rune_id") == OLD:
                if e.get("kind") in kinds_with_new:
                    continue
                e = {**e, "rune_id": NEW}
            fixed.append(e)
        conn.execute(sa.text("UPDATE character_buff_presets SET runes=CAST(:j AS json) WHERE id=:id"),
                     {"j": json.dumps(fixed), "id": row.id})

    # Мешки забегов в руинах: {"runes": {id: n}, ...}.
    for row in conn.execute(sa.text("SELECT id, bag FROM ruin_members WHERE bag::text LIKE :p"),
                            {"p": f"%{OLD}%"}).all():
        bag = row.bag if isinstance(row.bag, dict) else json.loads(row.bag)
        got = dict(bag.get("runes") or {})
        if OLD in got:
            got[NEW] = got.get(NEW, 0) + got.pop(OLD)
            bag = {**bag, "runes": got}
            conn.execute(sa.text("UPDATE ruin_members SET bag=CAST(:j AS json) WHERE id=:id"), {"j": json.dumps(bag), "id": row.id})

    for table in ("market_orders", "market_trades", "market_inbox"):
        conn.execute(sa.text(f"UPDATE {table} SET good=:new WHERE good=:old"),
                     {"new": f"rune:{NEW}", "old": f"rune:{OLD}"})

    # Копия эффектов: ключ старой руны долой, «Лёгкий шаг» - по мастерству.
    new_def = rc.BY_ID[NEW]
    for row in conn.execute(sa.text(
            "SELECT id, rune_effects FROM characters WHERE rune_effects::text LIKE :p"), {"p": f"%rune:{OLD}%"}).all():
        touched.add(row.id)
    for cid in touched:
        effects = conn.execute(sa.text("SELECT rune_effects FROM characters WHERE id=:c"), {"c": cid}).scalar()
        effects = dict(effects if isinstance(effects, dict) else json.loads(effects or "{}"))
        effects.pop(f"rune:{OLD}", None)
        equipped = conn.execute(sa.text(
            "SELECT 1 FROM character_rune_slots WHERE character_id=:c AND kind='gear' AND rune_id=:r"),
            {"c": cid, "r": NEW}).first()
        if equipped:
            absorbed = conn.execute(sa.text(
                "SELECT absorbed FROM character_rune_mastery WHERE character_id=:c AND rune_id=:r"),
                {"c": cid, "r": NEW}).scalar() or 0
            effects[f"rune:{NEW}"] = round(runes.value(new_def, int(absorbed)), 6)
        conn.execute(sa.text("UPDATE characters SET rune_effects=CAST(:j AS json) WHERE id=:c"),
                     {"j": json.dumps(effects), "c": cid})


def downgrade():
    pass  # слияние не разворачивается: копии уже сложены
