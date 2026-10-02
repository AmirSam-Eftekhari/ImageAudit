"""Exception hierarchy. Every expected failure derives from ImageAuditError."""

from __future__ import annotations


class ImageAuditError(Exception):
    """Base class for expected, user-presentable errors."""


class ConfigError(ImageAuditError):
    """Invalid configuration file or override."""


class DatasetError(ImageAuditError):
    """The dataset is missing, unreadable, or in an unsupported layout."""


class SecurityError(ImageAuditError):
    """Untrusted input violated a safety rule (path traversal, unsafe archive, size limits)."""


class ScanCancelled(ImageAuditError):  # noqa: N818 - public name used across the codebase
    """The scan was cancelled by the caller."""
