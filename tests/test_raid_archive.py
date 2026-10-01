"""Рейд «Безликий архив»: головоломки, фраза из загадок, механики Архивариуса."""

import itertools
import random
from collections import deque

from game import archive_riddles, raid_puzzles
from game.combat import raid_archive
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from game.economy import raid_archive_config as ac
from game.economy import craft_config as cc
from game.economy import crafting
from tests.conftest import NoCritRng, combatant

# --- Головоломки -----------------------------------------------------------------


def test_every_player_gets_a_different_puzzle() -> None:
    for players in range(1, 6):
        kinds = [p.kind for p in raid_puzzles.deal(random.Random(players), players)]
        assert len(kinds) == len(set(kinds)) == players


def test_puzzle_boards_fit_a_vk_keyboard() -> None:
    """Обычная клавиатура VK: до 10 рядов и до 5 кнопок в ряду."""
    for puzzle in raid_puzzles.deal(random.Random(3), 5):
        rows = puzzle.cells()
        assert len(rows) <= 10
        assert all(1 <= len(row) <= 5 for row in rows)


def _solve_slide(board: list[int]) -> list[int]:
    """BFS: последовательность клеток, которые надо нажать."""
    start, goal = tuple(board), tuple(raid_puzzles.Slide.SOLVED)
    prev = {start: None}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        if state == goal:
            break
        empty = state.index(0)
        for n in raid_puzzles._neighbors(empty):
            nxt = list(state)
            nxt[empty], nxt[n] = nxt[n], 0
            nxt = tuple(nxt)
            if nxt not in prev:
                prev[nxt] = (state, n)
                queue.append(nxt)
    path = []
    state = goal
    while prev[state] is not None:
        state, n = prev[state]
        path.append(n)
    return list(reversed(path))


def test_slide_is_always_solvable() -> None:
    for seed in range(15):
        puzzle = raid_puzzles.Slide(random.Random(seed))
        assert not puzzle.solved
        for cell in _solve_slide(puzzle.board):
            puzzle.press(str(cell))
        assert puzzle.solved


def test_candles_are_always_solvable() -> None:
    for seed in range(15):
        puzzle = raid_puzzles.Candles(random.Random(seed))
        start = list(puzzle.lit)
        for presses in itertools.product((0, 1), repeat=9):
            trial = raid_puzzles.Candles(random.Random(seed))
            trial.lit = list(start)
            for i, on in enumerate(presses):
                if on:
                    trial.press(str(i))
            if trial.solved:
                break
        else:
            raise AssertionError(f"свечи не гасятся, seed={seed}")


def test_pairs_can_be_cleared() -> None:
    puzzle = raid_puzzles.Pairs(random.Random(4))
    by_symbol: dict[str, list[int]] = {}
    for i, sym in enumerate(puzzle.tiles):
        by_symbol.setdefault(sym, []).append(i)
    for a, b in by_symbol.values():
        puzzle.press(str(a))
        puzzle.press(str(b))
    assert puzzle.solved


def test_pairs_mismatch_closes_again() -> None:
    puzzle = raid_puzzles.Pairs(random.Random(4))
    a = 0
    b = next(i for i, s in enumerate(puzzle.tiles) if s != puzzle.tiles[a])
    assert puzzle.press(str(a)) == ""
    assert puzzle.press(str(b)) == "Не пара."
    assert not puzzle.matched


def test_tictactoe_reaches_three_wins() -> None:
    """Архивариус иногда пропускает чужую линию - три победы достижимы."""
    rng = random.Random(7)
    puzzle = raid_puzzles.TicTacToe(rng)
    for _ in range(400):
        if puzzle.solved:
            break
        free = [i for i in range(9) if not puzzle.board[i]]
        win = next((i for i in free if raid_puzzles._winner(
            [("X" if j == i else v) for j, v in enumerate(puzzle.board)]) == "X"), None)
        puzzle.press(str(win if win is not None else rng.choice(free)))
    assert puzzle.solved


