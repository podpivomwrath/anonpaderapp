"""Венец топ-1 (патч 91): кто держит доску, что с этого и как его теряют."""

import pytest

from game.economy import crown_config as cc
from services import (
    crown_service,
    experience_service,
    leaderboard_service,
    movement_service,
)

BOARDS = leaderboard_service.BOARDS


async def _stats(db_session, character):
    """Фабрика персонажа кладёт статы отдельной строкой и связь не заполняет,
    поэтому character.stats пришлось бы подгружать лениво - а это падение."""
    from sqlalchemy import select

    from models import CharacterStats

    return (
        await db_session.scalars(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
    ).one()


async def _crowned(db_session, make_character, board: str, **kwargs):
    """Персонаж с уже выданным венцом — без пересчёта, когда он не важен."""
    character = await make_character(**kwargs)
    character.crowns = {board: "2026-09-01T00:00:00+00:00"}
    await db_session.flush()
    return character


# --- Пересчёт ---------------------------------------------------------------


async def test_first_recompute_hands_out_the_crown(db_session, make_character) -> None:
    leader = await make_character(level=60)
    leader.pvp_wins = 10
    await db_session.flush()

    displaced = await crown_service.recompute(db_session)

    assert displaced == [], "венец выдан впервые, смещать было некого"
    await db_session.refresh(leader)
    assert crown_service.crown_boards(leader) == [leaderboard_service.BOARD_PVP]


async def test_holder_who_stays_first_keeps_the_crown(db_session, make_character) -> None:
    """И, что важнее, сохраняет отсчёт удержания: если переписывать дату
    каждые сутки, «держишь четыре дня» не вырастет никогда."""
    leader = await make_character(level=60)
    leader.pvp_wins = 10
    await db_session.flush()
    await crown_service.recompute(db_session)
    since = crown_service.held_since(leader, leaderboard_service.BOARD_PVP)
    assert since is not None

    displaced = await crown_service.recompute(db_session)

    assert displaced == []
    assert crown_service.held_since(leader, leaderboard_service.BOARD_PVP) == since


async def test_overtaking_moves_the_crown_and_reports_the_loser(db_session, make_character) -> None:
    old = await make_character(level=60)
    old.pvp_wins = 10
    await db_session.flush()
    await crown_service.recompute(db_session)

    new = await make_character(level=60)
    new.pvp_wins = 25
    await db_session.flush()

    displaced = await crown_service.recompute(db_session)

    assert len(displaced) == 1
    assert displaced[0].character_id == old.id
    assert displaced[0].board == leaderboard_service.BOARD_PVP
    assert displaced[0].successor_name == new.name
    await db_session.refresh(old)
    await db_session.refresh(new)
    assert crown_service.crown_boards(old) == []
    assert crown_service.crown_boards(new) == [leaderboard_service.BOARD_PVP]


async def test_recompute_takes_the_crown_from_everyone_but_the_leader(
    db_session, make_character
) -> None:
    """Держателей у доски не может остаться двое даже после ручной порчи
    данных: пересчёт исходит из доски, а не из того, что записано у игроков."""
    first = await make_character(level=60)
    second = await make_character(level=60)
    first.pvp_wins, second.pvp_wins = 5, 50
    first.crowns = {"pvp": "2026-09-01T00:00:00+00:00"}
    second.crowns = {"pvp": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()

    await crown_service.recompute(db_session)

    assert crown_service.crown_boards(first) == []
    assert crown_service.crown_boards(second) == [leaderboard_service.BOARD_PVP]


async def test_one_player_can_hold_several_boards(db_session, make_character) -> None:
    """Пять досок независимы, и запрещать совмещение незачем - но рамка в
    шапке одна, поэтому порядок обязан быть устойчивым."""
    player = await make_character(level=60)
    player.mobs_killed = 100
    player.mining_level = 20
    await db_session.flush()

    await crown_service.recompute(db_session)
    await db_session.refresh(player)

    held = crown_service.crown_boards(player)
    assert set(held) >= {leaderboard_service.BOARD_KILLS, leaderboard_service.BOARD_MINING}
    assert held == [b for b in BOARDS if b in held], "порядок должен идти по BOARDS"


# --- Бонусы -----------------------------------------------------------------


async def test_pvp_crown_adds_experience(db_session, make_character) -> None:
    plain = await make_character(level=10)
    crowned = await _crowned(db_session, make_character, leaderboard_service.BOARD_PVP, level=10)

    base = experience_service.add_experience(
        plain, await _stats(db_session, plain), 1000, apply_premium=False
    )
    with_crown = experience_service.add_experience(
        crowned, await _stats(db_session, crowned), 1000, apply_premium=False
    )

    assert with_crown.xp_awarded == round(base.xp_awarded * (1 + cc.XP_BONUS))


async def test_trophy_crown_does_not_touch_experience(db_session, make_character) -> None:
    """Проверка того самого правила: бонус не влияет на чужой счётчик, но и
    чужой венец не влияет на этот."""
    crowned = await _crowned(db_session, make_character, leaderboard_service.BOARD_MINING, level=10)
    plain = await make_character(level=10)

    with_other_crown = experience_service.add_experience(
        crowned, await _stats(db_session, crowned), 1000, apply_premium=False
    )
    without = experience_service.add_experience(
        plain, await _stats(db_session, plain), 1000, apply_premium=False
    )
    assert with_other_crown.xp_awarded == without.xp_awarded


async def test_record_crown_shortens_the_walk(db_session, make_character) -> None:
    crowned = await _crowned(
        db_session, make_character, leaderboard_service.BOARD_FISH_WEIGHT, level=10
    )
    plain = await make_character(level=10)

    for person in (crowned, plain):
        person.pos_x, person.pos_y = 0, 0
    fast = movement_service.start_travel(crowned, 1, 0)
    normal = movement_service.start_travel(plain, 1, 0)

    assert fast == pytest.approx(normal * (1 - cc.TRAVEL_CUT))


async def test_no_bonus_feeds_the_board_that_granted_it() -> None:
    """Главное правило набора, записанное проверкой, а не только в комментарии.

    Бонус к своему же счётчику запирает лестницу: первый по PvP получает
    бонус к PvP и потому остаётся первым. Таблица соответствий должна
    оставаться «поперечной» и после любой будущей правки.
    """
    forbidden = {
        leaderboard_service.BOARD_PVP: ("PvP", "побед"),
        leaderboard_service.BOARD_KILLS: ("убийств", "мобов убит"),
        leaderboard_service.BOARD_FISHING: ("уровн", "рыбалк"),
        leaderboard_service.BOARD_FISH_WEIGHT: ("вес", "рекорд"),
        leaderboard_service.BOARD_MINING: ("уровн", "горно"),
    }
    for board, words in forbidden.items():
        effect = cc.CROWN_EFFECTS[board].lower()
        for word in words:
            assert word.lower() not in effect, (
                f"венец «{cc.CROWN_TITLES[board]}» усиливает свой же топ: {effect}"
            )


def test_every_board_has_a_title_and_an_effect() -> None:
    """Новая доска не должна тихо появиться без венца - иначе первое место на
    ней окажется единственным без награды, и заметит это игрок."""
    assert set(cc.CROWN_TITLES) == set(BOARDS)
    assert set(cc.CROWN_EFFECTS) == set(BOARDS)


# --- Выбор рамки (патч 92) --------------------------------------------------


async def test_without_a_choice_the_first_crown_is_worn(db_session, make_character) -> None:
    player = await make_character(level=60)
    player.crowns = {"mining": "2026-09-01T00:00:00+00:00", "pvp": "2026-09-02T00:00:00+00:00"}
    await db_session.flush()

    # Порядок берётся из BOARDS, а не из порядка ключей в JSON - иначе рамка
    # менялась бы от показа к показу.
    assert crown_service.frame_board(player) == leaderboard_service.BOARD_PVP


async def test_player_can_wear_the_crown_he_prefers(db_session, make_character) -> None:
    player = await make_character(level=60)
    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00", "mining": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()

    assert crown_service.set_frame(player, leaderboard_service.BOARD_MINING) is True
    assert crown_service.frame_board(player) == leaderboard_service.BOARD_MINING


async def test_taking_the_frame_off_survives_a_new_crown(db_session, make_character) -> None:
    """«Снял» и «не выбирал» - разные вещи. Если их смешать, снятая рамка
    вернётся сама, как только игрок возьмёт следующий венец."""
    player = await make_character(level=60)
    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()
    crown_service.set_frame(player, None)
    assert crown_service.frame_board(player) is None

    player.crowns = {**player.crowns, "mining": "2026-09-02T00:00:00+00:00"}
    await db_session.flush()

    assert crown_service.frame_board(player) is None


async def test_cannot_wear_a_crown_you_do_not_hold(db_session, make_character) -> None:
    player = await make_character(level=60)
    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()

    assert crown_service.set_frame(player, leaderboard_service.BOARD_MINING) is False
    assert crown_service.frame_board(player) == leaderboard_service.BOARD_PVP


async def test_losing_the_worn_crown_falls_back_to_another(db_session, make_character) -> None:
    """Выбор остаётся записанным, а венца уже нет: показывать его рамку -
    значит показывать награду, которую отобрали."""
    player = await make_character(level=60)
    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00", "mining": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()
    crown_service.set_frame(player, leaderboard_service.BOARD_MINING)

    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()

    assert crown_service.frame_board(player) == leaderboard_service.BOARD_PVP


async def test_all_bonuses_work_regardless_of_the_worn_frame(db_session, make_character) -> None:
    """Рамка - только вид. Бонусы действуют все сразу, иначе выбор рамки
    превратился бы в выбор бонуса."""
    player = await make_character(level=10)
    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00", "mining": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()
    crown_service.set_frame(player, leaderboard_service.BOARD_MINING)

    assert crown_service.xp_multiplier(player) == 1 + cc.XP_BONUS
    assert crown_service.mining_multiplier(player) == 1 - cc.MINING_CUT


async def test_menu_describes_every_held_crown(db_session, make_character) -> None:
    player = await make_character(level=60)
    player.crowns = {"pvp": "2026-09-01T00:00:00+00:00"}
    await db_session.flush()

    (row,) = crown_service.menu(player)
    assert row["board"] == leaderboard_service.BOARD_PVP
    assert row["title"] == cc.CROWN_TITLES[leaderboard_service.BOARD_PVP]
    assert row["effect"] == cc.CROWN_EFFECTS[leaderboard_service.BOARD_PVP]
    assert row["board_title"]


def test_arrival_is_scheduled_by_the_actual_travel_time() -> None:
    """Планировщик прибытия обязан брать ТУ ЖЕ величину, что записана в
    travel_arrives_at.

    С венцом «Трофей» переход короче константы. Если планировщик продолжит
    брать world_config.CELL_TRAVEL_SECONDS, игрок придёт по часам базы, а
    сообщение о прибытии подождёт полную десятку секунд - и разницы от венца
    он не увидит вовсе. Ошибка тихая: обе величины валидны по отдельности.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "bot" / "handlers" / "world.py").read_text(
        encoding="utf-8"
    )
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "schedule"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "_travel_scheduler"
    ]
    assert calls, "вызов планировщика перехода не найден"
    for call in calls:
        argument = ast.unparse(call.args[-1])
        assert "CELL_TRAVEL_SECONDS" not in argument, (
            f"планировщик берёт константу мимо movement_service: {argument}"
        )
