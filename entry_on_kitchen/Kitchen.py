"""
Kitchen Client Library for Entry on Kitchen API

Provides a simple interface for executing recipes synchronously and
receiving real-time streaming updates.
"""

import requests
import json
from typing import Iterator, Dict, Any, Optional, List, Union, Callable

from .tools import (
    create_tool_error,
    create_tool_result,
    get_tool_call_request,
    with_tool_results,
    with_tools,
)


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
        body_obj = json.loads(body) if isinstance(body, str) else json.loads(json.dumps(body))

        # Add KITCHEN_BILLING_OVERRIDE if specified
        if use_kitchen_billing:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_BILLING_OVERRIDE": True}
            else:
                body_obj = {"KITCHEN_BILLING_OVERRIDE": True}

        # Add KITCHEN_MODELS_OVERRIDE if llm_override is specified
        if llm_override:
            existing_model_overrides = {}
            if isinstance(body_obj, dict) and isinstance(body_obj.get("KITCHEN_MODELS_OVERRIDE"), dict):
                existing_model_overrides = body_obj["KITCHEN_MODELS_OVERRIDE"]

            if isinstance(body_obj, dict):
                body_obj = {
                    **body_obj,
                    "KITCHEN_MODELS_OVERRIDE": {
                        **existing_model_overrides,
                        "models__llm_override": llm_override,
                    },
                }
            else:
                body_obj = {"KITCHEN_MODELS_OVERRIDE": {"models__llm_override": llm_override}}

        # Add KITCHEN_APIKEYS_OVERRIDE if api_key_override is specified
        if api_key_override and isinstance(api_key_override, dict) and len(api_key_override) > 0:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_APIKEYS_OVERRIDE": api_key_override}
            else:
                body_obj = {"KITCHEN_APIKEYS_OVERRIDE": api_key_override}

        return json.dumps(body_obj)

    def _parse_stream_event(self, value: str) -> Optional[Dict[str, Any]]:
        """Parse a stream event, including payloads that were JSON encoded twice."""
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    def _is_final_payload_ref(self, value: Any) -> bool:
        return isinstance(value, dict) and (
            ("bucket" in value and "key" in value) or "url" in value
        )

    def _fetch_final_payload(self, ref: Dict[str, Any]) -> Dict[str, Any]:
        url = ref.get("url")
        if not url:
            raise ValueError("Final payload reference does not include a URL")

        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def _hydrate_terminal_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        if event.get("type") not in ("end", "error"):
            return event

        data = event.get("data")
        if isinstance(data, str):
            parsed_data = self._parse_stream_event(data)
            if parsed_data is not None:
                data = parsed_data
                event = {**event, "data": data}

        if not isinstance(data, dict):
            return event

        has_inline_error = data.get("error") not in (None, "", "null")
        has_inline_payload = (
            "result" in data or has_inline_error or "exitBlock" in data
        )
        ref = data.get("finalPayloadRef")
        if has_inline_payload or not self._is_final_payload_ref(ref):
            return event

        return {
            **event,
            "data": self._fetch_final_payload(ref),
        }

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

    def run_with_tools(
        self,
        recipe_id: str,
        entry_id: str,
        body: Any,
        tools: List[Dict[str, Any]],
        handlers: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]],
        use_kitchen_billing: bool = False,
        llm_override: str = None,
        api_key_override: Dict[str, Dict[str, str]] = None,
        headers: Dict[str, str] = None,
        max_tool_iterations: int = 5,
        on_tool_call: Callable[[Dict[str, Any]], Any] = None,
        on_tool_result: Callable[[Dict[str, Any]], Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a recipe and automatically satisfy external LLM tool calls.

        The recipe should expose tools/tool_results/continuation entry params to
        its LLM block. This helper reruns the recipe with tool results until the
        model completes or max_tool_iterations is reached.
        """
        current_body = with_tools(body, tools)
        last_response = None

        for _ in range(max_tool_iterations):
            response = self.sync(
                recipe_id=recipe_id,
                entry_id=entry_id,
                body=current_body,
                use_kitchen_billing=use_kitchen_billing,
                llm_override=llm_override,
                api_key_override=api_key_override,
                headers=headers,
            )
            last_response = response

            request = get_tool_call_request(response)
            if not request:
                return response

            tool_results = []
            for tool_call in request.get("tool_calls", []):
                if on_tool_call:
                    on_tool_call(tool_call)

                name = tool_call.get("name")
                handler = handlers.get(name)
                if handler is None:
                    tool_result = create_tool_error(
                        tool_call_id=tool_call.get("id"),
                        name=name,
                        message=f"No handler registered for tool '{name}'",
                        code="HANDLER_NOT_FOUND",
                    )
                else:
                    try:
                        output = handler(tool_call.get("arguments", {}), tool_call)
                        tool_result = create_tool_result(
                            tool_call_id=tool_call.get("id"),
                            name=name,
                            output=output,
                        )
                    except Exception as exc:
                        tool_result = create_tool_error(
                            tool_call_id=tool_call.get("id"),
                            name=name,
                            message=str(exc),
                            code="HANDLER_ERROR",
                        )

                if on_tool_result:
                    on_tool_result(tool_result)
                tool_results.append(tool_result)

            current_body = with_tool_results(body, tool_results, request["continuation"])

        result = dict(last_response or {})
        result["status"] = "error"
        result["error"] = f"Maximum tool iterations reached ({max_tool_iterations})"
        return result

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
        buffer = ""

        def extract_complete_json_objects(input_str):
            """Extract complete JSON objects from input string."""
            objects = []
            depth = 0
            in_string = False
            escape_next = False
            start_idx = -1

            for i, char in enumerate(input_str):
                if escape_next:
                    escape_next = False
                    continue

                if char == "\\":
                    escape_next = True
                    continue

                if char == '"':
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == "{":
                        if depth == 0:
                            start_idx = i
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0 and start_idx != -1:
                            objects.append(input_str[start_idx:i+1])
                            start_idx = -1

            return objects

        for chunk in response.iter_content():
            if chunk:
                # Decode chunk as UTF-8 and accumulate
                buffer += chunk.decode('utf-8')

                # Try to parse and yield complete objects as they arrive
                # SSE format: split by "data:" and try to parse each complete line
                if "data:" in buffer:
                    lines = buffer.split("data:")

                    # Check if the last line is complete (ends with } or ])
                    last_line = lines[-1].strip()
                    all_but_last_complete = True
                    if last_line and not last_line.endswith("}") and not last_line.endswith("]"):
                        all_but_last_complete = False

                    # Process all complete lines
                    lines_to_process = len(lines) if all_but_last_complete else len(lines) - 1
                    processed_chars = 0

                    for i in range(lines_to_process):
                        line = lines[i].strip()
                        if line:
                            obj = self._parse_stream_event(line)
                            if obj:
                                yield self._hydrate_terminal_event(obj)
                            else:
                                # Try concatenated format
                                objects = extract_complete_json_objects(line)
                                for obj_str in objects:
                                    obj = self._parse_stream_event(obj_str)
                                    if obj:
                                        yield self._hydrate_terminal_event(obj)
                            processed_chars += len(line) + 5  # +5 for "data:"
                        else:
                            processed_chars += 5  # Empty line, just skip "data:"

                    # Remove processed data from buffer
                    if processed_chars > 0 and processed_chars < len(buffer):
                        buffer = buffer[processed_chars:]
                    elif lines_to_process == len(lines):
                        buffer = ""
                else:
                    # No SSE format, try concatenated JSON
                    objects = extract_complete_json_objects(buffer)
                    last_end_idx = 0

                    for obj_str in objects:
                        obj = self._parse_stream_event(obj_str)
                        if obj:
                            yield self._hydrate_terminal_event(obj)
                            last_end_idx += len(obj_str)

                    # Keep unprocessed data in buffer
                    buffer = buffer[last_end_idx:]

        # Process any remaining data in buffer after stream completes
        if buffer.strip():
            lines = buffer.split("data:")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                obj = self._parse_stream_event(line)
                if obj:
                    yield self._hydrate_terminal_event(obj)
                else:
                    objects = extract_complete_json_objects(line)
                    for obj_str in objects:
                        obj = self._parse_stream_event(obj_str)
                        if obj:
                            yield self._hydrate_terminal_event(obj)

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
