"""Картинки рудников и озёр - по тирам (патч 99).

Мест по двадцать семь, а тиров пять: одна картинка на тир. Своё поле image у
места остаётся главнее - то же правило наследования, что у мобов (патч 36).
"""

from pathlib import Path

import pytest

from bot import fishing_texts as ft
from bot import mining_texts as mt
from game import content_loader as cl

PROMPTS = Path(__file__).resolve().parent.parent / "tools" / "story_art_prompts.md"

SETS = [
    ("рудник", mt, cl.load_mines, mt.mine_attachment),
    ("озеро", ft, cl.load_lakes, ft.lake_attachment),
]


@pytest.mark.parametrize(("label", "texts", "load", "_attach"), SETS)
def test_every_tier_in_the_content_has_a_slot(label, texts, load, _attach) -> None:
    """Новый тир не должен появиться без места под картинку."""
    assert {place.tier for place in load()} == set(texts.TIER_PHOTO_IDS), label


@pytest.mark.parametrize(("label", "texts", "load", "attach"), SETS)
def test_tier_picture_is_used_when_the_place_has_none(label, texts, load, attach, monkeypatch) -> None:
    place = next(p for p in load() if not p.image)
    monkeypatch.setitem(texts.TIER_PHOTO_IDS, place.tier, "457230001")
    assert attach(place).endswith("_457230001"), label


@pytest.mark.parametrize(("label", "texts", "load", "attach"), SETS)
def test_own_picture_of_a_place_wins(label, texts, load, attach, monkeypatch) -> None:
    place = load()[0].model_copy(update={"image": "457230009"})
    monkeypatch.setitem(texts.TIER_PHOTO_IDS, place.tier, "457230001")
    assert attach(place).endswith("_457230009"), label


@pytest.mark.parametrize(("label", "texts", "load", "attach"), SETS)
def test_no_picture_means_no_attachment(label, texts, load, attach, monkeypatch) -> None:
    """Пустой слот обязан давать None, а не «photo-0_»: иначе ВК отклонит
    сообщение целиком, и игрок не сможет войти к жиле или к воде."""
    place = next(p for p in load() if not p.image)
    monkeypatch.setitem(texts.TIER_PHOTO_IDS, place.tier, "")
    assert attach(place) is None, label


@pytest.mark.parametrize(("label", "texts", "load", "_attach"), SETS)
def test_every_tier_has_a_prompt(label, texts, load, _attach) -> None:
    doc = PROMPTS.read_text(encoding="utf-8")
    missing = [tier for tier in texts.TIER_PHOTO_IDS if f"{label.capitalize()}, тир {tier}" not in doc]
    assert not missing, f"{label}: нет промта для тиров {missing}"


def test_picture_is_attached_only_to_the_entrance() -> None:
    """Вход видят один раз за визит, а подсечку и ход добычи - постоянно:
    картинка там была бы шумом."""
    root = Path(__file__).resolve().parent.parent / "bot" / "handlers"
    assert (root / "fishing.py").read_text(encoding="utf-8").count("lake_attachment") == 1
    assert (root / "mining.py").read_text(encoding="utf-8").count("mine_attachment") == 1
