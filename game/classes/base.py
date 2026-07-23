"""Определения подклассов и реестр.

Роль ГИБКАЯ: определяется выбранными микробаффами, а не подклассом.
У подкласса есть «естественная» роль и 1-2 «дотягиваемые» (п.6 дизайна).
"""

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    TANK = "tank"
    DD = "dd"
    SUPPORT = "support"
    HEALER = "healer"


@dataclass(frozen=True)
class SubclassDef:
    id: str
    title: str
    base_class: str          # models.enums.BaseClass
    primary_stat: str        # "str" | "agi" | "int"
    natural_role: Role
    flexible_roles: tuple[Role, ...]
    skills: tuple[str, ...]  # id умений (реализация — в модуле подкласса)


REGISTRY: dict[str, SubclassDef] = {}


def register(subclass: SubclassDef) -> SubclassDef:
    REGISTRY[subclass.id] = subclass
    return subclass
