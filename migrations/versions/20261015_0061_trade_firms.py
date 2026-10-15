"""Торговые фирмы (2026-10-15): фирма игрока, повозки, журнал рейсов,
процветание городов и вклад торговцев. Старые повозки переносятся в фирмы
(без названия - игрок назовёт сам) со всеми улучшениями и уровнем торговли;
груз возвращается золотом (уплаченное +10%), плюс разница цены фирмы и
старой повозки. Караваны и старые повозки удаляются."""
import json

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

CITY_COORDS = {"ridge": (0, 30), "docks": (30, 0), "scorched": (0, -30), "woods": (-30, 0)}
CARGO_REFUND = 1.10
PRICE_DIFF = 10_000 - 5_000
START_POINTS = 2_000


def upgrade():
    op.create_table(
        "trade_firms",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("name", sa.String(24), nullable=True),
        sa.Column("name_key", sa.String(24), nullable=True, unique=True),
        sa.Column("trade_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trade_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profit_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("notify_arrival", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_orders", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "trade_carts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(16), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="idle"),
        sa.Column("to_city", sa.String(16), nullable=True),
        sa.Column("route", sa.String(8), nullable=True),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrives_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ambushes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("horses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("body", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plating", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("guard", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("durability", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("cargo", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("paid", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("character_id", "slot", name="uq_trade_carts_slot"),
    )
    op.create_index("ix_trade_carts_character_id", "trade_carts", ["character_id"])
    op.create_index("ix_trade_carts_arrives_at", "trade_carts", ["arrives_at"])
    op.create_table(
        "trade_trips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("from_city", sa.String(16), nullable=False),
        sa.Column("to_city", sa.String(16), nullable=False),
        sa.Column("route", sa.String(8), nullable=False),
        sa.Column("crates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ambushes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lost", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_trips_character_id", "trade_trips", ["character_id"])
    op.create_table(
        "faction_states",
        sa.Column("city", sa.String(16), primary_key=True),
        sa.Column("points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trade_contributions",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("city", sa.String(16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_trade_contributions_city", "trade_contributions", ["city"])

    conn = op.get_bind()
    for city in CITY_COORDS:
        conn.execute(
            sa.text("INSERT INTO faction_states (city, points, updated_at) VALUES (:c, :p, now())"),
            {"c": city, "p": float(START_POINTS)},
        )

    rows = conn.execute(sa.text(
        "SELECT cc.character_id, cc.cart_x, cc.cart_y, cc.horses, cc.body, cc.plating, cc.guard, cc.durability, "
        "cc.paid, cc.trade_level, cc.trade_xp, cc.profit_total, c.region "
        "FROM character_carts cc JOIN characters c ON c.id = cc.character_id"
    )).mappings().all()
    for r in rows:
        paid = r["paid"]
        if isinstance(paid, str):
            paid = json.loads(paid or "{}")
        refund = PRICE_DIFF + round(sum((paid or {}).values()) * CARGO_REFUND)
        city = r["region"] if r["region"] in CITY_COORDS else next(
            (c for c, xy in CITY_COORDS.items() if xy == (r["cart_x"], r["cart_y"])), "ridge",
        )
        conn.execute(sa.text(
            "INSERT INTO trade_firms (character_id, trade_level, trade_xp, profit_total) "
            "VALUES (:cid, :lvl, :xp, :profit)"
        ), {"cid": r["character_id"], "lvl": r["trade_level"], "xp": r["trade_xp"], "profit": r["profit_total"]})
        conn.execute(sa.text(
            "INSERT INTO trade_carts (character_id, slot, city, horses, body, plating, guard, durability) "
            "VALUES (:cid, 1, :city, :h, :b, :p, :g, :d)"
        ), {
            "cid": r["character_id"], "city": city, "h": min(r["horses"], 5), "b": min(r["body"], 5),
            "p": min(r["plating"], 5), "g": min(r["guard"], 5), "d": r["durability"],
        })
        conn.execute(sa.text(
            "UPDATE wallets SET farm_currency = farm_currency + :g WHERE character_id = :cid"
        ), {"g": refund, "cid": r["character_id"]})

    # Поездки с повозкой (их ведёт уже не персонаж) - стоп там, где застала.
    conn.execute(sa.text(
        "UPDATE mount_travels SET status = 'stopped' "
        "WHERE mount_id = 'trade_cart' AND status IN ('traveling', 'ambushed')"
    ))
    op.drop_index("ix_trade_caravans_expires_at", table_name="trade_caravans")
    op.drop_table("trade_caravans")
    op.drop_table("character_carts")


def downgrade():
    op.create_table(
        "character_carts",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cart_x", sa.Integer(), nullable=False),
        sa.Column("cart_y", sa.Integer(), nullable=False),
        sa.Column("horses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("body", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plating", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("guard", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("durability", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("cargo", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("paid", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("trade_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trade_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profit_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "trade_caravans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("buys", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sells", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_caravans_expires_at", "trade_caravans", ["expires_at"])
    op.drop_index("ix_trade_contributions_city", table_name="trade_contributions")
    op.drop_table("trade_contributions")
    op.drop_table("faction_states")
    op.drop_index("ix_trade_trips_character_id", table_name="trade_trips")
    op.drop_table("trade_trips")
    op.drop_index("ix_trade_carts_arrives_at", table_name="trade_carts")
    op.drop_index("ix_trade_carts_character_id", table_name="trade_carts")
    op.drop_table("trade_carts")
    op.drop_table("trade_firms")
