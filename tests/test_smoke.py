"""Смоук: модули импортируются, реестры заполнены."""


def test_imports() -> None:
    import main  # noqa: F401
    import models  # noqa: F401
    from bot import webhook  # noqa: F401
    from game.combat import duel_engine, formulas, resolver, session, tick_engine  # noqa: F401
    from game.economy import exchange  # noqa: F401


def test_formulas_are_real_now() -> None:
    from game.combat import formulas

    assert formulas.hp(1, 15, 1.0) == 232  # заглушек больше нет


def test_all_six_subclasses_registered() -> None:
    from game.classes import REGISTRY, Role

    assert set(REGISTRY) == {
        "guardian", "blood_knight", "shadow_blade",
        "poisoner", "elementalist", "dark_mystic",
    }
    by_class: dict[str, int] = {}
    for sub in REGISTRY.values():
        by_class[sub.base_class] = by_class.get(sub.base_class, 0) + 1
    assert by_class == {"warrior": 2, "rogue": 2, "mage": 2}
    # хилер намеренно один — Тёмный мистик
    healers = [s for s in REGISTRY.values() if s.natural_role == Role.HEALER]
    assert [h.id for h in healers] == ["dark_mystic"]


def test_guardian_skills_registered() -> None:
    from game.combat.skills import DEFENSIVE_SKILLS, OFFENSIVE_SKILLS
    import game.classes  # noqa: F401

    assert "attack" in OFFENSIVE_SKILLS
    for skill in ("guardian_block", "guardian_provoke", "guardian_group_shield"):
        assert skill in DEFENSIVE_SKILLS
