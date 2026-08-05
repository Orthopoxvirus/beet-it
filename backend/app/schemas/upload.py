"""Schemas for file upload endpoint."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class UploadedFile(BaseModel):
    """Details of a successfully uploaded file."""

    filename: str = Field(..., description="Original filename")
    path: str = Field(..., description="Relative path where file was saved")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")


class UploadResponse(BaseModel):
    """Response for successful file upload."""

    status: Literal["success"] = Field("success", description="Upload status")
    message: str = Field(..., description="Human-readable success message")
    files_uploaded: int = Field(..., ge=1, description="Number of files successfully uploaded")
    files: List[UploadedFile] = Field(..., description="Details of uploaded files")


class FileConflict(BaseModel):
    """Details of a conflicting file."""

    filename: str = Field(..., description="Original filename")
    path: str = Field(..., description="Relative path that conflicts")


class ConflictError(BaseModel):
    """Error response for file conflicts."""

    code: Literal["FILE_EXISTS"] = Field("FILE_EXISTS", description="Error code")
    message: str = Field(..., description="Human-readable error message")
    conflicts: List[FileConflict] = Field(..., description="List of conflicting files")


class ErrorDetail(BaseModel):
    """Generic error detail model."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    invalid_paths: Optional[List[str]] = Field(
        None, description="List of invalid paths (for path validation errors)"
    )
    conflicts: Optional[List[FileConflict]] = Field(
        None, description="List of conflicting files (for conflict errors)"
    )
