# Деплой на прод (VPS)

Пошаговая инструкция развёртывания бота + мини-аппа на боевом сервере через
Docker Compose. Для локальной разработки эта инструкция не нужна — см. общий
[README.md](README.md).

## Сервер

```
IP (IPv4):     186.246.12.136
IPv6:          2a03:6f00:a::3:1d56   (не используется, ВК работает по IPv4)
SSH:           ssh root@186.246.12.136
ОС:            Ubuntu 24.04 LTS
Провайдер:     Timeweb Cloud
```

Провайдер блокирует порты 2525, 3389, 53413, 389, 25, 5060, 587, 465 — стек
их не использует (только 22/80/443), так что это не помеха.

Домен пока не подключён — везде ниже, где встречается `$DOMAIN`, работаем по
IP, пока он не появится. Как только домен привяжете (A-запись → 186.246.12.136),
достаточно заполнить `DOMAIN=` в `.env` и перезапустить `caddy` — автоматический
HTTPS включится сам.

## Состав стека (`docker-compose.prod.yml`)

- **bot** — aiohttp + vkbottle, собирается из `Dockerfile`
- **postgres** — PostgreSQL 16, данные в volume, порт наружу не пробрасывается
- **redis** — Redis 7, данные в volume, порт наружу не пробрасывается
- **caddy** — реверс-прокси (80/443) + автоматический HTTPS + статика мини-аппа
  (собирается из `Dockerfile.caddy`, который сначала собирает `miniapp/` через
  Vite, потом кладёт результат рядом с Caddy)

`docker-compose.yml` (без суффикса) — это **отдельный** файл для локальной
разработки (только Postgres+Redis, дефолтные креды `mmo/mmo`), его трогать не
нужно и с прод-файлом он не пересекается.

---

## 1. Первое подключение

```bash
ssh root@186.246.12.136
passwd   # сменить пароль root, если ещё не менялся
```

## 2. Первичная настройка сервера

Скопируйте `scripts/server-setup.sh` на сервер (или вставьте содержимое прямо
в консоль) и запустите:

```bash
sh server-setup.sh
```

Скрипт спросит имя нового sudo-пользователя (по умолчанию `deploy`) и попросит
вставить ваш **публичный** SSH-ключ. Сделает: обновление системы, установку
Docker + compose plugin (официальный репозиторий, не snap), `ufw` (разрешены
только 22/80/443), `fail2ban` для SSH, пользователя с sudo и правом на docker.

**Важно:** скрипт НЕ отключает вход по паролю. Прежде чем это делать:

1. Откройте **новую** сессию SSH под новым пользователем: `ssh deploy@186.246.12.136`
2. Убедитесь, что вход по ключу работает
3. Только после этого правьте `/etc/ssh/sshd_config` (`PasswordAuthentication no`) и перезапускайте `sshd`

Если что-то пойдёт не так — аварийный доступ есть через веб-консоль в панели
Timeweb Cloud (работает даже без SSH).

## 3. Клонирование проекта

```bash
ssh deploy@186.246.12.136
git clone <URL-вашего-репозитория> pines
cd pines
```

## 4. Заполнение `.env`

```bash
cp .env.example .env
nano .env
```

Что и откуда взять:

| Переменная | Откуда |
|---|---|
| `VK_TOKEN` | Сообщество → Управление → Настройки → Работа с API → Ключи доступа (права: сообщения) |
| `VK_GROUP_ID` | ID сообщества (число, без минуса) |
| `VK_CONFIRMATION_CODE` | Работа с API → Callback API → «Строка, которую должен вернуть сервер» |
| `VK_SECRET` | Там же, поле «Секретный ключ» |
| `VK_MINIAPP_SECRET` | vk.com/editapp → ваше приложение → «Настройки» → «Защищённый ключ» (НЕ Callback-секрет!) |
| `VK_MINIAPP_URL` | `https://vk.com/app<ID>` — после создания приложения в VK |
| `POSTGRES_PASSWORD` | Придумать самому, длинный случайный пароль |
| `DOMAIN` | Пока пусто — заполнить, когда подключите домен |

Для боевого запуска дополнительно поменяйте:

```
BOT_MODE=callback
```

(режим `polling` из `.env.example` рассчитан на локальную разработку без
публичного адреса).

`ALLOW_WIPE` в прод-`.env` **не задавайте вовсе** (или оставьте пустым) —
`scripts/wipe.py` откажется работать без `ALLOW_WIPE=true`, это защита от
случайного вайпа игроков на проде.

## 5. Запуск стека

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps   # все сервисы должны быть healthy
```

## 6. Миграции

Если `APPLY_MIGRATIONS_ON_START=true` в `.env` — миграции применяются
автоматически при каждом старте контейнера `bot`. Вручную:

```bash
docker compose -f docker-compose.prod.yml exec bot alembic upgrade head
```

## 7. Логи

```bash
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs -f caddy
```

## 8. Обновление после изменений

```bash
cd pines
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec bot alembic upgrade head   # если APPLY_MIGRATIONS_ON_START=false
```

(Автоматизация этого шага через GitHub Actions — см. «CI/CD» ниже, это
отдельный, необязательный этап.)

## 9. Что вписать в ВК

**Работа с API → Callback API:**

- Адрес сервера: `http://186.246.12.136/vk/callback` (по IP, пока нет
  домена) или `https://<ваш-домен>/vk/callback` (после подключения домена)
- Строка подтверждения и секретный ключ — те, что уже в `.env`
  (`VK_CONFIRMATION_CODE`, `VK_SECRET`)
- Типы событий → включить «Входящее сообщение» (`message_new`)

**vk.com/editapp (Mini App):**

- Адрес приложения: `http://186.246.12.136` или `https://<ваш-домен>`
  (если мини-апп раздаётся тем же Caddy) — либо адрес отдельного хостинга
  статики (напр. Vercel), если мини-апп собирается там

---

## Бэкапы Postgres

`scripts/backup.sh` — `pg_dump` + gzip в `/opt/backups/`, ротация 14 дней.

Ручной запуск:

```bash
./scripts/backup.sh
```

Ежедневный cron (в 4 утра, из-под пользователя с доступом к docker):

```bash
crontab -e
# добавить строку:
0 4 * * * cd /home/deploy/pines && ./scripts/backup.sh >> /var/log/pines-backup.log 2>&1
```

### Восстановление из бэкапа

```bash
gunzip -c /opt/backups/postgres_20260101_040000.sql.gz | \
    docker compose -f docker-compose.prod.yml exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

(Перед восстановлением поверх работающей базы — остановите `bot`, чтобы он не
писал в БД параллельно: `docker compose -f docker-compose.prod.yml stop bot`.)

---

## CI/CD (опционально)

`.github/workflows/deploy.yml` — push в `main` запускает SSH-деплой на
сервер (`git pull` + `docker compose build/up` + миграции). Требует GitHub
Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`.

Включайте только после того, как ручной деплой (шаги 1-9 выше) уже надёжно
работает.

---

## Защита прода — памятка

- `ALLOW_WIPE` не задаётся в прод-`.env` — `scripts/wipe.py` откажется работать
- `postgres`/`redis` не публикуют порты наружу — доступ только из docker-сети
- `.env` в `.gitignore`, секреты никогда не попадают в репозиторий
- Не делаем: Kubernetes, балансировщики, репликацию БД, мониторинг сложнее
  `GET /health`
