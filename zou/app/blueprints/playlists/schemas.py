"""
Pydantic schemas for request body validation in the playlists blueprint.

Use these schemas with validate_request_body() to ensure incoming JSON bodies
match the expected format and to return clear validation errors (400 with
field-level messages).
"""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _ensure_uuid(v, field_name: str):
    """Validate and coerce string to UUID for Pydantic."""
    if isinstance(v, UUID):
        return v
    if isinstance(v, str):
        from zou.app.utils.fields import is_valid_id
        if not is_valid_id(v):
            raise ValueError(f"{field_name} must be a valid UUID")
        return v
    return v


class AddEntityToPlaylistSchema(BaseModel):
    """Body for adding an entity to a playlist."""
    entity_id: UUID = Field(..., description="Entity unique identifier to add")
    preview_file_id: Optional[UUID] = Field(
        None,
        description="Optional preview file identifier associated to the entity",
    )

    @field_validator("entity_id", mode="before")
    @classmethod
    def validate_entity_id(cls, v):
        return _ensure_uuid(v, "entity_id")

    @field_validator("preview_file_id", mode="before")
    @classmethod
    def validate_preview_file_id(cls, v):
        if v is None or v == "":
            return None
        return _ensure_uuid(v, "preview_file_id")


class TempPlaylistCreateSchema(BaseModel):
    """Body for generating a temporary playlist from task IDs."""
    task_ids: List[UUID] = Field(
        ...,
        min_length=0,
        description="List of task unique identifiers",
    )

    @field_validator("task_ids", mode="before")
    @classmethod
    def validate_task_ids(cls, v):
        if not isinstance(v, list):
            raise ValueError("task_ids must be a list")
        result = []
        for i, item in enumerate(v):
            try:
                result.append(_ensure_uuid(item, f"task_ids[{i}]"))
            except ValueError as e:
                raise ValueError(f"task_ids[{i}]: invalid UUID") from e
        return result


class NotifyClientsPlaylistSchema(BaseModel):
    """Optional body for notifying clients that a playlist is ready."""
    studio_id: Optional[UUID] = Field(
        None,
        description="Studio unique identifier to notify",
    )
    department_id: Optional[UUID] = Field(
        None,
        description="Department unique identifier to notify",
    )

    @field_validator("studio_id", mode="before")
    @classmethod
    def validate_studio_id(cls, v):
        if v is None or v == "":
            return None
        return _ensure_uuid(v, "studio_id")

    @field_validator("department_id", mode="before")
    @classmethod
    def validate_department_id(cls, v):
        if v is None or v == "":
            return None
        return _ensure_uuid(v, "department_id")
