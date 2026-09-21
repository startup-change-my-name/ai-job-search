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

"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
"$repo_root/platform/scripts/verify-stack.sh" "$env_file"
