#!/usr/bin/env bash
# Run in the checkout to deploy. Never restores a database automatically.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
dc() { docker compose -f docker-compose.prod.yml "$@"; }
stamp=$(date -u +%Y%m%d_%H%M%S)
backup_dir=${BACKUP_DIR:-/opt/backups}
mkdir -p "$backup_dir"
bot_id=$(dc ps -q bot)
caddy_id=$(dc ps -q caddy)
old_bot=$(docker inspect --format '{{.Image}}' "$bot_id")
old_caddy=$(docker inspect --format '{{.Image}}' "$caddy_id")
rollback=$(mktemp)
printf 'services:\n  bot:\n    image: %s\n  caddy:\n    image: %s\n' "$old_bot" "$old_caddy" > "$rollback"
stopped=false
rollback_on_error() {
    code=$?
    trap - ERR
    if $stopped; then
        echo 'Deployment failed: restoring previous container images (database retained).' >&2
        dc -f "$rollback" up -d --no-build --no-deps bot caddy || true
    fi
    rm -f "$rollback"
    exit "$code"
}
trap rollback_on_error ERR
# Build while the old application is still serving players.
dc build bot caddy
# This also ensures pg_dump failure cannot be hidden by the gzip pipeline.
backup="$backup_dir/pre_release_${stamp}.sql.gz"
dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$backup"
gzip -t "$backup"
test -s "$backup"
echo "Verified database backup: $backup"
stopped=true
dc stop bot
# Apply additive schema changes before the new application starts.
dc run --rm --no-deps --entrypoint alembic bot upgrade head
dc up -d --no-build --no-deps bot caddy
healthy=false
for attempt in $(seq 1 30); do
    if dc exec -T bot python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"; then
        healthy=true
        break
    fi
    sleep 2
done
$healthy
dc exec -T bot alembic current
dc ps
stopped=false
rm -f "$rollback"
trap - ERR
echo "Deployment verified; previous images: $old_bot $old_caddy"
