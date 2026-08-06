import json
import unittest
from unittest.mock import patch

from entry_on_kitchen import EntryCodeAuthorization, KitchenClient


class FakeResponse:
    def __init__(self, chunks=None, json_body=None, status_code=200):
        self._chunks = chunks or []
        self._json_body = json_body
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)
        return None

    def close(self):
        self.closed = True

    def iter_content(self):
        for chunk in self._chunks:
            yield chunk

    def json(self):
        return self._json_body


def sse_event(event):
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


class StreamTests(unittest.TestCase):
    def test_stream_decodes_stringified_sse_events(self):
        client = KitchenClient(EntryCodeAuthorization("test-auth-code"))
        inner_data = {
            "runId": None,
            "status": "error",
            "error": "bad request, user does not have permission to execute pipeline",
        }
        stringified_event = json.dumps({
            "runId": None,
            "type": "end",
            "time": 123,
            "data": json.dumps(inner_data),
            "socket": None,
            "statusCode": 400,
        })

        with patch("entry_on_kitchen.Kitchen.requests.post") as mock_post:
            mock_post.return_value = FakeResponse(chunks=[sse_event(stringified_event)])

            events = list(client.stream("recipe", "entry", {"message": "Hello!"}))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "end")
        self.assertEqual(events[0]["statusCode"], 400)
        self.assertEqual(events[0]["data"], inner_data)

    def test_stream_hydrates_terminal_final_payload_refs(self):
        client = KitchenClient(EntryCodeAuthorization("test-auth-code"))
        terminal_event = {
            "runId": "run-1",
            "seq": 1,
            "type": "end",
            "time": 123,
            "data": {
                "runId": "run-1",
                "status": "finished",
                "finalPayloadRef": {"url": "https://signed.example/final.json"},
                "error": None,
            },
            "socket": None,
            "statusCode": 200,
        }
        final_payload = {
            "runId": "run-1",
            "status": "finished",
            "result": "{\"ok\":true}",
        }

        with patch("entry_on_kitchen.Kitchen.requests.post") as mock_post, patch(
            "entry_on_kitchen.Kitchen.requests.get"
        ) as mock_get:
            mock_post.return_value = FakeResponse(chunks=[sse_event(terminal_event)])
            mock_get.return_value = FakeResponse(json_body=final_payload)

            events = list(client.stream("recipe", "entry", {"message": "Hello!"}))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"], final_payload)
        mock_get.assert_called_once_with("https://signed.example/final.json")


if __name__ == "__main__":
    unittest.main()
