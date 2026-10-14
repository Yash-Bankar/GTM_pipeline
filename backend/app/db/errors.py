"""Storage-layer error types (database-backed)."""

from __future__ import annotations


class StorageError(RuntimeError):
    """Base class for storage-layer errors."""


class DuplicateLeadError(StorageError):
    """A lead with the same normalized username already exists."""


class LeadNotFoundError(StorageError):
    """The requested lead does not exist."""
