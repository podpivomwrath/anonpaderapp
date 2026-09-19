"""Миграции (патч 60): цепочка и совпадение результата со схемой моделей.

Тесты поднимают базу через Base.metadata.create_all, то есть миграции не
прогоняются НИ ОДНИМ обычным тестом. Сломанная миграция обнаруживалась бы
только на деплое.

Прогнать всю цепочку на временном SQLite не выйдет: в ранних миграциях есть
Postgres-специфичный ALTER COLUMN ... TYPE. Поэтому схема сверяется иначе —
миграции «проигрываются» статически по их же исходникам (набор операций тут
простой: create_table / add_column / drop_column / drop_table), и результат
сравнивается с моделями. Это ловит ровно ту ошибку, которая случается на
практике: колонку добавили в модель и забыли в миграции.
"""

import ast
import pathlib
import re

from models import Base

MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _revisions() -> dict[str, tuple[str | None, str]]:
    """{revision: (down_revision, имя файла)} по всем файлам миграций."""
    result: dict[str, tuple[str | None, str]] = {}
    for path in MIGRATIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        # Часть миграций объявляет ревизии с аннотацией типа
        # (revision: str = "0001"), часть — без. Разбираем оба вида.
        rev = re.search(r"^revision(?:\s*:[^=]+)?\s*=\s*['\"]([^'\"]+)", text, re.MULTILINE)
        down = re.search(
            r"^down_revision(?:\s*:[^=]+)?\s*=\s*(?:['\"]([^'\"]+)|None)", text, re.MULTILINE
        )
        if rev:
            result[rev.group(1)] = (down.group(1) if down and down.group(1) else None, path.name)
    return result


def test_migration_chain_is_linear_and_has_one_head() -> None:
    """Две головы означают, что кто-то ответвился и alembic upgrade head
    упадёт на проде — ошибка, которую хочется знать до деплоя."""
    revisions = _revisions()
    assert revisions, "миграции не найдены"

    downs = {down for down, _name in revisions.values() if down}
    heads = [rev for rev in revisions if rev not in downs]
    assert len(heads) == 1, f"голов должно быть ровно одна, а их {len(heads)}: {heads}"

    roots = [rev for rev, (down, _n) in revisions.items() if down is None]
    assert len(roots) == 1, f"корней должно быть ровно один: {roots}"

    # Каждая ссылка down_revision обязана указывать на существующую ревизию.
    for rev, (down, name) in revisions.items():
        if down is not None:
            assert down in revisions, f"{name}: down_revision={down} не существует"

    # Цепочка обязана обходиться целиком, без петель.
    seen, current = set(), heads[0]
    while current is not None:
        assert current not in seen, f"петля в цепочке миграций на {current}"
        seen.add(current)
        current = revisions[current][0]
    assert seen == set(revisions), f"вне цепочки остались ревизии: {set(revisions) - seen}"


def test_every_migration_has_a_downgrade() -> None:
    """Без downgrade откат деплоя невозможен, а deploy-release.sh на него
    рассчитывает."""
    missing = [
        path.name for path in MIGRATIONS.glob("*.py")
        if "def downgrade" not in path.read_text(encoding="utf-8")
    ]
    assert not missing, f"миграции без downgrade: {missing}"




def _schema_from_migrations() -> dict[str, set[str]]:
    """Схема, которая получится, если проиграть все миграции по порядку.

    Читаются именно исходники, а не результат прогона: полную цепочку негде
    выполнить (Postgres-специфичный DDL внутри), зато набор операций здесь
    простой и разбирается однозначно.
    """
    revisions = _revisions()
    downs = {down for down, _n in revisions.values() if down}
    head = next(rev for rev in revisions if rev not in downs)

    order: list[str] = []
    current: str | None = head
    while current is not None:
        order.append(current)
        current = revisions[current][0]
    order.reverse()

    tables: dict[str, set[str]] = {}
    for rev in order:
        path = MIGRATIONS / revisions[rev][1]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        upgrade = next(
            (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
            None,
        )
        if upgrade is None:
            continue
        for node in ast.walk(upgrade):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            op_name = node.func.attr
            args = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if op_name == "create_table" and args:
                columns = {
                    inner.args[0].value
                    for inner in ast.walk(node)
                    if isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "Column"
                    and inner.args
                    and isinstance(inner.args[0], ast.Constant)
                }
                tables[args[0]] = columns
            elif op_name == "add_column" and args:
                column = next(
                    (
                        inner.args[0].value
                        for inner in ast.walk(node)
                        if isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "Column"
                        and inner.args
                        and isinstance(inner.args[0], ast.Constant)
                    ),
                    None,
                )
                if column:
                    tables.setdefault(args[0], set()).add(column)
            elif op_name == "drop_column" and len(args) >= 2:
                tables.get(args[0], set()).discard(args[1])
            elif op_name == "drop_table" and args:
                tables.pop(args[0], None)
    return tables


def test_migrations_build_the_same_schema_as_the_models() -> None:
    """Главная проверка: то, что строят миграции, совпадает с моделями.

    Без неё забытая миграция всплывала бы только на боевой базе — обычные
    тесты поднимают схему через Base.metadata.create_all и миграции не
    трогают вовсе.
    """
    built = _schema_from_migrations()
    problems = []

    for table in Base.metadata.sorted_tables:
        if table.name not in built:
            problems.append(f"миграции не создают таблицу {table.name}")
            continue
        model_cols = {c.name for c in table.columns}
        missing = model_cols - built[table.name]
        extra = built[table.name] - model_cols
        if missing:
            problems.append(f"{table.name}: нет в миграциях -> {sorted(missing)}")
        if extra:
            problems.append(f"{table.name}: в миграциях лишнее -> {sorted(extra)}")

    orphans = set(built) - {t.name for t in Base.metadata.sorted_tables}
    for name in sorted(orphans):
        problems.append(f"таблица {name} есть в миграциях, но не в моделях")

    assert not problems, "схема миграций разошлась с моделями:\n" + "\n".join(problems)
