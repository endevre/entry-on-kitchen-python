import json
import unittest
from unittest.mock import patch

import requests

from entry_on_kitchen import (
    AuthorizationError,
    BearerAuthorization,
    EntryCodeAuthorization,
    KitchenClient,
)


AUTH_ERROR = "Authorization expired or invalid"


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, chunks=None, lines=None):
        self.status_code = status_code
        self._json_body = json_body
        self._chunks = chunks or []
        self._lines = lines or []
        self.closed = False
        self.json_calls = 0

    def json(self):
        self.json_calls += 1
        if isinstance(self._json_body, Exception):
            raise self._json_body
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def iter_content(self):
        for chunk in self._chunks:
            yield chunk

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


def sse_event(event):
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


class AuthorizationTests(unittest.TestCase):
    def test_constructor_requires_an_authorization_capability(self):
        with self.assertRaises(ValueError):
            KitchenClient(None)
        with self.assertRaises(TypeError):
            KitchenClient("legacy-auth-code")
        with self.assertRaises(ValueError):
            EntryCodeAuthorization("")
        with self.assertRaises(ValueError):
            BearerAuthorization(None)

    def test_entry_code_auth_is_static_and_reserved_headers_cannot_be_overridden(self):
        client = KitchenClient(EntryCodeAuthorization("entry-code"))
        response = FakeResponse(json_body={"status": "finished"})

        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            client.sync(
                "recipe",
                "entry",
                {},
                headers={
                    "authorization": "attacker-token",
                    "X-ENTRY-AUTH-CODE": "attacker-code",
                    "X-Trace": "trace-1",
                },
            )

        sent_headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(sent_headers["X-Entry-Auth-Code"], "entry-code")
        self.assertNotIn("authorization", sent_headers)
        self.assertNotIn("X-ENTRY-AUTH-CODE", sent_headers)
        self.assertEqual(sent_headers["X-Trace"], "trace-1")

    def test_bearer_value_is_used_raw_and_is_acquired_for_each_request(self):
        calls = []

        def get_token(refresh):
            calls.append(refresh)
            return "raw-token"

        client = KitchenClient(BearerAuthorization(get_token))
        response = FakeResponse(json_body={"status": "finished"})
        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            client.sync("recipe", "entry", {}, headers={"Authorization": "attacker"})
            client.sync("recipe", "entry", {})

        self.assertEqual(calls, [False, False])
        for call in mock_post.call_args_list:
            self.assertEqual(call.kwargs["headers"]["Authorization"], "raw-token")
            self.assertNotIn("X-Entry-Auth-Code", call.kwargs["headers"])

    def test_bearer_retries_once_after_http_401_with_forced_refresh(self):
        calls = []

        def get_token(force_refresh):
            calls.append(force_refresh)
            return "new-token" if force_refresh else "old-token"

        client = KitchenClient(BearerAuthorization(get_token))
        first = FakeResponse(status_code=401, json_body={"error": "Unauthorized"})
        second = FakeResponse(json_body={"status": "finished"})

        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=[first, second]) as mock_post:
            result = client.sync("recipe", "entry", {})

        self.assertEqual(result["status"], "finished")
        self.assertEqual(calls, [False, True])
        self.assertEqual(
            [call.kwargs["headers"]["Authorization"] for call in mock_post.call_args_list],
            ["old-token", "new-token"],
        )

    def test_http_401_with_run_id_is_not_replayed(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(lambda refresh: calls.append(refresh) or "token")
        )
        response = FakeResponse(
            status_code=401,
            json_body={"runId": "run-1", "error": AUTH_ERROR},
        )

        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            result = client.sync("recipe", "entry", {})

        self.assertEqual(result["_statusCode"], 401)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(calls, [False])

    def test_bearer_retries_exact_runner_payload_once(self):
        calls = []

        def get_token(force_refresh):
            calls.append(force_refresh)
            return "new-token" if force_refresh else "old-token"

        client = KitchenClient(BearerAuthorization(get_token))
        first = FakeResponse(status_code=400, json_body={"error": AUTH_ERROR})
        second = FakeResponse(json_body={"status": "finished"})
        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=[first, second]) as mock_post:
            result = client.sync("recipe", "entry", {})

        self.assertEqual(result["status"], "finished")
        self.assertEqual(calls, [False, True])
        self.assertEqual(mock_post.call_count, 2)

    def test_auth_failure_matching_accepts_raw_and_error_message_shapes(self):
        self.assertTrue(KitchenClient._is_authorization_expired_payload(AUTH_ERROR))
        self.assertTrue(
            KitchenClient._is_authorization_expired_payload({"error_message": AUTH_ERROR})
        )

    def test_generic_403_is_not_retried(self):
        calls = []
        client = KitchenClient(BearerAuthorization(lambda force_refresh: calls.append(force_refresh) or "token"))
        response = FakeResponse(status_code=403, json_body={"error": "Forbidden"})

        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            result = client.sync("recipe", "entry", {})

        self.assertEqual(result["_statusCode"], 403)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(calls, [False])

    def test_static_entry_code_is_not_retried_after_401(self):
        client = KitchenClient(EntryCodeAuthorization("entry-code"))
        response = FakeResponse(status_code=401, json_body={"error": AUTH_ERROR})
        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            result = client.sync("recipe", "entry", {})

        self.assertEqual(result["_statusCode"], 401)
        self.assertEqual(mock_post.call_count, 1)

    def test_second_authorization_failure_is_not_retried(self):
        calls = []
        client = KitchenClient(BearerAuthorization(lambda force_refresh: calls.append(force_refresh) or "token"))
        responses = [
            FakeResponse(status_code=401, json_body={"error": AUTH_ERROR}),
            FakeResponse(status_code=401, json_body={"error": AUTH_ERROR}),
        ]
        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=responses) as mock_post:
            result = client.sync("recipe", "entry", {})

        self.assertEqual(result["_statusCode"], 401)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(calls, [False, True])

    def test_stream_retries_auth_event_before_yielding_any_event(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(
                lambda force_refresh: calls.append(force_refresh)
                or ("new-token" if force_refresh else "old-token")
            )
        )
        auth_event = {
            "runId": None,
            "type": "error",
            "statusCode": 400,
            "data": {"error": AUTH_ERROR},
        }
        success_event = {
            "runId": "run-1",
            "type": "end",
            "statusCode": 200,
            "data": {"status": "finished"},
        }
        responses = [
            FakeResponse(chunks=[sse_event(auth_event)]),
            FakeResponse(chunks=[sse_event(success_event)]),
        ]

        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=responses) as mock_post:
            events = list(client.stream("recipe", "entry", {}))

        self.assertEqual([event["runId"] for event in events], ["run-1"])
        self.assertEqual(calls, [False, True])
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(responses[0].json_calls, 0)
        self.assertEqual(responses[1].json_calls, 0)

    def test_stream_401_then_auth_event_uses_one_total_recovery_replay(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(lambda refresh: calls.append(refresh) or "token")
        )
        auth_event = {
            "runId": None,
            "type": "error",
            "statusCode": 400,
            "data": {"error_message": AUTH_ERROR},
        }
        responses = [
            FakeResponse(status_code=401, json_body={"error": "Unauthorized"}),
            FakeResponse(chunks=[sse_event(auth_event)]),
        ]

        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=responses) as mock_post:
            events = list(client.stream("recipe", "entry", {}))

        self.assertEqual(len(events), 1)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(calls, [False, True])

    def test_stream_does_not_retry_after_a_non_auth_event(self):
        calls = []
        client = KitchenClient(BearerAuthorization(lambda force_refresh: calls.append(force_refresh) or "token"))
        progress = {"runId": None, "type": "progress", "statusCode": 200, "data": {}}
        auth_event = {
            "runId": None,
            "type": "error",
            "statusCode": 400,
            "data": {"error": AUTH_ERROR},
        }
        response = FakeResponse(chunks=[sse_event(progress), sse_event(auth_event)])
        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            events = list(client.stream("recipe", "entry", {}))

        self.assertEqual(len(events), 2)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(calls, [False])

    def test_stream_does_not_replay_auth_event_with_nested_run_id(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(lambda refresh: calls.append(refresh) or "token")
        )
        event = {
            "runId": None,
            "type": "error",
            "statusCode": 400,
            "data": {"runId": "run-1", "error": AUTH_ERROR},
        }
        response = FakeResponse(chunks=[sse_event(event)])
        with patch("entry_on_kitchen.Kitchen.requests.post", return_value=response) as mock_post:
            events = list(client.stream("recipe", "entry", {}))

        self.assertEqual(len(events), 1)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(calls, [False])

    def test_stream_recovery_request_does_not_open_a_second_retry_budget(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(
                lambda force_refresh: calls.append(force_refresh) or "token"
            )
        )
        auth_event = {
            "runId": None,
            "type": "error",
            "statusCode": 400,
            "data": {"error": AUTH_ERROR},
        }
        first = FakeResponse(chunks=[sse_event(auth_event)])
        second = FakeResponse(status_code=401, json_body={"error": AUTH_ERROR})
        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=[first, second]) as mock_post:
            with self.assertRaises(requests.HTTPError):
                list(client.stream("recipe", "entry", {}))

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(calls, [False, True])

    def test_stream_raw_retries_auth_event_before_yielding_any_line(self):
        calls = []
        client = KitchenClient(BearerAuthorization(lambda force_refresh: calls.append(force_refresh) or "token"))
        auth_line = json.dumps({"runId": None, "statusCode": 400, "data": {"error": AUTH_ERROR}})
        success_line = json.dumps({"runId": "run-1", "statusCode": 200, "type": "end"})
        responses = [
            FakeResponse(lines=[auth_line]),
            FakeResponse(lines=[success_line]),
        ]
        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=responses) as mock_post:
            lines = list(client.stream_raw("recipe", "entry", {}))

        self.assertEqual(lines, [success_line])
        self.assertEqual(calls, [False, True])
        self.assertEqual(mock_post.call_count, 2)

    def test_stream_raw_401_then_auth_event_uses_one_total_recovery_replay(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(lambda refresh: calls.append(refresh) or "token")
        )
        auth_line = json.dumps(
            {"runId": None, "statusCode": 400, "data": {"error_message": AUTH_ERROR}}
        )
        responses = [
            FakeResponse(status_code=401, json_body={"error": "Unauthorized"}),
            FakeResponse(lines=[auth_line]),
        ]

        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=responses) as mock_post:
            lines = list(client.stream_raw("recipe", "entry", {}))

        self.assertEqual(lines, [auth_line])
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(calls, [False, True])

    def test_stream_retries_exact_http_payload_before_opening_stream(self):
        calls = []
        client = KitchenClient(
            BearerAuthorization(
                lambda force_refresh: calls.append(force_refresh) or "token"
            )
        )
        first = FakeResponse(status_code=400, json_body={"error": AUTH_ERROR})
        second = FakeResponse(chunks=[sse_event({"runId": "run-1", "type": "end"})])
        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=[first, second]) as mock_post:
            events = list(client.stream("recipe", "entry", {}))

        self.assertEqual(len(events), 1)
        self.assertEqual(calls, [False, True])
        self.assertEqual(mock_post.call_count, 2)

    def test_tool_iterations_acquire_auth_for_each_sync_request(self):
        calls = []
        client = KitchenClient(BearerAuthorization(lambda force_refresh: calls.append(force_refresh) or "token"))
        requires_tools = {
            "status": "requires_tool_outputs",
            "tool_calls": [
                {"id": "call-1", "name": "echo", "arguments": {"value": "ok"}}
            ],
            "continuation": {"type": "LLMContinuation", "version": 1},
        }
        responses = [
            FakeResponse(json_body={"result": json.dumps(requires_tools)}),
            FakeResponse(json_body={"status": "finished", "result": "ok"}),
        ]
        with patch("entry_on_kitchen.Kitchen.requests.post", side_effect=responses) as mock_post:
            result = client.run_with_tools(
                "recipe",
                "entry",
                {},
                tools=[],
                handlers={"echo": lambda args, call: args["value"]},
            )

        self.assertEqual(result["status"], "finished")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(calls, [False, False])

    def test_signed_final_payload_fetch_has_no_kitchen_credentials(self):
        client = KitchenClient(EntryCodeAuthorization("entry-code"))
        final_payload = FakeResponse(json_body={"status": "finished"})
        with patch("entry_on_kitchen.Kitchen.requests.get", return_value=final_payload) as mock_get:
            result = client._fetch_final_payload({"url": "https://signed.example/final.json"})

        self.assertEqual(result["status"], "finished")
        mock_get.assert_called_once_with("https://signed.example/final.json")


if __name__ == "__main__":
    unittest.main()
