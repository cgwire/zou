"""
Pydantic schemas for request body validation in the previews blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class PreviewFileUploadSchema(BaseSchema):
    """
    Body for setting a preview as main preview.
    """

    frame_number: Optional[int] = None


class PreviewFilePositionSchema(BaseSchema):
    """
    Body for updating preview file position.
    """

    position: int = Field(0, ge=0)


class ExtractAnnotatedFrameSchema(BaseSchema):
    """
    Query args for extracting an annotated frame from a preview.
    Required for movies (identifies the frame); ignored for pictures
    where the first annotation entry is used.
    """

    frame_number: Optional[int] = Field(None, ge=1)
