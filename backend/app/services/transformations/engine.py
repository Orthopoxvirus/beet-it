"""Transformation engine for applying rules to import items."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .models import (
    TransformationRule,
    FixedRule,
    RegexRule,
    SequenceRule,
    ExplicitRule,
    TagName,
    SourceField,
)
from .fixed import FixedTransformer
from .regex import RegexTransformer, RegexPatternError, validate_regex_pattern
from .sequence import SequenceTransformer
from .explicit import ExplicitTransformer

logger = logging.getLogger(__name__)


@dataclass
class TransformWarning:
    """Warning for a tag that couldn't be fully transformed."""

    tag: str
    code: str
    message: str


@dataclass
class ItemTransformResult:
    """Result of transforming a single item."""

    item_id: int
    changes: Dict[str, str] = field(default_factory=dict)
    warnings: List[TransformWarning] = field(default_factory=list)


@dataclass
class TransformError:
    """Error for an item that couldn't be transformed."""

    item_id: int
    code: str
    message: str


@dataclass
class TransformationResult:
    """Result of applying transformations to a batch of items."""

    previews: List[ItemTransformResult]
    errors: List[TransformError]


class TransformationEngine:
    """Engine for applying transformation rules to import items.

    The engine takes a list of rules and applies them to items,
    producing preview results that show what changes would be made.
    """

    def __init__(self, rules: List[TransformationRule]):
        """Initialize the transformation engine.

        Args:
            rules: List of transformation rules to apply.

        Raises:
            RegexPatternError: If any regex rule has an invalid pattern.
        """
        self.rules = rules
        self._validate_rules()

    def _validate_rules(self):
        """Validate all rules.

        Raises:
            RegexPatternError: If any regex rule has an invalid pattern.
        """
        for rule in self.rules:
            if isinstance(rule, RegexRule):
                is_valid, error = validate_regex_pattern(rule.pattern)
                if not is_valid:
                    raise RegexPatternError(f"Invalid regex pattern: {error}")

    def compute_previews(
        self,
        items: List[Dict[str, Any]],
    ) -> TransformationResult:
        """Compute preview transformations for a list of items.

        This method applies all rules to all items and returns the
        computed changes without actually modifying anything.

        Args:
            items: List of import items with their current tag values.
                   Each item should have keys: id, filename, directory,
                   album, album_artist, artist, title, genre, track_number, etc.

        Returns:
            TransformationResult with previews and errors.
        """
        previews: List[ItemTransformResult] = []
        errors: List[TransformError] = []

        # Create transformers for each rule
        transformers = self._create_transformers(items)

        for item in items:
            item_id = item.get("id")
            if item_id is None:
                errors.append(
                    TransformError(
                        item_id=-1,
                        code="MISSING_ID",
                        message="Item has no ID field",
                    )
                )
                continue

            result = self._transform_item(item, transformers)
            previews.append(result)

        return TransformationResult(
            previews=previews,
            errors=errors,
        )

    def _create_transformers(
        self,
        items: List[Dict[str, Any]],
    ) -> List[tuple[TransformationRule, Any]]:
        """Create transformer instances for each rule.

        Args:
            items: List of items (needed for sequence transformer).

        Returns:
            List of (rule, transformer) tuples.
        """
        transformers = []

        for rule in self.rules:
            if isinstance(rule, FixedRule):
                transformer = FixedTransformer(rule.value)
            elif isinstance(rule, RegexRule):
                transformer = RegexTransformer(
                    source_field=rule.source_field.value,
                    pattern=rule.pattern,
                    replacement=rule.replacement,
                )
            elif isinstance(rule, SequenceRule):
                # Filter to only file items for sequence numbering
                file_items = [
                    item
                    for item in items
                    if item.get("item_type") == "file" or item.get("item_type") is None
                ]
                transformer = SequenceTransformer(
                    items=file_items,
                    start=rule.start,
                    per_directory=rule.per_directory,
                )
            elif isinstance(rule, ExplicitRule):
                transformer = ExplicitTransformer(values=rule.values)
            else:
                logger.warning(f"Unknown rule type: {type(rule)}")
                continue

            transformers.append((rule, transformer))

        return transformers

    def _transform_item(
        self,
        item: Dict[str, Any],
        transformers: List[tuple[TransformationRule, Any]],
    ) -> ItemTransformResult:
        """Apply all transformers to a single item.

        Args:
            item: The import item data.
            transformers: List of (rule, transformer) tuples.

        Returns:
            ItemTransformResult with changes and warnings.
        """
        item_id = item.get("id")
        changes: Dict[str, str] = {}
        warnings: List[TransformWarning] = []

        for rule, transformer in transformers:
            tag_name = rule.tag.value if isinstance(rule.tag, TagName) else rule.tag

            # Apply the transformation
            if isinstance(transformer, (FixedTransformer, ExplicitTransformer)):
                result = transformer.transform(item)
                if result.success and result.value is not None:
                    # Only include change if value differs from current
                    current_value = item.get(tag_name)
                    if current_value is None:
                        current_value = ""
                    else:
                        current_value = str(current_value)

                    if result.value != current_value:
                        changes[tag_name] = result.value

            elif isinstance(transformer, RegexTransformer):
                result = transformer.transform(item)
                if result.success:
                    if result.value is not None:
                        # Only include change if value differs from current
                        current_value = item.get(tag_name)
                        if current_value is None:
                            current_value = ""
                        else:
                            current_value = str(current_value)

                        if result.value != current_value:
                            changes[tag_name] = result.value
                    elif result.warning_code:
                        warnings.append(
                            TransformWarning(
                                tag=tag_name,
                                code=result.warning_code,
                                message=result.warning or "",
                            )
                        )
                else:
                    warnings.append(
                        TransformWarning(
                            tag=tag_name,
                            code="TRANSFORM_ERROR",
                            message=result.error or "Unknown error",
                        )
                    )

            elif isinstance(transformer, SequenceTransformer):
                result = transformer.transform(item)
                if result.success and result.value is not None:
                    # Only include change if value differs from current
                    current_value = item.get(tag_name)
                    if current_value is None:
                        current_value = ""
                    else:
                        current_value = str(current_value)

                    if result.value != current_value:
                        changes[tag_name] = result.value
                elif not result.success:
                    warnings.append(
                        TransformWarning(
                            tag=tag_name,
                            code="SEQUENCE_ERROR",
                            message=result.error or "Unknown error",
                        )
                    )

        return ItemTransformResult(
            item_id=item_id,
            changes=changes,
            warnings=warnings,
        )
