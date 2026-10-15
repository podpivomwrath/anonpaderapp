"""Пакеты самоцветов за рубли (2026-10-15). Цены - ровно как в прайс-листе
miniapp/public/legal/prices.html: 1 самоцвет = 1 рубль, без скидок за объём.
Меняешь здесь - меняй и прайс-лист (юридический документ)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GemPack:
    id: str
    name: str
    gems: int
    rub: int


PACKS: tuple[GemPack, ...] = (
    GemPack("handful", "Горсть", 100, 100),
    GemPack("pouch", "Мешочек", 300, 300),
    GemPack("purse", "Кошель", 500, 500),
    GemPack("casket", "Ларец", 1000, 1000),
    GemPack("chest", "Сундук", 2500, 2500),
    GemPack("treasury", "Казна", 5000, 5000),
)
BY_ID = {p.id: p for p in PACKS}
