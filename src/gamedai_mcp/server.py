# NOTE: no `from __future__ import annotations` here. mcp FastMCP tool
# registration inspects runtime annotations on Python 3.12.

import argparse
import asyncio
import inspect
import os
from datetime import date
from typing import Any, Awaitable, Callable

import httpx


ToolResult = dict[str, Any]
ToolCall = Callable[..., Awaitable[ToolResult]]

# Backend query parameters only. event_id is intentionally absent because it
# is an MCP-local filter applied after the slate response is fetched; season is
# intentionally absent from rankings because the backend route does not accept it.
TOOL_TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "get_game_scores": ("/v1/games/slate", ("date",)),
    "get_wire_news": ("/api/wire/feed", ("page", "page_size")),
    "get_player_grade": (
        "/v1/scout/player-grade",
        ("player", "season", "week"),
    ),
    "get_start_sit_recommendation": (
        "/v1/scout/start-sit",
        ("player_a", "player_b", "season", "week"),
    ),
    "get_scout_rankings": (
        "/v1/scout/rankings",
        ("position", "scoring", "week"),
    ),
}


def latest_complete_nfl_season(today: date | None = None) -> int:
    """Return the latest complete NFL stats season from the calendar clock."""
    current = today or date.today()
    return current.year - 1 if current.month >= 3 else current.year - 2


def current_nfl_league_year(today: date | None = None) -> int:
    """Return the CURRENT NFL league year from the calendar clock.

    Start/sit is a decision about the upcoming slate, so its season default is
    the league year (projections load for it), not the stats season: on
    2026-08-30 that is 2026, while grades default to 2025 (complete stats).
    A league year spans Mar..Feb, so Jan/Feb still belong to the prior year.
    """
    current = today or date.today()
    return current.year if current.month >= 3 else current.year - 1


def _with_request_context(result: ToolResult, **requested: Any) -> ToolResult:
    """Attach what the backend was asked for, as `requested_*` keys.

    These are the query, not the source. The backend's own `source_*` fields
    (rankings) and `stats_season` (grades) say what was served; when the
    backend does not say, the source context stays unknown rather than being
    copied from the request.
    """
    if "code" in result and "http_status" in result:
        return result
    return {**{f"requested_{key}": value for key, value in requested.items()}, **result}


def _tool_error(exc: Any) -> ToolResult:
    return exc.as_dict()


async def _call_tool(operation: Callable[[], Awaitable[ToolResult]]) -> ToolResult:
    from .client import GamedaiMCPError

    try:
        return await operation()
    except GamedaiMCPError as exc:
        return _tool_error(exc)


def _build_fastmcp(name: str, *, host: str, port: int) -> Any:
    from mcp.server.fastmcp import FastMCP

    settings: dict[str, Any] = {"host": host, "port": port}
    if "stateless_http" in inspect.signature(FastMCP).parameters:
        settings["stateless_http"] = True
    return FastMCP(name, **settings)


def build_mcp_server(*, host: str = "127.0.0.1", port: int = 8080) -> Any:
    from mcp.types import ToolAnnotations
    from starlette.responses import JSONResponse

    from .client import GamedaiClient

    mcp = _build_fastmcp("Scout by gamedai", host=host, port=port)

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(request: Any) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "gamedai-mcp"})

    @mcp.custom_route("/readyz", methods=["GET"], include_in_schema=False)
    async def readyz(request: Any) -> JSONResponse:
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                async with GamedaiClient(http_client=http_client) as client:
                    await client.scout_health()
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False}, status_code=503)
        return JSONResponse({"ok": True}, status_code=200)

    @mcp.custom_route(
        "/.well-known/openai-apps-challenge", methods=["GET"], include_in_schema=False
    )
    async def openai_apps_challenge(request: Any) -> Any:
        # OpenAI ChatGPT-app domain verification. The token is a PUBLIC
        # challenge value issued by the dashboard for this app, not a secret.
        from starlette.responses import PlainTextResponse

        token = os.environ.get(
            "OPENAI_APPS_CHALLENGE_TOKEN",
            "MJEfnQI4ZBcy76DXVzupKGOA1H75JGaSwVIBztwFmtQ",
        )
        return PlainTextResponse(token)

    annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=True,
    )

    @mcp.tool(annotations=annotations)
    async def get_game_scores(
        date: str | None = None,
        event_id: str | None = None,
    ) -> ToolResult:
        """Return the public NFL slate, optionally filtered by event id."""
        async with GamedaiClient() as client:
            return await _call_tool(lambda: client.get_game_scores(date=date, event_id=event_id))

    @mcp.tool(annotations=annotations)
    async def get_wire_news(page: int = 1, page_size: int = 10) -> ToolResult:
        """Return paginated Wire NFL news."""
        async with GamedaiClient() as client:
            return await _call_tool(lambda: client.get_wire_news(page=page, page_size=page_size))

    @mcp.tool(annotations=annotations)
    async def get_player_grade(
        player: str,
        season: int | None = None,
        week: int | None = None,
    ) -> ToolResult:
        """Return a public Scout player grade."""
        effective_season = season if season is not None else latest_complete_nfl_season()
        async with GamedaiClient() as client:
            return await _call_tool(lambda: client.player_grade(player, effective_season, week))

    @mcp.tool(annotations=annotations)
    async def get_start_sit_recommendation(
        player_a: str,
        player_b: str,
        week: int,
        season: int | None = None,
    ) -> ToolResult:
        """Return a public Scout start/sit comparison."""
        effective_season = season if season is not None else current_nfl_league_year()
        async with GamedaiClient() as client:
            result = await _call_tool(
                lambda: client.start_sit(player_a, player_b, effective_season, week)
            )
        return _with_request_context(result, season=effective_season, week=week)

    @mcp.tool(annotations=annotations)
    async def get_scout_rankings(
        position: str = "ALL",
        scoring: str = "PPR",
        week: int | None = None,
    ) -> ToolResult:
        """Return the public Scout rankings board (FantasyPros consensus).

        Omit `week` for the source's current week. `requested_week` echoes the
        query; `source_season`/`source_week` come from the backend and stay
        null when the source did not say.
        """
        async with GamedaiClient() as client:
            result = await _call_tool(
                lambda: client.rankings(
                    position=position,
                    scoring=scoring,
                    week=week,
                )
            )
        return _with_request_context(result, week=week)

    return mcp


def _default_port() -> int:
    return int(os.environ.get("PORT", "8080"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the gamedai MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport to run.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transports.")
    parser.add_argument(
        "--port",
        type=int,
        default=_default_port(),
        help="Port for HTTP transports. Defaults to PORT or 8080.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    mcp = build_mcp_server(host=args.host, port=args.port)
    result = mcp.run(transport=args.transport)
    if asyncio.iscoroutine(result):
        asyncio.run(result)
