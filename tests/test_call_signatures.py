"""Статическая проверка: вызов функции своего же модуля обязан сходиться
с её сигнатурой.

Написан после боевого случая: `_broadcast_board(...)` в рейде звали с
`boss_lines=`, которого в сигнатуре не было. Питон ловит такое только в
момент вызова, а вызов этот - разрешение хода рейда, то есть код падал уже
у игроков: ход проходил, доска не уходила, бой выглядел намертво зависшим.
Тестов на этот путь нет и вряд ли будут на каждый - поэтому проверяем
арность статически, по всему дереву сразу.

Осознанные ограничения: смотрим только вызовы по голому имени (`f(...)`,
не `mod.f(...)`) и только на функции, объявленные в ТОМ ЖЕ модуле на верхнем
уровне и БЕЗ декораторов - декоратор вправе поменять сигнатуру, и тогда
проверять нечего. Вызовы со `*args`/`**kwargs` пропускаем по той же причине.
"""

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_TOP_LEVEL = {".venv", "miniapp", "alembic", "tests", "tools", ".git", "node_modules"}

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _signature_of(fn: FunctionNode) -> inspect.Signature:
    """Сигнатура из AST: нас интересует только арность, не типы и не значения
    по умолчанию, поэтому любое умолчание представляем как None."""
    kind = inspect.Parameter
    args = fn.args
    params: list[inspect.Parameter] = []
    params += [kind(p.arg, kind.POSITIONAL_ONLY) for p in args.posonlyargs]
    params += [kind(p.arg, kind.POSITIONAL_OR_KEYWORD) for p in args.args]
    if args.vararg:
        params.append(kind(args.vararg.arg, kind.VAR_POSITIONAL))
    params += [kind(p.arg, kind.KEYWORD_ONLY) for p in args.kwonlyargs]
    if args.kwarg:
        params.append(kind(args.kwarg.arg, kind.VAR_KEYWORD))

    if args.defaults:
        positional = [
            i for i, p in enumerate(params)
            if p.kind in (kind.POSITIONAL_ONLY, kind.POSITIONAL_OR_KEYWORD)
        ]
        for index in positional[-len(args.defaults):]:
            params[index] = params[index].replace(default=None)
    for name, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is None:
            continue
        index = next(i for i, p in enumerate(params) if p.name == name.arg)
        params[index] = params[index].replace(default=None)
    return inspect.Signature(params)


def _source_files() -> list[Path]:
    return [
        path for path in sorted(ROOT.rglob("*.py"))
        if not set(path.relative_to(ROOT).parts) & SKIP_TOP_LEVEL
    ]


def test_intra_module_calls_match_signatures() -> None:
    mismatches: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {
            node.name: node for node in tree.body
            if isinstance(node, FunctionNode) and not node.decorator_list
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            target = defined.get(node.func.id)
            if target is None:
                continue
            if any(isinstance(a, ast.Starred) for a in node.args):
                continue
            if any(k.arg is None for k in node.keywords):
                continue
            try:
                _signature_of(target).bind(
                    *[None] * len(node.args), **{k.arg: None for k in node.keywords},
                )
            except TypeError as exc:
                where = path.relative_to(ROOT).as_posix()
                mismatches.append(f"{where}:{node.lineno} {node.func.id}(): {exc}")
    assert not mismatches, "Вызов не сходится с сигнатурой:\n" + "\n".join(mismatches)


def test_the_check_actually_catches_a_mismatch() -> None:
    """Страховка от «тест зелёный, потому что ничего не проверяет»."""
    tree = ast.parse("def f(a, b=1):\n    pass\n")
    signature = _signature_of(tree.body[0])
    signature.bind(None)  # достаточно одного обязательного
    signature.bind(None, None)
    signature.bind(None, b=None)
    for bad in ((), (None, None, None)):
        try:
            signature.bind(*bad)
        except TypeError:
            continue
        raise AssertionError(f"Проверка проспала неверный вызов: {bad}")
    try:
        signature.bind(None, c=None)
    except TypeError:
        return
    raise AssertionError("Проверка проспала неизвестный именованный аргумент")
