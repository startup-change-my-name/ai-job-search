# Job Control Platform

Reusable services live here. Personal values live in
`ai-job-search-private/config/job-control/runtime.env` and are passed with
Docker Compose's `--env-file` option.

## Network boundary

Compose publishes only `127.0.0.1:3000`. Tailscale Serve proxies that local
port over private HTTPS. Funnel must remain disabled. The Next.js request
boundary accepts only identities listed in `TAILSCALE_ALLOWED_LOGINS`.

## Start from WSL2

    ./scripts/start-stack.sh \
      /mnt/c/Users/you/Documents/ChatGPT/ai-job-search-private/config/job-control/runtime.env

## Verify

    ./scripts/verify-stack.sh \
      /mnt/c/Users/you/Documents/ChatGPT/ai-job-search-private/config/job-control/runtime.env

## Stop

    docker compose --env-file /path/to/private/runtime.env down

The dashboard is intentionally unavailable through direct LAN addresses. Use
the Tailscale Serve HTTPS URL for both desktop and phone access.
