"""
Pydantic schemas for request body validation in the comments blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class CommentReplySchema(BaseSchema):
    """Body for replying to a comment."""

    text: Optional[str] = Field("", description="Reply text content")


class MoveCommentSchema(BaseSchema):
    """Body for moving a comment to another task of the same entity."""

    target_task_id: str = Field(
        ..., description="Identifier of the task to move the comment to"
    )
