#!/usr/bin/env bash
set -eu
umask 077
mkdir -p infra/secrets
chmod 700 infra/secrets
if [ ! -e infra/secrets/ch_password ]; then
    printf 'Aa1!%s\n' "$(openssl rand -hex 24)" > infra/secrets/ch_password
    chmod 644 infra/secrets/ch_password
fi
if [ ! -s infra/secrets/ch_password ]; then
    echo 'infra/secrets/ch_password is empty; supply a valid password' >&2
    exit 1
fi
if [ -z "${SENTINEL_DEV_PASSWORD:-}" ] && [ ! -e infra/secrets/dev_password ]; then
    printf 'Aa1!%s\n' "$(openssl rand -hex 24)" > infra/secrets/dev_password
fi
if [ -z "${SENTINEL_DEV_PASSWORD:-}" ] && [ ! -s infra/secrets/dev_password ]; then
    echo 'infra/secrets/dev_password is empty; supply a valid password' >&2
    exit 1
fi
