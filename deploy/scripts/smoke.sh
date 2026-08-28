#!/usr/bin/env sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: smoke.sh <https-base-url> [expected-release-id]" >&2
    exit 2
fi

base_url=${1%/}
curl --fail --silent --show-error --max-time 10 "$base_url/ready" \
    | grep -q '"status":"ready"'
curl --fail --silent --show-error --max-time 10 "$base_url/" \
    | grep -q '"status":"success"'

if [ "$#" -eq 2 ]; then
    expected_release=$2
    curl --fail --silent --show-error --max-time 10 "$base_url/" \
        | grep -Fq "\"release_id\":\"$expected_release\""
fi
