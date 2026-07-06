"""
Pydantic schemas for request body validation in the comments blueprint.
"""

from typing import Optional

import orjson as json

from pydantic import Field, field_validator

from zou.app.utils.validation import BaseSchema


class CommentReplySchema(BaseSchema):
    """
    Body for replying to a comment.
    """

    text: Optional[str] = Field("", description="Reply text content")


class MoveCommentSchema(BaseSchema):
    """
    Body for moving a comment to another task of the same entity.
    """

    target_task_id: str = Field(
        ..., description="Identifier of the task to move the comment to"
    )


class CommentCreateSchema(BaseSchema):
    """
    Body for adding a comment to a task. Sent either as JSON or as a
    multipart form (when files are attached), where checklist and links
    arrive as JSON-encoded strings.
    """

    task_status_id: str = Field(..., description="Task status UUID")
    comment: str = Field("", description="Comment text content")
    person_id: str = Field("", description="Author UUID (managers only)")
    created_at: str = Field(
        "", description="Creation date override (managers only)"
    )
    checklist: list = Field(
        default_factory=list, description="Checklist items"
    )
    links: list = Field(default_factory=list, description="Linked URLs")
    for_client: bool = Field(
        False, description="Make the comment visible to clients"
    )

    @field_validator("checklist", "links", mode="before")
    @classmethod
    def decode_json_strings(cls, value):
        """
        Accept the JSON-encoded strings sent by multipart forms.
        """
        if isinstance(value, str):
            return json.loads(value) if value else []
        return value
