from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from gamedai_mcp.client import GamedaiClient
from gamedai_mcp.server import TOOL_TARGETS


CONTRACT = (
    Path(__file__).resolve().parents[3] / "backend/openapi/scout_public_contract.openapi.json"
)

# The contract is generated from the FastAPI routes in the monorepo
# (scripts/mcp/generate_public_contract.py). The standalone mirror at
# github.com/omniviewai/gamedai-nfl-mcp has no backend/ beside it, so these
# tests skip there instead of failing on a missing file.
requires_contract = pytest.mark.skipif(
    not CONTRACT.exists(), reason=f"public Scout contract not present at {CONTRACT}"
)


def _operation(contract: dict[str, Any], path: str) -> dict[str, Any]:
    return contract["paths"][path]["get"]


class CapturedAsyncClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.requests.append((method, url, kwargs))
        payload: dict[str, Any] = {"games": []} if url.endswith("/v1/games/slate") else {"ok": True}
        return httpx.Response(
            200,
            json=payload,
            request=httpx.Request(method, url),
        )

    async def aclose(self) -> None:
        return None


CLIENT_METHODS = {
    "get_game_scores": "get_game_scores",
    "get_wire_news": "get_wire_news",
    "get_player_grade": "player_grade",
    "get_start_sit_recommendation": "start_sit",
    "get_scout_rankings": "rankings",
}

MINIMAL_VALUES: dict[str, str | int] = {
    "player": "Player A",
    "player_a": "Player A",
    "player_b": "Player B",
    "season": 2025,
    "week": 1,
}


def _minimal_required_kwargs(method: Any) -> dict[str, str | int]:
    return {
        name: MINIMAL_VALUES[name]
        for name, parameter in inspect.signature(method).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }


@requires_contract
def test_client_sends_all_contract_required_query_parameters() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    captured = CapturedAsyncClient()

    async def invoke_tools() -> None:
        client = GamedaiClient(
            base_url="https://api.test",
            http_client=captured,  # type: ignore[arg-type]
        )
        for tool_name, method_name in CLIENT_METHODS.items():
            method = getattr(client, method_name)
            await method(**_minimal_required_kwargs(method))

    asyncio.run(invoke_tools())

    for (tool_name, (path, _expected_names)), request in zip(
        TOOL_TARGETS.items(), captured.requests, strict=True
    ):
        assert path in contract["paths"], tool_name
        operation = _operation(contract, path)
        contract_parameters = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "query"
        }
        sent_params = set(request[2].get("params") or {})
        required_parameters = {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "query" and parameter.get("required") is True
        }
        assert sent_params <= contract_parameters, tool_name
        assert required_parameters <= sent_params, tool_name


@requires_contract
def test_start_sit_recommendation_is_nullable_in_the_generated_contract() -> None:
    schema = contract_schema("StartSitResponse")
    recommendation = schema["properties"]["recommendation"]

    assert any(option == {"type": "null"} for option in recommendation["anyOf"])


def contract_schema(name: str) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return contract["components"]["schemas"][name]
