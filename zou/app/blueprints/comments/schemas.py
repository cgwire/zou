"""
Pydantic schemas that validate the request bodies of the comments
blueprint.
"""

from typing import List, Optional
from uuid import UUID

import orjson as json
from pydantic import Field, field_validator

from zou.app.utils.validation import BaseSchema


class CopyClientCommentsSchema(BaseSchema):
    """
    Body to copy the last client comment of each of the given tasks.
    """

    task_ids: List[UUID] = Field(..., min_length=1)
    prefix: str = ""


class BatchCommentItemSchema(BaseSchema):
    """
    One entry of the batch of comment bodies. If an entry has no task, no
    status or no text, the route skips it and does not refuse it. Thus no
    field is required here.
    """

    object_id: Optional[UUID] = None
    task_status_id: Optional[UUID] = None
    comment: Optional[str] = None
    links: List[str] = Field(default_factory=list)


class CommentReplySchema(BaseSchema):
    """
    Body to reply to a comment.
    """

    text: Optional[str] = Field("", description="Reply text content")


class MoveCommentSchema(BaseSchema):
    """
    Body to move a comment to another task of the same entity.
    """

    target_task_id: str = Field(
        ..., description="Identifier of the task to move the comment to"
    )


class CommentCreateSchema(BaseSchema):
    """
    Body to add a comment to a task. The client sends it as JSON, or as a
    multipart form when it attaches files. In a multipart form, checklist
    and links come as JSON-encoded strings.
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
        Accept the JSON-encoded strings of multipart forms. Also accept the
        explicit nulls that Kitsu sends when the field is empty.
        """
        if value is None:
            return []
        if isinstance(value, str):
            return json.loads(value) if value else []
        return value