def test_runes_score_and_code_reset() -> None:
    assert raid_puzzles.Runes.score(["ᚠ", "ᚢ", "ᚦ"], ["ᚠ", "ᚦ", "ᚱ"]) == (1, 1)
    puzzle = raid_puzzles.Runes(random.Random(1))
    first_code = list(puzzle.code)
    wrong = [r for r in raid_puzzles._RUNES if r not in first_code][:ac.RUNE_CODE_LEN]
    for _ in range(ac.RUNE_ATTEMPTS):
        for r in wrong:
            puzzle.press(r)
    assert puzzle.attempts == ac.RUNE_ATTEMPTS  # попытки кончились - новый код
    for r in puzzle.code:
        puzzle.press(r)
    assert puzzle.solved


# --- Фраза из загадок ----------------------------------------------------------------


def test_every_phrase_word_has_riddles_and_templates_are_complete() -> None:
    data = archive_riddles.data()
    for size, phrases in data["phrases"].items():
        assert phrases, size
        for phrase in phrases:
            assert len(phrase["words"]) == int(size)
            for i in range(1, int(size) + 1):
                assert "{" + str(i) + "}" in phrase["template"]
            for word in phrase["words"]:
                assert data["words"][word]["riddles"], word
                assert word in data["words"][word]["answers"]


def test_phrase_size_follows_the_group() -> None:
    assert archive_riddles.deal(random.Random(1), 1).size == ac.SOLO_PHRASE_WORDS
    for players in range(2, 6):
        assert archive_riddles.deal(random.Random(players), players).size == players


def test_phrase_accepts_connectors_or_bare_words_in_order() -> None:
    phrase = archive_riddles.deal(random.Random(2), 3)
    assert archive_riddles.phrase_is(phrase.full(), phrase)
    assert archive_riddles.phrase_is(" ".join(phrase.words).upper(), phrase)
    assert not archive_riddles.phrase_is(" ".join(reversed(phrase.words)), phrase)


def test_riddle_answer_matching() -> None:
    phrase = archive_riddles.deal(random.Random(5), 2)
    a = phrase.assignments[0]
    assert archive_riddles.answer_is(f"Это {a.word.capitalize()}!", a)
    assert not archive_riddles.answer_is("не знаю", a)


# --- Архивариус ---------------------------------------------------------------------


def _fight(players: int = 2):
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for i in range(1, players + 1):
        state.add(combatant(i, side=0, level=60, vitality=400, strength=150))
    stage = raid_archive.ArchiveStage(100)
    stage.setup(state)
    return state, stage, state.combatants[stage.boss_id]


def _tick(state, actions):
    state.tick_number += 1
    return resolve_tick(state, actions, NoCritRng())


def test_catalog_copies_the_damage_of_a_repeated_skill() -> None:
    state, stage, boss = _fight()
    stage.last_skill[1] = "warrior_cleave"
    result = _tick(state, {})
    # Резолвер не знает про навык без подклассовых данных - подставляем след
    # удара напрямую: игрок 1 повторил «Рассекающий удар» на 500 урона.
    result.actions[1] = DeclaredAction(type=ActionType.SKILL, skill_id="warrior_cleave", target_id=boss.id)
    from game.combat.resolver import RenderedHit

    result.hit_renders.append(RenderedHit(
        source_id=1, target_id=boss.id, source_side=0, target_side=1, label="Рассекающий удар",
        amount=500, crit=False, missed=False, is_dot=False, hp_before=0, hp_after=0, max_hp=1,
    ))
    hp = state.combatants[1].current_hp
    out = stage.after_tick(state, result, random.Random(1))
    assert state.combatants[1].current_hp == hp - 500
    assert any("Каталог" in line for line in out.lines)


def test_catalog_copies_heal_to_himself() -> None:
    state, stage, boss = _fight()
    boss.current_hp = boss.max_hp - 1000
    stage.last_skill[1] = "dark_mystic_blood_pact"
    result = _tick(state, {})
    result.actions[1] = DeclaredAction(type=ActionType.SKILL, skill_id="dark_mystic_blood_pact")
    from game.combat.resolver import RenderedHeal

    result.heal_renders.append(RenderedHeal(
        source_id=1, target_id=2, source_side=0, target_side=0, label="пакт",
        amount=300, hp_before=0, hp_after=0, max_hp=1,
    ))
    before = boss.current_hp
    stage.after_tick(state, result, random.Random(1))
    assert boss.current_hp >= before + 300 - 1


