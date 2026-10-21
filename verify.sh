#!/usr/bin/env bash
set -euo pipefail

if [ -f "infra/docker-compose.yml" ]; then
  COMPOSE_FILE="infra/docker-compose.yml"
else
  COMPOSE_FILE="docker-compose.yml"
fi

echo "=== 1. Validating Compose Syntax ==="
docker compose -f "${COMPOSE_FILE}" config --services | grep -w "redis"

echo "=== 2. Checking Pinned Redis Image ==="
IMAGE_TAG=$(docker compose -f "${COMPOSE_FILE}" config | grep -A 5 "redis:" | grep "image:" | awk '{print $2}')
echo "Configured image: ${IMAGE_TAG}"
if [[ "${IMAGE_TAG}" == *"latest"* ]] || [[ "${IMAGE_TAG}" != *"redis:7."* ]]; then
  echo "FAIL: Redis image must be pinned to a specific 7.x tag (found: ${IMAGE_TAG})" >&2
  exit 1
fi

echo "=== 3. Checking Network Isolation ==="
NETWORKS=$(docker compose -f "${COMPOSE_FILE}" config | grep -A 10 "container_name: labflow-redis" | grep -A 2 "networks:" || true)
echo "Redis networks configuration: ${NETWORKS}"
if docker compose -f "${COMPOSE_FILE}" config | grep -A 15 "container_name: labflow-redis" | grep -q "edge"; then
  echo "FAIL: Redis must NOT be connected to the edge network" >&2
  exit 1
fi

echo "=== 4. Checking Host Port Binding ==="
PORTS=$(docker compose -f "${COMPOSE_FILE}" config | grep -A 5 "container_name: labflow-redis" | grep -A 2 "ports:" || true)
echo "Port mappings: ${PORTS}"
if echo "${PORTS}" | grep -q '0\.0\.0\.0'; then
  echo "FAIL: Redis ports must NOT be bound to 0.0.0.0" >&2
  exit 1
fi

echo "=== 5. Starting Redis and Verifying Healthcheck ==="
docker compose -f "${COMPOSE_FILE}" up -d redis

echo "Waiting for Redis to become healthy..."
TIMEOUT=30
ELAPSED=0
STATUS=""
while [ $ELAPSED -lt $TIMEOUT ]; do
  STATUS=$(docker inspect --format='{{json .State.Health.Status}}' labflow-redis | tr -d '"')
  if [ "$STATUS" = "healthy" ]; then
    break
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

if [ "$STATUS" != "healthy" ]; then
  echo "FAIL: labflow-redis failed to reach healthy status within ${TIMEOUT}s (status: ${STATUS})" >&2
  docker logs --tail 20 labflow-redis
  exit 1
fi
echo "Redis container is healthy!"

echo "=== 6. Validating PING / PONG ==="
PONG_RESP=$(docker exec labflow-redis redis-cli ping)
if [ "${PONG_RESP}" != "PONG" ]; then
  echo "FAIL: Expected PONG, got ${PONG_RESP}" >&2
  exit 1
fi
echo "Received PONG successfully."

echo "=== 7. Validating AOF Persistence ==="
AOF_CONFIG=$(docker exec labflow-redis redis-cli config get appendonly | tail -n 1)
if [ "${AOF_CONFIG}" != "yes" ]; then
  echo "FAIL: appendonly is not set to 'yes' (found: ${AOF_CONFIG})" >&2
  exit 1
fi
echo "AOF persistence confirmed: ${AOF_CONFIG}"

echo "=== 8. Validating Volume Mount ==="
MOUNT_DEST=$(docker inspect --format='{{range .Mounts}}{{if eq .Type "volume"}}{{.Destination}}{{end}}{{end}}' labflow-redis)
if [ "${MOUNT_DEST}" != "/data" ]; then
  echo "FAIL: Expected volume mounted at /data, got: ${MOUNT_DEST}" >&2
  exit 1
fi
echo "Volume mount confirmed at /data"

echo "=== ALL VERIFICATIONS PASSED ==="

