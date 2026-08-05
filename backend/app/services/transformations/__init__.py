"""Transformation engine module for batch tag editing.

This module provides the logic for applying transformation rules to
import items. It supports three transformation modes:

- Fixed: Replace a tag with a constant value
- Regex: Apply pattern matching with capture group substitution
- Sequence: Auto-number tracks with optional per-directory grouping

Usage:
    from app.services.transformations import (
        TransformationEngine,
        FixedRule,
        RegexRule,
        SequenceRule,
        TagName,
        SourceField,
    )

    rules = [
        FixedRule(tag=TagName.ALBUM, mode="fixed", value="Greatest Hits"),
        RegexRule(
            tag=TagName.TITLE,
            mode="regex",
            source_field=SourceField.FILENAME,
            pattern=r"^\\d+\\s*[-_]\\s*(.+)\\.mp3$",
            replacement="$1",
        ),
        SequenceRule(
            tag=TagName.TRACK_NUMBER,
            mode="sequence",
            start=1,
            per_directory=True,
        ),
    ]

    engine = TransformationEngine(rules)
    result = engine.compute_previews(items)
"""

from .models import (
    TransformationMode,
    TagName,
    SourceField,
    FixedRule,
    RegexRule,
    SequenceRule,
    ExplicitRule,
    TransformationRule,
)
from .fixed import FixedTransformer, FixedTransformResult
from .regex import (
    RegexTransformer,
    RegexTransformResult,
    RegexTimeoutError,
    RegexPatternError,
    validate_regex_pattern,
)
from .sequence import SequenceTransformer, SequenceTransformResult
from .source_path import relative_source_path
from .explicit import ExplicitTransformer, ExplicitTransformResult
from .engine import (
    TransformationEngine,
    TransformWarning,
    ItemTransformResult,
    TransformError,
    TransformationResult,
)

__all__ = [
    # Models
    "TransformationMode",
    "TagName",
    "SourceField",
    "FixedRule",
    "RegexRule",
    "SequenceRule",
    "ExplicitRule",
    "TransformationRule",
    # Fixed transformer
    "FixedTransformer",
    "FixedTransformResult",
    # Explicit transformer
    "ExplicitTransformer",
    "ExplicitTransformResult",
    # Regex transformer
    "RegexTransformer",
    "RegexTransformResult",
    "RegexTimeoutError",
    "RegexPatternError",
    "validate_regex_pattern",
    # Sequence transformer
    "SequenceTransformer",
    "SequenceTransformResult",
    # Source path helper
    "relative_source_path",
    # Engine
    "TransformationEngine",
    "TransformWarning",
    "ItemTransformResult",
    "TransformError",
    "TransformationResult",
]
