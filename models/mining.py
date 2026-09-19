from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
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
