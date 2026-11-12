"""Создание персонажа без второго «Уверен?» (2026-11-13, владелец): кнопки
«Выбрать этот путь» и «Иду туда» сразу делают выбор."""

from bot import onboarding_texts as texts
from bot.handlers import onboarding


async def test_choose_path_confirms_at_once(monkeypatch) -> None:
    done = []

    async def fake_class(message):
        done.append(("class", message))

    async def fake_region(message):
        done.append(("region", message))

    monkeypatch.setattr(onboarding, "class_confirm", fake_class)
    monkeypatch.setattr(onboarding, "region_confirm", fake_region)
    await onboarding.class_choose_path("m1")
    await onboarding.region_go("m2")
    assert done == [("class", "m1"), ("region", "m2")]


def test_name_hint_under_awakening() -> None:
    text = texts.awakening_text()
    assert text.startswith(texts.KEEPER["scene_awakening"])
    assert "от 3 до 16 знаков" in text
