"""Побег в два нажатия (2026-10-15): первое спрашивает, второе бежит."""

from types import SimpleNamespace

from bot.handlers import combat


async def test_first_flee_press_only_asks(monkeypatch):
    peer = 7771
    session = SimpleNamespace(combatants={
        combat.PLAYER_ID: SimpleNamespace(level=10, current_hp=50),
        combat.MOB_ID: SimpleNamespace(level=10),
    })
    aborted = []

    class _Engine:
        sessions = {peer: session}

        def abort_session(self, sid):
            aborted.append(sid)

        async def declare_action(self, *args):
            pass

    answers = []

    async def answer(text, keyboard=None):
        answers.append(text)

    monkeypatch.setattr(combat, "_engine", _Engine())
    monkeypatch.setattr(combat, "_combat_kb", lambda state, peer_id: "kb")
    monkeypatch.setattr(combat, "has_active_encounter", lambda p: True)
    message = SimpleNamespace(peer_id=peer, answer=answer)
    combat._flee_confirm.pop(peer, None)

    await combat.flee(message)
    assert aborted == [] and "ещё раз" in answers[-1]

    # Атака между нажатиями отменяет подтверждение.
    await combat.attack(SimpleNamespace(peer_id=peer, answer=answer))
    await combat.flee(message)
    assert aborted == [] and "ещё раз" in answers[-1]
    combat._flee_confirm.pop(peer, None)
