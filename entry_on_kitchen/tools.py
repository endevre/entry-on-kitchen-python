import json
import re
from typing import Any, Callable, Dict, List, Optional


JSONSchema = Dict[str, Any]
KitchenTool = Dict[str, Any]
LLMToolCall = Dict[str, Any]
LLMToolResult = Dict[str, Any]
LLMContinuation = Dict[str, Any]
ToolHandler = Callable[[Dict[str, Any], LLMToolCall], Any]


def _sanitize_tool_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", str(name or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "tool"
    if not re.match(r"^[a-zA-Z_]", cleaned):
        cleaned = f"tool_{cleaned}"
    return cleaned[:64]


def _normalize_input_schema(input_schema: Optional[JSONSchema] = None) -> JSONSchema:
    schema = dict(input_schema or {})
    if "type" not in schema:
        schema["type"] = "object"
    if str(schema.get("type", "")).lower() == "object" and "properties" not in schema:
        schema["properties"] = {}
    return schema


def _body_to_object(body: Any) -> Dict[str, Any]:
    if isinstance(body, str):
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {"input": parsed}
    return dict(body) if isinstance(body, dict) else {"input": body}


def create_external_tool(
    name: str,
    description: str,
    input_schema: Optional[JSONSchema] = None,
) -> KitchenTool:
    return {
        "type": "KitchenTool",
        "version": 1,
        "name": _sanitize_tool_name(name),
        "description": description or "",
        "input_schema": _normalize_input_schema(input_schema),
        "executor": {"type": "external"},
    }


def create_kitchen_entry_tool(
    name: str,
    description: str,
    pipeline_id: str,
    entry_block_id: str,
    input_schema: Optional[JSONSchema] = None,
    output_mode: str = "full_exit",
    selected_output: Optional[str] = None,
) -> KitchenTool:
    executor = {
        "type": "entry",
        "pipelineId": pipeline_id,
        "entryBlockId": entry_block_id,
        "output_mode": output_mode or "full_exit",
    }
    if selected_output:
        executor["selected_output"] = selected_output
    return {
        "type": "KitchenTool",
        "version": 1,
        "name": _sanitize_tool_name(name),
        "description": description or "",
        "input_schema": _normalize_input_schema(input_schema),
        "executor": executor,
    }


def create_tool_result(tool_call_id: str, name: str, output: Any) -> LLMToolResult:
    return {
        "type": "LLMToolResult",
        "version": 1,
        "tool_call_id": tool_call_id,
        "name": _sanitize_tool_name(name),
        "status": "success",
        "output": output,
    }


def create_tool_error(
    tool_call_id: str,
    name: str,
    message: str,
    code: Optional[str] = None,
    details: Any = None,
) -> LLMToolResult:
    error = {"message": message}
    if code:
        error["code"] = code
    if details is not None:
        error["details"] = details
    return {
        "type": "LLMToolResult",
        "version": 1,
        "tool_call_id": tool_call_id,
        "name": _sanitize_tool_name(name),
        "status": "error",
        "error": error,
    }


def with_tools(body: Any, tools: List[KitchenTool]) -> Dict[str, Any]:
    body_obj = _body_to_object(body)
    body_obj["tools"] = tools
    return body_obj


def with_tool_results(
    body: Any,
    tool_results: List[LLMToolResult],
    continuation: LLMContinuation,
) -> Dict[str, Any]:
    body_obj = _body_to_object(body)
    body_obj["tool_results"] = tool_results
    body_obj["continuation"] = continuation
    return body_obj


def _parse_maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if not value.strip():
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def get_tool_call_request(value: Any) -> Optional[Dict[str, Any]]:
    parsed = _parse_maybe_json(value)
    candidate = _parse_maybe_json(parsed.get("result")) if isinstance(parsed, dict) and "result" in parsed else parsed
    if (
        isinstance(candidate, dict)
        and candidate.get("status") == "requires_tool_outputs"
        and isinstance(candidate.get("tool_calls"), list)
        and isinstance(candidate.get("continuation"), dict)
    ):
        return candidate
    return None


def is_tool_call_request(value: Any) -> bool:
    return get_tool_call_request(value) is not None


def get_tool_calls(value: Any) -> List[LLMToolCall]:
    request = get_tool_call_request(value)
    return request.get("tool_calls", []) if request else []


def get_continuation(value: Any) -> Optional[LLMContinuation]:
    request = get_tool_call_request(value)
    return request.get("continuation") if request else None
