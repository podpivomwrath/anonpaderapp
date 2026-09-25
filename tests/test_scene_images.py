"""Слоты иллюстраций для рейда, путей и сюжетных актов.

Картинки в игре лежат не в репозитории, а в альбоме группы ВК, и в коде от
них остаётся только номер фото. Из-за этого обычный «файл не найден» здесь не
сработает: пустой слот выглядит ровно как заполненный, просто сообщение
уходит без вложения. Замечает это игрок, а не сборка.

Тесты следят за тем, что слоты СУЩЕСТВУЮТ и не разъезжаются с контентом:
новый подкласс или новый акт не должны тихо появиться без места под картинку.
Сами номера фото не проверяются - пустой слот это нормальное состояние, пока
художник не закончил.
"""

import ast
import json
import re
from pathlib import Path

import pytest

from bot import raid_texts as rt
from game.classes import REGISTRY
from game.content_loader import load_story_line

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
REGIONS = ("ridge", "woods", "docks", "scorched")


# --- Рейд: один кадр на бой ------------------------------------------------


def test_every_raid_stage_has_a_photo_slot() -> None:
    """Три этапа - три картинки. Четвёртого этапа нет, лишних слотов тоже."""
    assert set(rt.STAGE_PHOTO_IDS) == {1, 2, 3}


def test_raid_stage_without_a_photo_sends_no_attachment() -> None:
    """Пустой слот обязан давать None, а не строку photo-0_ : иначе ВК
    отклонит сообщение целиком, и этап не начнётся вовсе."""
    rt.STAGE_PHOTO_IDS[1] = ""
    assert rt.stage_attachment(1) is None
    assert rt.stage_attachment(99) is None


def test_both_raid_scenes_carry_the_stage_picture() -> None:
    """Этапы появляются в ДВУХ разных местах: первый вместе с прологом при
    старте рейда, второй и третий при смене этапа. Забыть одно из них легко,
    и тогда картинки будут у части боёв."""
    source = (ROOT / "bot" / "handlers" / "raid_combat.py").read_text(encoding="utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and any(
            isinstance(kw.value, (ast.Name, ast.JoinedStr, ast.Subscript))
            and kw.arg == "message"
            for kw in node.keywords
        )
    ]
    with_stage_picture = [
        call
        for call in calls
        if any(
            kw.arg == "attachment"
            and "stage_attachment" in ast.unparse(kw.value)
            for kw in call.keywords
        )
    ]
    assert len(with_stage_picture) == 2, (
        "обе сцены появления (старт рейда и смена этапа) должны нести "
        f"картинку этапа, нашлось {len(with_stage_picture)}"
    )


# --- Подклассы: картинка к описанию пути -----------------------------------


def _keeper() -> dict:
    return json.loads((CONTENT / "npc" / "list_keeper.json").read_text(encoding="utf-8"))


def test_every_subclass_has_a_picture_slot() -> None:
    """Слоты берутся из того же файла, что и описания путей, поэтому новый
    подкласс без картинки виден сразу - а не через месяц, когда кто-то
    заметит, что у одного пути иллюстрации нет."""
    images = _keeper()["subclass_select"]["path_images"]
    assert set(images) == {s.id for s in REGISTRY.values()}


def test_subclass_description_carries_its_picture() -> None:
    source = (ROOT / "bot" / "handlers" / "list_keeper.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", "", source)
    assert "attachment=path_attachment(subclass_id)" in code, (
        "описание пути должно нести его иллюстрацию"
    )


# --- Сюжет: одна картинка на акт -------------------------------------------


@pytest.mark.parametrize("region", REGIONS)
def test_acts_beyond_the_first_have_a_picture_slot(region: str) -> None:
    """У акта 1 слота нет намеренно: его первое задание выдаёт наставник, и к
    тому сообщению уже прикреплён его портрет."""
    line = load_story_line(region)
    for act in line.acts:
        if act.act == 1:
            continue
        raw = json.loads((CONTENT / "story" / f"{region}.json").read_text(encoding="utf-8"))
        slots = {a["act"]: ("image" in a) for a in raw["acts"]}
        assert slots[act.act], f"{region}: у акта {act.act} нет слота под картинку"


@pytest.mark.parametrize("region", REGIONS)
def test_act_picture_belongs_only_to_the_quest_that_opens_the_act(region: str) -> None:
    """Иначе она повторится на каждом задании акта и перестанет что-либо
    значить."""
    from services.story_service import act_opening_image

    line = load_story_line(region)
    for act in line.acts:
        for position, quest in enumerate(act.quests):
            got = act_opening_image(line, quest.id)
            if position == 0:
                assert got == act.image, f"{quest.id} открывает акт, но картинки не получил"
            else:
                assert got is None, f"{quest.id} не открывает акт, а картинку получил"


def test_story_turn_result_keeps_act_image_last() -> None:
    """Поля StoryTurnResult передаются ПОЗИЦИОННО в нескольких ветках
    visit_mentor. Новое поле в середине не сломает ни импорт, ни линтер - оно
    молча сдвинет levels_gained в чужой слот, и игрок перестанет получать
    уведомление об уровне."""
    from services.story_service import StoryTurnResult

    fields = list(StoryTurnResult.__dataclass_fields__)
    assert fields[-1] == "act_image", f"act_image обязан быть последним, сейчас {fields}"


# --- Промты не должны отставать от контента -------------------------------

PROMPTS = ROOT / "tools" / "story_art_prompts.md"


def test_every_picture_slot_has_a_prompt_written_for_it() -> None:
    """Слот без промта - это картинка, которую никто не закажет.

    Тот же урок, из-за которого промты иконок генерируются из контента
    (tools/icon_prompts.py): список, набранный руками, расходится с игрой на
    первом же новом акте, и замечают это по пустому месту в чате.
    """
    doc = PROMPTS.read_text(encoding="utf-8")

    missing = [s.title for s in REGISTRY.values() if s.title not in doc]
    assert not missing, f"пути без промта: {missing}"

    for region in REGIONS:
        for act in load_story_line(region).acts:
            if act.act == 1:
                continue
            assert act.title in doc, f"{region}: у акта «{act.title}» нет промта"
