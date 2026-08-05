"""Fixed value transformer implementation."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class FixedTransformResult:
    """Result of a fixed transformation."""

    success: bool
    value: Optional[str]
    error: Optional[str] = None


class FixedTransformer:
    """Transformer that replaces a tag with a fixed constant value.

    This is the simplest transformer - it just returns the configured
    value for every item, regardless of the item's current state.
    """

    def __init__(self, value: str):
        """Initialize the fixed transformer.

        Args:
            value: The fixed value to use. Empty string means clear the tag.
        """
        self.value = value

    def transform(self, item: Dict[str, Any]) -> FixedTransformResult:
        """Transform an item by returning the fixed value.

        Args:
            item: The import item data (not used for fixed transform).

        Returns:
            FixedTransformResult with the fixed value.
        """
        return FixedTransformResult(
            success=True,
            value=self.value,
        )
