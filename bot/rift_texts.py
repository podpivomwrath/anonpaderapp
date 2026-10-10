"""Разломы: тексты чата. Бой ведёт bot/handlers/raid_combat.py и ждёт от
модуля текстов рейда пролог, переходы, эпилог и картинки - RiftTexts
отдаёт то же самое для одного типа разлома."""

from bot.vk_media import photo_attachment
from game.economy import rift_config as rc
from models import Rift

BTN_CANCEL = "✖ Отменить вход"


def _photo(photo_id: str) -> str | None:
    return photo_attachment(photo_id) if photo_id else None


def title(kind: str) -> str:
    t = rc.RIFT_TYPES[kind]
    return f"{t.emoji} {t.name}"


def size_line(kind: str) -> str:
    t = rc.RIFT_TYPES[kind]
    low = 3 if t.max_size >= 5 else 2
    return f"до {t.max_size} игроков (лучше {low}-{t.max_size})"


class RiftTexts:
    """Тексты одного типа в форме модуля текстов рейда."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.t = rc.RIFT_TYPES[kind]
        self.PROLOGUE_TEXT = f"{title(kind)}\n\n{self.t.entry_text}"
        self.EPILOGUE_TEXT = f"🌀 Разлом пройден.\n{self.t.victory_text}"
        self.RAID_DEFEAT_TEXT = f"🌀 Разлом не пройден.\n{self.t.defeat_text}"

    def stage_name(self, stage: int) -> str:
        return self.t.stages[stage - 1]

    def appear_text(self, stage: int) -> str:
        total = len(self.t.stages)
        if stage == total:
            return f"👁 {self.t.boss}\n{self.t.hint}"
        return f"⚔️ Этап {stage} из {total}: {self.stage_name(stage)}."

    def transition_text(self, cleared: int) -> str:
        return f"Этап взят. Впереди - {self.stage_name(cleared + 1)}."

    def prologue_attachment(self) -> str | None:
        return _photo(rc.RIFT_IMAGES[self.kind]["entry"])

    def stage_attachment(self, stage: int) -> str | None:
        if stage == len(self.t.stages):
            return _photo(rc.RIFT_IMAGES[self.kind]["boss"])
        return None


def here_text(rift: Rift, minutes: int) -> str:
    lo, hi = rc.BANDS[rift.ring]
    t = rc.RIFT_TYPES[rift.kind]
    return (
        f"🌀 Здесь разлом: {title(rift.kind)}\n"
        f"Уровни {lo}-{hi} · {size_line(rift.kind)} · закроется через {minutes} мин.\n"
        f"{t.hint}\n\n"
        "Вход - вся группа на клетке, лидер жмёт «Войти». Минуту вы ждёте у входа, "
        "и в это время на вас могут напасть."
    )


def busy_text(rift: Rift) -> str:
    what = "внутри уже группа" if rift.state == "running" else "у входа ждёт группа"
    return f"🌀 Здесь разлом: {title(rift.kind)} - {what}."


def wait_text(rift: Rift) -> str:
    return (
        f"⏳ {title(rift.kind)}: вход через {rc.ENTRY_WAIT_SECONDS} сек.\n"
        "Стойте на клетке. Если на вас нападут и победят - разлом достанется другим. "
        f"Передумали - «{BTN_CANCEL}», выйдет вся группа."
    )


WAITING_REMINDER = f"⏳ Вы ждёте у входа в разлом. Отменить - «{BTN_CANCEL}»."
CANCELLED_TEXT = "Вход в разлом отменён."
LOST_TEXT = "Вход в разлом сорван: у входа никого не осталось."
RESTART_TEXT = "🌀 Разлом закрылся: мир дрогнул (перезапуск). Разлом снова свободен."
