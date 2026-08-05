"""Explicit per-item transformer for direct value assignment.

Unlike the rule-based transformers (fixed/regex/sequence), the explicit
transformer carries a pre-computed ``item_id -> value`` map. The caller
decides each item's new value — the UI drag-reorder feature uses this to
commit the exact track numbers (and, when "keep titles" is on, titles) it
already showed in the preview, with no server-side recomputation.

Items absent from the map emit no value, so a single explicit rule only
touches the items it was given.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ExplicitTransformResult:
    """Result of an explicit transformation."""

    success: bool
    value: Optional[str]
    error: Optional[str] = None


class ExplicitTransformer:
    """Transformer that assigns a per-item explicit value.

    The transformer is initialised with a map of beets item ID to the
    explicit value to set. Items not present in the map are left untouched
    (``value`` is ``None``, which the engine treats as "no change").
    """

    def __init__(self, values: Dict[int, str]):
        """Initialise the explicit transformer.

        Args:
            values: Map of item ID to the explicit value for the rule's tag.
        """
        self.values = values

    def transform(self, item: Dict[str, Any]) -> ExplicitTransformResult:
        """Return the explicit value mapped for this item, if any.

        Args:
            item: The library item data.

        Returns:
            ExplicitTransformResult — ``value`` is the mapped string, or
            ``None`` when the item is not part of this explicit mapping.
        """
        item_id = item.get("id")
        if item_id is None:
            return ExplicitTransformResult(
                success=False,
                value=None,
                error="Item has no ID",
            )

        if item_id not in self.values:
            return ExplicitTransformResult(success=True, value=None)

        return ExplicitTransformResult(
            success=True,
            value=self.values[item_id],
        )
