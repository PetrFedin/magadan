#!/bin/sh
set -eu
cd "$(dirname "$0")"
umask 077
if [ ! -f .lab.env ]; then
  JWT=$(openssl rand -hex 32)
  AUDIT=$(openssl rand -hex 32)
  {
    printf "HYDRO_JWT_SECRET='%s'\n" "$JWT"
    printf "HYDRO_AUDIT_SECRET='%s'\n" "$AUDIT"
    printf "HYDRO_DATABASE_URL='sqlite:///./hydro_v7_lab.db'\n"
  } > .lab.env
  chmod 600 .lab.env
  echo 'Created .lab.env (mode 600), keep private and never commit.'
fi
set -a
. ./.lab.env
set +a
if [ ! -f hydro_v7_lab.db ]; then
  HYDRO_ALLOW_DEMO_SEED=YES python -m hydro_api.seed_lab
fi
exec uvicorn hydro_api.asgi:app --host 127.0.0.1 --port 8000
