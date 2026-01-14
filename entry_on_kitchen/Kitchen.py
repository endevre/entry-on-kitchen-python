"""
Kitchen Client Library for Entry on Kitchen API

Provides a simple interface for executing recipes synchronously and
receiving real-time streaming updates.
"""

import requests
import json
from typing import Iterator, Dict, Any, Optional, List, Union


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

    def _prepare_body(self, body: Any, use_kitchen_billing: bool = False, llm_override: str = None, api_key_override: Dict[str, Dict[str, str]] = None) -> str:
        """
        Prepare the request body.

        Args:
            body: Either a string (already JSON) or a dict/list to be serialized
            use_kitchen_billing: Enable Kitchen billing (optional)
            llm_override: LLM model override (optional)
            api_key_override: API key overrides (optional)

        Returns:
            JSON string
        """
        body_obj = body if isinstance(body, str) else json.loads(json.dumps(body))

        # Add KITCHEN_BILLING_OVERRIDE if specified
        if use_kitchen_billing:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_BILLING_OVERRIDE": True}
            else:
                body_obj = {"KITCHEN_BILLING_OVERRIDE": True}

        # Add KITCHEN_MODELS_OVERRIDE if llm_override is specified
        if llm_override:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_MODELS_OVERRIDE": {"llm_override": llm_override}}
            else:
                body_obj = {"KITCHEN_MODELS_OVERRIDE": {"llm_override": llm_override}}

        # Add KITCHEN_APIKEYS_OVERRIDE if api_key_override is specified
        if api_key_override and isinstance(api_key_override, dict) and len(api_key_override) > 0:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_APIKEYS_OVERRIDE": api_key_override}
            else:
                body_obj = {"KITCHEN_APIKEYS_OVERRIDE": api_key_override}

        return json.dumps(body_obj)

    def sync(self, recipe_id: str, entry_id: str, body: Any, use_kitchen_billing: bool = False, llm_override: str = None, api_key_override: Dict[str, Dict[str, str]] = None, headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Execute a recipe synchronously.

        Args:
            recipe_id: The ID of the pipeline/recipe
            entry_id: The ID of the entry block
            body: The request body (dict or JSON string)
            use_kitchen_billing: Enable Kitchen billing (optional)
            llm_override: LLM model override (optional)
            api_key_override: API key overrides (optional)
            headers: Custom headers (optional, for HMAC signatures, etc.)

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
        request_headers = self._get_headers()
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(body, use_kitchen_billing, llm_override, api_key_override)

        # Merge custom headers
        if headers:
            request_headers.update(headers)

        url = f"{base_url}/{recipe_id}/{entry_id}/sync"

        response = requests.post(
            url,
            data=stringified_body,
            headers=request_headers
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

    def stream(self, recipe_id: str, entry_id: str, body: Any, use_kitchen_billing: bool = False, llm_override: str = None, api_key_override: Dict[str, Dict[str, str]] = None, headers: Dict[str, str] = None) -> Iterator[Dict[str, Any]]:
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
            use_kitchen_billing: Enable Kitchen billing (optional)
            llm_override: LLM model override (optional)
            api_key_override: API key overrides (optional)
            headers: Custom headers (optional, for HMAC signatures, etc.)

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
        request_headers = self._get_headers()
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(body, use_kitchen_billing, llm_override, api_key_override)

        # Merge custom headers
        if headers:
            request_headers.update(headers)

        url = f"{base_url}/{recipe_id}/{entry_id}/stream"

        response = requests.post(
            url,
            data=stringified_body,
            headers=request_headers,
            stream=True
        )

        response.raise_for_status()

        # The API returns either:
        # 1. Server-Sent Events with "data:" prefix: data:{...}data:{...}
        # 2. Raw concatenated JSON objects: {...}{...}{...}
        # Reference implementation approach: split on "data:" and "}{"
        buffer = ""

        for chunk in response.iter_content():
            if chunk:
                # Decode chunk as UTF-8 and accumulate
                buffer += chunk.decode('utf-8')

        # Process all accumulated data
        # The API returns either:
        # 1. SSE format: data:{...}\ndata:{...} (each line is valid JSON)
        # 2. Concatenated JSON: {...}{...}{...} (no separators)
        lines = buffer.split("data:")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                # Try parsing as single JSON object (SSE format)
                obj = json.loads(line)
                yield obj
            except json.JSONDecodeError:
                # If that fails, try splitting on "}{" (concatenated format)
                split_values = line.split("}{")
                for i in range(len(split_values)):
                    reconstructed = (
                        ("{" if i > 0 else "") +
                        split_values[i] +
                        ("}" if i < len(split_values) - 1 else "")
                    )

                    try:
                        obj = json.loads(reconstructed)
                        yield obj
                    except json.JSONDecodeError:
                        # Skip invalid JSON
                        continue

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

    @staticmethod
    def apply_delta(original: str, delta: List[List[Any]]) -> str:
        """
        Apply delta operations to a string.

        Delta operations format:
        - ["i", position, string] - Insert string at position (string is JSON-encoded)
        - ["d", position] or ["d", position, length] - Delete characters

        Note: The insert string is JSON-encoded and will be automatically parsed.

        Args:
            original: The original string
            delta: List of delta operations

        Returns:
            The modified string

        Example:
            >>> text = "Hello"
            >>> ops = [["i", 5, " World"]]
            >>> KitchenClient.apply_delta(text, ops)
            "Hello World"
        """
        result = list(original)
        offset = 0

        for operation in delta:
            op_type = operation[0]

            if op_type == "d":
                # Delete operation
                position = operation[1] + offset
                length = operation[2] if len(operation) > 2 else 1

                # Delete characters at position
                del result[position:position + length]
                offset -= length

            elif op_type == "i":
                # Insert operation
                position = operation[1] + offset
                text = operation[2]

                # Parse JSON-encoded string if applicable
                if isinstance(text, str) and text.startswith('"'):
                    try:
                        text = json.loads(text)
                    except:
                        pass  # Not valid JSON, use as-is

                # Insert text at position
                result[position:position] = list(str(text))
                offset += len(str(text))

        return "".join(result)
