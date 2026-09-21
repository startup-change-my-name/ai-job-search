#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /absolute/path/to/private/runtime.env" >&2
  exit 64
fi

env_file="$1"
if [[ ! -f "$env_file" ]]; then
  echo "private runtime environment not found: $env_file" >&2
  exit 66
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose_file="$repo_root/platform/compose.yaml"
if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$env_file" -f "$compose_file")
elif command -v docker.exe >/dev/null 2>&1 && docker.exe version >/dev/null 2>&1; then
  private_workspace_path=""
  while IFS='=' read -r key value; do
    key="${key%$'\r'}"
    value="${value%$'\r'}"
    if [[ "$key" == "PRIVATE_WORKSPACE_PATH" ]]; then
      private_workspace_path="$value"
    fi
  done < "$env_file"
  if [[ "$private_workspace_path" != /* || ! -d "$private_workspace_path" ]]; then
    echo "PRIVATE_WORKSPACE_PATH is missing or invalid in private runtime environment" >&2
    exit 78
  fi
  export PRIVATE_WORKSPACE_PATH="$(wslpath -w "$private_workspace_path")"
  if [[ ! ":${WSLENV-}:" =~ :PRIVATE_WORKSPACE_PATH(/[^:]*)?: ]]; then
    export WSLENV="${WSLENV:+$WSLENV:}PRIVATE_WORKSPACE_PATH"
  fi
  compose=(
    docker.exe compose
    --env-file "$(wslpath -w "$env_file")"
    -f "$(wslpath -w "$compose_file")"
  )
else
  echo "Docker engine unavailable from WSL and Windows" >&2
  exit 69
fi
expected_services=(
  airflow-api-server
  airflow-dag-processor
  airflow-scheduler
  airflow-triggerer
  airflow-worker
  api
  postgres
  redis
  web
)

stack_containers_are_healthy() {
  local rows="$1"
  local service state health
  local -A expected=()
  local -A seen=()
  local valid=1

  for service in "${expected_services[@]}"; do
    expected["$service"]=1
  done

  while IFS='|' read -r service state health; do
    [[ -n "$service" ]] || continue

    if [[ -z "${expected[$service]+present}" || -n "${seen[$service]+present}" ]]; then
      valid=0
      continue
    fi

    seen["$service"]=1
    if [[ "$state" != "running" || "$health" != "healthy" ]]; then
      valid=0
    fi
  done <<< "$rows"

  [[ "$valid" -eq 1 && "${#seen[@]}" -eq "${#expected_services[@]}" ]]
}

dependencies_are_healthy() {
  local payload
  if ! payload="$("${compose[@]}" exec -T api python -c \
    "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).read().decode('utf-8'))")"; then
    return 1
  fi

  python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
    services = payload["services"]
except (KeyError, TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)

if not isinstance(services, list):
    raise SystemExit(1)

for required_name in ("postgres", "airflow"):
    matches = [
        service
        for service in services
        if isinstance(service, dict) and service.get("name") == required_name
    ]
    if len(matches) != 1 or matches[0].get("state") != "healthy":
        raise SystemExit(1)
' <<< "$payload" 2>/dev/null
}

for _attempt in $(seq 1 40); do
  rows="$("${compose[@]}" ps --format '{{.Service}}|{{.State}}|{{.Health}}')"
  if stack_containers_are_healthy "$rows" \
    && dependencies_are_healthy; then
    echo "job-control stack healthy"
    exit 0
  fi
  sleep 3
done

"${compose[@]}" ps
echo "job-control stack did not become healthy" >&2
exit 1
