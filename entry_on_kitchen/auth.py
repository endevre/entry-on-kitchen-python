"""Authorization capabilities for the Entry on Kitchen client.

The client deliberately stores an authorization capability rather than a
bearer token.  A bearer capability asks its caller for the current token for
each request and can be asked to force a refresh when the server rejects the
previous value.
"""

from typing import Callable, Dict


class AuthorizationError(RuntimeError):
    """Raised when an authorization capability cannot produce credentials."""


class Authorization:
    """Base class for Kitchen authorization capabilities."""

    can_refresh = False

    def get_headers(self, force_refresh: bool = False) -> Dict[str, str]:
        """Return request headers for one HTTP attempt."""
        raise NotImplementedError


class EntryCodeAuthorization(Authorization):
    """Authenticate with a static ``X-Entry-Auth-Code`` value."""

    can_refresh = False

    def __init__(self, code: str):
        if not isinstance(code, str) or not code.strip():
            raise ValueError("entry code is required")
        self.code = code

    def get_headers(self, force_refresh: bool = False) -> Dict[str, str]:
        # ``force_refresh`` is intentionally ignored: entry codes do not have
        # a refresh mechanism and are never replayed by KitchenClient.
        return {"X-Entry-Auth-Code": self.code}


class BearerAuthorization(Authorization):
    """Authenticate with a caller-owned synchronous bearer-token provider.

    ``get_token`` is called immediately before every authenticated request and
    receives ``True`` only when the client is retrying an authorization
    failure.  The callback's return value is used as the raw ``Authorization``
    header value; callers that need a ``Bearer `` prefix should return it.
    """

    can_refresh = True

    def __init__(self, get_token: Callable[[bool], str]):
        if not callable(get_token):
            raise ValueError("get_token callback is required")
        self._get_token = get_token

    def get_headers(self, force_refresh: bool = False) -> Dict[str, str]:
        try:
            token = self._get_token(bool(force_refresh))
        except AuthorizationError:
            raise
        except Exception:
            # Do not leak a provider exception (which may contain a token) in
            # the public client error.  The provider remains the owner of
            # refresh diagnostics.
            raise AuthorizationError("Bearer authorization provider failed") from None

        if not isinstance(token, str) or not token.strip():
            raise AuthorizationError("Bearer authorization provider returned no token")

        # Preserve raw Authorization semantics.  Do not add or remove a
        # scheme here; the provider decides whether the value is ``Bearer …``
        # or another accepted raw authorization value.
        return {"Authorization": token}


__all__ = [
    "Authorization",
    "AuthorizationError",
    "BearerAuthorization",
    "EntryCodeAuthorization",
]
