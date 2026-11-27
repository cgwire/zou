"""
Pydantic schemas for request body validation in the previews blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class PreviewFileUploadSchema(BaseSchema):
    """
    Body to set a preview as the main preview.
    """

    frame_number: Optional[int] = None


class PreviewFilePositionSchema(BaseSchema):
    """
    Body to update the position of a preview file.
    """

    position: int = Field(0, ge=0)


class ExtractAnnotatedFrameSchema(BaseSchema):
    """
    Query arguments to extract an annotated frame from a preview. They are
    necessary for movies (they identify the frame). For pictures, the
    function ignores them and uses the first annotation entry.
    """

    frame_number: Optional[int] = Field(None, ge=1)


class AnnotationsUpdateSchema(BaseSchema):
    """
    Body to update the annotations of a preview file.
    """

    additions: list = Field(default_factory=list)
    updates: list = Field(default_factory=list)
    deletions: list = Field(default_factory=list)


class PreviewFileTrimSchema(BaseSchema):
    """
    Body to set the in/out handles of a preview file. Only the keys in the
    body change. A null value clears a handle.
    """

    handle_in: Optional[int] = Field(None, ge=0)
    handle_out: Optional[int] = Field(None, ge=0)
