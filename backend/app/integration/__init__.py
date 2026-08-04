"""Integration abstraction layer — a plug-in point for data extractors.

Extractors program against the stable contract in :mod:`.contract` and push records
through an :class:`~.contract.IngestSession`; the :class:`~.layer.AbstractionLayer`
runs them against a target schema and tracks status. See the README section
"Integration abstraction layer" for the guide.
"""

from __future__ import annotations

from .backends import InMemoryIngestBackend, SqlIngestBackend
from .contract import (
    ColumnType,
    ExtractResult,
    Extractor,
    ExtractorInfo,
    IngestError,
    IngestSession,
)
from .layer import AbstractionLayer, layer
from .status import LayerState, LayerStatus

__all__ = [
    "AbstractionLayer",
    "ColumnType",
    "ExtractResult",
    "Extractor",
    "ExtractorInfo",
    "IngestError",
    "IngestSession",
    "InMemoryIngestBackend",
    "LayerState",
    "LayerStatus",
    "SqlIngestBackend",
    "layer",
]
