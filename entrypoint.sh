#!/bin/sh
# Точка входа контейнера бота: опционально применяет миграции перед стартом
# (APPLY_MIGRATIONS_ON_START=true в .env), затем запускает main.py.
set -e

if [ "$APPLY_MIGRATIONS_ON_START" = "true" ]; then
    echo "entrypoint: применяю миграции (alembic upgrade head)..."
    alembic upgrade head
fi

exec python main.py
