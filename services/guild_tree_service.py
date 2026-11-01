"""Древо гильдии: взять узел, сбросить древо.

Узел стоит очки (их дают уровни гильдии) и золото из казны. Золото растёт
с числом уже взятых узлов: древо огромное, и последние узлы должны
доставаться дороже первых.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import guild_config as gc
from game.guild import tree as guild_tree
from models import Character, Guild
from services import guild_service
from services.guild_service import GuildError

_KIND_GOLD = {
    guild_tree.KIND_SMALL: gc.TREE_GOLD_SMALL,
    guild_tree.KIND_NOTABLE: gc.TREE_GOLD_NOTABLE,
    guild_tree.KIND_KEYSTONE: gc.TREE_GOLD_KEYSTONE,
}


def node_gold(guild: Guild, node_id: str) -> int:
    node = guild_tree.node(node_id)
    if node is None or node.kind == guild_tree.KIND_ROOT:
        return 0
    taken = len(guild.tree_nodes or [])
    return round(_KIND_GOLD[node.kind] * (1 + gc.TREE_GOLD_GROWTH * taken))


async def allocate(db: AsyncSession, actor: Character, node_id: str) -> guild_tree.TreeNode:
    guild, _member = await guild_service.require_treasurer(db, actor)
    node = guild_tree.node(node_id)
    taken = set(guild.tree_nodes or [])
    if node is None or node.kind == guild_tree.KIND_ROOT:
        raise GuildError("Нет такого узла.")
    if node_id in taken:
        raise GuildError("Этот узел уже взят.")
    if not guild_tree.can_allocate(node_id, taken):
        raise GuildError("Узел можно взять только рядом с уже взятым.")
    points = guild_tree.POINTS[node.kind]
    if guild_service.tree_points_available(guild) < points:
        raise GuildError(f"Не хватает очков древа: нужно {points}. Очки дают уровни гильдии.")
    gold = node_gold(guild, node_id)
    await guild_service.treasury_spend(db, guild.id, gold=gold)
    await db.refresh(guild)
    guild.tree_nodes = [*taken, node_id]
    guild.tree_gold_spent += gold
    await guild_service.log(db, guild.id, "tree", f"{actor.name} берёт узел «{node.name}».", actor.id)
    await db.flush()
    await guild_service.refresh_perks(db, guild)
    return node


async def reset(db: AsyncSession, actor: Character, branch: str | None = None) -> int:
    """Сброс ветви (branch) или всего древа (None): очки возвращаются, золото
    за узлы - нет. Платит казна. Вернёт, сколько узлов снято."""
    guild, member = await guild_service.require_treasurer(db, actor)
    if member.rank != gc.RANK_LEADER:
        raise GuildError("Сбросить древо может только глава.")
    if branch is not None and branch not in guild_tree.BRANCH_TITLES:
        raise GuildError("Нет такой ветви.")
    taken = list(guild.tree_nodes or [])
    dropped = [n for n in taken if branch is None or (guild_tree.node(n) and guild_tree.node(n).branch == branch)]
    if not dropped:
        raise GuildError("Сбрасывать нечего.")
    gold = gc.TREE_RESET_ALL_GOLD if branch is None else gc.TREE_RESET_BRANCH_GOLD
    await guild_service.treasury_spend(db, guild.id, gold=gold)
    await db.refresh(guild)
    guild.tree_nodes = [n for n in taken if n not in dropped]
    what = "древо гильдии" if branch is None else f"ветвь «{guild_tree.BRANCH_TITLES[branch]}»"
    await guild_service.log(db, guild.id, "tree", f"{actor.name} сбрасывает {what}.", actor.id)
    await db.flush()
    await guild_service.refresh_perks(db, guild)
    return len(dropped)


def payload(guild: Guild | None) -> dict:
    """Древо целиком для мини-аппа: узлы, связи, что взято, что доступно."""
    nodes = guild_tree.build()
    taken = set(guild.tree_nodes or []) if guild else set()
    result = []
    for node in nodes.values():
        result.append({
            "id": node.id, "branch": node.branch, "kind": node.kind, "name": node.name,
            "description": node.description, "x": node.x, "y": node.y,
            "links": sorted(node.links),
            "taken": node.id in taken or node.kind == guild_tree.KIND_ROOT,
            "available": guild is not None and guild_tree.can_allocate(node.id, taken),
            "points": guild_tree.POINTS[node.kind],
            "gold": node_gold(guild, node.id) if guild else 0,
        })
    effects = guild_tree.total_effects(taken)
    return {
        "nodes": result,
        "branches": guild_tree.BRANCH_TITLES,
        "points_available": guild_service.tree_points_available(guild) if guild else 0,
        "taken": len(taken),
        "total_nodes": sum(1 for n in nodes.values() if n.kind != guild_tree.KIND_ROOT),
        "effects": [guild_tree.effect_text(k, v) for k, v in sorted(effects.items())],
        "reset_branch_gold": gc.TREE_RESET_BRANCH_GOLD,
        "reset_all_gold": gc.TREE_RESET_ALL_GOLD,
    }
