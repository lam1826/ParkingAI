#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/common.sh"

if [ "$#" -ne 1 ]; then
    echo "Usage: migrate.sh <immutable-backend-image>" >&2
    exit 2
fi

image=$1
validate_image "$image"
require_runtime_state
acquire_deploy_lock
migrate_image "$image"
