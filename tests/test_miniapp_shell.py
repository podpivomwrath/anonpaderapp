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


def test_wide_background_overrides_the_mobile_one() -> None:
    """Обе строки обязаны лежать в ОДНОМ файле: когда выбор по ширине жил в
    index.css, а картинки - в background.css, правило из подключённого позже
    файла перебивало медиазапрос, и на ПК оставался телефонный фон."""
    css = (MINIAPP / "src" / "background.css").read_text(encoding="utf-8")
    if "--app-bg" not in css:
        pytest.skip("фоны ещё не сгенерированы")
    mobile = css.find("--app-bg:")
    wide = css.rfind("--app-bg:")
    assert "min-width" in css, "широкий фон должен подключаться медиазапросом"
    assert wide > mobile, "широкий фон обязан идти вторым, иначе он не переопределит"
