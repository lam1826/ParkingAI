#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/common.sh"
require_runtime_state

exec 9>"$STATE_DIR/.deploy.lock"
if ! flock -n 9; then
    echo "Another deployment is already running" >&2
    exit 1
fi

if [ ! -f "$ACTIVE_FILE" ] || [ ! -f "$IMAGES_FILE" ]; then
    echo "No completed blue/green deployment to roll back" >&2
    exit 1
fi

active=$(tr -d '\r\n' < "$ACTIVE_FILE")
case "$active" in
    blue) target=green ;;
    green) target=blue ;;
    *) echo "Invalid active color state: $active" >&2; exit 1 ;;
esac

service="backend_$target"
if [ "$target" = "blue" ]; then
    target_image=$(read_image_value BACKEND_IMAGE_BLUE)
else
    target_image=$(read_image_value BACKEND_IMAGE_GREEN)
fi
[ -n "$target_image" ] || { echo "Missing rollback image state" >&2; exit 1; }
wait_for_healthy "$service" 5
previous_file="$CADDY_DIR/Caddyfile.previous.$$"
cp "$CADDY_DIR/Caddyfile" "$previous_file"
switch_proxy "$target"

api_domain=$(sed -n 's/^API_DOMAIN=//p' "$ENV_FILE" | tail -n 1)
if ! sh "$CONTROL_DIR/scripts/smoke.sh" \
    "https://$api_domain" "$target_image"; then
    mv -f "$previous_file" "$CADDY_DIR/Caddyfile"
    compose exec -T caddy caddy reload \
        --config /etc/caddy/Caddyfile --adapter caddyfile
    echo "Rollback smoke failed; original route restored" >&2
    exit 1
fi
rm -f "$previous_file"
printf '%s\n' "$target" > "$ACTIVE_FILE.tmp.$$"
mv -f "$ACTIVE_FILE.tmp.$$" "$ACTIVE_FILE"
echo "Rollback active: color=$target"
