"""Патч 82: оболочка мини-аппа — тема и слой фона.

Два бага доехали до прода подряд, и оба ловятся статически:

1. `<ConfigProvider appearance="dark">` — в VKUI 8 такого пропа НЕТ. React
   передал неизвестный проп дальше, VKUI молча взял тему из системы, и на
   телефоне интерфейс был белым при «зафиксированной» тёмной теме. Опечатку
   в имени пропа не видно ни в сборке, ни в линтере — только глазами на
   устройстве с другой темой.

2. Слой с фоновой картинкой лежал ПОД непрозрачной заливкой контейнеров
   VKUI, и фон не появлялся нигде.

Смотреть глазами каждую сборку никто не будет, поэтому смотрит тест.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MINIAPP = ROOT / "miniapp"
VKUI_PROPS = (
    MINIAPP / "node_modules" / "@vkontakte" / "vkui" / "dist" / "components"
    / "ConfigProvider" / "ConfigProviderContext.d.ts"
)


def _app_jsx() -> str:
    return (MINIAPP / "src" / "App.jsx").read_text(encoding="utf-8")


def test_config_provider_gets_only_props_vkui_knows() -> None:
    """Именно этим `appearance` и проскочил: несуществующий проп не ломает
    ни сборку, ни линтер - он просто ничего не делает."""
    if not VKUI_PROPS.exists():
        pytest.skip("node_modules не установлены")

    declared = set(re.findall(r"^\s{4}(\w+)[?:]", VKUI_PROPS.read_text(encoding="utf-8"), re.MULTILINE))
    assert declared, "не удалось прочитать список пропов ConfigProvider"

    used = re.search(r"<ConfigProvider\s([^>]*)>", _app_jsx())
    assert used, "ConfigProvider не найден в App.jsx"
    passed = set(re.findall(r"(\w+)=", used.group(1)))

    unknown = passed - declared - {"children"}
    assert not unknown, (
        f"ConfigProvider не знает таких пропов: {sorted(unknown)}. "
        f"Известные: {sorted(declared)}"
    )


def test_theme_is_pinned_to_dark() -> None:
    """Тема зафиксирована намеренно (патч 77): игра нарисована тёмной."""
    app = _app_jsx()
    assert "colorScheme" in app
    assert re.search(r"COLOR_SCHEME\s*=\s*'dark'", app), "тёмная тема должна быть жёстко задана"
    # Проверяем МЕХАНИЗМ, а не слово: упоминание в комментарии - это история
    # правки, и запрещать её незачем (ровно на этом тест уже спотыкался
    # в патче 73).
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", app, flags=re.DOTALL)
    assert "bridge.subscribe" not in code, "за темой клиента ВК больше не следуем"


def test_background_layer_is_not_covered_by_vkui() -> None:
    """Контейнеры VKUI красятся непрозрачно и перекрывали слой с картинкой."""
    css = (MINIAPP / "src" / "index.css").read_text(encoding="utf-8")
    assert "body::before" in css, "слой фона пропал"
    assert "var(--app-bg)" in css, "слой фона не читает переменную с картинкой"
    for selector in (".vkuiAppRoot__layoutPlain", ".vkuiPanel__in"):
        assert selector in css, f"{selector} снова закроет фон своей заливкой"


def test_background_css_is_always_present() -> None:
    """Файл генерируется всегда, даже пустой: иначе импорт в main.jsx ломает
    сборку до того, как картинки нарисуют."""
    generated = MINIAPP / "src" / "background.css"
    assert generated.exists()
    assert "background.css" in (MINIAPP / "src" / "main.jsx").read_text(encoding="utf-8")


def test_background_is_desktop_only() -> None:
    """Патч 84: на телефоне фона нет вовсе.

    Список там занимает почти весь экран, свободного места под картинку не
    остаётся, а сама сцена очень тёмная - разглядывать было нечего, зато вес
    и лишний запрос были. На ПК колонка ограничена, по бокам остаются поля.
    """
    css = (MINIAPP / "src" / "background.css").read_text(encoding="utf-8")
    if "--app-bg" not in css:
        pytest.skip("фон ещё не сгенерирован")
    assert "min-width" in css, "фон обязан подключаться только на широком экране"
    before_media = css[: css.index("@media")]
    assert "--app-bg" not in before_media, "вне медиазапроса фона быть не должно"


def test_background_layer_sits_below_content_without_negative_z() -> None:
    """Отрицательный слой зависит от того, кто из предков создаёт контекст
    наложения, и отлаживать это в вебвью нечем. Контент поднят явно."""
    css = (MINIAPP / "src" / "index.css").read_text(encoding="utf-8")
    layer = css[css.index("body::before"):]
    layer = layer[: layer.index("}")]
    assert "z-index: -1" not in layer, "слой фона снова на отрицательном z-index"
    assert re.search(r"#root\s*\{[^}]*z-index:\s*1", css, re.DOTALL),         "#root должен явно лежать над слоем фона"


def test_background_layer_has_no_heavy_vignette() -> None:
    """Виньетка inset 0 0 120px 10px при 75% чёрного роняла картинку с 42 до
    10 из 255 - темнее базового фона. Игрок видел ровную черноту и решил,
    что картинка не подключилась."""
    css = (MINIAPP / "src" / "index.css").read_text(encoding="utf-8")
    layer = css[css.index("body::before"):]
    layer = layer[: layer.index("}")]
    blur = re.search(r"box-shadow:[^;]*?(\d+)px\s+\d+px", layer)
    if blur:
        assert int(blur.group(1)) <= 40, (
            f"виньетка {blur.group(1)}px снова съест картинку: у неё яркость 28-42 из 255"
        )


# --- Кто на самом деле красит контейнер (патч 85) --------------------------------


def _built_css() -> str | None:
    import glob

    files = glob.glob(str(MINIAPP / "dist" / "assets" / "index-*.css"))
    return Path(files[0]).read_text(encoding="utf-8") if files else None


def _specificity(selector: str) -> tuple[int, int, int]:
    """Вес ОДНОГО селектора. Считать надо именно по одному.

    На этом я и ошибся: правило `.a,.b,.c{...}` на глаз выглядит
    специфичным, но каждый его селектор весит как один класс. Своё
    `.vkuiPanel__in` (0,1,0) проигрывало темному `.vkuiPanel__modePlain
    .vkuiPanel__in` (0,2,0) при любом порядке - панель оставалась чёрной на
    весь экран, и фон под ней было не разглядеть.
    """
    sel = re.sub(r"::[a-z-]+", "", selector)
    ids = len(re.findall(r"#[\w-]+", sel))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]+\]", sel))
    classes += len(re.findall(r":(?!:)[a-z-]+", sel))
    return (ids, classes, 0)


def _winning_background(css: str, target_class: str) -> str | None:
    """Правило, которое реально красит элемент: максимум веса, затем последнее."""
    found = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors, body = match.group(1), match.group(2)
        values = re.findall(r"background(?:-color)?:\s*([^;]+)", body)
        if not values:
            continue
        for selector in selectors.split(","):
            selector = selector.strip()
            if selector.endswith("." + target_class):
                found.append((_specificity(selector), match.start(), values[-1].strip()))
    if not found:
        return None
    found.sort(key=lambda row: (row[0], row[1]))
    return found[-1][2]


OPAQUE_TOKENS = ("var(--vkui--color_background", "#17181a", "#000")


@pytest.mark.parametrize(
    "container",
    ["vkuiPanel__in", "vkuiAppRoot__layoutPlain", "vkuiAppRoot__layoutCard"],
)
def test_layout_containers_do_not_paint_over_the_background(container: str) -> None:
    """Слой с картинкой лежит ПОД разметкой VKUI: любой непрозрачный
    контейнер поверх - и фона не видно вовсе."""
    css = _built_css()
    if css is None:
        pytest.skip("мини-апп не собран")
    winner = _winning_background(css, container)
    assert winner is not None, f".{container} не найден в сборке"
    assert not winner.startswith(OPAQUE_TOKENS), (
        f".{container} красится непрозрачно ({winner}) и закроет фон"
    )


def test_panel_really_asks_vkui_to_drop_its_background() -> None:
    """Проверка выше смотрит CSS, но его одного мало.

    Правило `.vkuiPanel__disableBackground .vkuiPanel__in{background:0 0}`
    VKUI отдаёт всегда - сработает оно только если КЛАСС есть на элементе, а
    класс появляется от пропа. Без этой проверки предыдущий тест оставался
    зелёным при убранном пропе (проверено).
    """
    hub = (MINIAPP / "src" / "components" / "Hub.jsx").read_text(encoding="utf-8")
    panels = re.findall(r"<Panel\b([^>]*)>", hub)
    assert panels, "Panel не найден в Hub.jsx"
    without = [p for p in panels if "disableBackground" not in p]
    assert not without, (
        f"{len(without)} из {len(panels)} Panel без disableBackground - "
        "они закрасят фон своей заливкой"
    )


def test_map_is_not_squeezed_by_the_column_cap() -> None:
    """Колонка ограничена 560 ради читаемости списков, но карта рисует сетку
    мира - в такой ширине видно несколько клеток вместо области вокруг
    игрока. Сломалось это не сразу: до патча 84 браузер пропускал весь
    медиазапрос из-за range-синтаксиса, и карта оставалась во всю ширину."""
    hub = (MINIAPP / "src" / "components" / "Hub.jsx").read_text(encoding="utf-8")
    css = (MINIAPP / "src" / "index.css").read_text(encoding="utf-8")
    assert "hub-content--wide" in hub, "карта должна просить себе широкую колонку"
    assert "'map'" in hub
    assert ".hub-content--wide" in css, "модификатор ширины не описан в стилях"
