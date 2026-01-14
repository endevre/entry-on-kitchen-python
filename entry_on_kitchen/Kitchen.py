"""
Kitchen Client Library for Entry on Kitchen API

Provides a simple interface for executing recipes synchronously and
receiving real-time streaming updates.
"""

import requests
import json
from typing import Iterator, Dict, Any, Optional


class KitchenClient:
    """
    Client for interacting with the Entry on Kitchen API.

    Example:
        client = KitchenClient(auth_code="your-auth-code", entry_point="beta")
        result = client.sync(recipe_id="abc123", entry_id="entry1", body={"key": "value"})

        for event in client.stream(recipe_id="abc123", entry_id="entry1", body={"key": "value"}):
            print(f"Event: {event['type']}")
    """

    def __init__(self, auth_code: str, entry_point: str = "entry"):
        """
        Initialize the KitchenClient.

        Args:
            auth_code: The X-Entry-Auth-Code for authentication
            entry_point: Entry point environment (default: "entry" for production).
                        Use "beta" for beta environment.

        Raises:
            ValueError: If auth_code is not provided
        """
        if not auth_code:
            raise ValueError("auth_code is required")

        self.auth_code = auth_code
        self.entry_point = entry_point

    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for API requests."""
        return {
            'Content-Type': 'application/json',
            'X-Entry-Auth-Code': self.auth_code,
        }

    def _get_base_url(self) -> str:
        """Get the base URL for API requests."""
        entry_point_prefix = f"{self.entry_point}." if self.entry_point else ""
        return f"https://{entry_point_prefix}entry.on.kitchen"

    def _prepare_body(self, body: Any) -> str:
        """
        Prepare the request body.

        Args:
            body: Either a string (already JSON) or a dict/list to be serialized

        Returns:
            JSON string
        """
        return body if isinstance(body, str) else json.dumps(body)

    def sync(self, recipe_id: str, entry_id: str, body: Any) -> Dict[str, Any]:
        """
        Execute a recipe synchronously.

        Args:
            recipe_id: The ID of the pipeline/recipe
            entry_id: The ID of the entry block
            body: The request body (dict or JSON string)

        Returns:
            Dictionary containing the response with keys:
                - runId: The execution run ID
                - status: Execution status ("finished", "error", etc.)
                - result: The execution result (if successful)
                - error: Error message (if failed)
                - exitBlock: Exit block information

        Raises:
            requests.HTTPError: If the request fails
        """
        headers = self._get_headers()
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(body)

        url = f"{base_url}/{recipe_id}/{entry_id}/sync"

        response = requests.post(
            url,
            data=stringified_body,
            headers=headers
        )

        # Try to parse JSON response
        try:
            result = response.json()
            # If we got an error response, return it instead of raising
            if response.status_code != 200:
                result['_statusCode'] = response.status_code
                return result
            return result
        except:
            # If response isn't JSON, raise the HTTP error
            response.raise_for_status()
            return None

    def stream(self, recipe_id: str, entry_id: str, body: Any) -> Iterator[Dict[str, Any]]:
        """
        Execute a recipe with streaming responses.

        Yields events as they arrive from the server. Each event is a dictionary
        containing:
            - runId: The execution run ID
            - type: Event type ("progress", "result", "delta", "info", "end")
            - time: Timestamp of the event
            - data: Event-specific data
            - socket: Socket ID (for "result" and "delta" events)
            - statusCode: HTTP status code

        Args:
            recipe_id: The ID of the pipeline/recipe
            entry_id: The ID of the entry block
            body: The request body (dict or JSON string)

        Yields:
            Dictionary objects representing stream events

        Raises:
            requests.HTTPError: If the initial request fails

        Example:
            for event in client.stream(recipe_id, entry_id, body):
                if event['type'] == 'progress':
                    print(f"Progress: {event['data']}")
                elif event['type'] == 'result':
                    print(f"Result: {event['data']}")
                elif event['type'] == 'end':
                    print(f"Complete: {event['data']}")
        """
        headers = self._get_headers()
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(body)

        url = f"{base_url}/{recipe_id}/{entry_id}/stream"

        response = requests.post(
            url,
            data=stringified_body,
            headers=headers,
            stream=True
        )

        response.raise_for_status()

        # The API returns concatenated JSON objects: {"..."}{"..."}{"..."}
        # We need to parse them incrementally
        buffer = ""
        decoder = json.JSONDecoder()

        for chunk in response.iter_content(decode_unicode=True):
            if chunk:
                buffer += chunk
                # Try to parse as many JSON objects as we can from the buffer
                while buffer:
                    buffer = buffer.strip()
                    if not buffer:
                        break

                    try:
                        # Parse one JSON object from the beginning of buffer
                        obj, idx = decoder.raw_decode(buffer)
                        yield obj
                        # Remove the parsed object from buffer
                        buffer = buffer[idx:].lstrip()
                    except json.JSONDecodeError:
                        # Not enough data yet, wait for more chunks
                        break

    def stream_raw(self, recipe_id: str, entry_id: str, body: Any) -> Iterator[str]:
        """
        Execute a recipe with streaming responses, yielding raw JSON strings.

        This is useful if you want to handle JSON parsing yourself or need
        to deal with malformed JSON chunks.

        Args:
            recipe_id: The ID of the pipeline/recipe
            entry_id: The ID of the entry block
            body: The request body (dict or JSON string)

        Yields:
            Raw JSON strings from the stream

        Example:
            for raw_json in client.stream_raw(recipe_id, entry_id, body):
                print(raw_json)
        """
        headers = self._get_headers()
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(body)

        url = f"{base_url}/{recipe_id}/{entry_id}/stream"

        response = requests.post(
            url,
            data=stringified_body,
            headers=headers,
            stream=True
        )

        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if line:
                line = line.strip()
                if line.startswith("data: "):
                    line = line[6:]
                if line:
                    yield line
