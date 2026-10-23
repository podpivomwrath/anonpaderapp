# Pines - заметки для Claude

## Игровой текст

Любой текст, который увидит игрок (сообщения бота, лор, события, мобы, NPC,
рейды, патчноуты, подписи мини-аппа), пишется и правится только по скиллу
`game-text` (.claude/skills/game-text/SKILL.md). Перед коммитом - проверка
`.venv/Scripts/python.exe tools/text_slop.py <изменённые файлы> --top 50`.
Игроки жалуются, что тексты выглядят как сгенерированные, - это главное
требование к тексту.

Число из данных перед словом - только через `game/plural.py` («1 убийство»,
«2 самоцвета»), в мини-аппе - склонялка рядом. Название не склеивать с
родовым словом вслепую («Свиток ларец», «в Шепчущие Пущи»). Фильтр -
`tests/test_plural_forms.py`.

## Рассылки игрокам

Патчноуты и анонсы - только через `tools/broadcast.py`: текст кладётся в
`patchnotes/<дата>-<тема>.txt`, коммитится (тест проверяет жёсткие правила),
на сервере - `cat файл | docker compose -f docker-compose.prod.yml exec -T bot
python tools/broadcast.py - [--hours 24] [--photo N] --send`. Скрипт сам
прогоняет text_slop и не отправит текст с находками (`--force` - только для
ложных мягких). Без `--send` - сухой прогон: текст, находки, число получателей.

## Где что живёт

Слои: `game/` - чистая логика и числа (`game/economy/*_config.py` - весь
баланс), `services/` - работа с базой, `bot/handlers/` - чат, `bot/miniapp_*api.py`
- мини-апп, `content/` - тексты и каталоги. Логика - в `game/` и `services/`,
обработчики только собирают ответ.

## Чек-листы типовых правок

Связки ниже раньше расходились молча; тесты-сверки (`tests/test_busy.py`,
`tests/test_wiring.py`, `tests/test_shop_rename.py`) ловят большую часть, но
не всё.

- **Новое занятие, которое блокирует игрока** (как забой, варка): только
  `bot/busy.py` - код в `STATES` и способ окончания в `ENDS_BY` (`unstick`
  - тогда снять его в `world.force_unstick`). Свои копии проверки не писать:
  все входы берут `busy()` (`activity.blocked_reason`, маунт, карта мини-аппа,
  поход). Если код нужен карте - `_MAP_REASONS` и текст в `MapTab.jsx`.
- **Где мир**: `bot/handlers/world.py` - город, карта, ходьба, клавиатуры экранов;
  исследование и события - `explore.py`, отдых - `rest.py`, `/застрял` - `stuck.py`.
  Общее состояние мира остаётся в world.py, модули берут его как `world.X`.
- **PvP, рейды, мини-апп** (нарезка 2026-10-22): обработчики PvP - `pvp.py`,
  итоги боёв - `pvp_results.py`, осмотр клетки и цели - `pvp_scene.py`; рейды -
  `raid_combat.py` (обработчики), разбор хода и награды - `raid_results.py`;
  мини-апп - `miniapp_api.py`, инвентарь - `miniapp_inventory_api.py`, пресеты -
  `miniapp_presets_api.py`. Состояние - в старом модуле (`pvp.X`,
  `raid_combat.X`). Перенос функции меняет её адрес «модуль.функция» в журналах
  золота и ресурсов - добавь новый ключ в `admin_service.WALLET_REASONS`, старый
  оставь для истории.
- **Урон механики рейда** (не удар резолвера) - только `raid_field.stage_hurt`
  (щиты, «Последний вздох», гибель); правило для обоих движков боя -
  `game/combat/shared_rules.py`. Сверки: `tests/test_hp_writes.py`,
  `tests/test_duel_parity.py`.
- **Что держится в памяти** - `bot/memory_state.py`: новое хранилище впиши туда
  с ответом «кто снимает» (сверка `tests/test_memory_state.py`).
- **Ввод словами** (не кнопкой) - строка в `bot/button_gate.TYPED_INPUTS` и
  пропуск в `_typed_input_expected`, иначе фильтр кнопок отрежет его.
- **Исследование и отдых**: отметки «занят» только через `bot/explore_rest.py`
  (`start`/`stop`/`drop`) - там память и запись в Redis меняются вместе.
- **Новый экран чата**: родитель в `services/screen_service.PARENT` и
  восстановление в `world._screen_keyboard` или в `rebuild()` модуля.
- **Новая кнопка с payload**: обработчик `payload_contains={"type": ...}`.
- **Новый товар магазина**: каталог в `shop_service`, обработчик покупки и
  `BUYABLE` в `bot/miniapp_shop_api.py`.
- **Новый бафф или источник силы** (как еда): урон/защита/здоровье в бою -
  через модификаторы `preset_service.resolve_active_modifiers`; здоровье ещё и
  вне боя - `vitals_service.max_hp`, `derived_stats_service`; опыт - соло
  `encounter_service` и группа `group_combat_service`; реликвии - бонус в
  `encounter_service`.
- **Новый предмет или ресурс**: выдача в админке (`admin_grant_service.catalog`),
  строка в карточке игрока (`admin_service.player_card`), иконка
  (`tools/icon_assets.py`, `EXTRA_FILES`).
- **Новое ремесло или уровень**: шкала опыта под логом (`display.craft_xp_line`),
  карточка в админке, опыт в походах (`voyage_service.CRAFTS`).
- **Вкладки мини-аппа** - только `components/ScrollTabs.jsx`, не `Tabs` из VKUI.
