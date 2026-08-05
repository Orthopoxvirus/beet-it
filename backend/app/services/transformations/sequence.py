"""Sequence transformer implementation for auto-numbering tracks."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SequenceTransformResult:
    """Result of a sequence transformation."""

    success: bool
    value: Optional[str]
    error: Optional[str] = None


class SequenceTransformer:
    """Transformer that auto-numbers tracks sequentially.

    This transformer assigns sequential numbers to tracks, optionally
    restarting the sequence for each directory when per_directory is enabled.

    The transformer must be initialized with the full list of items to
    properly compute the sequence, especially when per_directory grouping
    is used.
    """

    def __init__(
        self,
        items: List[Dict[str, Any]],
        start: int = 1,
        per_directory: bool = False,
    ):
        """Initialize the sequence transformer.

        Args:
            items: List of all items that will be transformed.
            start: Starting number for the sequence.
            per_directory: If True, restart numbering for each directory.
        """
        self.start = start
        self.per_directory = per_directory
        self._sequence_map: Dict[int, int] = {}

        # Pre-compute sequences for all items
        self._compute_sequences(items)

    def _compute_sequences(self, items: List[Dict[str, Any]]):
        """Pre-compute sequence numbers for all items.

        Args:
            items: List of items to compute sequences for.
        """
        if self.per_directory:
            # Group items by directory
            directory_items: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for item in items:
                directory = item.get("directory", "")
                directory_items[directory].append(item)

            # Assign sequence numbers within each directory
            for directory, dir_items in directory_items.items():
                # Sort items by filename within each directory for consistent ordering
                sorted_items = sorted(
                    dir_items,
                    key=lambda x: (x.get("filename", "") or "").lower(),
                )
                for i, item in enumerate(sorted_items):
                    item_id = item.get("id")
                    if item_id is not None:
                        self._sequence_map[item_id] = self.start + i
        else:
            # Simple sequential numbering across all items
            # Sort by directory first, then filename for consistent ordering
            sorted_items = sorted(
                items,
                key=lambda x: (
                    (x.get("directory", "") or "").lower(),
                    (x.get("filename", "") or "").lower(),
                ),
            )
            for i, item in enumerate(sorted_items):
                item_id = item.get("id")
                if item_id is not None:
                    self._sequence_map[item_id] = self.start + i

    def transform(self, item: Dict[str, Any]) -> SequenceTransformResult:
        """Transform an item by returning its sequence number.

        Args:
            item: The import item data.

        Returns:
            SequenceTransformResult with the sequence number as a string.
        """
        item_id = item.get("id")
        if item_id is None:
            return SequenceTransformResult(
                success=False,
                value=None,
                error="Item has no ID",
            )

        sequence_num = self._sequence_map.get(item_id)
        if sequence_num is None:
            return SequenceTransformResult(
                success=False,
                value=None,
                error="Item not found in sequence map",
            )

        return SequenceTransformResult(
            success=True,
            value=str(sequence_num),
        )

    def get_sequence_number(self, item_id: int) -> Optional[int]:
        """Get the pre-computed sequence number for an item.

        Args:
            item_id: The item's ID.

        Returns:
            The sequence number, or None if not found.
        """
        return self._sequence_map.get(item_id)
