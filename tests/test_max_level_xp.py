"""На 60 уровне опыт не начисляется и не списывается (решение владельца).

Раньше код считал начисление, писал его в базу и тут же обнулял, а игроку
показывал «+105 опыта», ежедневки обещали «+97832 опыта», профиль - «опыт: 0».
"""

from types import SimpleNamespace

from bot import dailies_texts
from game.combat import balance_config as bc
from game.combat import display
from services import experience_service


def _character(level: int, experience: int = 0):
    return SimpleNamespace(level=level, experience=experience, current_hp=100, premium_until=None)


def test_no_xp_is_granted_at_max_level() -> None:
    character = _character(bc.MAX_LEVEL)
    stats = SimpleNamespace(unspent_points=0)
    result = experience_service.add_experience(character, stats, 5000)
    assert (result.xp_awarded, result.levels_gained, result.new_level) == (0, 0, bc.MAX_LEVEL)
    assert character.experience == 0 and character.current_hp == 100 and stats.unspent_points == 0


def test_death_takes_no_xp_at_max_level() -> None:
    assert experience_service.apply_death_penalty(_character(bc.MAX_LEVEL, experience=900)) == 0


def test_zero_xp_prints_nothing() -> None:
    assert display.xp_delta_line(0) == ""
    assert display.xp_delta_line(105) == "(+105 опыта)"


def test_daily_texts_skip_zero_xp() -> None:
    done = SimpleNamespace(quest_title="Охота", xp=0, gold=390, xp_premium_applied=False)
    text = dailies_texts.progress_notice_from([done], None)
    assert "опыта" not in text and "+390 золота" in text
