"""Stable exception types for read-only research-run access."""


class ResearchRunStoreError(RuntimeError):
    """Base error for read-only research-run access."""


class InvalidRunIdError(ResearchRunStoreError):
    """Raised when a run identifier is not safe."""


class ResearchRunNotFoundError(ResearchRunStoreError):
    """Raised when a requested run does not exist."""


class ResearchArtifactNotFoundError(ResearchRunStoreError):
    """Raised when a required artifact is missing."""


class ResearchArtifactDecodeError(ResearchRunStoreError):
    """Raised when an artifact cannot be decoded."""
