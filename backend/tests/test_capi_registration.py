import asyncio
from types import SimpleNamespace

import httpx


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, statuses: list[int]) -> None:
        self._statuses = statuses
        self.paths: list[str] = []
        self._calls = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        self._calls.set()
        return httpx.Response(self._statuses.pop(0), request=request)

    async def wait_for_calls(self, count: int) -> None:
        while len(self.paths) < count:
            self._calls.clear()
            await asyncio.wait_for(self._calls.wait(), timeout=1)


def test_registration_payload_matches_observed_gnomledger_responsibilities() -> None:
    from backend.app.services.capi_registration import _registration_payload

    payload = _registration_payload()

    assert payload["service_name"] == "gnomledger"
    assert payload["capabilities"] == ["pgl_ledger", "verification"]
    assert "x402_settlement" not in payload["capabilities"]


def test_heartbeat_refreshes_an_existing_registration() -> None:
    from backend.app.services.capi_registration import maintain_capi_registration

    async def exercise() -> None:
        settings = SimpleNamespace(
            capi_backend_url="http://capi.test",
            capi_api_key="registry-token",
            CAPI_REGISTRY_TTL_MS=1,
        )
        transport = RecordingTransport([201, 200])
        stop = asyncio.Event()
        task = asyncio.create_task(maintain_capi_registration(settings, stop, transport))
        await transport.wait_for_calls(2)
        stop.set()
        await task
        assert transport.paths == ["/api/v1/registry/register", "/api/v1/registry/heartbeat"]

    asyncio.run(exercise())


def test_heartbeat_404_re_registers_before_clean_shutdown() -> None:
    from backend.app.services.capi_registration import maintain_capi_registration

    async def exercise() -> None:
        settings = SimpleNamespace(
            capi_backend_url="http://capi.test",
            capi_api_key="registry-token",
            CAPI_REGISTRY_TTL_MS=1,
        )
        transport = RecordingTransport([201, 404, 201])
        stop = asyncio.Event()
        task = asyncio.create_task(maintain_capi_registration(settings, stop, transport))
        await transport.wait_for_calls(3)
        stop.set()
        await task
        assert transport.paths == [
            "/api/v1/registry/register",
            "/api/v1/registry/heartbeat",
            "/api/v1/registry/register",
        ]

    asyncio.run(exercise())
