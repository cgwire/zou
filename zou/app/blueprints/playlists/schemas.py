"""
Pydantic schemas for request body validation in the playlists blueprint.

Use these schemas with validate_request_body() to ensure incoming JSON bodies
match the expected format and to return clear validation errors (400 with
field-level messages).
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field, field_validator

from zou.app.utils.validation import BaseSchema


class AddEntityToPlaylistSchema(BaseSchema):
    """Body for adding an entity to a playlist."""

    entity_id: UUID = Field(..., description="Entity unique identifier to add")
    preview_file_id: Optional[UUID] = Field(
        None,
        description="Optional preview file identifier associated to the entity",
    )

    @field_validator("preview_file_id", mode="before")
    @classmethod
    def coerce_empty_to_none(cls, v):
        if v == "":
            return None
        return v


class TempPlaylistCreateSchema(BaseSchema):
    """Body for generating a temporary playlist from task IDs."""

    task_ids: List[UUID] = Field(
        ...,
        min_length=0,
        description="List of task unique identifiers",
    )


class NotifyClientsPlaylistSchema(BaseSchema):
    """Optional body for notifying clients that a playlist is ready."""

    studio_id: Optional[UUID] = Field(
        None,
        description="Studio unique identifier to notify",
    )
    department_id: Optional[UUID] = Field(
        None,
        description="Department unique identifier to notify",
    )

    @field_validator("studio_id", "department_id", mode="before")
    @classmethod
    def coerce_empty_to_none(cls, v):
        if v == "":
            return None
        return v
