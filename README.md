# gamedai-nfl-mcp

Part of [gamedai](https://gamedai.app), the interactive sports radio. This
MIT-licensed MCP server exposes five read-only NFL tools backed by the public
gamedai API.

The default backend is `https://gamedai-v2-preview.fly.dev`. Override it with
`GAMEDAI_API_BASE`. Scout calls optionally use `GAMEDAI_SCOUT_API_KEY`; the
legacy `GAMEDAI_PUBLIC_API_KEY` name is accepted as an alias.

## Install

```bash
cd tools/gamedai-mcp
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
```

## Tools

- `get_game_scores(date?, event_id?)` reads the public slate. `date` is sent
  to the backend; `event_id` filters the returned slate locally.
- `get_wire_news(page?, page_size?)` reads the paginated Wire feed.
- `get_player_grade(player, season?, week?)` reads Scout player grades.
- `get_start_sit_recommendation(player_a, player_b, week, season?)` reads the
  Scout start/sit comparison. `week` is required.
- `get_scout_rankings(position?, scoring?, week?)` reads the Scout rankings
  board.

When `season` is omitted, `get_player_grade` uses the latest complete NFL
stats season, and `get_start_sit_recommendation` uses the CURRENT league year
(projections load for the upcoming slate):
`today.year - 1` when the month is March or later, otherwise `today.year - 2`.
An explicit season always wins. Rankings derive their source season in the
backend.

All backend errors are returned as structured objects with `code`,
`http_status`, and a bounded `message`. Scout keys are sent only to
`/v1/scout/*` calls.

## Hosted mode

The hosted service uses streamable HTTP:

```bash
gamedai-nfl-mcp --transport streamable-http --host 0.0.0.0 --port 8080
```

The MCP endpoint is `/mcp`; process liveness is `/healthz`; backend readiness
is `/readyz`. The Fly app is the existing `gamedai-mcp` app and deploys from
this directory with `flyctl deploy`.

The pinned MCP SDK enables stateless HTTP when its `FastMCP` constructor
supports `stateless_http=True`. Older SDKs keep normal sessions, as a safe
fallback.

## Environment

```bash
export GAMEDAI_API_BASE="https://gamedai-v2-preview.fly.dev"
export GAMEDAI_SCOUT_API_KEY="<server-provisioned Scout key>"
```

`OPENAI_APPS_CHALLENGE_TOKEN` is only needed for the existing public Apps
challenge route. Never commit keys or expose the Scout key to an MCP model.

## Tests

Tests use mocked HTTP clients and do not call the live backend:

```bash
pytest
```

The canonical backend contract is generated at
`backend/openapi/scout_public_contract.openapi.json`; run
`python scripts/mcp/check_contract_drift.py` from the repository root to check
for route or schema drift.

License: MIT.
