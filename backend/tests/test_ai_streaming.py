import asyncio

from openai.types.responses import ResponseFunctionToolCall

from app.ai.provider import OpenAIProvider, _configured_provider, response_items_as_input


class Event:
    def __init__(self, event_type, delta=None):
        self.type = event_type
        self.delta = delta


class Response:
    output = []
    output_text = "Hello world"
    usage = None


class Stream:
    def __init__(self):
        self.events = iter([Event("response.output_text.delta", "Hello "), Event("response.output_text.delta", "world")])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.events)
        except StopIteration:
            raise StopAsyncIteration

    async def get_final_response(self):
        return Response()


class Responses:
    def stream(self, **_kwargs):
        return Stream()


class Client:
    responses = Responses()


def test_provider_forwards_real_text_deltas():
    async def run():
        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider.async_client = Client()
        chunks = []

        result = await provider.respond(model="test", inputs=[], tools=[], on_text_delta=chunks.append)

        assert chunks == ["Hello ", "world"]
        assert result.text == "Hello world"

    asyncio.run(run())


def test_tool_call_continuation_strips_sdk_only_parsed_arguments():
    call = ResponseFunctionToolCall(
        arguments='{"subject":"clients"}',
        call_id="call_1",
        name="business_records",
        type="function_call",
        parsed_arguments={"subject": "clients"},
    )

    items = response_items_as_input([call])

    assert items == [{
        "type": "function_call",
        "call_id": "call_1",
        "name": "business_records",
        "arguments": '{"subject":"clients"}',
    }]
    assert "parsed_arguments" not in str(items)


def test_provider_clients_are_reused_for_connection_pooling(monkeypatch):
    created = []

    class ReusedProvider:
        def __init__(self):
            created.append(self)

    _configured_provider.cache_clear()
    monkeypatch.setattr("app.ai.provider.OpenAIProvider", ReusedProvider)
    first = _configured_provider("same-key", "same-url")
    second = _configured_provider("same-key", "same-url")

    assert first is second
    assert len(created) == 1
    _configured_provider.cache_clear()
