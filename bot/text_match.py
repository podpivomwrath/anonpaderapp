"""Сравнение текста команды без учёта регистра (2026-10-12).

Правила text= у всех лейблеров не смотрят на регистр (vbml_ignore_case):
«страж» проходит туда же, куда «Страж». Но обработчик, который потом ищет
нажатый текст в словаре по точному написанию, на «страж» падал бы с KeyError
или молча ничего не делал. Сюда - всё, что сопоставляет message.text с
заранее известными подписями."""

from typing import TypeVar

T = TypeVar("T")


def canonical(options, text: str | None) -> str | None:
    """Подпись из options, совпадающая с text без учёта регистра."""
    if text is None:
        return None
    if text in options:
        return text
    folded = text.strip().casefold()
    return next((o for o in options if o.casefold() == folded), None)


def lookup(mapping: dict[str, T], text: str | None) -> T | None:
    key = canonical(mapping, text)
    return mapping[key] if key is not None else None


def same(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.strip().casefold() == b.strip().casefold()
