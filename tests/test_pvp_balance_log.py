"""PvP-журнал с уровнем и подклассом на момент боя (2026-10-21): честная
статистика подклассов на равных уровнях, а не по одному сильному игроку."""

from services import pvp_service


async def test_duels_count_by_subclass_at_close_levels(db_session, make_character) -> None:
    bk = await make_character(level=50, subclass="blood_knight")
    mage = await make_character(level=48, subclass="elementalist", base_class="mage")
    low = await make_character(level=20, base_class="rogue")
    await pvp_service.log_battle(db_session, "duel", [bk.id, mage.id], [bk.id])
    await pvp_service.log_battle(db_session, "duel", [bk.id, mage.id], [mage.id])
    await pvp_service.log_battle(db_session, "duel", [bk.id, low.id], [bk.id])  # разница 30 - не в счёт
    rows = {r["sub"]: r for r in await pvp_service.subclass_winrates(db_session)}
    assert rows["blood_knight"]["fights"] == 2 and rows["blood_knight"]["winrate"] == 50
    assert "rogue" not in rows


def test_fighter_kind_names_path_and_base() -> None:
    from types import SimpleNamespace

    assert pvp_service.fighter_kind(SimpleNamespace(subclass=None, subclass_declined=True, base_class="warrior")) == "warrior_path"
    assert pvp_service.fighter_kind(SimpleNamespace(subclass=None, subclass_declined=False, base_class="mage")) == "mage"
