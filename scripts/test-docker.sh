#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-test-preview.yml}"
SERVICE="${IRIS_SERVICE:-iris}"

if [ "$#" -eq 0 ]; then
  PYTEST_ARGS=(tests)
else
  PYTEST_ARGS=("$@")
fi

ENV_ARGS=()
for name in \
  IRIS_HOST \
  IRIS_PORT \
  IRISNAMESPACE \
  IRISUSERNAME \
  IRISPASSWORD \
  IRIS_E2E_MODES \
  IRIS_REQUIRE_EMBEDDED \
  IRIS_REQUIRE_EMBEDDED_SQL \
  IRIS_RUN_KERNEL_TEST
do
  if [ -n "${!name+x}" ]; then
    ENV_ARGS+=("-e" "$name=${!name}")
  fi
done

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "docker compose is required" >&2
  exit 1
fi

"${COMPOSE[@]}" -f "$COMPOSE_FILE" up -d "$SERVICE"

CONTAINER_ID="$("${COMPOSE[@]}" -f "$COMPOSE_FILE" ps -q "$SERVICE")"
if [ -z "$CONTAINER_ID" ]; then
  echo "Could not find the $SERVICE container" >&2
  exit 1
fi

docker exec "$CONTAINER_ID" bash -lc 'if [ -x /usr/irissys/dev/Container/waitReady.sh ]; then /usr/irissys/dev/Container/waitReady.sh -m 60; else /usr/irissys/dev/Cloud/ICM/waitReady.sh -m 60; fi'
docker exec "$CONTAINER_ID" iris session iris -U%SYS '##class(Security.Users).UnExpireUserPasswords("*")'

docker exec \
  "${ENV_ARGS[@]}" \
  "$CONTAINER_ID" \
  bash -lc 'cd /irisdev/app && ./scripts/run-pytest-in-iris.sh "$@"' test-docker "${PYTEST_ARGS[@]}"
