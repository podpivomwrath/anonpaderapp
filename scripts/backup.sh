#!/bin/sh
# Бэкап Postgres: pg_dump внутри контейнера + gzip на хосте, ротация 14 дней.
# Запуск (с хоста, из корня проекта):
#   ./scripts/backup.sh
# Обычно вызывается по крону (см. DEPLOY.md), но можно и вручную.
set -eu

BACKUP_DIR="/opt/backups"
KEEP_DAYS=14
COMPOSE_FILE="docker-compose.prod.yml"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/postgres_${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

# .env лежит в корне проекта — читаем POSTGRES_* оттуда же, откуда их берёт compose.
if [ -f .env ]; then
    # shellcheck disable=SC1091
    . ./.env
fi

docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "$OUT_FILE"

echo "Бэкап сохранён: $OUT_FILE"

# Ротация: удалить бэкапы старше $KEEP_DAYS дней
find "$BACKUP_DIR" -name 'postgres_*.sql.gz' -mtime "+${KEEP_DAYS}" -delete

echo "Готово. Бэкапов в $BACKUP_DIR:"
ls -lh "$BACKUP_DIR"
