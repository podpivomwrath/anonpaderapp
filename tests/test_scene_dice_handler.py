"""Кости в событиях: проигрыш списывает ставку, выигрыш платит вдвое.

Игрок сообщил, что проигрыш не отобрал баланс (2026-10-12) - здесь весь путь
броска через обработчик, на базе, с подменённым исходом."""

import pytest
from sqlalchemy import select

from bot.handlers import scene_events as h
from game.world import scene_events as se
from models import CharacterStats
from services import wallet_service


def _dice_scene():
    for event in se.content().events:
        for scene_id, scene in event.scenes.items():
            if scene.type == "dice":
                return event, scene_id, scene
    pytest.skip("в контенте нет костей")


@pytest.fixture
def silent(monkeypatch):
    sent = []

    async def fake_send(peer_id, text, keyboard=None, attachment=None):
        sent.append(text)

    async def fake_epilogue(peer_id, lines, applied):
        sent.append("\n".join(lines))

    monkeypatch.setattr(h, "_send", fake_send)
    monkeypatch.setattr(h, "_epilogue", fake_epilogue)
    return sent


@pytest.mark.parametrize("won", [False, True])
async def test_dice_roll_moves_the_stake(db_session, make_character, monkeypatch, silent, won) -> None:
    event, scene_id, scene = _dice_scene()
    character = await make_character()
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    await wallet_service.deposit(db_session, character.id, "farm", 1000, taxable=False)
    before = (await wallet_service.get_wallet(db_session, character.id)).farm_currency

    monkeypatch.setattr(se, "roll_dice", lambda rng, chance: (won, (6, 6), (1, 1)) if won else (won, (1, 1), (6, 6)))
    p = h.Pending(event_id=event.id, scene_id=scene_id, token=1, currency="gold", stake=300)
    await h._dice(1, db_session, character, stats, p, scene, "roll", {})

    wallet = await wallet_service.get_wallet(db_session, character.id)
    await db_session.refresh(wallet)
    assert wallet.farm_currency == (before + 300 if won else before - 300)


async def test_guild_tax_takes_only_the_winnings(db_session, make_character, monkeypatch, silent) -> None:
    """2026-10-13: налог гильдии облагал всю удвоенную ставку - при налоге 50%
    победа возвращала ровно ставку, выиграть было нельзя. Теперь своя ставка
    возвращается без налога, налог - только с выигрыша."""
    from services import guild_service

    event, scene_id, scene = _dice_scene()
    character = await make_character()
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    await wallet_service.deposit(db_session, character.id, "farm", 1000, taxable=False)
    before = (await wallet_service.get_wallet(db_session, character.id)).farm_currency

    async def half_tax(db, character_id, amount):
        return amount // 2

    monkeypatch.setattr(wallet_service, "_guild_tax", half_tax)
    monkeypatch.setattr(guild_service, "after_tax", lambda c, amount: amount - amount // 2)
    monkeypatch.setattr(se, "roll_dice", lambda rng, chance: (True, (6, 6), (1, 1)))
    p = h.Pending(event_id=event.id, scene_id=scene_id, token=1, currency="gold", stake=300)
    await h._dice(1, db_session, character, stats, p, scene, "roll", {})

    wallet = await wallet_service.get_wallet(db_session, character.id)
    await db_session.refresh(wallet)
    assert wallet.farm_currency == before + 150
    assert "после налога гильдии +150" in silent[-1]
