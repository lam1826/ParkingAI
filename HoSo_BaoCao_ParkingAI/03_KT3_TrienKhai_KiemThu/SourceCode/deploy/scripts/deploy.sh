#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/common.sh"

if [ "$#" -ne 1 ]; then
    echo "Usage: deploy.sh <immutable-backend-image>" >&2
    exit 2
fi

image=$1
validate_image "$image"
require_runtime_state
acquire_deploy_lock

# The same lock covers migration, readiness gates and the traffic switch.
migrate_image "$image"

active=none
if [ -f "$ACTIVE_FILE" ]; then
    active=$(tr -d '\r\n' < "$ACTIVE_FILE")
fi
case "$active" in
    blue) target=green ;;
    green) target=blue ;;
    none|"") target=blue; bootstrap=true ;;
    *) echo "Invalid active color state: $active" >&2; exit 1 ;;
esac
bootstrap=${bootstrap:-false}

blue=$(read_image_value BACKEND_IMAGE_BLUE)
green=$(read_image_value BACKEND_IMAGE_GREEN)
[ -n "$blue" ] || blue=$image
[ -n "$green" ] || green=$image
if [ "$target" = "blue" ]; then blue=$image; else green=$image; fi
write_images "$blue" "$green"

service="backend_$target"
if [ "$bootstrap" = true ]; then
    # Keep an immediately usable rollback color from the first release.
    compose pull backend_blue backend_green
    compose up -d --no-deps backend_blue backend_green
    wait_for_healthy backend_blue 45
    wait_for_healthy backend_green 45
else
    compose pull "$service"
    compose up -d --no-deps "$service"
    wait_for_healthy "$service" 45
fi

# Verify the candidate directly before exposing any customer traffic.
compose exec -T "$service" python -c \
    "import json, os, urllib.request; ready=json.load(urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5)); root=json.load(urllib.request.urlopen('http://127.0.0.1:8000/', timeout=5)); assert ready['status']=='ready'; assert root['release_id']==os.environ['RELEASE_ID']"

previous_file="$CADDY_DIR/Caddyfile.previous.$$"
had_previous=false
if [ -f "$CADDY_DIR/Caddyfile" ]; then
    cp "$CADDY_DIR/Caddyfile" "$previous_file"
    had_previous=true
fi

if ! switch_proxy "$target"; then
    if [ "$had_previous" = true ]; then
        mv -f "$previous_file" "$CADDY_DIR/Caddyfile"
        compose exec -T caddy caddy reload \
            --config /etc/caddy/Caddyfile --adapter caddyfile || true
    fi
    exit 1
fi

api_domain=$(sed -n 's/^API_DOMAIN=//p' "$ENV_FILE" | tail -n 1)
if ! sh "$CONTROL_DIR/scripts/smoke.sh" "https://$api_domain" "$image"; then
    echo "Public smoke test failed; restoring previous route" >&2
    if [ "$had_previous" = true ]; then
        mv -f "$previous_file" "$CADDY_DIR/Caddyfile"
        compose exec -T caddy caddy reload \
            --config /etc/caddy/Caddyfile --adapter caddyfile
    fi
    exit 1
fi

rm -f "$previous_file"
printf '%s\n' "$target" > "$ACTIVE_FILE.tmp.$$"
mv -f "$ACTIVE_FILE.tmp.$$" "$ACTIVE_FILE"
echo "Deployment active: color=$target image=$image"
