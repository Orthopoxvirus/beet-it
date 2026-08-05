"""Pydantic schemas for import folder tree browsing."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


class ImportFolderNode(BaseModel):
    """Represents a folder in the import tree hierarchy."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel
    )

    name: str = Field(..., description="Folder name (e.g., 'Folge_26')")
    path: str = Field(..., description="Relative path from import root")
    is_album: bool = Field(
        ..., description="True if this is a leaf/album folder or multi-disc parent"
    )
    is_multi_disc_parent: bool = Field(
        ..., description="True if parent of multi-disc album set"
    )
    children: List["ImportFolderNode"] = Field(
        default_factory=list, description="Child folder nodes"
    )
    has_subfolders: bool = Field(
        ..., description="Hint for lazy loading optimization"
    )


# Required for self-referential model
ImportFolderNode.model_rebuild()


class ImportTreeResponse(BaseModel):
    """Response body for import folder tree."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

    import_path: Optional[str] = Field(
        ..., description="The library's import path (absolute), or null if not set"
    )
    children: List[ImportFolderNode] = Field(
        default_factory=list, description="Top-level folder nodes"
    )
