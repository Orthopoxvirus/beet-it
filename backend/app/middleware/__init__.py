"""Middleware package for the Beets Web Manager."""

from .auth import BasicAuthMiddleware

__all__ = ["BasicAuthMiddleware"]
