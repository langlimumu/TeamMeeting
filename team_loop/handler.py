from http.server import BaseHTTPRequestHandler

from .handlers import (
    AccountsHandlerMixin,
    CollaborationHandlerMixin,
    OperationsHandlerMixin,
    RequestHandlerMixin,
    SystemHandlerMixin,
)


class Handler(
    RequestHandlerMixin,
    AccountsHandlerMixin,
    CollaborationHandlerMixin,
    OperationsHandlerMixin,
    SystemHandlerMixin,
    BaseHTTPRequestHandler,
):
    """Composed HTTP handler; domain behavior lives in focused mixins."""

    pass
