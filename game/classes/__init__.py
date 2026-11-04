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

__all__ = ["REGISTRY", "Role", "SubclassDef"]
