"""Число и слово в нужной форме: 1 очко, 2 очка, 5 очков (2026-10-23 -
в текстах висели «1 убийств», «2 самоцветов»)."""


def word(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def count(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {word(n, one, few, many)}"


def gems(n: int) -> str:
    return count(n, "самоцвет", "самоцвета", "самоцветов")
