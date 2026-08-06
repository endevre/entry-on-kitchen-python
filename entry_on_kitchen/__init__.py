"""
Entry on Kitchen Python Library

A simple Python library for executing recipes on the Entry on Kitchen API.
Supports both synchronous execution and real-time streaming.
"""

from .Kitchen import KitchenClient, ThinkingLevel
from .auth import Authorization, AuthorizationError, BearerAuthorization, EntryCodeAuthorization
from .tools import (
    create_external_tool,
    create_kitchen_entry_tool,
    create_tool_error,
    create_tool_result,
    get_continuation,
    get_tool_call_request,
    get_tool_calls,
    is_tool_call_request,
    with_tool_results,
    with_tools,
)

__version__ = "0.4.0"
__all__ = [
    "Authorization",
    "AuthorizationError",
    "BearerAuthorization",
    "EntryCodeAuthorization",
    "KitchenClient",
    "ThinkingLevel",
    "create_external_tool",
    "create_kitchen_entry_tool",
    "create_tool_error",
    "create_tool_result",
    "get_continuation",
    "get_tool_call_request",
    "get_tool_calls",
    "is_tool_call_request",
    "with_tool_results",
    "with_tools",
]
