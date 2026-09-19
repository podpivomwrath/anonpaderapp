from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterOre(Base):
    """Руда в инвентаре: стак по (вид + градация) ШТУКАМИ (патч 59).

    Не весом, в отличие от рыбы: носить руды можно сколько угодно, ограничивать
    нечем, а будущие рецепты прокачки будут требовать «3 редкого железа», то
    есть штуки. Потолка на количество нет сознательно.

    Руда не продаётся ни одному НПС и не теряется при поражении в PvP: терять
    то, что некуда девать, было бы чистым наказанием без обратной стороны.
    """

    __tablename__ = "character_ore"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "ore_id", "grade", name="uq_character_ore_char_ore_grade"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    ore_id: Mapped[str] = mapped_column(String(32))
    # Значения из mining_config.GRADES: common|rare|epic|legendary
    grade: Mapped[str] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(BigInteger, default=0)


class MineVein(Base):
    """Сколько руды сейчас лежит в статичном руднике (патч 59).

    Это состояние МИРА, общее для всех игроков, а не свойство персонажа:
    рудник — ограниченный общий ресурс, который наполняет активность всего
    сервера (mining_config.ORE_SPAWN_CHANCE_PER_EXPLORATION) и опустошают те,
    кто успел прийти. Пустой рудник — нормальное состояние.

    Строка заводится лениво, при первом обращении к руднику: сидировать все
    27 в миграции смысла нет, а добавление нового рудника в контент тогда
    требовало бы ещё одной миграции.

    Вид и градация здесь НЕ хранятся намеренно — только количество. Иначе
    игроки выцепляли бы из общих рудников легендарное, оставляя другим
    обычное; розыгрыш идёт в момент добычи (game/economy/mining.py::roll_grade).
    """

    __tablename__ = "mine_veins"

    mine_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    ore_count: Mapped[int] = mapped_column(default=0)


class MiningEvent(Base):
    """Журнал событий горного дела (патч 61): что добыли и когда появилось.

    Заведён, чтобы смотреть, как ремесло ведёт себя НА ПРОДЕ, а не в
    симуляторе: сколько руды реально собирают, какой именно, и успевает ли
    спавн за добычей. Текущий остаток в жилах на эти вопросы не отвечает — по
    нему не видно ни оборота, ни скорости.

    Одна строка на событие, агрегаты считаются запросом. Так можно задать
    вопрос, который не предусмотрели заранее; счётчики этого не умеют.

    Поля заполняются по виду события:
      spawn — mine_id, остальное пусто (вид и градация при спавне ещё не
              определены, они разыгрываются в момент добычи);
      dig   — character_id, ore_id, grade, seconds; mine_id пуст у мелкой
              жилы из исследования, её нет на карте.
    """

    __tablename__ = "mining_events"
    __table_args__ = (
        Index("ix_mining_events_kind_created", "kind", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # spawn | dig
    kind: Mapped[str] = mapped_column(String(8))
    mine_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    ore_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Сколько секунд заняла добыча — видно, как на деле работает штраф за
    # глубину и насколько он мешает.
    seconds: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
