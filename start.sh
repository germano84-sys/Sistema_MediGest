#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
    cp .env.example .env
    printf '%s\n' "Created .env from .env.example. Review development credentials before use."
fi

exec docker compose up --build "$@"
