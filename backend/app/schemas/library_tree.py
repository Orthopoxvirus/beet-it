"""Pydantic schemas for the library folder tree.

The library tree is derived from the beets SQLite DB (`items.path` + `album_id`)
and reflects the on-disk folder structure of a library's organised music. It's
used by the batch-edit UI to let users select a folder and load every album
below it in one action.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


def _to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class LibraryFolderNode(BaseModel):
    """A folder in the library's on-disk layout."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    name: str = Field(..., description="Folder basename (e.g. 'Abbey Road')")
    path: str = Field(
        ...,
        description="Path relative to the library root; empty string for the root node",
    )
    is_album: bool = Field(
        ...,
        description="True if this folder contains at least one track directly (not only subfolders)",
    )
    album_ids: List[int] = Field(
        default_factory=list,
        description=(
            "Union of distinct beets album_ids in this folder and all its "
            "descendants. Selecting this node for batch edit loads exactly "
            "these albums."
        ),
    )
    children: List["LibraryFolderNode"] = Field(
        default_factory=list, description="Child folder nodes, sorted alphabetically"
    )


LibraryFolderNode.model_rebuild()


class LibraryTreeResponse(BaseModel):
    """Response for GET /libraries/{slug}/library-tree."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    library_path: Optional[str] = Field(
        None, description="Absolute container path of the library root"
    )
    root: LibraryFolderNode = Field(..., description="Root of the folder tree")
