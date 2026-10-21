#!/bin/sh
# Проверка, что из резервной копии база действительно поднимается (2026-10-21).
# Разворачивает свежую копию во временную базу рядом с боевой, сверяет число
# персонажей и игроков с живой базой и удаляет временную. Боевую не трогает.
# Запуск с хоста, из корня проекта:  sh scripts/backup_verify.sh [файл.sql.gz]
set -eu

BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
FILE="${1:-$(ls -t "$BACKUP_DIR"/*.sql.gz | head -1)}"
CHECK_DB="pines_restore_check"
DC="docker compose -f docker-compose.prod.yml"

echo "Копия: $FILE"
gzip -t "$FILE"

psql_live() {
    $DC exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tA -c \"$1\""
}
psql_check() {
    $DC exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d $CHECK_DB -tA -v ON_ERROR_STOP=1 $1"
}

$DC exec -T postgres sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $CHECK_DB && createdb -U \"\$POSTGRES_USER\" $CHECK_DB"
gunzip -c "$FILE" | psql_check "-q" > /dev/null

restored=$(psql_check "-c 'select count(*) from characters'" | tr -d '\r ')
users=$(psql_check "-c 'select count(*) from users'" | tr -d '\r ')
version=$(psql_check "-c 'select version_num from alembic_version'" | tr -d '\r ')
live=$(psql_live "select count(*) from characters" | tr -d '\r ')

$DC exec -T postgres sh -c "dropdb -U \"\$POSTGRES_USER\" $CHECK_DB"

echo "Восстановлено: персонажей $restored, игроков $users, миграция $version (сейчас в игре персонажей: $live)"
if [ "$restored" -lt 1 ] || [ "$restored" -gt "$live" ]; then
    echo "ПРОВАЛ: копия не похожа на базу игры" >&2
    exit 1
fi
echo "OK: копия восстанавливается"
