"""
Pydantic schemas that validate the request bodies of the shared playlist
blueprint. Use them with `validate_request_body()`. Then each error names
its field, and the routes work as the other routes of the codebase do.
"""

from typing import Any, List, Optional
from uuid import UUID

from pydantic import Field, field_validator

from zou.app.utils.validation import BaseSchema


class CreateGuestSchema(BaseSchema):
    """
    Body to create a guest on a shared playlist, or to use an existing guest
    again.
    """

    first_name: Optional[str] = Field(
        "Guest",
        description="First name of the guest reviewer",
    )
    last_name: Optional[str] = Field(
        "",
        description="Last name of the guest reviewer",
    )
    guest_id: Optional[UUID] = Field(
        None,
        description=(
            "Existing guest identifier — when provided the server "
            "looks the guest up instead of creating a new one"
        ),
    )

    @field_validator("guest_id", mode="before")
    @classmethod
    def coerce_empty_to_none(cls, v):
        if v == "":
            return None
        return v


class CreateGuestCommentSchema(BaseSchema):
    """
    Body to post a comment as a guest.
    """

    guest_id: UUID = Field(..., description="Guest unique identifier")
    task_id: UUID = Field(
        ...,
        description="Task to comment on (must belong to the shared playlist)",
    )
    task_status_id: UUID = Field(
        ...,
        description=("Target task status. Must be flagged is_client_allowed."),
    )
    text: Optional[str] = Field(
        "",
        description="Comment body",
    )
    checklist: Optional[List[Any]] = Field(
        None,
        description="Optional checklist entries attached to the comment",
    )


class EditGuestCommentSchema(BaseSchema):
    """
    Body to edit a comment that a guest owns.

    The schema accepts only the fields that the service uses: ``text``,
    ``checklist`` and ``task_status_id``. ``guest_id`` identifies the guest
    who makes the edit.
    """

    guest_id: UUID = Field(..., description="Guest unique identifier")
    text: Optional[str] = Field(None, description="New comment body")
    checklist: Optional[List[Any]] = Field(
        None, description="New checklist entries"
    )
    task_status_id: Optional[UUID] = Field(
        None,
        description=(
            "New task status — must be flagged is_client_allowed, "
            "enforced server-side"
        ),
    )


class GuestActionSchema(BaseSchema):
    """
    Small schema for the delete endpoints that carry only a `guest_id`.
    The `guest_id` comes in the JSON body or in the query string.
    """

    guest_id: UUID = Field(
        ...,
        description="Guest unique identifier on whose behalf the action runs",
    )


class UpdateGuestAnnotationsSchema(BaseSchema):
    """
    Body for the endpoint that applies an annotation diff to a preview
    file of a shared playlist.
    """

    guest_id: UUID = Field(..., description="Guest unique identifier")
    preview_file_id: UUID = Field(
        ...,
        description="Preview file the diff applies to",
    )
    additions: Optional[List[Any]] = Field(
        None,
        description="Annotations to add",
    )
    updates: Optional[List[Any]] = Field(
        None,
        description="Annotations to update in place",
    )
    deletions: Optional[List[Any]] = Field(
        None,
        description="Annotation identifiers to remove",
    )