def test_catalog_turns_repeated_defence_into_his_guard() -> None:
    state, stage, boss = _fight()
    stage.last_skill[1] = "guardian_block"
    result = _tick(state, {})
    result.actions[1] = DeclaredAction(type=ActionType.SKILL, skill_id="guardian_block")
    stage.after_tick(state, result, random.Random(1))
    assert stage.guard_turns == ac.CATALOG_GUARD_TURNS
    hit = type("H", (), {"label": "бьёт", "is_dot": False})()
    assert stage._hook(hit, None, 100) == round(100 * (1 - ac.CATALOG_GUARD_REDUCTION))


def test_catalog_ignores_a_skill_used_for_the_first_time() -> None:
    state, stage, boss = _fight()
    result = _tick(state, {})
    result.actions[1] = DeclaredAction(type=ActionType.SKILL, skill_id="guardian_block")
    stage.after_tick(state, result, random.Random(1))
    assert stage.guard_turns == 0
    assert stage.last_skill[1] == "guardian_block"


def test_quote_returns_the_strongest_hit() -> None:
    state, stage, boss = _fight()
    stage.quote_open = True
    result = _tick(state, {1: DeclaredAction(type=ActionType.ATTACK, target_id=boss.id)})
    strongest = max(h.amount for h in result.hit_renders if h.target_id == boss.id)
    hp = {c: state.combatants[c].current_hp for c in (1, 2)}
    out = stage.after_tick(state, result, random.Random(1))
    lost = sum(hp[c] - state.combatants[c].current_hp for c in (1, 2))
    assert lost == strongest
    assert any("Цитата" in line for line in out.lines)


def test_eraser_strips_buffs_and_shields() -> None:
    state, stage, boss = _fight()
    player = state.combatants[1]
    player.apply_effect(EffectKind.SHIELD_POOL, 500, 3, 1)
    player.apply_effect(EffectKind.DAMAGE_BUFF, 0.3, 3, 1)
    player.apply_effect(EffectKind.WEAKEN, 0.2, 3, boss.id)
    stage.eraser_up = True
    stage.after_tick(state, _tick(state, {}), random.Random(1))
    kinds = {e.kind for e in player.effects}
    assert EffectKind.SHIELD_POOL not in kinds and EffectKind.DAMAGE_BUFF not in kinds
    assert EffectKind.WEAKEN in kinds  # ослабления он не трогает


def test_quote_and_eraser_are_announced_a_turn_ahead() -> None:
    state, stage, boss = _fight()
    seen = []
    for _ in range(12):
        out = stage.after_tick(state, _tick(state, {}), random.Random(1))
        seen += [line for line in out.lines if line.startswith("⚠️")]
        for c in (1, 2):
            state.combatants[c].current_hp = state.combatants[c].max_hp
    assert any("книгу" in line for line in seen) and any("ластик" in line for line in seen)


def test_last_chapter_deals_a_page_to_everyone() -> None:
    state, stage, boss = _fight(players=3)
    boss.current_hp = round(boss.max_hp * ac.LAST_CHAPTER_HP) - 1
    out = stage.after_tick(state, _tick(state, {}), random.Random(3))
    pages = next(line for line in out.lines if line.startswith("📜 ") and " - " in line)
    for c in (1, 2, 3):
        assert state.combatants[c].name in pages


# --- Награда ---------------------------------------------------------------------


def test_mask_is_a_helmet_with_vitality_and_class_stat() -> None:
    from services import item_service

    mask = item_service.unique_items()[ac.RAID_UNIQUE_ITEM_ID]
    assert mask.slot == "helmet"
    for seed in range(20):
        stats = crafting.roll_boss_item_stats(random.Random(seed), mask.power, "str", mask.weights)
        assert set(stats) <= {"vit", "str"}
    for spec in cc.SPECS:
        assert set(crafting.spec_weights(ac.RAID_UNIQUE_ITEM_ID, spec)) == {"vit", "primary"}


def test_archive_is_offered_at_the_monolith() -> None:
    from bot import raid_texts

    assert ac.RAID_ARCHIVE_ID in raid_texts.RAID_IDS
