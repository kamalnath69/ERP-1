from app.services.billing import provider_error
from app.services.razorpay_provider import RazorpayProvider, RazorpayProviderError


class Response:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.content = b"json"

    def json(self):
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def plan_payload():
    return {
        "period": "monthly", "interval": 1,
        "item": {"name": "Growth", "amount": 294882, "currency": "INR"},
        "notes": {"plan_version_id": "version-2", "mode": "test"},
    }


def test_provider_preserves_safe_error_details():
    session = Session([Response(500, {"error": {"code": "SERVER_ERROR", "description": "Temporary failure"}}, {"X-Razorpay-Request-Id": "req-1"})])
    provider = RazorpayProvider("key", "secret", session=session, sleep=lambda _seconds: None)

    try:
        provider.create_order({"amount": 100, "currency": "INR"})
        assert False, "Expected provider error"
    except RazorpayProviderError as exc:
        assert exc.status_code == 500
        assert exc.error["code"] == "SERVER_ERROR"
        assert exc.request_id == "req-1"


def test_provider_authentication_failure_has_a_safe_client_message():
    error = RazorpayProviderError("Unauthorized", status_code=401)

    assert provider_error(error, "plan") == (
        "provider_authentication",
        "Online payments are temporarily unavailable",
    )


def test_plan_creation_recovers_an_accepted_response_without_duplicate_creation():
    payload = plan_payload()
    existing = {"id": "plan_existing", **payload}
    session = Session([
        Response(500, {"error": {"code": "SERVER_ERROR", "description": "Temporary failure"}}),
        Response(200, {"items": [existing]}),
    ])
    provider = RazorpayProvider("key", "secret", session=session, sleep=lambda _seconds: None)

    assert provider.create_plan(payload)["id"] == "plan_existing"
    assert [call[0] for call in session.calls] == ["POST", "GET"]


def test_plan_creation_retries_once_when_no_plan_was_created():
    payload = plan_payload()
    session = Session([
        Response(503, {"error": {"code": "SERVER_ERROR", "description": "Unavailable"}}),
        Response(200, {"items": []}),
        Response(200, {"id": "plan_new", **payload}),
    ])
    provider = RazorpayProvider("key", "secret", session=session, sleep=lambda _seconds: None)

    assert provider.create_plan(payload)["id"] == "plan_new"
    assert [call[0] for call in session.calls] == ["POST", "GET", "POST"]
