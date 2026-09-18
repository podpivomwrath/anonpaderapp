from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterFish(Base):
    """Садок: рыба стакается по (вид + градация) СУММАРНЫМ ВЕСОМ, а не
    отдельными хвостами (патч 58).

    Три окуня на 1, 2 и 3 кг — это одна строка «6.0 кг обычных окуней», а не
    три записи. Так таблица не пухнет от мелочи, экран читается, а цена
    считается точно: она линейна по весу, поэтому цена стака равна сумме цен
    его рыб (именно поэтому в price_of нельзя вводить нелинейность по весу —
    стак сразу начнёт врать).

    Рекордные экземпляры при этом НЕ теряются в стаке: лучший вес по каждому
    виду пишется отдельно в CharacterFishRecord в момент поимки. Стак — это
    товар, рекорд — достижение, и жизненные циклы у них разные.
    """

    __tablename__ = "character_fish"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "fish_id", "grade", name="uq_character_fish_char_fish_grade"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    fish_id: Mapped[str] = mapped_column(String(32))
    # Значения из fishing_config.GRADES: small|common|big|trophy|legendary
    grade: Mapped[str] = mapped_column(String(16))
    # Вес ТОЛЬКО в граммах целым числом: см. комментарий в fishing_config.
    total_grams: Mapped[int] = mapped_column(BigInteger, default=0)


class CharacterFishRecord(Base):
    """Личный рекорд по виду — самый тяжёлый пойманный экземпляр (патч 58).

    Он же источник общего топа по весу: ORDER BY weight_grams DESC по всей
    таблице. Отдельной «серверной» таблицы рекордов не нужно.

    Не удаляется никогда: ни продажа садка, ни смерть в PvP рекорд не трогают
    — потерять можно товар, но не то, что уже поймал.
    """

    __tablename__ = "character_fish_records"
    __table_args__ = (
        UniqueConstraint("character_id", "fish_id", name="uq_character_fish_records_char_fish"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    fish_id: Mapped[str] = mapped_column(String(32))
    weight_grams: Mapped[int] = mapped_column(index=True)
    caught_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
