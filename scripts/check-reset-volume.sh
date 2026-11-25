#!/usr/bin/env bash
set -eu
volume=sentinel-clickhouse-data
if docker volume inspect "$volume" >/dev/null 2>&1; then
    project=$(docker compose config --format json | sed -n 's/^  "name": "\([^"]*\)",\{0,1\}$/\1/p')
    owner=$(docker volume inspect --format '{{index .Labels "com.docker.compose.project"}}' "$volume")
    if [ -z "$project" ] || [ "$owner" != "$project" ]; then
        echo "$volume belongs to another Compose project or its owner is unknown; refusing reset." >&2
        exit 1
    fi
    for container in $(docker ps -aq --no-trunc --filter "volume=$volume"); do
        container_project=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")
        if [ "$container_project" != "$project" ]; then
            echo "$volume is also used by another container; refusing reset." >&2
            exit 1
        fi
    done
fi
