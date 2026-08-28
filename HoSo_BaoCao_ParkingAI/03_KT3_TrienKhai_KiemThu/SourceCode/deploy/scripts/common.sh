#!/usr/bin/env sh
set -eu

CONTROL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STATE_DIR=${PARKINGAI_STATE_DIR:-/opt/parkingai/state}
COMPOSE_FILE="$CONTROL_DIR/compose.blue-green.yml"
IMAGES_FILE="$STATE_DIR/.images.env"
ACTIVE_FILE="$STATE_DIR/.active-color"
CADDY_DIR="$STATE_DIR/caddy"
ENV_FILE="$STATE_DIR/.env.production"

export PARKINGAI_STATE_DIR="$STATE_DIR"

require_runtime_state() {
    if [ ! -f "$ENV_FILE" ]; then
        echo "Missing production environment: $ENV_FILE" >&2
        exit 1
    fi
    mkdir -p "$CADDY_DIR"
}

validate_image() {
    image=$1
    case "$image" in
        ""|*[!a-zA-Z0-9._/@:+-]*)
            echo "Invalid immutable image reference" >&2
            exit 1
            ;;
    esac

    repository=${image%@sha256:*}
    digest=${image##*@sha256:}
    if [ "$repository" = "$image" ] || [ -z "$repository" ] \
       || [ "${#digest}" -ne 64 ]; then
        echo "Backend image must use an immutable sha256 digest" >&2
        exit 1
    fi
    case "$repository" in
        *@*)
            echo "Invalid immutable image repository" >&2
            exit 1
            ;;
    esac
    case "$digest" in
        *[!0-9a-f]*)
            echo "Invalid sha256 image digest" >&2
            exit 1
            ;;
    esac
}

acquire_deploy_lock() {
    exec 9>"$STATE_DIR/.deploy.lock"
    if ! flock -n 9; then
        echo "Another deployment is already running" >&2
        exit 1
    fi
}

read_image_value() {
    key=$1
    if [ ! -f "$IMAGES_FILE" ]; then
        return 0
    fi
    sed -n "s/^${key}=//p" "$IMAGES_FILE" | tail -n 1
}

write_images() {
    blue=$1
    green=$2
    temp_file="$STATE_DIR/.images.env.tmp.$$"
    umask 077
    {
        printf 'BACKEND_IMAGE_BLUE=%s\n' "$blue"
        printf 'BACKEND_IMAGE_GREEN=%s\n' "$green"
    } > "$temp_file"
    mv -f "$temp_file" "$IMAGES_FILE"
}

compose() {
    docker compose \
        --env-file "$ENV_FILE" \
        --env-file "$IMAGES_FILE" \
        -f "$COMPOSE_FILE" "$@"
}

migrate_image() {
    image=$1
    docker pull "$image"
    docker run --rm \
        --env-file "$ENV_FILE" \
        --read-only \
        --tmpfs /tmp:size=64m,mode=1777 \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        "$image" \
        alembic -c /app/alembic.ini upgrade head

    # Alembic head alone cannot prove cross-table business invariants.
    docker run --rm \
        --env-file "$ENV_FILE" \
        --read-only \
        --tmpfs /tmp:size=64m,mode=1777 \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        "$image" \
        python -c "from database import engine; from db_rollout import check_database_readiness; from postgres_readiness import assert_postgres_release_revision; assert_postgres_release_revision(engine); check_database_readiness(engine, deep=True)"
}

wait_for_healthy() {
    service=$1
    attempts=${2:-30}
    count=0
    while [ "$count" -lt "$attempts" ]; do
        container_id=$(compose ps -q "$service")
        if [ -n "$container_id" ]; then
            health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")
            if [ "$health" = "healthy" ]; then
                return 0
            fi
            if [ "$health" = "unhealthy" ]; then
                compose logs --tail=100 "$service" >&2
                return 1
            fi
        fi
        count=$((count + 1))
        sleep 2
    done
    compose logs --tail=100 "$service" >&2
    return 1
}

switch_proxy() {
    color=$1
    source_file="$CONTROL_DIR/Caddyfile.$color"
    target_file="$CADDY_DIR/Caddyfile"
    temp_file="$CADDY_DIR/Caddyfile.tmp.$$"
    cp "$source_file" "$temp_file"
    mv -f "$temp_file" "$target_file"

    if compose ps -q caddy | grep -q .; then
        compose exec -T caddy caddy reload \
            --config /etc/caddy/Caddyfile --adapter caddyfile
    else
        compose up -d caddy
    fi
}
