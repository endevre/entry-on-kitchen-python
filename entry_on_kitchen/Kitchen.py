"""
Kitchen Client Library for Entry on Kitchen API.

Provides a simple interface for executing recipes synchronously and
receiving real-time streaming updates.
"""

import json
from typing import Any, Callable, Dict, Iterator, List, Literal, Optional

import requests

from .auth import Authorization
from .tools import (
    create_tool_error,
    create_tool_result,
    get_tool_call_request,
    with_tool_results,
    with_tools,
)


ThinkingLevel = Literal["off", "low", "medium", "high", "xhigh", "max"]
_THINKING_LEVELS = frozenset(("off", "low", "medium", "high", "xhigh", "max"))
_AUTHORIZATION_EXPIRED_MESSAGE = "Authorization expired or invalid"
_AUTHORIZATION_HEADER_NAMES = frozenset(("authorization", "x-entry-auth-code"))


class KitchenClient:
    """Client for interacting with the Entry on Kitchen API.

    Example:
        from entry_on_kitchen import BearerAuthorization, KitchenClient

        client = KitchenClient(
            authorization=BearerAuthorization(
                lambda force_refresh: get_current_token(force_refresh)
            ),
            entry_point="beta",
        )
        result = client.sync(
            recipe_id="abc123", entry_id="entry1", body={"key": "value"}
        )

        for event in client.stream(
            recipe_id="abc123", entry_id="entry1", body={"key": "value"}
        ):
            print(f"Event: {event['type']}")
    """

    def __init__(self, authorization: Authorization, entry_point: str = "entry"):
        """Initialize the KitchenClient.

        Args:
            authorization: An :class:`EntryCodeAuthorization` or
                :class:`BearerAuthorization` capability.  The client stores
                this capability, never a bearer token returned by it.
            entry_point: Entry point environment (default: ``"entry"`` for
                production). Use ``"beta"`` for the beta environment.

        Raises:
            ValueError: If authorization is not provided.
            TypeError: If authorization is not an authorization capability.
        """
        if authorization is None:
            raise ValueError("authorization is required")
        if not isinstance(authorization, Authorization):
            raise TypeError("authorization must be an Authorization capability")

        self.authorization = authorization
        self.entry_point = entry_point

    def _get_headers(
        self,
        custom_headers: Optional[Dict[str, str]] = None,
        force_refresh: bool = False,
    ) -> Dict[str, str]:
        """Build one request's headers and acquire auth immediately before it."""
        request_headers = {"Content-Type": "application/json"}
        if custom_headers:
            request_headers.update(custom_headers)

        # Auth headers are client-owned. Remove case variants supplied by a
        # caller before putting the capability's current value in place.
        for key in list(request_headers):
            if str(key).lower() in _AUTHORIZATION_HEADER_NAMES:
                del request_headers[key]
        request_headers.update(self.authorization.get_headers(force_refresh=force_refresh))
        return request_headers

    def _get_base_url(self) -> str:
        """Get the base URL for API requests."""
        entry_point_prefix = f"{self.entry_point}." if self.entry_point else ""
        return f"https://{entry_point_prefix}entry.on.kitchen"

    def _prepare_body(
        self,
        body: Any,
        use_kitchen_billing: bool = False,
        llm_override: str = None,
        api_key_override: Dict[str, Dict[str, str]] = None,
        thinking_override: ThinkingLevel = None,
    ) -> str:
        """Prepare a request body and apply optional Kitchen overrides."""
        body_obj = json.loads(body) if isinstance(body, str) else json.loads(json.dumps(body))

        if use_kitchen_billing:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_BILLING_OVERRIDE": True}
            else:
                body_obj = {"KITCHEN_BILLING_OVERRIDE": True}

        if llm_override:
            existing_model_overrides = {}
            if isinstance(body_obj, dict) and isinstance(
                body_obj.get("KITCHEN_MODELS_OVERRIDE"), dict
            ):
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

        if thinking_override is not None and str(thinking_override).strip() != "":
            normalized_thinking = str(thinking_override).strip().lower()
            if normalized_thinking not in _THINKING_LEVELS:
                raise ValueError(
                    "Invalid thinking_override. Expected one of: "
                    + ", ".join(("off", "low", "medium", "high", "xhigh", "max"))
                )
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_THINKING_OVERRIDE": normalized_thinking}
            else:
                body_obj = {"KITCHEN_THINKING_OVERRIDE": normalized_thinking}

        if api_key_override and isinstance(api_key_override, dict) and len(api_key_override) > 0:
            if isinstance(body_obj, dict):
                body_obj = {**body_obj, "KITCHEN_APIKEYS_OVERRIDE": api_key_override}
            else:
                body_obj = {"KITCHEN_APIKEYS_OVERRIDE": api_key_override}

        return json.dumps(body_obj)

    @staticmethod
    def _parse_stream_event(value: Any) -> Optional[Dict[str, Any]]:
        """Parse a stream event, including twice-JSON-encoded payloads."""
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _is_final_payload_ref(value: Any) -> bool:
        return isinstance(value, dict) and (
            ("bucket" in value and "key" in value) or "url" in value
        )

    @staticmethod
    def _payload_has_run_id(value: Any) -> bool:
        if isinstance(value, str):
            value = KitchenClient._parse_stream_event(value)
        if not isinstance(value, dict):
            return False
        if value.get("runId") or value.get("run_id"):
            return True
        for key in ("data", "body", "response", "error"):
            nested = value.get(key)
            if isinstance(nested, (dict, str)) and KitchenClient._payload_has_run_id(nested):
                return True
        return False

    @staticmethod
    def _is_authorization_expired_payload(value: Any) -> bool:
        """Match only the Runner's explicit expired/invalid authorization payload."""
        if isinstance(value, str):
            if value == _AUTHORIZATION_EXPIRED_MESSAGE:
                return True
            parsed = KitchenClient._parse_stream_event(value)
            if parsed is None:
                return False
            value = parsed
        if not isinstance(value, dict):
            return False

        for key in ("error", "message", "error_message", "error_description"):
            if value.get(key) == _AUTHORIZATION_EXPIRED_MESSAGE:
                return True
        for key in ("data", "body", "response", "error"):
            nested = value.get(key)
            if isinstance(nested, (dict, str)) and KitchenClient._is_authorization_expired_payload(
                nested
            ):
                return True
        return False

    def _response_json(self, response: Any) -> Any:
        try:
            return response.json()
        except Exception:
            return None

    def _should_retry_authorization_response(self, response: Any) -> bool:
        if not self.authorization.can_refresh:
            return False
        status_code = getattr(response, "status_code", None)
        if status_code == 401:
            payload = self._response_json(response)
            return not self._payload_has_run_id(payload)
        # Never call response.json() on a successful streaming response: doing
        # so would consume the live body before the event parser sees it.
        if status_code == 200:
            return False

        payload = self._response_json(response)
        return self._is_authorization_expired_payload(payload) and not self._payload_has_run_id(
            payload
        )

    def _should_retry_authorization_event(self, event: Dict[str, Any], response_status: int) -> bool:
        if not self.authorization.can_refresh:
            return False
        if self._payload_has_run_id(event):
            return False

        status_code = event.get("statusCode", response_status)
        if status_code not in (400, 401):
            return False
        return self._is_authorization_expired_payload(event) or self._is_authorization_expired_payload(
            event.get("data")
        )

    @staticmethod
    def _close_response(response: Any) -> None:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    def _post(
        self,
        url: str,
        body: str,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
        force_refresh: bool = False,
        retry_auth: bool = True,
    ) -> Any:
        """POST with one bounded bearer-auth recovery attempt.

        All arguments after ``url`` are named deliberately.  This keeps the
        Python transport from reintroducing the duplicate positional-URL bug
        that previously made ``requests.post(url, url, data=...)`` invalid.
        """
        # A stream-level recovery already consumed the one allowed replay;
        # the forced request must not open a second retry budget of its own.
        max_attempts = 1 if force_refresh or not retry_auth else 2
        for attempt in range(max_attempts):
            request_kwargs = {
                "data": body,
                "headers": self._get_headers(
                    headers, force_refresh=force_refresh or attempt == 1
                ),
            }
            if stream:
                request_kwargs["stream"] = True

            response = requests.post(url, **request_kwargs)
            if (
                retry_auth
                and not force_refresh
                and attempt == 0
                and self._should_retry_authorization_response(response)
            ):
                self._close_response(response)
                continue
            return response

        # The loop always returns; keep a defensive error for type checkers.
        raise RuntimeError("unreachable authorization retry state")

    def _fetch_final_payload(self, ref: Dict[str, Any]) -> Dict[str, Any]:
        url = ref.get("url")
        if not url:
            raise ValueError("Final payload reference does not include a URL")

        # Signed final-payload URLs carry their own authorization and must not
        # receive Kitchen credentials.
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
        has_inline_payload = "result" in data or has_inline_error or "exitBlock" in data
        ref = data.get("finalPayloadRef")
        if has_inline_payload or not self._is_final_payload_ref(ref):
            return event

        return {**event, "data": self._fetch_final_payload(ref)}

    def sync(
        self,
        recipe_id: str,
        entry_id: str,
        body: Any,
        use_kitchen_billing: bool = False,
        llm_override: str = None,
        api_key_override: Dict[str, Dict[str, str]] = None,
        headers: Dict[str, str] = None,
        thinking_override: ThinkingLevel = None,
    ) -> Dict[str, Any]:
        """Execute a recipe synchronously."""
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(
            body,
            use_kitchen_billing,
            llm_override,
            api_key_override,
            thinking_override,
        )
        url = f"{base_url}/{recipe_id}/{entry_id}/sync"
        response = self._post(url, stringified_body, headers=headers)

        try:
            result = response.json()
            if response.status_code != 200:
                if isinstance(result, dict):
                    result = dict(result)
                    result["_statusCode"] = response.status_code
                    return result
                return {"result": result, "_statusCode": response.status_code}
            return result
        except Exception:
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
        thinking_override: ThinkingLevel = None,
    ) -> Dict[str, Any]:
        """Execute a recipe and automatically satisfy external LLM tool calls."""
        current_body = with_tools(body, tools)
        last_response = None

        for _ in range(max_tool_iterations):
            # sync() acquires the current authorization immediately before each
            # iteration, including every continuation request.
            response = self.sync(
                recipe_id=recipe_id,
                entry_id=entry_id,
                body=current_body,
                use_kitchen_billing=use_kitchen_billing,
                llm_override=llm_override,
                api_key_override=api_key_override,
                headers=headers,
                thinking_override=thinking_override,
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
                            tool_call_id=tool_call.get("id"), name=name, output=output
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

    @staticmethod
    def _extract_complete_json_objects(input_str: str) -> List[str]:
        """Extract complete JSON objects from concatenated stream text."""
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
                        objects.append(input_str[start_idx : i + 1])
                        start_idx = -1
        return objects

    def _iter_response_events(self, response: Any) -> Iterator[Dict[str, Any]]:
        """Parse SSE and concatenated JSON response chunks into events."""
        buffer = ""

        for chunk in response.iter_content():
            if not chunk:
                continue
            buffer += chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

            if "data:" in buffer:
                lines = buffer.split("data:")
                last_line = lines[-1].strip()
                all_but_last_complete = not last_line or last_line.endswith("}") or last_line.endswith("]")
                lines_to_process = len(lines) if all_but_last_complete else len(lines) - 1
                processed_chars = 0

                for i in range(lines_to_process):
                    line = lines[i].strip()
                    if line:
                        obj = self._parse_stream_event(line)
                        if obj:
                            yield obj
                        else:
                            for obj_str in self._extract_complete_json_objects(line):
                                obj = self._parse_stream_event(obj_str)
                                if obj:
                                    yield obj
                        processed_chars += len(line) + 5
                    else:
                        processed_chars += 5

                if processed_chars > 0 and processed_chars < len(buffer):
                    buffer = buffer[processed_chars:]
                elif lines_to_process == len(lines):
                    buffer = ""
            else:
                objects = self._extract_complete_json_objects(buffer)
                last_end_idx = 0
                for obj_str in objects:
                    obj = self._parse_stream_event(obj_str)
                    if obj:
                        yield obj
                        last_end_idx += len(obj_str)
                buffer = buffer[last_end_idx:]

        if buffer.strip():
            lines = buffer.split("data:")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                obj = self._parse_stream_event(line)
                if obj:
                    yield obj
                else:
                    for obj_str in self._extract_complete_json_objects(line):
                        obj = self._parse_stream_event(obj_str)
                        if obj:
                            yield obj

    def stream(
        self,
        recipe_id: str,
        entry_id: str,
        body: Any,
        use_kitchen_billing: bool = False,
        llm_override: str = None,
        api_key_override: Dict[str, Dict[str, str]] = None,
        headers: Dict[str, str] = None,
        thinking_override: ThinkingLevel = None,
    ) -> Iterator[Dict[str, Any]]:
        """Execute a recipe with streaming responses."""
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(
            body,
            use_kitchen_billing,
            llm_override,
            api_key_override,
            thinking_override,
        )
        url = f"{base_url}/{recipe_id}/{entry_id}/stream"

        for attempt in range(2):
            response = self._post(
                url,
                stringified_body,
                headers=headers,
                stream=True,
                force_refresh=attempt == 1,
                retry_auth=False,
            )
            retry_before_event = False
            yielded_event = False
            try:
                if attempt == 0 and self._should_retry_authorization_response(response):
                    retry_before_event = True
                else:
                    response.raise_for_status()
                if retry_before_event:
                    continue
                for event in self._iter_response_events(response):
                    if (
                        attempt == 0
                        and not yielded_event
                        and self._should_retry_authorization_event(
                            event, getattr(response, "status_code", 200)
                        )
                    ):
                        retry_before_event = True
                        break

                    yielded_event = True
                    yield self._hydrate_terminal_event(event)
            finally:
                self._close_response(response)

            if retry_before_event:
                continue
            return

    def stream_raw(
        self,
        recipe_id: str,
        entry_id: str,
        body: Any,
        thinking_override: ThinkingLevel = None,
    ) -> Iterator[str]:
        """Execute a recipe with streaming responses, yielding raw JSON strings."""
        base_url = self._get_base_url()
        stringified_body = self._prepare_body(body, thinking_override=thinking_override)
        url = f"{base_url}/{recipe_id}/{entry_id}/stream"

        for attempt in range(2):
            response = self._post(
                url,
                stringified_body,
                stream=True,
                force_refresh=attempt == 1,
                retry_auth=False,
            )
            retry_before_event = False
            yielded_event = False
            try:
                if attempt == 0 and self._should_retry_authorization_response(response):
                    retry_before_event = True
                else:
                    response.raise_for_status()
                if retry_before_event:
                    continue
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    line = line.strip()
                    if line.startswith("data: "):
                        line = line[6:]
                    if not line:
                        continue

                    parsed = self._parse_stream_event(line)
                    if (
                        attempt == 0
                        and not yielded_event
                        and parsed is not None
                        and self._should_retry_authorization_event(
                            parsed, getattr(response, "status_code", 200)
                        )
                    ):
                        retry_before_event = True
                        break

                    yielded_event = True
                    yield line
            finally:
                self._close_response(response)

            if retry_before_event:
                continue
            return

    @staticmethod
    def apply_delta(original: str, delta: List[List[Any]]) -> str:
        """Apply delta operations to a string."""
        result = list(original)
        offset = 0

        for operation in delta:
            op_type = operation[0]
            if op_type == "d":
                position = operation[1] + offset
                length = operation[2] if len(operation) > 2 else 1
                del result[position : position + length]
                offset -= length
            elif op_type == "i":
                position = operation[1] + offset
                text = operation[2]
                if isinstance(text, str) and text.startswith('"'):
                    try:
                        text = json.loads(text)
                    except Exception:
                        pass
                result[position:position] = list(str(text))
                offset += len(str(text))

        return "".join(result)
