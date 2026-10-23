import json
import pytest
from bot.providers.anilist import AniListProvider


class FakeContent:
    def __init__(self, data): self.data = data
    async def read(self, amount): return self.data[:amount]


class FakeResponse:
    def __init__(self, status, headers, body): self.status=status; self.headers=headers; self.content=FakeContent(body)
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False


class FakeSession:
    def __init__(self, responses): self.responses=list(responses); self.calls=0
    def post(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_anilist_429_respects_retry_and_succeeds(monkeypatch):
    async def no_sleep(_seconds): return None
    monkeypatch.setattr("asyncio.sleep", no_sleep)
    good = json.dumps({"data": {"Page": {"media": []}}}).encode()
    session = FakeSession([
        FakeResponse(429, {"Retry-After": "1"}, b'{"errors":[]}'),
        FakeResponse(200, {}, good),
    ])
    provider = AniListProvider(session=session)
    result = await provider._graphql("query { Page { media { id } } }", {})
    assert result == {"Page": {"media": []}}
    assert session.calls == 2


@pytest.mark.asyncio
async def test_anilist_response_size_limit_rejects_oversized_payload():
    session = FakeSession([FakeResponse(200, {}, b'x' * 100)])
    provider = AniListProvider(session=session, max_bytes=20)
    with pytest.raises(ValueError, match="size limit"):
        await provider._graphql("query { x }", {})


@pytest.mark.asyncio
async def test_anilist_retries_transient_network_errors(monkeypatch):
    import aiohttp

    async def no_sleep(_seconds): return None
    monkeypatch.setattr("asyncio.sleep", no_sleep)

    class FlakySession(FakeSession):
        def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise aiohttp.ClientError("temporary connection issue")
            return self.responses.pop(0)

    good = json.dumps({"data": {"Page": {"media": []}}}).encode()
    session = FlakySession([FakeResponse(200, {}, good)])
    provider = AniListProvider(session=session)
    assert await provider._graphql("query { Page { media { id } } }", {}) == {"Page": {"media": []}}
    assert session.calls == 2
