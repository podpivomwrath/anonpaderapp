"""Сюжетный враг в групповом бою (2026-10-11): шаг засчитывается тем, у кого
он активен; остальным враг - обычный моб."""

from bot.handlers import group_combat
from models import CharacterStoryProgress
from services import story_service


async def _progress(db, character, step: str, status: str = "active"):
    db.add(CharacterStoryProgress(character_id=character.id, region=character.region, act=1,
                                  quest_step=step, status=status))
    await db.flush()


async def test_story_kill_marks_only_quest_holders(db_session, make_character) -> None:
    holder = await make_character(region="ridge", level=20)
    other = await make_character(region="ridge", level=20)
    stranger = await make_character(region="docks", level=20)
    await _progress(db_session, holder, "ridge_1_2")
    await _progress(db_session, other, "ridge_1_1")  # другой шаг сюжета

    battle = group_combat.GroupBattle(
        group_id=1,
        participants={c.id: group_combat.Participant(c.id, 100 + c.id, c.name, c.base_class, None)
                      for c in (holder, other, stranger)},
        mob_ids={10_000_000, 10_000_001},
        story_mob_id=10_000_000, story_quest_id="ridge_1_2",
    )
    lines = await group_combat._story_kill(db_session, battle)

    assert set(lines) == {holder.id}
    assert "Цель задания выполнена" in lines[holder.id]
    assert (await story_service.get_progress(db_session, holder)).status == "ready"
    assert (await story_service.get_progress(db_session, other)).status == "active"


async def test_story_enemy_waits_for_explore_combat(db_session, character_at) -> None:
    """2026-10-11: в зоне цели шаг с врагом находится для боя исследования;
    вне зоны - нет."""
    import random

    from bot.handlers import world

    near = await character_at(-10, 25, region="ridge", level=20)
    far = await character_at(0, 30, region="ridge", level=20)
    for c in (near, far):
        await _progress(db_session, c, "ridge_1_2")
    quest = await world.story_fight_quest(db_session, near)
    assert quest is not None and quest.id == "ridge_1_2"
    assert await world.story_fight_quest(db_session, far) is None

    mobs, quest_id = await world.group_story_mobs(db_session, [far, near], random.Random(1))
    assert quest_id == "ridge_1_2"
    assert mobs[0].combatant.name == quest.named_enemy.name  # первым - сюжетный враг
    assert len(mobs) == 2 and mobs[1].combatant.id != mobs[0].combatant.id
    assert await world.group_story_mobs(db_session, [far], random.Random(1)) is None
