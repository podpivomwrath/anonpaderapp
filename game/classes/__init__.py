"""6 подклассов (3 базовых класса × 2). Импорт модулей регистрирует
определения и боевые умения в реестрах."""

from game.classes.base import REGISTRY, Role, SubclassDef
from game.classes import (
    blood_knight,
    dark_mystic,
    elementalist,
    guardian,
    poisoner,
    shadow_blade,
)
from game.combat import rune_skills  # noqa: F401 - новые навыки рун (2026-11-10)

__all__ = ["REGISTRY", "Role", "SubclassDef"]
